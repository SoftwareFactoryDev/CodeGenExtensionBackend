import os 
import json
from datetime import datetime
import shutil
from copy import deepcopy

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn
import clang.cindex as cl

from client.CodeBaseBuild.build_codebase import get_repository,repo_parse_multy,sum_tokenize,gen_sum_single,repo_parse_single,gen_sum_single,rm_repo,gen_sum_multy
from client.CodeSearch.code_search import code_search_custom
from client.CodeGeneration.generation import generate_api
from client.CodeGeneration.prompt import code_gen_instruct
from client.CodeGeneration.content_process import history_content
from client.CodeGeneration.content_process import code_parse
from client.CodeSearch.code_search import NlRetriever
from client.CodeCheck.analysis_snippet.analysis_snippet import SnippetAnalyzer
from client.CodeCheck.prompt import code_check
from client.CodeCheck.content_process import err_parse
from openai import APITimeoutError, APIError, APIConnectionError

app = FastAPI(title="Code Generation Server", version="1.0.0")

# 加载配置文件
config_path = 'config.json'
try:
    with open(config_path, 'r', encoding='utf-8') as file:
        config = json.load(file)
except Exception as e:
    print(f'配置文件加载出错: {e}, 请将配置文件放在安装目录下并检查配置文件格式')
lib_path=config['codeBaseBuild']['clang_Path']
if lib_path:
    cl.Config.set_library_file(lib_path)
else:
    raise ValueError("Please provide the path to libclang shared library -> libclang.dll.")

class BuildRequest(BaseModel):
    repo_url: str

class BuildResponse(BaseModel):
    message: str

from threading import Lock
build_lock = Lock()
is_building = False
@app.post("/api/v1/bcb", response_model=BuildResponse)
async def build(request: BuildRequest):
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = json.load(file)
    except Exception as e:
        print(f'配置文件加载出错: {e}, 请将配置文件放在安装目录下并检查配置文件格式')
        return {"message": f'配置文件加载出错: {e}, 请将配置文件放在安装目录下并检查配置文件格式'}
    global is_building
    if is_building:
        return {"message": f'服务器正在处理其他代码资产，请稍后再试'}
    try:
        is_building = True
        print(f'********** 接收到代码库复用请求 {datetime.now()} **********')
        if not build_lock.acquire(blocking=False):
            return {"message": f'服务器正在处理其他代码资产，请稍后再试'}
        # 从 git地址克隆代码库
        try:
            is_building = True
            distination = config['codeBaseBuild']['repoPath']
            repo_path,version = get_repository(request.repo_url, distination)
            print(f'********** 代码库克隆成功 {datetime.now()} **********')
        except Exception as e:
            print(f'********** 代码库克隆失败  {e} **********')
            return {"message": f'代码库克隆失败'}
        
        output_path=config['codeBaseBuild']['codebasePath']
        #解析代码库
        if os.path.exists(output_path) and os.path.isdir(output_path):
            output_path = os.path.join(output_path, f'{os.path.basename(repo_path)}_{version}.csv')
        else:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

        print(f'********** 开始提取C语言函数 {datetime.now()} **********')
        max_workers=config['codeBaseBuild']['max_workers']
        if max_workers == 0:
            result = repo_parse_single(repo_path=repo_path,lib_path=config['codeBaseBuild']['clang_Path'], output_path=output_path, version=version)
        else:
            result = await repo_parse_multy(repo_path=repo_path,lib_path=config['codeBaseBuild']['clang_Path'], output_path=output_path, version=version, max_workers=max_workers)
        rm_repo(repo_path)
        print(f'********** {result} **********')

        print(f'********** 开始生成代码库摘要 {datetime.now()} **********')
        if max_workers == 0:
            result = gen_sum_single(codebase_path=output_path)
        else:
            result = await gen_sum_multy(codebase_path=output_path, max_workers=max_workers)
        print(f'********** {result} **********')

        print(f'********** 开始生成代码库摘要向量和分词 {datetime.now()} **********')
        result = sum_tokenize(codebase_path=output_path)
        print(f'********** {result} **********')
        print(f'********** 代码库构建完成 {datetime.now()} **********')
        repo_name = os.path.basename(repo_path)
        for file in os.listdir(os.path.dirname(output_path)):
            if repo_name in file and file.endswith('.csv') and file != os.path.basename(output_path):
                output_path = os.path.join(os.path.dirname(output_path), file)
                break
        codebase = pd.read_csv(output_path)
    finally:
        build_lock.release()
        is_building = False
    return {"message": f'代码库构建完成: {os.path.basename(repo_path)}, 提交版本：{version}, 总共解析函数数目: {len(codebase)}'}

class GenerateRequest(BaseModel):
    prompt: str
    history: Optional[List[Dict[str, Any]]] = None
    # history 参考格式:{role:"assistant/user", message:"xxxx"}

class GenerateResponse(BaseModel):
    code: str

