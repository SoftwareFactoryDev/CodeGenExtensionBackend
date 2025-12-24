import os
from copy import deepcopy
from datetime import datetime
import json
import requests
import pandas as pd
import time

from llmtest.data.process import req_exact
from llmtest.data.load import req_load
from app.config import config
from client.CodeCheck.prompt import code_check
from client.CodeCheck.analysis_snippet.analysis_snippet import SnippetAnalyzer
from client.CodeCheck.content_process import err_parse, compare_code
from client.CodeGeneration.generation import generate_api
from client.CodeGeneration.content_process import code_parse
from client.CodeSearch.code_search import code_search_custom
from client.CodeSearch.code_search import NlRetriever
from client.CodeGeneration.prompt import code_gen_history

def generate_code(requirement, asset_info):

    config.load()
    config_info = config.get()
    prompt_templete = deepcopy(code_gen_history)
    prompt_templete.generate_prompt(
        user_param={"asset": asset_info, "requirement": requirement}
    )
    messages = prompt_templete.generate_message()
    # code generation
    host = config_info.get("llm", {}).get("url")
    model = config_info.get("llm", {}).get("model")
    key = config_info.get("llm", {}).get("key")
    print(f"--- 提示词 {datetime.now()} ---\n{messages}")
    code = generate_api(messages, host=host, model=model, key=key)
    code = code.split("</think>")[-1]
    itea_max = config_info.get("CodeGeneration", {}).get("itea")
    itea_count = 0
    for itea in range(itea_max):
        code = code.split("</think>")[-1]
        itea_count = itea
        if not code:
            messages[-1][
                "content"
            ] += "如果需要生成C语言，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这句话"
            code = generate_api(messages, host=host, model=model, key=key)
        elif not('```c' in code and '```' in code):
            messages[-1][
                "content"
            ] += "code中的代码使用```c ```包裹起来."
            code = generate_api(messages, host=host, model=model, key=key)
        else:
            break
    code = code_parse(code)
    print(f"--- 完成生成 {datetime.now()} ---")
    print(f"********** 迭代次数:{itea_count} **********")
    print(f"--- 生成结果 ---\n{code}")
    return code

def code_gen_test(req_dir, checkpoint_file="./result/code_gen_checkpoint.json"):
    def load_checkpoint():
        if not os.path.exists(checkpoint_file):
            return None
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载检查点文件失败: {str(e)}")
            return None

    def save_checkpoint(data):
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存检查点文件失败: {str(e)}")

    def validate_result(requirement, code):
        if not code or len(code) <= 10:
            return False
        return True

    checkpoint = load_checkpoint()
    last_processed_index = checkpoint.get("last_index", -1) if checkpoint else -1
    results = checkpoint.get("results", []) if checkpoint else []

    req_exact(req_dir)
    
    requirement = req_load(req_dir)
    if requirement is None or requirement.empty:
        print("没有加载到需求数据，结束程序。")
        return pd.DataFrame(results)

    # 显示进度信息
    total_requirements = len(requirement)
    if last_processed_index >= 0:
        print(f"检测到之前的进度，将从第 {last_processed_index + 1}/{total_requirements} 条需求继续处理")

    for index, row in requirement.iterrows():
        if index <= last_processed_index:
            continue

        print(f"正在处理需求：{index+1}/{total_requirements}")
        req_id = row["ID"]
        req_content = row["Content"]
        
        try:
            code = generate_code(req_content, "无")
            
            if not validate_result(req_content, code):
                print(f"警告：需求 {req_id} 的生成结果未通过校验")
                info = f"校验失败: {info}"

            result_dict = {
                "id": req_id,
                "req": req_content,
                "code": code
            }
            results.append(deepcopy(result_dict))
            
            checkpoint_data = {
                "last_index": index,
                "results": results,
                "total": total_requirements
            }
            save_checkpoint(checkpoint_data)
            
        except Exception as e:
            print(f"处理需求 {req_id} 时出错: {str(e)}")
            continue

    return pd.DataFrame(results)


