import os
from typing import Dict, Any
from datetime import datetime
from threading import Lock
from copy import deepcopy
import json

from fastapi import APIRouter, Depends
import pandas as pd
from openai import APITimeoutError

from app.models import (
    Asset,
    SearchRequest,
    SearchResponse,
    ImportRepoRequest,
    ImportRepoResponse,
    GenerateCodeRequest,
    GenerateCodeResponse,
    GenerateCodeWithEditRequest,
    GenerateCodeWithEditResponse,
    ReviewRequest,
    ReviewResponse,
    StoreRequest,
    StoreResponse,
)
from app.config import config
from client.CodeBaseBuild.build_codebase import get_repository
from client.CodeSearch.code_search import code_search_custom
from client.CodeSearch.code_search import NlRetriever
from client.CodeBaseBuild.build_codebase import repo_parse_single
from client.CodeBaseBuild.build_codebase import repo_parse_multy
from client.CodeBaseBuild.build_codebase import rm_repo
from client.CodeBaseBuild.build_codebase import gen_code_sum_single
from client.CodeBaseBuild.build_codebase import gen_code_sum_multy
from client.CodeBaseBuild.build_codebase import code_sum_tokenize_single
from client.CodeBaseBuild.build_codebase import code_sum_tokenize_multy
from client.CodeBaseBuild.build_codebase import sum_embedding
from client.CodeBaseBuild.build_codebase import code_embedding_single
from client.CodeBaseBuild.build_codebase import code_embedding_multy
from client.CodeBaseBuild.build_codebase import gen_module_sum_multy
from client.CodeBaseBuild.build_codebase import gen_module_sum_single
from client.CodeBaseBuild.build_codebase import gen_repo_sum_single
from client.CodeBaseBuild.build_codebase import repo_sum_emb_single
from client.CodeGeneration.prompt import code_gen_instruct
from client.CodeGeneration.content_process import asset_content
from client.CodeGeneration.generation import generate_api
from client.CodeGeneration.content_process import json_parse
from client.CodeGeneration.content_process import code_parse
from client.CodeCheck.prompt import code_check
from client.CodeCheck.analysis_snippet.analysis_snippet import SnippetAnalyzer
from client.CodeCheck.content_process import err_parse, compare_code
from client.CodeBaseBuild.build_codebase import string_parse_new
from client.CodeBaseBuild.build_codebase import string_parse_old
from app.logger import logger_global
router = APIRouter()

def get_config():
    config.load()
    data = config.get()
    return data

"""
代码资产检索接口实现
"""
@router.post("/search", response_model=SearchResponse)
async def search_assets(
    request: SearchRequest, settings: Dict[str, Any] = Depends(get_config)
):

    logger = deepcopy(logger_global)
    logger.info(f"*********** 接收到代码资产检索请求 **********")

    # 检索信息加载
    logger.info(f"=== 加载检索信息 ===")
    retriever = NlRetriever()
    topk = request.topk
    codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
    columns = settings.get("CodeSearch", {}).get("columns")
    logger.info(f"=== 检索信息加载完成 ===")
    logger.info(f"=== 检索数量 {topk} ===")
    logger.info(f"=== 代码库地址 {codebase_path}===")
    logger.info(f"=== 停用词地址 {stopword_path} ===")
    logger.info(f"=== 检索使用信息内容 {columns} ===")
    
    # 内容检索
    retriever.load_stopwords(stopword_path)
    examples = code_search_custom(
        retriever=retriever,
        key_words=request.requirement,
        top_K=topk,
        codebase_path=codebase_path,
        columns=columns,
        emb_url=settings.get("nlp_emb", {}).get("url"),
    )

    # 检索结果处理
    result_list = []
    reslut_info = f"检索资产数量：{topk}\n用户需求：{request.requirement}"
    result_item = None
    for count, example in examples.iterrows():
        if count >= topk:
            break
        if example["sim_score"] <= 0:
            continue
        reslut_info += "\t" + f"【代码资产{count+1}】:"
        name = example["repo_name"]
        reslut_info += "\t\t" + f'系统名：{example["repo_name"]} \n'
        module = example["module"].replace("\\", "/")
        reslut_info += "\t\t" + f'所属模块：{example["module"]} \n'
        signature = example["signature"]
        reslut_info += "\t\t" + f'资产签名：{example["signature"]} \n'
        description = example["summary"]
        reslut_info += "\t\t" + f'资产概述：{example["summary"]} \n'
        source_code = example["source_code"]
        reslut_info += "\t\t" + f'资产源码：\n{example["source_code"]} \n'
        if result_item is None:
            result_item = Asset(
                name=name,
                module=module,
                signature=signature,
                description=description,
                source_code=source_code,
            )
        else:
            result_item.name = name
            result_item.module = module
            result_item.signature = signature
            result_item.description = description
            result_item.source_code = source_code
        result_list.append(deepcopy(result_item))
    logger.info(f"=== 检索结果 ===")
    logger.info(reslut_info)
    logger.info(f"********** 完成检索 **********")
    return {"result": result_list}

