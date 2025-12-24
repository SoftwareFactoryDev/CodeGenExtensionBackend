import os
import json
import re
import glob
import shutil
import stat
import asyncio
import threading
import concurrent.futures
from typing import List

from git import Repo
from copy import deepcopy
import jieba
import clang.cindex as cl
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from client.CodeBaseBuild.CParser import CParser
from client.CodeBaseBuild.prompt import function_sum_template
from client.CodeBaseBuild.llm_gen import generate_api
from client.CodeBaseBuild.llm_gen import code_emb_api
from client.CodeBaseBuild.llm_gen import nlp_emb_api
from client.CodeBaseBuild.content_process import asset_in_module
from client.CodeBaseBuild.content_process import module_in_repo
from client.CodeBaseBuild.prompt import module_sum_template
from client.CodeBaseBuild.prompt import repo_sum_template
from app.logger import logger_global

thread_local = threading.local()
async def process_file(c_file, repo_path, c_parser):
    logger = deepcopy(logger_global)
    module = os.path.dirname(os.path.relpath(c_file, repo_path))
    if module.strip() == "":
        module = "根模块"
    file_path = os.path.relpath(c_file, repo_path)
    try:
        c_parser.parse_file(c_file)
        for func in c_parser.functions:
            func["file_path"] = file_path
            func["module"] = module
        return deepcopy(c_parser.functions)
    except Exception as e:
        logger.error(f"解析文件 {c_file} 时发生异常: {e}")
        return []


async def repo_parse_multy(repo_path, codebase_path, version, max_workers=4):
    logger = deepcopy(logger_global)
    repo_name = os.path.basename(repo_path)
    asset_path = os.path.join(codebase_path, f"{repo_name}_assets_v_{version}.csv")
    info_path = os.path.join(codebase_path, f"{repo_name}_info_v_{version}.json")

    if os.path.exists(asset_path) and os.path.exists(info_path):
        return f"代码库{os.path.basename(repo_path)}(Commit版本：{version})已存在，跳过提取代码资产步骤，仅进行代码库功能描述生成。"

    for file in os.listdir(codebase_path):
        if repo_name in file:
            os.remove(os.path.join(codebase_path, file))
    # 获取所有文件
    c_files = glob.glob(f"{repo_path}/**/*.c", recursive=True)
    h_files = glob.glob(f"{repo_path}/**/*.h", recursive=True)
    all_files = c_files + h_files

    # 使用线程池处理文件
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 创建任务列表
        tasks = []
        for index, c_file in enumerate(all_files):
            logger.info(f"正在处理代码文件 No{index+1}:{c_file}")
            c_parser = CParser()
            task = loop.run_in_executor(
                executor,
                lambda f=c_file, p=repo_path, parser=c_parser: asyncio.run(
                    process_file(f, p, parser)
                ),
            )
            tasks.append(task)
        results = await asyncio.gather(*tasks)
        asset_list = []
        module_list = set()
        for result in results:
            if result:
                asset_list.extend(result)
                for item in result:
                    module_list.add(item["module"])

        info = {
            "name": repo_name,
            "version": version,
            "description": "",
            "modules": [{"name": module, "description": ""} for module in module_list],
        }

        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=4)

        df = pd.DataFrame(asset_list)
        df['repo_name'] = repo_name
        df.to_csv(asset_path, index=False, encoding="utf-8-sig")

        return f"代码库{os.path.basename(repo_path)}_{version}解析完成。"