def batch_import_repo(repo_file, column_name, checkpoint_file="./result/repo_process_checkpoint.json"):
    def load_checkpoint():
        if not os.path.exists(checkpoint_file):
            return None
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载检查点文件失败: {str(e)}")
            return None

    def save_checkpoint(data):
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存检查点文件失败: {str(e)}")

    def process_single_repo(repo_url):
        try:
            data = {"repo_url": repo_url}
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                "http://127.0.0.1:14514/imrepo", headers=headers, json=data
            )
            response.raise_for_status()
            result = response.json()
            print(result)
            return True
        except requests.exceptions.RequestException as e:
            print(f"{repo_url} 请求失败: {str(e)}")
            return False
        except json.JSONDecodeError as e:
            print(f"{repo_url} 响应解析失败: {str(e)}")
            return False
        except Exception as e:
            print(f"{repo_url} 发生错误: {str(e)}")
            return False
    checkpoint = load_checkpoint()
    processed_repos = checkpoint.get("processed_repos", []) if checkpoint else []
    last_processed_index = checkpoint.get("last_index", -1) if checkpoint else -1
    try:
        df = pd.read_excel(repo_file)
        if column_name not in df.columns:
            raise ValueError(f"在Excel文件中未找到名为 '{column_name}' 的列")
        ssh_addresses = df[column_name].dropna().tolist()
        ssh_addresses = [str(address) for address in ssh_addresses]
    except Exception as e:
        print(f"读取文件时出错: {str(e)}")
        return processed_repos

    total_repos = len(ssh_addresses)
    if last_processed_index >= 0:
        print(f"检测到之前的进度，将从第 {last_processed_index + 1}/{total_repos} 个代码库继续处理")
    for index, repo_url in enumerate(ssh_addresses):
        if index <= last_processed_index:
            continue

        print(f"{datetime.now()}正在解析代码库 {index+1}/{total_repos} ({repo_url})")
        
        if process_single_repo(repo_url):
            processed_repos.append(repo_url)
            
            checkpoint_data = {
                "last_index": index,
                "processed_repos": processed_repos,
                "total": total_repos
            }
            save_checkpoint(checkpoint_data)
        else:
            print(f"解析代码库 {repo_url} 失败，跳过")
            continue

    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print("所有代码库处理完成，已清理进度文件")

    return processed_repos


def codeCheckTest(code_file, checkpoint_file="./result/code_check_checkpoint.json"):

    def load_checkpoint():
        if not os.path.exists(checkpoint_file):
            return None
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载检查点文件失败: {str(e)}")
            return None

    def save_checkpoint(data):
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存检查点文件失败: {str(e)}")

    def process_single_code(code, index):
        itea = 5
        fixed = False
        raw_res = deepcopy(code)
        snippet = deepcopy(code)
        i = 0
        
        while i < itea:
            analyzer = SnippetAnalyzer()
            result_str = analyzer.analyze(snippet)
            
            if len(result_str.strip()) > 0:
                err_list = json.loads(result_str)
                if len(err_list) == 0:
                    fixed = True
                    break
                if isinstance(err_list, dict):
                    if 'error' in err_list.keys():
                        err_info = err_list['error']
                    else:
                        err_info = str(err_list)
                else:
                    err_info = err_parse(err_list)
                print(f"--- 第{i+1}轮审查意见 ---\n{err_info}")
                
                if i == 0:
                    prompt.generate_prompt(user_param={"code": snippet, "error": err_info})
                    messages = prompt.generate_message()
                else:
                    messages = prompt.add_chat("assistant", snippet)
                    messages = prompt.add_chat(
                        "user",
                        prompt.user_prompt_template.invoke(
                            {"code": snippet, "error": err_info}
                        ).text,
                    )
                
                snippet = generate_api(messages, host=host, model=model, key=key)
                snippet = snippet.split("</think>")[-1]
                
                if ((not "```c" in snippet) and (not "```C" in snippet)) or (not "```" in snippet):
                    messages[-1]["content"] += "如果需要生成代码，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这句话"
                    snippet = generate_api(messages, host=host, model=model, key=key)
                    snippet = snippet.split("</think>")[-1]
                
                snippet = code_parse(snippet)
                i += 1
            else:
                break
                
        snippet = snippet.strip()
        return {
            'raw_right': fixed and i == 0,
            'check_right': fixed,
            'check_code': raw_res if fixed and i == 0 else snippet
        }

    # 初始化参数
    host = 'http://10.13.1.102:8021/v1'
    model = "deepseek-ai/DeepSeek-R1"
    key = "103"
    prompt = code_check

    # 加载检查点
    checkpoint = load_checkpoint()
    check_code = checkpoint.get("check_code", []) if checkpoint else []
    last_processed_index = checkpoint.get("last_index", -1) if checkpoint else -1

    # 读取代码文件
    with open(code_file, 'r', encoding='utf-8') as f:
        raw_code = json.load(f)['results']
    # 显示进度信息
    total_codes = len(raw_code)
    if last_processed_index >= 0:
        print(f"检测到之前的进度，将从第 {last_processed_index + 1}/{total_codes} 个代码片段继续处理")

    # 处理代码
    for index, row in enumerate(raw_code):
        if index <= last_processed_index:
            continue

        print(f"{datetime.now()}处理代码{index+1} / {total_codes}")
        code = row['code']
        
        if not isinstance(code, str):
            row['raw_right'] = False
            row['check_right'] = False
            row['check_code'] = code
        else:
            code = code.strip()
            result = process_single_code(code, index)
            row.update(result)

        check_code.append(deepcopy(row))

        # 保存检查点
        checkpoint_data = {
            "last_index": index,
            "check_code": check_code,
            "total": total_codes
        }
        save_checkpoint(checkpoint_data)

    # 处理完成后删除检查点文件
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print("所有代码处理完成，已清理进度文件")

    return pd.DataFrame(check_code)