build_lock = Lock()
is_building = False
@router.post("/imrepo", response_model=ImportRepoResponse)
async def import_repository(
    request: ImportRepoRequest, settings: Dict[str, Any] = Depends(get_config)
):
    logger = deepcopy(logger_global)
    repo_path = ""
    logger.info(f"********** 接收到代码库导入请求 **********")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")

    logger.info(f"=== 检测执行条件 ===")
    global is_building
    if is_building:
        logger.info(
            f"********** 服务器正在处理其他代码资产，服务已拒绝 **********"
        )
        return {"message": f"服务器正在处理其他代码资产，请稍后再试"}
    logger.info(f"=== 可以执行代码库导入 ===")
    try:
        is_building = True
        if not build_lock.acquire(blocking=False):
            logger.error(
                f"********** 服务器正在处理其他代码资产，服务已拒绝 **********"
            )
            return {"message": f"服务器正在处理其他代码资产，请稍后再试"}
        
        logger.info(f"=== 开始克隆代码库 ===")
        try:
            is_building = True
            distination = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
            if not os.path.exists(distination):
                os.makedirs(distination)
            repo_path, version = get_repository(request.repo_url, distination)
            logger.info(f"=== 代码库克隆成功 ===")
        except Exception as e:
            logger.error(f"=== 代码库克隆失败 ===\n{e}")
            logger.error(
                f"********** 代码库克隆失败，服务已停止 **********"
            )
            return {
                "message": f"代码库克隆失败，请检查当前服务器是否具备代码库克隆权限"
            }

        logger.info(f"=== 开始提取代码资产 ===")
        codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath", "./data")
        if not (os.path.exists(codebase_path) and os.path.isdir(codebase_path)):
            os.makedirs(codebase_path, exist_ok=True)
        max_workers = settings.get("codeBaseBuild", {}).get("max_workers", 1)
        if max_workers <= 1:
            result = repo_parse_single(
                repo_path=repo_path,
                codebase_path=codebase_path,
                version=version,
            )
        else:
            result = await repo_parse_multy(
                repo_path=repo_path,
                codebase_path=codebase_path,
                version=version,
                max_workers=max_workers,
            )
        repo_name = os.path.basename(repo_path)
        asset_path = os.path.join(codebase_path, f"{repo_name}_assets_v_{version}.csv")
        info_path = os.path.join(codebase_path, f"{repo_name}_info_v_{version}.json")
        logger.info(f"=== {result} ===")

        logger.info(f"=== 开始生成函数级资产摘要 ===")
        if max_workers <= 1:
            result = gen_code_sum_single(asset_path=asset_path)
        else:
            result = await gen_code_sum_multy(
                asset_path=asset_path, max_workers=max_workers
            )
        logger.info(f"=== {result} ===")

        logger.info(f"=== 函数级资产摘要预分词 ===")
        if max_workers <= 1:
            result = code_sum_tokenize_single(
                asset_path=asset_path, stopword_path=stopword_path
            )
        else:
            result = await code_sum_tokenize_multy(
                asset_path=asset_path,
                stopword_path=stopword_path,
                max_workers=max_workers,
            )
        logger.info(f"=== {result} ===")

        logger.info(f"=== 函数级资产摘要嵌入 ===")
        sum_embedding(asset_path=asset_path, url=settings.get("nlp_emb", {}).get("url"))
        logger.info(f"=== {result} ===")

        logger.info(f"=== 开始生成模块级别资产摘要 ===")
        if max_workers <= 1:
            result = gen_module_sum_single(asset_path=asset_path, info_path=info_path)
        else:
            result = await gen_module_sum_multy(
                asset_path=asset_path, info_path=info_path, max_workers=max_workers
            )
        logger.info(f"=== {result} ===")
        logger.info(f"=== 开始生成系统级资产摘要 ===")
        result = gen_repo_sum_single(info_path=info_path)
        logger.info(f"=== {result} ===")

        logger.info(f"=== 开始生成模块、系统级资产嵌入 ===")
        result = repo_sum_emb_single(
            info_path=info_path, url=settings.get("nlp_emb", {}).get("url")
        )
        logger.info(f"=== {result} ===")

        repo_name = os.path.basename(repo_path)
        codebase = pd.read_csv(asset_path)
        info = json.load(open(info_path, "r", encoding="utf-8"))
    finally:
        build_lock.release()
        is_building = False
        rm_repo(repo_path)
    return {
        "message": f"代码库构建完成: {os.path.basename(repo_path)}, 提交版本：{version}, 系统概述：{info['description']},模块数量：{len(info['modules'])},总共解析函数数目: {len(codebase)}"
    }