def repo_parse_single(repo_path, codebase_path, version, add=False):
    logger = deepcopy(logger_global)
    repo_name = os.path.basename(repo_path)
    asset_path = os.path.join(codebase_path, f"{repo_name}_assets_v_{version}.csv")
    info_path = os.path.join(codebase_path, f"{repo_name}_info_v_{version}.json")
    if os.path.exists(asset_path) and os.path.exists(info_path):
        result = f"代码库{os.path.basename(repo_path)}(Commit版本：{version})已存在，跳过提取代码资产步骤，仅进行代码库功能描述生成。"
    else:
        if not add:
            for file in os.listdir(codebase_path):
                if repo_name in file:
                    os.remove(os.path.join(codebase_path, file))
        # 获取信息：所有文件
        c_files = glob.glob(f"{repo_path}/**/*.c", recursive=True)
        h_files = glob.glob(f"{repo_path}/**/*.h", recursive=True)
        all_files = c_files + h_files
        c_parser = CParser()

        # 逐个解析C语言文件
        asset_list = []
        module_list = []
        for index, c_file in enumerate(all_files):
            logger.info(f"正在处理代码文件 No{index+1}:{c_file}")
            module = os.path.dirname(os.path.relpath(c_file, repo_path))
            if module.strip() == "":
                module = "根模块"
            if module not in module_list:
                module_list.append(module)
            file_path = os.path.relpath(c_file, repo_path)
            try:
                c_parser.parse_file(c_file)
                for func in c_parser.functions:
                    func["file_path"] = file_path
                    func["module"] = module
                    func["repo_name"] = repo_name
                asset_list.extend(deepcopy(c_parser.functions))
                logger.info(f"完成解析代码文件 No{index+1}:{c_file}")
            except Exception as e:
                logger.error(f"解析文件 {c_file} 时发生异常: {e}")

        # 保存代码库信息
        info = {"name": repo_name, "version": version, "description": "", "modules": []}
        for module in module_list:
            info["modules"].append({"name": module, "description": ""})
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=4)

        # 保存代码资产
        df = pd.DataFrame(asset_list)
        df.to_csv(asset_path, index=False, encoding="utf-8-sig")

        result = f"代码库{os.path.basename(repo_path)}(Commit版本：{version})解析完成,代码库信息：{info_path}，代码资产：{asset_path}"

    return result


def get_prompt_template():
    if not hasattr(thread_local, "prompt_template"):
        thread_local.prompt_template = function_sum_template
    return thread_local.prompt_template