def account_of_asset(asset_path):
    
    repo_account = 0
    repo_size = []
    asset_account = 0
    columns = ["name","return_type","signature","params","summary","source_code","extent","file_path","module","repo_name","sum_tokenize","sum_embedding"]
    for file in os.listdir(asset_path):
        if file.endswith(".csv"):
            repo_account += 1
            df = pd.read_csv(os.path.join(asset_path, file))
            asset_account += len(df)
            repo_size.append(len(df))
    result ={
        "repo_account": repo_account,
        "asset_account": asset_account,
        "repo_size": repo_size
    }
    with open("./asset_account.json", "w") as f:
        json.dump(result, f, indent=4)
    return repo_account, asset_account, repo_size
    
def retrievel_speed_test(req_dir, checkpoint_file="retrieval_speed_checkpoint.json"):

    def load_checkpoint():
        if not os.path.exists(checkpoint_file):
            return None
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载检查点文件失败: {str(e)}")
            return None

    def save_checkpoint(data):
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存检查点文件失败: {str(e)}")

    # 加载检查点
    checkpoint = load_checkpoint()
    speed_result = checkpoint.get("speed_result", []) if checkpoint else []
    last_processed_index = checkpoint.get("last_index", -1) if checkpoint else -1
    last_processed_topk = checkpoint.get("last_topk", 0) if checkpoint else 0

    # 加载需求数据
    requirement = req_load(req_dir)
    if requirement is None or requirement.empty:
        print("没有加载到需求数据，结束程序。")
        return {"result": speed_result}

    # 显示进度信息
    total_requirements = len(requirement)
    if last_processed_index >= 0:
        print(f"检测到之前的进度，将从第 {last_processed_index + 1}/{total_requirements} 条需求继续处理")

    # 处理需求
    for index, row in enumerate(requirement):
        if index < last_processed_index:
            continue

        req = row['Content']
        req_id = row['ID']

        # 如果是恢复运行，需要确定从哪个topk开始
        start_topk = 1 if index > last_processed_index else last_processed_topk + 1

        for topk in range(start_topk, 11):
            print(f"{datetime.now()}处理需求{index+1} / {total_requirements}, topk: {topk}")
            
            try:
                start_time = time.time()
                retriever = NlRetriever()
                codebase_path = config.get().get("codeBaseBuild", {}).get("codebasePath")
                stopword_path = config.get().get("CodeSearch", {}).get("stopwords")
                columns = config.get().get("CodeSearch", {}).get("columns")

                # 内容检索
                retriever.load_stopwords(stopword_path)
                examples = code_search_custom(
                    retriever=retriever,
                    key_words=req,
                    top_K=topk,
                    codebase_path=codebase_path,
                    columns=columns,
                )

                # 检索结果处理
                result_list = []
                reslut_info = f"检索资产数量：{topk}\n用户需求：{req}"
                result_item = {}
                for count, example in examples.iterrows():
                    if float(example["sim_score"]) > 0:
                        reslut_info += "\t" + f"【代码资产{count+1}】:"
                        result_item['name'] = example["repo_name"]
                        reslut_info += "\t\t" + f'系统名：{example["repo_name"]} \n'
                        result_item['module'] = example["file_path"].replace("\\", "/")
                        reslut_info += "\t\t" + f'所属模块：{example["file_path"]} \n'
                        result_item['signature'] = example["signature"]
                        reslut_info += "\t\t" + f'资产签名：{example["signature"]} \n'
                        result_item['source_code'] = example["summary"]
                        reslut_info += "\t\t" + f'资产概述：{example["summary"]} \n'
                        result_item['source_code'] = example["source_code"]
                        reslut_info += "\t\t" + f'资产源码：\n{example["source_code"]} \n'
                        result_list.append(deepcopy(result_item))

                end_time = time.time()
                speed = {
                    "req_id": req_id,
                    "req": req,
                    "time": end_time - start_time,
                    "result_list": result_list,
                }
                speed_result.append(deepcopy(speed))

                # 保存检查点
                checkpoint_data = {
                    "last_index": index,
                    "last_topk": topk,
                    "speed_result": speed_result,
                    "total": total_requirements
                }
                save_checkpoint(checkpoint_data)

            except Exception as e:
                print(f"处理需求 {req_id} (topk={topk}) 时出错: {str(e)}")
                continue

    # 处理完成后删除检查点文件
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print("所有需求处理完成，已清理进度文件")

    return {"result": speed_result}
    
def main(req_dir, repo_file, code_file):
    print('代码生成')
    result = code_gen_test(req_dir)
    print('代码审查')
    result = codeCheckTest(code_file)
    result.to_csv("./result/check_result.csv", index=False)
    columns = ["name","return_type","signature","params","summary","source_code","extent","file_path","module","repo_name","sum_tokenize","sum_embedding"]
    print('代码导入')
    batch_import_repo(repo_file, column_name="SSH地址")
    account_of_asset("./data")
    print('代码检索')
    retrievel_speed_test(req_dir)


if __name__ == "__main__":
    config.set_path("./config.json")
    req_dir = "./llmtest/requirement"
    repo_file = "./repo_list-副本.xlsx"
    code_file = "./result/code_gen_checkpoint.json"
    main(req_dir, repo_file, code_file)