@app.post("/api/v1/gen", response_model=GenerateResponse, tags=["Generate"])
def generate(request: GenerateRequest):

    print(f'********** 接收到代码生成请求 {datetime.now()} **********')
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = json.load(file)
    except Exception as e:
        print(f'配置文件加载出错: {e}, 请将配置文件放在安装目录下并检查配置文件格式')
        return {"message": f'配置文件加载出错: {e}, 请将配置文件放在安装目录下并检查配置文件格式'}
    
    retriever = NlRetriever()
    codebase_path = config['codeBaseBuild']['codebasePath']
    stopword_path = config['codeBaseBuild']['stopword_path']
    data = []
    retriever.load_stopwords(stopword_path)
    if not request.history:
        history = ''
    else:
        history = history_content(request.history)

    prompt_templete = code_gen_instruct
    prompt_templete.generate_prompt(user_param={'history':history, 'requirement': request.prompt})

    print(f'********** 完成提示词加载 {datetime.now()} **********')


    # reference_retrievel
    k = config['CodeSearch']['topk']
    examples = code_search_custom(retriever=retriever, key_words=request.prompt, top_K=k, codebase_path=codebase_path, columns = config['CodeSearch']['columns'])
    param_list = []
    result_list = []
    ret_info = ''
    messages = prompt_templete.generate_message()
    for count,example in examples.iterrows():
        if float(example['bm25_score']) > 0:
            param_list.append({'requirement': example['summary']})
            result_list.append(example['source_code'])
            ret_info += f'代码片段{count+1}: 来自代码库{example["repo_name"]} \n\t【摘要】 {example["summary"]}\n\t 【签名】\n\t{example["signature"]}\n'
    if len(result_list) > 0:
        messages = prompt_templete.add_example(param_list, result_list)    
    print(f'********** 完成检索  **********')
    print(f'检索结果: {ret_info}')

    try:
        # code generation
        host = config['llm']['url']
        model = config['llm']['model']
        key = config['llm']['key']
        print(f'--------------提示词-------\n{messages}')
        code = generate_api(messages, host=host, model=model, key=key)
        code = code.split('</think>')[-1]

        if  (not '```c' in code) and (not '```C' in code):
            messages[-1]['content'] += '如果需要生成代码，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这句话'
            code = generate_api(messages, host=host, model=model, key=key)
        print(f'********** 完成生成 {datetime.now()} **********')
        print(f'********** 迭代次数:{count} **********')
        print(f'--------------生成结果-------\n{code}')
        
        print(f'********** 开始代码审查 {datetime.now()} **********')
        itea = config['CodeCheck']['itea']
        i = 0
        prompt = code_check
        err_info = ''
        if  (not '```c' in code) and (not '```C' in code):
            print(f'--------------无法进行代码审查，代码生成格式不满足要求-------\n{code}')
            return {"code":code}
        response = deepcopy(code)
        codes = code_parse(code)
        print(f'--------------代码片段总数:{len(codes)}-------\n')
        for index, snippet in enumerate(codes):
            code_raw = deepcopy(snippet)
            i = 0
            while i < itea:
                analyzer = SnippetAnalyzer()
                result_str = analyzer.analyze(snippet)
                if len(result_str.strip()) > 0:
                    err_list = json.loads(result_str)
                    if len(err_list) == 0:
                        print(f'--------------第{index+1}个代码片段审查通过，轮次为：{i+1}-------')
                        break
                    if 'error' in err_list[0].keys():
                        print(f'--------------第{index+1}个代码片段审查第{i+1}轮次生成出现问题 -------\n{str(err_list)}')
                        snippet = code_raw
                    code_raw = deepcopy(snippet)
                    err_info = err_parse(err_list)
                    print(f'--------------第{index+1}个代码 第{i+1}轮审查意见 -------\n{err_info}')
                    if i == 0:
                        prompt.generate_prompt(user_param={'code':snippet, 'error':err_info})
                        messages = prompt.generate_message()
                    else: 
                        messages = prompt.add_chat('assistant', snippet)
                        messages = prompt.add_chat('user', prompt.user_prompt_template.invoke({'code':snippet, 'error':err_info}).text)
                    snippet = generate_api(messages, host=host, model=model, key=key)
                    snippet = snippet.split('</think>')[-1]
                    if  ((not '```c' in snippet) and (not '```C' in snippet)) or (not '```' in snippet):
                        messages[-1]['content'] += '如果需要生成代码，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这句话'
                        snippet = generate_api(messages, host=host, model=model, key=key)
                        snippet = snippet.split('</think>')[-1]
                    snippet = code_parse(snippet)
                    result = ''
                    for s in snippet:
                        result += s + '\n'
                    snippet = result
                    i+=1
                else:
                    break
            if i > 0:
                print(f'--------------第{index+1}个代码片段完成修改-------\n 【修改前】：\n {codes[index]}\n 【修改后】：\n{snippet}')
            response = response.replace(codes[index], snippet)
    except APITimeoutError:
        return {"code":"服务器繁忙，请稍后再试"} 
    return {"code":response.strip()}


# ==================== 主程序 ====================
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=14514
)