def process_single_row(args):

    index, row, codebase_path = args
    prompt_template = get_prompt_template()
    logger = deepcopy(logger_global)
    logger.info(f'processing Function No.{index+1}: {row["signature"]}')

    # 检查是否需要生成功能描述
    if (
        (row["summary"] is not None)
        and (row["summary"] != "Not Generated")
        and (row["summary"] != "功能描述失败")
        and (len(row["summary"]) < 300)
    ):
        return index, row["summary"]

    param = {
        "name": row["name"],
        "file_path": row["file_path"],
        "source_code": row["source_code"],
        "signature": row["signature"],
    }

    prompt_template.generate_prompt(user_param=param)
    messages = prompt_template.generate_message()
    ite = 0

    while True:
        response = generate_api(messages)
        if not response or len(response.strip()) == 0:
            sum_data = None
        else:
            m = re.search(
                r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```", response, re.DOTALL
            )
            if m:
                sum_data = json_parse(response)
            else:
                sum_data = None

        if not sum_data:
            summary = response
        elif "summary" in sum_data.keys():
            summary = sum_data["summary"]
        else:
            summary = list(sum_data.values())[-1]

        if summary and len(summary) > 10 and len(summary) < 300:
            break
        elif summary is None or len(summary) == 0:
            messages = prompt_template.generate_message()
            messages[1]["content"] += ". Do not output empty string."
        elif " " not in summary:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({"role": "assistant", "content": summary})
            messages.append(
                {
                    "role": "user",
                    "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                }
            )
        elif len(summary) >= 300:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({"role": "assistant", "content": summary})
            messages.append(
                {
                    "role": "user",
                    "content": "将功能描述缩减至不超过50字, 不要包含当前函数所在的文件地址.",
                }
            )
        elif len(summary) <= 10:
            messages[0] = {"role": "assistant", "content": summary}
            messages[1] = {
                "role": "user",
                "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
            }

        ite += 1
        if ite > 10:
            break

    if not summary:
        summary = "功能描述失败."

    return index, summary.strip()


def gen_code_sum_single(asset_path):
    logger = deepcopy(logger_global)
    prompt_template = deepcopy(function_sum_template)

    try:
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"
    if len(codebase) == 0:
        return f"代码库{os.path.basename(asset_path)}为空，跳过功能描述生成步骤。"

    for index, row in codebase.iterrows():
        logger.info(f'processing Function No.{index+1}:{row["signature"]}')
        if (
            (row["summary"] is not None)
            and (row["summary"] != "功能描述失败")
            and (row["summary"] != "Not Generated")
            and (len(row["summary"]) < 300)
        ):
            continue
        param = {
            "name": row["name"],
            "source_code": row["source_code"],
            "signature": row["signature"],
        }
        prompt_template.generate_prompt(user_param=param)
        messages = prompt_template.generate_message()
        ite = 0

        while True:
            response = generate_api(messages)
            if not response or len(response.strip()) == 0:
                sum_data = None
            else:
                m = re.search(
                    r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```",
                    response,
                    re.DOTALL,
                )
                if m:
                    sum_data = json_parse(response)
                else:
                    sum_data = None
            if not sum_data:
                summary = response
            elif "summary" in sum_data.keys():
                summary = sum_data["summary"]
            else:
                summary = list(sum_data.values())[-1]
            if summary and len(summary) > 10 and len(summary) < 300:
                break
            elif summary is None or len(summary) == 0:
                messages = prompt_template.generate_message()
                messages[1]["content"] += ". Do not outpout empty string."
            elif " " not in summary:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": summary})
                messages.append(
                    {
                        "role": "user",
                        "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                    }
                )
            elif len(summary) >= 300:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": summary})
                messages.append(
                    {
                        "role": "user",
                        "content": "将功能描述缩减至不超过50字, 不要包含当前函数所在的文件地址.",
                    }
                )
            elif len(summary) <= 10:
                messages[0] = {"role": "assistant", "content": summary}
                messages[1] = {
                    "role": "user",
                    "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                }
            ite += 1
            if ite > 10:
                break
        if not summary:
            summary = "功能描述失败."
        row["summary"] = summary.strip()
    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功生成代码库功能描述"
async def gen_code_sum_multy(asset_path, max_workers=4):
    prompt_template = function_sum_template
    logger = deepcopy(logger_global)
    try:
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"
    
    if len(codebase) == 0:
        return f"代码库{os.path.basename(asset_path)}为空，跳过功能描述生成步骤。"

    def process_function(row_data):
        index, row = row_data
        logger.info(f'processing Function No.{index+1}:{row["signature"]}')
        
        if (
            (row["summary"] is not None)
            and (row["summary"] != "功能描述失败")
            and (row["summary"] != "Not Generated")
            and (len(row["summary"]) < 300)
        ):
            return row

        param = {
            "name": row["name"],
            "source_code": row["source_code"],
            "signature": row["signature"],
        }
        prompt_template.generate_prompt(user_param=param)
        messages = prompt_template.generate_message()
        ite = 0

        while True:
            response = generate_api(messages)
            if not response or len(response.strip()) == 0:
                sum_data = None
            else:
                m = re.search(
                    r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```",
                    response,
                    re.DOTALL,
                )
                if m:
                    sum_data = json_parse(response)
                else:
                    sum_data = None
            
            if not sum_data:
                summary = response
            elif "summary" in sum_data.keys():
                summary = sum_data["summary"]
            else:
                summary = list(sum_data.values())[-1]
            
            if summary and len(summary) > 10 and len(summary) < 300:
                break
            elif summary is None or len(summary) == 0:
                messages = prompt_template.generate_message()
                messages[1]["content"] += ". Do not outpout empty string."
            elif " " not in summary:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": summary})
                messages.append(
                    {
                        "role": "user",
                        "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                    }
                )
            elif len(summary) >= 300:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": summary})
                messages.append(
                    {
                        "role": "user",
                        "content": "将功能描述缩减至不超过50字, 不要包含当前函数所在的文件地址.",
                    }
                )
            elif len(summary) <= 10:
                messages[0] = {"role": "assistant", "content": summary}
                messages[1] = {
                    "role": "user",
                    "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                }
            ite += 1
            if ite > 10:
                break
        
        if not summary:
            summary = "功能描述失败."
        row["summary"] = summary.strip()
        return row
    futures = []
    processed_rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for row_data in codebase.iterrows():
            futures.append(executor.submit(process_function, row_data))
        futures = [executor.submit(process_function, row_data) for row_data in codebase.iterrows()]
        processed_rows = [future.result() for future in futures]


    codebase = pd.DataFrame(processed_rows)
    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功生成代码库功能描述"



def sum_embedding(asset_path, url):
    logger = deepcopy(logger_global)
    try:
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"
    codebase["sum_embedding"] = codebase["summary"].apply(
        lambda x: nlp_emb_api(
            x, url=url
        )
    )
    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功生成功能描述向量"


def code_sum_tokenize_single(asset_path, stopword_path=None):
    logger = deepcopy(logger_global)
    try:
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"
    if len(codebase) == 0:
        return f"代码库{os.path.basename(asset_path)}为空，跳过功能描述分词步骤。"
    if not stopword_path:
        codebase["sum_tokenize"] = codebase["summary"].apply(
            lambda x: list(jieba.cut_for_search(x))
        )
    else:
        with open(stopword_path, "r", encoding="utf-8") as f:
            stopwords = f.read().splitlines()
        codebase["sum_tokenize"] = codebase["summary"].apply(
            lambda x: list(jieba.cut_for_search(x))
        )
        codebase["sum_tokenize"] = codebase["sum_tokenize"].apply(
            lambda x: [token for token in x if token not in stopwords]
        )
    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功完成函数级资产预分词"


async def code_sum_tokenize_multy(asset_path, stopword_path=None, max_workers=4):

    def process_summary(x, stopwords=None):
        tokens = list(jieba.cut_for_search(x))
        if stopwords:
            tokens = [token for token in tokens if token not in stopwords]
        return tokens

    logger = deepcopy(logger_global)
    try:
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"

    if len(codebase) == 0:
        return f"代码库{os.path.basename(asset_path)}为空，跳过功能描述分词步骤。"

    stopwords = None
    if stopword_path:
        with open(stopword_path, "r", encoding="utf-8") as f:
            stopwords = set(f.read().splitlines())

    # 使用指定的线程数
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        codebase["sum_tokenize"] = list(
            executor.map(
                lambda x: process_summary(x, stopwords), codebase["summary"]
            )
        )

    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功完成函数级资产预分词"


def json_parse(content):

    def try_load(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    out = try_load(content.strip())
    if out is not None:
        return out
    m = re.search(r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```", content, re.DOTALL)
    if m:
        candidate = m.group(1)
        out = try_load(candidate)
        if out is not None:
            return out
        return None
    return None


def force_remove_readonly(func, path, excinfo):
    """处理只读文件的删除"""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_repository(repo_url, destination="./repos"):
    logger = deepcopy(logger_global)
    if not os.path.exists(destination):
        os.makedirs(destination)
    destination = os.path.join(destination, repo_url.split("/")[-1].split(".")[0])
    logger.info(f"开始克隆代码库 {repo_url}")

    if os.path.exists(destination):
        rm_repo(destination)
    repo = Repo.clone_from(repo_url, destination)
    version = repo.head.commit.hexsha
    logger.info(f"代码库克隆到{destination}")
    repo.close()
    repo.git.clear_cache()
    return destination, version


def rm_repo(repo_path):
    if not os.path.exists(repo_path):
        return
    for root, dirs, files in os.walk(repo_path):
        for dir in dirs:
            os.chmod(os.path.join(root, dir), stat.S_IRWXU)
        for file in files:
            os.chmod(os.path.join(root, file), stat.S_IRWXU)
    shutil.rmtree(repo_path)


def code_embedding_single(asset_path):
    logger = deepcopy(logger_global)
    try:
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"
    codebase["code_emb"] = codebase["source_code"].apply(lambda x: code_emb_api(x))
    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功完成代码嵌入"


async def code_embedding_multy(asset_path, max_workers=4):
    def process_code(x):
        return code_emb_api(x)
    logger = deepcopy(logger_global)

    try:
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"

    # 使用多线程处理，可以指定线程数
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        codebase["code_emb"] = list(executor.map(process_code, codebase["source_code"]))

    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功完成代码嵌入"


def gen_module_sum_single(asset_path, info_path, target_module=None):
    logger = deepcopy(logger_global)

    try:
        with open(info_path, "r", encoding="utf-8") as f:
            repo_info = json.load(f)
        asset_list = pd.read_csv(asset_path)
        module_list = repo_info.get("modules", [])
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"
    if len(asset_list) == 0:
        return f"代码库{os.path.basename(asset_path)}为空，跳过功能描述生成步骤。"

    if target_module and not (target_module in [d.get("name") for d in module_list]):
        module_list.append({"name": target_module, "description": ""})

    prompt_template = deepcopy(module_sum_template)
    module_sum_list = []
    for module in module_list:
        if target_module and module["name"] != target_module:
            continue
        mask = asset_list["module"] == module["name"]
        match_assets = asset_list[mask]
        asset_list = match_assets[["name", "file_path", "signature", "summary"]].copy()
        asset_info = asset_in_module(asset_list)
        user_param = {"path": module["name"], "assets": asset_info}
        prompt_template.generate_prompt(user_param=user_param)
        messages = prompt_template.generate_message()

        ite = 0
        while True:
            response = generate_api(messages)
            if not response or len(response.strip()) == 0:
                sum_data = None
            else:
                m = re.search(
                    r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```",
                    response,
                    re.DOTALL,
                )
                if m:
                    sum_data = json_parse(response)
                else:
                    sum_data = None
            if not sum_data:
                summary = response
            elif "summary" in sum_data.keys():
                summary = sum_data["summary"]
            else:
                summary = list(sum_data.values())[-1]
            if summary and len(summary) > 10 and len(summary) < 300:
                break
            elif summary is None or len(summary) == 0:
                messages = prompt_template.generate_message()
                messages[1]["content"] += " 不要输出空的功能描述."
            elif " " not in summary:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": summary})
                messages.append(
                    {
                        "role": "user",
                        "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                    }
                )
            elif len(summary) >= 300:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": summary})
                messages.append(
                    {
                        "role": "user",
                        "content": "将功能描述缩减至不超过50字.",
                    }
                )
            elif len(summary) <= 10:
                messages[0] = {"role": "assistant", "content": summary}
                messages[1] = {
                    "role": "user",
                    "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                }
            ite += 1
            if ite > 10:
                break
        if not summary:
            summary = "功能描述失败."
        module["description"] = summary.strip()
        module_sum_list.append(deepcopy(module))
    repo_info["modules"] = module_sum_list
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(repo_info, f, ensure_ascii=False, indent=4)
    return f"成功生成模块级代码资产功能描述"


def get_prompt_template():
    if not hasattr(thread_local, "prompt_template"):
        thread_local.prompt_template = deepcopy(module_sum_template)
    return thread_local.prompt_template


def process_single_module(args):
    module, asset_list = args
    prompt_template = get_prompt_template()

    mask = asset_list["module"] == module["name"]
    match_assets = asset_list[mask]
    asset_list = match_assets[["name", "file_path", "signature", "summary"]].copy()
    asset_info = asset_in_module(asset_list)

    user_param = {"path": module["name"], "assets": asset_info}

    prompt_template.generate_prompt(user_param=user_param)
    messages = prompt_template.generate_message()

    ite = 0
    while True:
        response = generate_api(messages)
        if not response or len(response.strip()) == 0:
            sum_data = None
        else:
            m = re.search(
                r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```",
                response,
                re.DOTALL,
            )
            if m:
                sum_data = json_parse(response)
            else:
                sum_data = None

        if not sum_data:
            summary = response
        elif "summary" in sum_data.keys():
            summary = sum_data["summary"]
        else:
            summary = list(sum_data.values())[-1]

        if summary and len(summary) > 10 and len(summary) < 300:
            break
        elif summary is None or len(summary) == 0:
            messages = prompt_template.generate_message()
            messages[1]["content"] += " 不要输出空的功能描述."
        elif " " not in summary:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({"role": "assistant", "content": summary})
            messages.append(
                {
                    "role": "user",
                    "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                }
            )
        elif len(summary) >= 300:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({"role": "assistant", "content": summary})
            messages.append(
                {
                    "role": "user",
                    "content": "将功能描述缩减至不超过50字.",
                }
            )
        elif len(summary) <= 10:
            messages[0] = {"role": "assistant", "content": summary}
            messages[1] = {
                "role": "user",
                "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
            }
        ite += 1
        if ite > 10:
            break

    if not summary:
        summary = "功能描述失败."

    module["description"] = summary.strip()
    return module


async def gen_module_sum_multy(asset_path, info_path, max_workers=4):
    """多线程版本的模块功能描述生成函数"""
    logger = deepcopy(logger_global)
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            repo_info = json.load(f)
        asset_list = pd.read_csv(asset_path)
        module_list = repo_info.get("modules", [])
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"

    if len(asset_list) == 0:
        return f"代码库{os.path.basename(asset_path)}为空，跳过功能描述生成步骤。"

    # 准备任务列表
    tasks = [(module, asset_list) for module in module_list]

    # 使用线程池处理任务
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_module = {
            executor.submit(process_single_module, task): task[0] for task in tasks
        }

        module_sum_list = []
        for future in as_completed(future_to_module):
            try:
                module = future.result()
                module_sum_list.append(module)
                logger.info(f"已完成处理模块: {module['name']}")
            except Exception as exc:
                module = future_to_module[future]
                logger.error(f"处理模块 {module['name']} 时发生异常: {exc}")
                module["description"] = "处理失败."
                module_sum_list.append(module)

    # 更新repo_info并保存
    repo_info["modules"] = module_sum_list
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(repo_info, f, ensure_ascii=False, indent=4)

    return f"成功生成模块级代码资产功能描述"


def gen_repo_sum_single(info_path):

    with open(info_path, "r", encoding="utf-8") as f:
        repo_info = json.load(f)
    module_list = repo_info.get("modules", [])
    if len(module_list) == 0:
        return f"代码库{os.path.basename(info_path)}为空，跳过功能描述生成步骤。"

    prompt_template = deepcopy(repo_sum_template)
    repo_sum = ""
    module_info = module_in_repo(module_list)
    user_param = {"modules": module_info}
    prompt_template.generate_prompt(user_param=user_param)
    messages = prompt_template.generate_message()

    ite = 0
    while True:
        response = generate_api(messages)
        if not response or len(response.strip()) == 0:
            sum_data = None
        else:
            m = re.search(
                r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```",
                response,
                re.DOTALL,
            )
            if m:
                sum_data = json_parse(response)
            else:
                sum_data = None
        if not sum_data:
            summary = response
        elif "summary" in sum_data.keys():
            summary = sum_data["summary"]
        else:
            summary = list(sum_data.values())[-1]
        if summary and len(summary) > 10 and len(summary) < 300:
            break
        elif summary is None or len(summary) == 0:
            messages = prompt_template.generate_message()
            messages[1]["content"] += " 不要输出空的功能描述."
        elif " " not in summary:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({"role": "assistant", "content": summary})
            messages.append(
                {
                    "role": "user",
                    "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                }
            )
        elif len(summary) >= 300:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({"role": "assistant", "content": summary})
            messages.append(
                {
                    "role": "user",
                    "content": "将功能描述缩减至不超过50字.",
                }
            )
        elif len(summary) <= 10:
            messages[0] = {"role": "assistant", "content": summary}
            messages[1] = {
                "role": "user",
                "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
            }
        ite += 1
        if ite > 10:
            break
    if not summary:
        summary = "功能描述失败."
    repo_sum = summary.strip()
    repo_info["description"] = repo_sum
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(repo_info, f, ensure_ascii=False, indent=4)
    return f"成功生成模块级代码资产功能描述"


def repo_sum_emb_single(info_path, url=None, target_module=None):
    with open(info_path, "r", encoding="utf-8") as f:
        repo_info = json.load(f)
    if len(repo_info["description"]) == 0:
        return f"代码库{os.path.basename(info_path)}不包含模块，跳过功能描述分词步骤。"
    repo_info["desp_emb"] = nlp_emb_api(repo_info["description"], url=url)
    for module in repo_info.get("modules", []):
        if target_module and module["name"] != target_module:
            continue
        module["desp_emb"] = nlp_emb_api(module["description"], url=url)
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(repo_info, f, ensure_ascii=False, indent=4)
    return f"成功完成系统级资产预分词"


def string_parse_new(codestring, repo_name, codebase_path, version, file_path):
    logger = deepcopy(logger_global)

    asset_path = os.path.join(codebase_path, f"{repo_name}_assets_v_{version}.csv")
    info_path = os.path.join(codebase_path, f"{repo_name}_info_v_{version}.json")
    c_parser = CParser()
    c_parser.file_path = file_path
    asset_list = []
    module = os.path.dirname(file_path)
    try:
        c_parser.parse_code(codestring)
        for func in c_parser.functions:
            func["file_path"] = file_path
            func["module"] = module
        asset_list.extend(deepcopy(c_parser.functions))
        df = pd.DataFrame(asset_list)
    except Exception as e:
        logger.error(f"解析时发生异常: {e}")
        df = pd.DataFrame()
    df.to_csv(asset_path, index=False, encoding="utf-8")

    info = {
        "name": repo_name,
        "version": version,
        "description": "",
        "modules": [{"name": module, "description": ""}],
    }

    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=4)
    result = f"解析完成"
    return result


def string_parse_old(codestring, repo_name, codebase_path, version, file_path):

    logger = deepcopy(logger_global)
    c_parser = CParser()
    asset_list = []
    module = os.path.dirname(file_path)
    try:
        c_parser.parse_code(codestring)
        for func in c_parser.functions:
            func["file_path"] = file_path
            func["module"] = module
        asset_list.extend(deepcopy(c_parser.functions))
        df = pd.DataFrame(asset_list)
    except Exception as e:
        logger.error(f"解析时发生异常: {e}")
        df = pd.DataFrame()
    return df