@router.post("/gencode", response_model=GenerateCodeResponse)
async def generate_code_without_edit(
    request: GenerateCodeRequest, settings: Dict[str, Any] = Depends(get_config)
):
    logger = deepcopy(logger_global)
    logger.info(f"********** 接收到代码生成请求 **********")
    asset_info = asset_content(request.example)
    prompt_templete = code_gen_instruct
    prompt_templete.generate_prompt(
        user_param={"asset": asset_info, "requirement": request.requirement}
    )
    messages = prompt_templete.generate_message()
    logger.info(f"=== 完成提示词加载 ===")
    logger.info(messages)
    
    try:
        # code generation
        host = settings.get("llm", {}).get("url")
        model = settings.get("llm", {}).get("model")
        key = settings.get("llm", {}).get("key")
        logger.info(f"--- 提示词 ---\n{messages}")
        code = generate_api(messages, host=host, model=model, key=key)
        code = code.split("</think>")[-1]
        result = json_parse(code)
        itea_max = settings.get("CodeGeneration", {}).get("itea")
        itea_count = 0
        for itea in range(itea_max):
            itea_count = itea
            if not result:
                messages[-1][
                    "content"
                ] += "如果需要生成Json数据，请将Json数据包裹在```json  ```之间，如果不需要生成代码请忽略这句话"
                result = generate_api(messages, host=host, model=model, key=key)
            elif not ("code" in result.keys() and "info" in result.keys()):
                messages[-1][
                    "content"
                ] += "请严格按照Json格式输出生成结果，包含code和info两个字段，Json数据使用```json  ```包裹起来, code中的代码使用```c ```包裹起来."
                result = generate_api(messages, host=host, model=model, key=key)
            elif not ("```c" in result["code"] and "```" in result["code"]) and not (
                "```C" in result["code"] and "```" in result["code"]
            ):
                messages[-1][
                    "content"
                ] += "请严格按照Json格式输出生成结果，包含code和info两个字段，Json数据使用```json  ```包裹起来, code中的代码使用```c ```包裹起来."
                result = generate_api(messages, host=host, model=model, key=key)
            else:
                break
        code = code_parse(result["code"])
        logger.info(f"=== 完成生成 ===")
        logger.info(f"=== 迭代次数:{itea_count} ===")
        logger.info(f"=== 生成代码 ==\n{code}")
        logger.info(f"=== 复用说明 ==\n{result['info']}")
        logger.info(f"********** 完成代码生成 **********")
        return {"code": f"{code}", "info": f"{result['info']}"}
    except APITimeoutError:
        return {"code": "服务器繁忙，请稍后再试", "info": "服务器繁忙，请稍后再试"}


@router.post("/gencoderag", response_model=GenerateCodeWithEditResponse)
async def generate_code_with_edit(
    request: GenerateCodeWithEditRequest, settings: Dict[str, Any] = Depends(get_config)
):
    logger = deepcopy(logger_global)
    logger.info(f"********** 接收到代码生成请求 **********")
    asset_info = asset_content(request.example)
    prompt_templete = code_gen_instruct
    prompt_templete.generate_prompt(
        user_param={"asset": asset_info, "requirement": request.requirement}
    )
    messages = prompt_templete.generate_message()
    logger.info(f"=== 完成提示词加载 ===")
    logger.info(messages)

    try:
        # code generation
        host = settings.get("llm", {}).get("url")
        model = settings.get("llm", {}).get("model")
        key = settings.get("llm", {}).get("key")
        logger.info(f"--- 提示词 ---\n{messages}")
        code = generate_api(messages, host=host, model=model, key=key)
        code = code.split("</think>")[-1]
        result = json_parse(code)
        itea_max = settings.get("CodeGeneration", {}).get("itea")
        itea_count = 0
        for itea in range(itea_max):
            itea_count = itea
            if not result:
                messages[-1][
                    "content"
                ] += "如果需要生成Json数据，请将Json数据包裹在```json  ```之间，如果不需要生成代码请忽略这句话"
                result = generate_api(messages, host=host, model=model, key=key)
            elif not ("code" in result.keys() and "info" in result.keys()):
                messages[-1][
                    "content"
                ] += "请严格按照Json格式输出生成结果，包含code和info两个字段，Json数据使用```json  ```包裹起来, code中的代码使用```c ```包裹起来."
                result = generate_api(messages, host=host, model=model, key=key)
            elif not ("```c" in result["code"] and "```" in result["code"]) and not (
                "```C" in result["code"] and "```" in result["code"]
            ):
                messages[-1][
                    "content"
                ] += "请严格按照Json格式输出生成结果，包含code和info两个字段，Json数据使用```json  ```包裹起来, code中的代码使用```c ```包裹起来."
                result = generate_api(messages, host=host, model=model, key=key)
            else:
                break
        code = code_parse(result["code"])
        logger.info(f"=== 完成生成 ===")
        logger.info(f"=== 迭代次数:{itea_count} ===")
        logger.info(f"=== 生成代码 ==\n{code}")
        logger.info(f"=== 复用说明 ==\n{result['info']}")
        logger.info(f"********** 完成代码生成 **********")
        return {"code": f"{code}", "info": f"{result['info']}"}
    except APITimeoutError:
        return {"code": "服务器繁忙，请稍后再试", "info": "服务器繁忙，请稍后再试"}

@router.post("/review", response_model=ReviewResponse)
async def review_code(
    request: ReviewRequest, settings: Dict[str, Any] = Depends(get_config)
):
    logger = deepcopy(logger_global)
    logger.info(f"********** 接收到代码审查请求 **********")

    itea = settings.get("CodeGeneration", {}).get("itea", 5)
    code = request.code
    i = 0
    prompt = code_check
    host = settings.get("llm", {}).get("url")
    model = settings.get("llm", {}).get("model")
    key = settings.get("llm", {}).get("key")
    raw_res = deepcopy(code)
    snippet = deepcopy(code)
    fixed = False
    i = 0
    while i < itea:
        analyzer = SnippetAnalyzer()
        result_str = analyzer.analyze(snippet)
        if len(result_str.strip()) > 0:
            err_list = json.loads(result_str)
            if len(err_list) == 0:
                break
            else:
                err_info = err_parse(err_list)
            code_raw = deepcopy(snippet)
            logger.info(f"--- 第{i+1}轮审查意见 ---\n{err_info}")
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
            if ((not "```c" in snippet) and (not "```C" in snippet)) or (
                not "```" in snippet
            ):
                messages[-1][
                    "content"
                ] += "如果需要生成代码，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这句话"
                snippet = generate_api(messages, host=host, model=model, key=key)
                snippet = snippet.split("</think>")[-1]
            snippet = code_parse(snippet)
            i += 1
        else:
            break
    snippet = snippet.strip()
    compare = compare_code(raw_res, snippet)
    logger.info(f"********** 完成代码审查 **********")
    return {"result": snippet, "info": compare["info"]}


@router.post("/store", response_model=StoreResponse)
async def store_asset(
    request: StoreRequest, settings: Dict[str, Any] = Depends(get_config)
):
    logger = deepcopy(logger_global)
    repo_path = ""
    logger.info(f"********** 接收到代码资产存储请求 **********")

    logger.info(f"=== 检测执行条件 ===")
    global is_building
    if is_building:
        logger.info(
            f"********** 服务器正在处理其他代码资产，服务已拒绝 **********"
        )
        return {"message": f"服务器正在处理其他代码资产，请稍后再试"}
    logger.info(f"=== 可以执行代码库导入 ===")
    
    # 加载配置信息
    codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath", "./data")
    repo_path = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
    if not (os.path.exists(codebase_path) and os.path.isdir(codebase_path)):
        os.makedirs(codebase_path, exist_ok=True)
    if not (os.path.exists(repo_path) and os.path.isdir(repo_path)):
        os.makedirs(repo_path, exist_ok=True)

    # 加载请求信息
    repo_name = request.name
    code = request.code
    file_path = request.module
    version = datetime.now().strftime("%Y%m%d%H%M%S")
    asset_path = ""
    info_path = ""
    # 构建模拟代码库
    logger.info(f"=== 开始模拟代码库 ===")
    repo_path = os.path.join(repo_path, f"{repo_name}")
    if os.path.exists(repo_path):
        rm_repo(repo_path)
    
    try:
        is_building = True
        if not build_lock.acquire(blocking=False):
            logger.info(
                f"********** 服务器正在处理其他代码资产，服务已拒绝 **********"
            )
            return {"message": f"服务器正在处理其他代码资产，请稍后再试"}

        os.makedirs(repo_path, exist_ok=True)
        with open(os.path.join(repo_path, file_path), "w") as f:
            f.write(code)
        logger.info(f"=== 模拟代码库构建完成 ===")
            
        # 提取代码资产
        logger.info(f"=== 开始提取代码资产 ===")
        codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath", "./data")
        if not (os.path.exists(codebase_path) and os.path.isdir(codebase_path)):
            os.makedirs(codebase_path, exist_ok=True)
        max_workers = settings.get("codeBaseBuild", {}).get("max_workers", 1)
        result = repo_parse_single(
            repo_path=repo_path,
            codebase_path=codebase_path,
            version=version,
            add = True
        )
        repo_name = os.path.basename(repo_path)
        asset_path = os.path.join(codebase_path, f"{repo_name}_assets_v_{version}.csv")
        info_path = os.path.join(codebase_path, f"{repo_name}_info_v_{version}.json")
        logger.info(f"=== {result} ===")
        logger.info(f"=== 开始生成函数级资产摘要 ===")
        result = gen_code_sum_single(asset_path=asset_path)
        logger.info(f"=== {result} ===")
        logger.info(f"=== 函数级资产摘要预分词 ===")
        result = code_sum_tokenize_single(
            asset_path=asset_path, stopword_path=stopword_path
        )
        logger.info(f"=== {result} ===")
        logger.info(f"=== 函数级资产摘要嵌入 ===")
        sum_embedding(asset_path=asset_path, url=settings.get("nlp_emb", {}).get("url"))
        logger.info(f"=== {result} ===")
        
        asset_path_new = deepcopy(asset_path)
        info_path_new = deepcopy(info_path)
        
        # 检查该系统的资产是否已经存在
        asset_path = ""
        info_path = ""
        for file in os.listdir(codebase_path):
            if repo_name in file and file.endswith(".csv") and not file == os.path.basename(asset_path_new):
                asset_path = os.path.join(codebase_path, file)
            if repo_name in file and file.endswith(".json") and not file == os.path.basename(info_path_new):
                info_path = os.path.join(codebase_path, file)
        
        # 检查该系统是否存在坏资产
        if not asset_path == "":
            try:
                asset = pd.read_csv(asset_path)
            except Exception as e:
                logger.info(f"=== 读取资产失败 ===")
                logger.info(e)
                os.remove(asset_path)
                os.remove(info_path)
                asset_path = ""
                info_path = ""
        if not info_path == "":
            info = json.load(open(info_path))
            if (len(info['modules']) == 0)\
                or (len(info['modules']) == 1 and info['modules'][0]['name'] == '')\
                or (info["name"] == ""):
                os.remove(asset_path)
                os.remove(info_path)
                asset_path = ""
                info_path = ""
        
        # 检查当前资产是否需要新增
        if not (asset_path == "" or info_path == ""):
            codebase = pd.read_csv(asset_path)
            info = json.load(open(info_path, "r", encoding="utf-8"))
            tmp_asset = pd.read_csv(asset_path_new)
            if codebase.empty:
                all_asset = tmp_asset
            else:
                codebase['key'] = codebase['signature'].astype(str) + '|' + codebase['file_path'].astype(str)
                tmp_asset['key'] = tmp_asset['signature'].astype(str) + '|' + tmp_asset['file_path'].astype(str)
                update_mask = tmp_asset['key'].isin(codebase['key'])
                updates = tmp_asset[update_mask].copy()
                new_entries = tmp_asset[~update_mask].copy()
                codebase = codebase.drop('key', axis=1)
                updates = updates.drop('key', axis=1)
                new_entries = new_entries.drop('key', axis=1)
                codebase = codebase[~codebase['signature'].isin(updates['signature']) | 
                                ~codebase['file_path'].isin(updates['file_path'])]
                all_asset = pd.concat([codebase, updates, new_entries], ignore_index=True)
            all_asset.to_csv(asset_path, index=False)
            os.remove(asset_path_new)
            os.remove(info_path_new)
            target_module=os.path.dirname(file_path)
            if target_module.strip() == '':
                target_module='根模块'
            logger.info(f"=== 开始生成模块级别资产摘要 ===")
            result = gen_module_sum_single(
                asset_path=asset_path,
                info_path=info_path,
                target_module=target_module
            )
            logger.info(f"=== {result} ===")

            logger.info(f"=== 开始生成系统级资产摘要 ===")
            result = gen_repo_sum_single(info_path=info_path)
            logger.info(f"=== {result} ===")
            logger.info(f"=== 开始生成模块、系统级资产嵌入 ===")
            result = repo_sum_emb_single(
                info_path=info_path, url=settings.get("nlp_emb", {}).get("url"), target_module=os.path.basename(file_path),
            )
            logger.info(f"=== {result} ===")
            logger.info(f"=== 合并资产完成 ===")
        else:
            if not asset_path == "":
                os.remove(asset_path)
            if not info_path == "":
                os.remove(info_path)
            asset_path = asset_path_new
            info_path = info_path_new
            logger.info(f"=== 开始生成模块级别资产摘要 ===")
            result = gen_module_sum_single(asset_path=asset_path, info_path=info_path)
            logger.info(f"=== {result} ===")
            logger.info(f"=== 开始生成系统级资产摘要 ===")
            result = gen_repo_sum_single(info_path=info_path)
            logger.info(f"=== {result} ===")
            logger.info(f"=== 开始生成模块、系统级资产嵌入 ===")
            result = repo_sum_emb_single(
                info_path=info_path, url=settings.get("nlp_emb", {}).get("url")
            )
            logger.info(f"=== {result} ===")
    except Exception as e:
        logger.error(f"=== 代码库构建失败 ===")
        logger.error(e)
    finally:
        build_lock.release()
        is_building = False
        rm_repo(repo_path)
    info = json.load(open(info_path, "r", encoding="utf-8"))
    codebase = pd.read_csv(asset_path)
    logger.info(f"代码库构建完成: {repo_name}, 版本：{version}, 系统概述：{info['description']},模块数量：{len(info['modules'])},总共解析函数数目: {len(codebase)}")
    logger.info(f"********** 完成代码资产存储 **********")
    return {
            "message": f"代码库构建完成: {repo_name}, 版本：{version}, 系统概述：{info['description']},模块数量：{len(info['modules'])},总共解析函数数目: {len(codebase)}"
        }