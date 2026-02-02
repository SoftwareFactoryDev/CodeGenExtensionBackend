import re
import zipfile
import os
from typing import Dict, Any
from datetime import datetime
from threading import Lock
from copy import deepcopy
import json
import uuid

import jieba
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
import pandas as pd
from openai import APITimeoutError

from app.models import (
    RepoStructRequest,
    RepoStructResponse,
    RepoParseRequest,
    RepoParseResponse,
    Asset,
    TempAsset,
    SearchRequest,
    SearchResponse,
    SearchCodeRequest,
    SearchCodeResponse,
    ImAssetRequest,
    ImAssetResponse,
    TempAssetRequest,
    TempAssetResponse,
    LibRegsResponse,
    RmTempAssetRequest,
    RmTempAssetResponse,
    EditAssetRequest,
    EditAssetResponse,
    ImReqResponse,
    RequirementItem,
    CodeGenResult,
    GenerateCodeRagRequest,
    GenerateCodeRagResponse,
    EditCodeRequest,
    EditCodeResponse,
    ReviewRequest,
    ReviewResponse,
    StoreRequest,
    StoreResponse,
    FixRequest,
    FixResponse,
    ConfigRequest,
    ToolListResponse,
    ToolSupportRequest,
    ToolSupportResponse,
)
from app.config import config
from app.util import temp_asset_from_df, process_temp_asset, asset_from_df
from function.CodeGeneration.util import requirement_extract
from function.CodeBaseBuild.build_codebase import get_repository
from function.CodeSearch.code_search import code_search_custom
from function.CodeSearch.code_search import NlRetriever
from function.CodeBaseBuild.build_codebase import repo_parse_single
from function.CodeBaseBuild.build_codebase import repo_parse_multy
from function.CodeBaseBuild.build_codebase import rm_repo
from function.CodeBaseBuild.build_codebase import gen_function_sum_single
from function.CodeBaseBuild.build_codebase import gen_function_sum_multy
from function.CodeBaseBuild.build_codebase import code_sum_tokenize_single
from function.CodeBaseBuild.build_codebase import code_sum_tokenize_multy
from function.CodeBaseBuild.build_codebase import sum_embedding
from function.CodeBaseBuild.build_codebase import code_embedding_single
from function.CodeBaseBuild.build_codebase import code_embedding_multy
from function.CodeBaseBuild.build_codebase import gen_module_sum_multy
from function.CodeBaseBuild.build_codebase import gen_module_sum_single
from function.CodeBaseBuild.build_codebase import gen_repo_sum_single
from function.CodeBaseBuild.build_codebase import repo_sum_emb_single
from function.CodeBaseBuild.util import scan_repo_structure
from function.CodeGeneration.prompt import (
    code_gen_instruct,
    code_gen_edit,
    code_gen_mulreq,
)
from function.CodeGeneration.util import asset_content
from function.CodeGeneration.generation import generate_api
from function.CodeGeneration.util import json_parse
from function.CodeGeneration.util import code_parse
from function.CodeGeneration.util import info_parse
from function.CodeCheck.prompt import code_check
from function.CodeCheck.util import err_parse, compare_code
from function.CodeBaseBuild.util import gen_code_sum
from function.CodeBaseBuild.build_codebase import string_parse_new
from function.CodeBaseBuild.build_codebase import string_parse_old
from app.logger import logger_global
from function.CodeBaseBuild.llm_gen import nlp_emb_api
from function.CodeCheck.util import err_list_parse
from function.CodeCheck.code_check import build_in_check

router = APIRouter()
build_lock = Lock()
is_building = False


def get_config():
    config.load()
    data = config.get()
    if "config" not in data.keys():
        return data
    return data["config"]


@router.post("/update_config")
async def update_config(request: ConfigRequest):

    try:
        info_dict = json.loads(request.info)
        config.set_data(info_dict)
        return {"message": "配置已更新", "new_config": config.get()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/getconfig")
async def get_config(settings: Dict[str, Any] = Depends(get_config)):
    settings = (
        deepcopy(settings)["config"]
        if "config" in settings.keys()
        else settings if "config" in settings.keys() else settings
    )
    return {"config": settings}

@router.post("/repostruct", response_model=RepoStructResponse)
async def repo_struct(
    request: RepoStructRequest, settings: Dict[str, Any] = Depends(get_config)
):
    """
    代码仓库文件夹结构分析接口
    """

    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)

    repo_path = ""
    global is_building

    if is_building:
        return {
            "repo_url": request.repo_url,
            "status": "fail",
            "message": "服务器正在处理其他代码资产，请稍后再试",
            "directories": [],
        }

    try:
        is_building = True
        if not build_lock.acquire(blocking=False):
            return {
                "repo_url": request.repo_url,
                "status": "fail",
                "message": "服务器正在处理其他代码资产，请稍后再试",
                "directories": [],
            }

        # 配置中的 repoPath
        destination = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
        if not os.path.exists(destination):
            os.makedirs(destination, exist_ok=True)

        # 克隆仓库
        repo_path, version = get_repository(request.repo_url, destination)
        logger.info(f"代码库克隆成功: {repo_path}, version={version}")

        # 扫描目录结构
        directories = scan_repo_structure(repo_path)

        return {
            "repo_url": request.repo_url,
            "status": "success",
            "message": "代码仓库导入成功",
            "directories": directories,
        }

    except Exception as e:
        logger.error(f"/repostruct 执行失败: {e}")
        return {
            "repo_url": request.repo_url,
            "status": "fail",
            "message": f"导入失败: {str(e)}",
            "directories": [],
        }

    finally:
        if build_lock.locked():
            build_lock.release()
        is_building = False

        try:
            rm_repo(repo_path)
        except Exception as e:
            logger.error(f"清理仓库目录失败: {repo_path}, err={e}")

@router.post("/repoparse", response_model=RepoParseResponse)
async def import_repository(
    request: RepoParseRequest, settings: Dict[str, Any] = Depends(get_config)
):
    """
    代码库解析接口

    Args:
        request (RepoParseRequest): _description_
        settings (Dict[str, Any], optional): _description_. Defaults to Depends(get_config).

    Returns:
        _type_: _description_
    """
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    repo_path = ""
    logger.info(f"接收到代码库导入请求")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")

    logger.info(f"检测执行条件")
    global is_building
    if is_building:
        logger.info(f"服务器正在处理其他代码资产，服务已拒绝")
        return {"message": f"服务器正在处理其他代码资产，请稍后再试"}
    logger.info(f"可以执行代码库导入")
    try:
        is_building = True
        if not build_lock.acquire(blocking=False):
            logger.error(f"服务器正在处理其他代码资产，服务已拒绝")
            return {"message": f"服务器正在处理其他代码资产，请稍后再试"}
        logger.info(f"开始克隆代码库")
        try:
            is_building = True
            distination = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
            if not os.path.exists(distination):
                os.makedirs(distination)
            repo_path, version = get_repository(request.repo_url, distination)
            logger.info(f"代码库克隆成功")
        except Exception as e:
            logger.error(f"代码库克隆失败\n{e}")
            logger.error(f"代码库克隆失败，服务已停止")
            return {
                "message": f"代码库克隆失败，请检查当前服务器是否具备代码库克隆权限"
            }

        logger.info(f"开始提取代码资产")
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
        logger.info(f"{result}")
        host = settings.get("llm", {}).get("url")
        model = settings.get("llm", {}).get("model")
        key = settings.get("llm", {}).get("key")
        if not os.path.exists(asset_path):
            logger.error(f"代码资产提取失败，服务已停止")
            return {"message": f"代码资产提取失败，请检查代码资产中是否包含函数"}
        logger.info(f"开始生成函数级资产摘要")
        if max_workers <= 1:
            result = gen_function_sum_single(
                asset_path=asset_path, host=host, model=model, key=key
            )
        else:
            result = await gen_function_sum_multy(
                asset_path=asset_path,
                max_workers=max_workers,
                host=host,
                model=model,
                key=key,
            )
        logger.info(f"{result}")

        logger.info(
            f"【{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}】函数级资产摘要预分词"
        )
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
        logger.info(f"{result}")

        logger.info(f"函数级资产摘要嵌入")
        sum_embedding(asset_path=asset_path, url=settings.get("nlp_emb", {}).get("url"))
        logger.info(f"{result}")

        logger.info(f"开始生成模块级别资产摘要")
        if max_workers <= 1:
            result = gen_module_sum_single(
                asset_path=asset_path,
                info_path=info_path,
                host=host,
                model=model,
                key=key,
            )
        else:
            result = await gen_module_sum_multy(
                asset_path=asset_path,
                info_path=info_path,
                max_workers=max_workers,
                host=host,
                model=model,
                key=key,
            )
        logger.info(f"{result}")
        logger.info(f"开始生成系统级资产摘要")
        result = gen_repo_sum_single(
            info_path=info_path, host=host, model=model, key=key
        )
        logger.info(f"{result}")

        logger.info(f"开始生成模块、系统级资产嵌入")
        result = repo_sum_emb_single(
            info_path=info_path, url=settings.get("nlp_emb", {}).get("url")
        )
        logger.info(f"{result}")

        repo_name = os.path.basename(repo_path)
        codebase = pd.read_csv(asset_path)
        info = json.load(open(info_path, "r", encoding="utf-8"))
    finally:
        build_lock.release()
        is_building = False
        rm_repo(repo_path)
    logger.info(
        f"代码库构建完成: {os.path.basename(repo_path)}, 提交版本：{version}, 系统概述：{info['description']},模块数量：{len(info['modules'])},总共解析函数数目: {len(codebase)}"
    )
    return {
        "message": f"代码库构建完成: {os.path.basename(repo_path)}, 提交版本：{version}, 系统概述：{info['description']},模块数量：{len(info['modules'])},总共解析函数数目: {len(codebase)}"
    }




@router.post("/search", response_model=SearchResponse)
async def search_assets(
    request: SearchRequest, settings: Dict[str, Any] = Depends(get_config)
):
    """
    代码资产检索接口实现
    """
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info(f"*接收到代码资产检索请求")

    # 检索信息加载
    logger.info(f"加载检索信息")
    retriever = NlRetriever()
    topk = settings.get("CodeSearch", {}).get("topk")
    codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
    columns = settings.get("CodeSearch", {}).get("columns")
    logger.info(f"检索信息加载完成")
    logger.info(f"检索数量 {topk}")
    logger.info(f"代码库地址 {codebase_path}===")
    logger.info(f"停用词地址 {stopword_path}")
    logger.info(f"检索使用信息内容 {columns}")
    logger.info(f"检索依据 {request.keywords}")

    # 内容检索
    retriever.load_stopwords(stopword_path)
    examples = code_search_custom(
        retriever=retriever,
        key_words=request.keywords,
        top_K=topk,
        codebase_path=codebase_path,
        columns=columns,
        emb_url=settings.get("nlp_emb", {}).get("url"),
    )

    # 检索结果处理
    result_list = []
    reslut_info = f"检索资产数量：{topk}\n用户需求：{request.keywords}"
    result_item = None
    for count, example in examples.iterrows():
        if count >= topk:
            break
        # if example["sim_score"] <= 0:
        #     continue
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
    logger.info(f"检索结果")
    logger.info(reslut_info)
    logger.info(f"【{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}】完成检索")
    return {"result": result_list}


@router.post("/searchcode", response_model=SearchCodeResponse)
async def search_assets_code(
    request: SearchCodeRequest, settings: Dict[str, Any] = Depends(get_config)
):
    """
    代码资产检索接口实现
    """
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info(f"接收到代码资产检索请求")

    # 检索信息加载
    logger.info(f"加载检索信息")
    retriever = NlRetriever()
    topk = settings.get("CodeSearch", {}).get("topk")
    codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
    columns = settings.get("CodeSearch", {}).get("columns")
    host = settings.get("llm", {}).get("url")
    model = settings.get("llm", {}).get("model")
    key = settings.get("llm", {}).get("key")
    keywords = gen_code_sum(code=request.code, host=host, model=model, key=key)
    logger.info(f"检索信息加载完成")
    logger.info(f"检索数量 {topk}")
    logger.info(f"代码库地址 {codebase_path}===")
    logger.info(f"停用词地址 {stopword_path}")
    logger.info(f"检索使用信息内容 {columns}")
    logger.info(f"检索依据 {keywords}")
    logger.info(f"检索代码 {request.code}")

    # 内容检索
    retriever.load_stopwords(stopword_path)
    examples = code_search_custom(
        retriever=retriever,
        key_words=request.keywords,
        top_K=topk,
        codebase_path=codebase_path,
        columns=columns,
        emb_url=settings.get("nlp_emb", {}).get("url"),
    )

    # 检索结果处理
    result_list = []
    reslut_info = f"检索资产数量：{topk}\n用户需求：{request.keywords}"
    result_item = None
    for count, example in examples.iterrows():
        if count >= topk:
            break
        # if example["sim_score"] <= 0:
        #     continue
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
    logger.info(f"检索结果")
    logger.info(reslut_info)
    logger.info(f"【{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}】完成检索")
    return {"result": result_list}


@router.post("/imasset", response_model=ImAssetResponse)
async def import_assets(
    request: ImAssetRequest, settings: Dict[str, Any] = Depends(get_config)
):
    """
    代码资产入库
    """
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info(f"接收到代码资产入库请求")

    logger.info(f"检测执行条件")
    global is_building
    if is_building:
        logger.info(f"服务器正在处理其他代码资产，服务已拒绝")
        return {"message": f"服务器正在处理其他代码资产，请稍后再试"}
    is_building = True
    logger.info(f"可以执行代码库导入")

    # 加载配置信息
    temp_codebase_path = settings.get("codeBaseBuild", {}).get(
        "tempCodebasePath", "./temp"
    )
    codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath", "./data")
    repo_path = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
    if not (os.path.exists(codebase_path) and os.path.isdir(codebase_path)):
        os.makedirs(codebase_path, exist_ok=True)
    if not (os.path.exists(repo_path) and os.path.isdir(repo_path)):
        os.makedirs(repo_path, exist_ok=True)
    logger.info(
        f"配置信息加载完成\n临时代码资产库地址：{temp_codebase_path}\n代码库地址{codebase_path}\n代码资产库地址{repo_path}\n停用词地址{stopword_path}"
    )

    # 加载请求信息
    lib = request.lib
    # id_list = [imasset.id for imasset in request.imassets]
    id_list = request.assets
    asset_list = request.assets
    logger.info(
        f"请求信息加载完成\n资产所属临时资产库:{lib}\n资产数量:{len(asset_list)}"
    )

    # 加载临时入库资产列表
    temp_asset_path = os.path.join(temp_codebase_path, f"{lib}.csv")
    asset_list = pd.read_csv(temp_asset_path)

    logger.info(f"开始执行入库操作")
    if len(id_list) == 0:
        logger.info("拟定入库资产数量为0，不进行入库操作")
        result = temp_asset_from_df(asset_list)
        return {"message": "拟定入库资产数量为0，不进行入库操作", "assets": result}
    count = 0
    id_list = []
    version = datetime.now().strftime("%Y%m%d%H%M%S")
    for index, asset in asset_list.iterrows():

        logger.info(f"正在处理代码资产{index+1}/{len(asset_list)}")
        id = asset["id"]
        if id not in request.assets:
            continue
        repo_name = asset["repo_name"].split("_")[0]
        repo_path = os.path.join(repo_path, f"{repo_name}")
        asset_path = os.path.join(codebase_path, f"{repo_name}_assets_v_{version}.csv")
        info_path = os.path.join(codebase_path, f"{repo_name}_info_v_{version}.json")
        asset_path_new = deepcopy(asset_path)
        info_path_new = deepcopy(info_path)
        host = settings.get("llm", {}).get("url")
        model = settings.get("llm", {}).get("model")
        key = settings.get("llm", {}).get("key")
        # 检查该系统的资产是否已经存在
        asset_path = ""
        info_path = ""
        for file in os.listdir(codebase_path):
            r = file.split("_assets_v_")[0]
            if repo_name == r and file.endswith(".csv"):
                asset_path = os.path.join(codebase_path, file)
            i = file.split("_info_v_")[0]
            if repo_name == i and file.endswith(".json"):
                info_path = os.path.join(codebase_path, file)
        # 检查该系统是否存在坏资产
        if not asset_path == "":
            try:
                a = pd.read_csv(asset_path).to_dict()
            except Exception as e:
                logger.info(f"读取资产失败")
                logger.info(e)
                os.remove(asset_path)
                os.remove(info_path)
                asset_path = ""
                info_path = ""
        if not info_path == "":
            info = json.load(open(info_path))
            if (
                (len(info["modules"]) == 0)
                or (len(info["modules"]) == 1 and info["modules"][0]["name"] == "")
                or (info["name"] == "")
            ):
                os.remove(asset_path)
                os.remove(info_path)
                asset_path = ""
                info_path = ""

        # 检查当前资产是否需要新增
        try:
            if not build_lock.acquire(blocking=False):
                logger.info(f"服务器正在处理其他代码资产，服务已拒绝")
                return {"message": f"服务器正在处理其他代码资产，请稍后再试"}
            tmp_asset = {
                "name": [asset["name"]],
                "return_type": [asset["return_type"]],
                "signature": [asset["signature"]],
                "params": [asset["params"]],
                "summary": [asset["summary"]],
                "source_code": [asset["source_code"]],
                "extent": [asset["extent"]],
                "file_path": [asset["file_path"]],
                "module": [asset["module"]],
                "repo_name": [asset["repo_name"]],
                "sum_tokenize": [asset["sum_tokenize"]],
                "sum_embedding": [asset["sum_embedding"]],
            }
            tmp_asset = pd.DataFrame(tmp_asset)
            if not (asset_path == "" or info_path == ""):
                codebase = pd.read_csv(asset_path)
                info = json.load(open(info_path, "r", encoding="utf-8"))
                if codebase.empty:
                    all_asset = tmp_asset
                else:
                    codebase["key"] = (
                        codebase["signature"].astype(str)
                        + "|"
                        + codebase["file_path"].astype(str)
                    )
                    tmp_asset["key"] = (
                        tmp_asset["signature"].astype(str)
                        + "|"
                        + tmp_asset["file_path"].astype(str)
                    )
                    update_mask = tmp_asset["key"].isin(codebase["key"])
                    updates = tmp_asset[update_mask].copy()
                    new_entries = tmp_asset[~update_mask].copy()
                    codebase = codebase.drop("key", axis=1)
                    updates = updates.drop("key", axis=1)
                    new_entries = new_entries.drop("key", axis=1)
                    codebase = codebase[
                        ~codebase["signature"].isin(updates["signature"])
                        | ~codebase["file_path"].isin(updates["file_path"])
                    ]
                    all_asset = pd.concat(
                        [codebase, updates, new_entries], ignore_index=True
                    )
                all_asset.to_csv(asset_path, index=False)
                if not asset_path_new == asset_path and os.path.exists(asset_path_new):
                    os.remove(asset_path_new)
                if not info_path_new == info_path and os.path.exists(info_path_new):
                    os.remove(info_path_new)
                target_module = asset["module"]

                logger.info(f"开始生成模块级别资产摘要")
                result = gen_module_sum_single(
                    asset_path=asset_path,
                    info_path=info_path,
                    target_module=target_module,
                    host=host,
                    model=model,
                    key=key,
                )
                logger.info(f"{result}")

                logger.info(f"开始生成系统级资产摘要")
                result = gen_repo_sum_single(
                    info_path=info_path, host=host, model=model, key=key
                )
                logger.info(f"{result}")
                logger.info(f"开始生成模块、系统级资产嵌入")
                result = repo_sum_emb_single(
                    info_path=info_path,
                    url=settings.get("nlp_emb", {}).get("url"),
                    target_module=asset["module"],
                )
                logger.info(f"{result}")
                count += 1
                id_list.append(asset["id"])
                logger.info(f"合并资产完成")
            else:
                if not asset_path == "":
                    os.remove(asset_path)
                if not info_path == "":
                    os.remove(info_path)
                info = {
                    "name": repo_name,
                    "version": version,
                    "description": "",
                    "modules": [],
                }
                info["modules"].append({"name": asset["module"], "description": ""})
                with open(info_path_new, "w", encoding="utf-8") as f:
                    json.dump(info, f, ensure_ascii=False, indent=4)
                tmp_asset.to_csv(asset_path_new, index=False)
                asset_path = asset_path_new
                info_path = info_path_new
                logger.info(f"开始生成模块级别资产摘要")
                result = gen_module_sum_single(
                    asset_path=asset_path,
                    info_path=info_path,
                    host=host,
                    model=model,
                    key=key,
                    target_module=asset["module"],
                )
                logger.info(f"{result}")
                logger.info(f"开始生成系统级资产摘要")
                result = gen_repo_sum_single(
                    info_path=info_path, host=host, model=model, key=key
                )
                logger.info(f"{result}")
                logger.info(f"开始生成模块、系统级资产嵌入")
                result = repo_sum_emb_single(
                    info_path=info_path, url=settings.get("nlp_emb", {}).get("url")
                )
                logger.info(f"{result}")
                id_list.append(asset["id"])
                count += 1
        except Exception as e:
            logger.error(f"临时代码资产{asset['id']}入库失败")
            logger.error(e)
        finally:
            if build_lock.locked():
                build_lock.release()
            is_building = False
            rm_repo(repo_path)
        info = json.load(open(info_path, "r", encoding="utf-8"))
        codebase = pd.read_csv(asset_path)
        logger.info(f"临时代码资产{asset['id']}入库完成: {repo_name}, 版本：{version}")

    asset_list = asset_list[~asset_list["id"].isin(id_list)]
    asset_list.to_csv(temp_asset_path, index=False)

    logger.info(f"剩余{len(asset_list)}个临时资产,成功入库{count}个临时资产。")
    return {
        "message": f"剩余{len(asset_list)}个临时资产,成功入库{count}个临时资产。",
        "assets": temp_asset_from_df(asset_list),
    }


@router.post("/tempasset", response_model=TempAssetResponse)
async def temp_asset(
    request: TempAssetRequest, settings: Dict[str, Any] = Depends(get_config)
):

    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info("接收到获取临时资产请求")

    lib = request.lib
    logger.info(f"临时资产编号为:{lib}")
    temp_codebase_path = settings.get("codeBaseBuild", {}).get("tempCodebasePath")
    if not os.path.exists(os.path.join(temp_codebase_path, f"{lib}.csv")):
        result = []
        return {"assets": result}
    temp_asset = pd.read_csv(os.path.join(temp_codebase_path, f"{lib}.csv"))
    result = []
    for index, row in temp_asset.iterrows():
        temp = TempAsset(
            id=row["id"],
            name=row["repo_name"],
            module=row["file_path"],
            signature=row["signature"],
            description=row["summary"],
            source_code=row["source_code"],
        ).model_dump()
        result.append(temp)
    logger.info(f"返回临时资产列表")
    return {"assets": result}


@router.post("/rmtempasset", response_model=RmTempAssetResponse)
async def rm_temp_asset(
    request: RmTempAssetRequest, settings: Dict[str, Any] = Depends(get_config)
):
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info("接收到删除临时资产请求")
    lib = request.lib
    logger.info(f"临时资产库编号为:{lib}")
    logger.info(f"临时资产编号为:{request.asset}")
    temp_codebase_path = settings.get("codeBaseBuild", {}).get("tempCodebasePath")
    path = os.path.join(temp_codebase_path, f"{lib}.csv")
    id_list = [request.asset]
    temp_asset = pd.read_csv(path)
    temp_asset = temp_asset[~temp_asset["id"].isin(id_list)]
    temp_asset.to_csv(os.path.join(temp_codebase_path, f"{lib}.csv"), index=False)
    logger.info(f"删除临时资产{request.asset}成功")
    return {"message": f"删除临时资产成功"}


@router.post("/edittempasset", response_model=EditAssetResponse)
async def edit_temp_asset(
    request: EditAssetRequest, settings: Dict[str, Any] = Depends(get_config)
):
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info("接收到编辑临时资产请求")
    lib = request.lib
    asset = request.asset.model_dump()
    logger.info(f"临时资产库编号为:{lib}")
    logger.info(f"临时资产编号为:{asset['id']}")

    temp_codebase_path = settings.get("codeBaseBuild", {}).get("tempCodebasePath")
    temp_asset = pd.read_csv(os.path.join(temp_codebase_path, f"{lib}.csv"))
    codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath", "./data")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
    repo_path = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
    version = datetime.now().strftime("%Y%m%d%H%M%S")
    emb_url = settings.get("nlp_emb", {}).get("url")
    mask = temp_asset["id"] == asset["id"]
    if not mask.any():
        logger.error("临时资产库中不存在对应资产")
        result = temp_asset_from_df(temp_asset)
        result = [item.dict() for item in result]
        return {
            "message": "临时资产库中不存在对应资产",
            "assets": result,
        }
    repo_path = os.path.join(repo_path, f"{asset['name']}_{version}")
    host = settings.get("llm", {}).get("url")
    model = settings.get("llm", {}).get("model")
    key = settings.get("llm", {}).get("key")
    # 判断是否为源代码更改
    lib_code = temp_asset.loc[mask, "raw_code"].values[0].strip()
    asset_code = asset["source_code"].strip()
    if lib_code != asset_code:
        asset_list = process_temp_asset(
            repo_path=repo_path,
            file_path=asset["module"],
            code=asset_code,
            version=version,
            stopword_path=stopword_path,
            emb_url=emb_url,
            codebase_path=codebase_path,
            host=host,
            model=model,
            key=key,
        )
        if len(asset_list) == 0:
            logger.error(f"临时资产{asset['id']}编辑失败, 未检测到资产")
            result = temp_asset_from_df(temp_asset)
            result = [item.dict() for item in result]
            return {
                "message": f"临时资产{asset['id']}, 未检测到资产",
                "assets": result,
            }
        asset_info = asset_list[0]
        temp_asset.loc[mask, "name"] = asset_info["name"]
        temp_asset.loc[mask, "return_type"] = asset_info["return_type"]
        temp_asset.loc[mask, "signature"] = asset_info["signature"]
        temp_asset.loc[mask, "params"] = asset_info["params"]
        temp_asset.loc[mask, "summary"] = asset_info["summary"]
        temp_asset.loc[mask, "source_code"] = asset_info["source_code"]
        temp_asset.loc[mask, "extent"] = asset_info["extent"]
        temp_asset.loc[mask, "file_path"] = asset_info["file_path"]
        temp_asset.loc[mask, "module"] = asset_info["module"]
        temp_asset.loc[mask, "repo_name"] = asset["name"]
        temp_asset.loc[mask, "sum_tokenize"] = asset_info["sum_tokenize"]
        temp_asset.loc[mask, "sum_embedding"] = asset_info["sum_embedding"]
        temp_asset.loc[mask, "raw_code"] = asset_code
        if len(asset_list) > 1:
            for i in range(1, len(asset_list)):
                asset_info = asset_list[i]
                a = {
                    "id": str(uuid.uuid1()).replace("-", ""),
                    "name": asset_info["name"],
                    "description": asset_info["description"],
                    "return_type": asset_info["return_type"],
                    "signature": asset_info["signature"],
                    "params": asset_info["params"],
                    "summary": asset_info["summary"],
                    "source_code": asset_info["source_code"],
                    "extent": asset_info["extent"],
                    "file_path": asset_info["file_path"],
                    "module": asset_info["module"],
                    "repo_name": asset["name"],
                    "sum_tokenize": asset_info["sum_tokenize"],
                    "sum_embedding": asset_info["sum_embedding"],
                    "raw_code": asset_code,
                }
                new_asset = pd.DataFrame([a])
                temp_asset = pd.concat([temp_asset, new_asset], ignore_index=True)
    else:
        temp_asset.loc[mask, "name"] = asset["name"]

        lib_file_path = temp_asset.loc[mask, "file_path"].values[0].strip()
        asset_file_path = asset["module"].strip()
        if asset_file_path.startswith("/"):
            asset_file_path = asset_file_path[1:]
        elif asset_file_path.startswith("./"):
            asset_file_path = asset_file_path[2:]
        if not asset_file_path.endswith(".c"):
            asset_file_path = os.path.join(asset_file_path, "main.c")
        if lib_file_path != asset_file_path:
            module = os.path.dirname(asset_file_path)
            temp_asset.loc[mask, "module"] = "根模块" if module == "" else module
        temp_asset.loc[mask, "file_path"] = asset_file_path

        lib_sum = temp_asset.loc[mask, "summary"].values[0].strip()
        asset_sum = asset["description"].strip()
        if lib_sum != asset_sum:
            temp_asset.loc[mask, "summary"] = asset_sum
            temp_asset.loc[mask, "sum_tokenize"] = list(jieba.cut_for_search(asset_sum))
            a = temp_asset.loc[mask, "sum_embedding"]
            emb = nlp_emb_api(asset_sum, url=emb_url)
            temp_asset.loc[mask, "sum_embedding"] = str(emb)

    temp_asset.to_csv(os.path.join(temp_codebase_path, f"{lib}.csv"), index=False)
    logger.info(f"编辑临时资产{request.asset}成功")
    result = temp_asset_from_df(temp_asset)
    result = [item.dict() for item in result]
    return {
        "message": f"编辑临时资产成功系统已经自动执行资产分析",
        "assets": result,
    }


@router.post("/libregs", response_model=LibRegsResponse)
async def lib_regs(settings: Dict[str, Any] = Depends(get_config)):
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info("接收到获取临时代码资产库ID请求")
    id = str(uuid.uuid1()).replace("-", "")
    return {"id": id}


@router.post("/imreq", response_model=ImReqResponse, summary="解析WORD文档需求")
async def imreq(file: UploadFile = File(..., description="上传的WORD文档")):
    logger = deepcopy(logger_global)
    logger.info("接收到解析需求文档请求")

    if not file.filename.endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="仅支持.docx格式的Word文档")

    try:
        # 保存上传的临时文件
        temp_file_path = f"./tmp/{file.filename}"
        if not os.path.exists("./tmp"):
            os.makedirs("./tmp")
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        logger.info(f"保存上传的临时文件成功: {temp_file_path}")
        # 提取需求
        requirements_list = requirement_extract(temp_file_path)

        # 转换为响应格式
        requirement_items = [
            RequirementItem(id=req["id"].strip(), content=req["content"].strip())
            for req in requirements_list
        ]

        return {"requirements": requirement_items}

    except Exception as e:
        logger.info(f"解析文档失败{e}")
    finally:
        if "temp_file_path" in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@router.post("/gencoderag", response_model=GenerateCodeRagResponse)
async def gen_code_rag(
    request: GenerateCodeRagRequest, settings: Dict[str, Any] = Depends(get_config)
):
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info(f"接收到代码生成请求")

    # 开始检索代码资产
    req_list = request.requirements
    result = []
    ref_info = ""
    for index, req in enumerate(req_list):
        ref_info = ""
        req_id = req.id
        req_content = req.content
        logger.info(
            f"正在处理软件需求 {index+1}/{len(req_list)} : {req_id}-{req_content}"
        )

        for i, item in enumerate(req_list):
            if i != index:
                # 假设每个item有content和id属性
                ref_info += f"ID: {item.id}, Content: {item.content}\n"
        logger.info(f"开始检索代码资产")
        retriever = NlRetriever()
        topk = settings.get("CodeSearch", {}).get("topk")
        codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath")
        stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
        columns = settings.get("CodeSearch", {}).get("columns")
        keywords = req_content
        logger.info(f"检索信息")
        logger.info(f"检索数量 {topk}")
        logger.info(f"代码库地址 {codebase_path}===")
        logger.info(f"停用词地址 {stopword_path}")
        logger.info(f"检索使用信息内容 {columns}")
        logger.info(f"检索关键词 {keywords}")

        retriever.load_stopwords(stopword_path)
        examples = code_search_custom(
            retriever=retriever,
            key_words=req_content,
            top_K=topk,
            codebase_path=codebase_path,
            columns=columns,
            emb_url=settings.get("nlp_emb", {}).get("url"),
        )
        result_info = ""
        for count, example in examples.iterrows():
            if count >= topk:
                break
            # if example["sim_score"] <= 0:
            #     continue
            result_info += "\t" + f"【代码资产{count+1}】:"
            result_info += "\t\t" + f'系统名：{example["repo_name"]} \n'
            result_info += "\t\t" + f'所属模块：{example["module"]} \n'
            result_info += "\t\t" + f'资产签名：{example["signature"]} \n'
            result_info += "\t\t" + f'资产概述：{example["summary"]} \n'
            result_info += "\t\t" + f'资产源码：\n{example["source_code"]} \n'
        logger.info(f"检索结果")
        logger.info(result_info)
        example = asset_from_df(examples)
        asset_info = asset_content(example)
        prompt_templete = code_gen_mulreq
        prompt_templete.generate_prompt(
            user_param={
                "asset": asset_info,
                "requirement": req_content,
                "reference": ref_info,
            }
        )
        messages = prompt_templete.generate_message()
        logger.info(f"完成提示词加载")
        logger.info(messages)
        try:
            host = settings.get("llm", {}).get("url")
            model = settings.get("llm", {}).get("model")
            key = settings.get("llm", {}).get("key")
            response = generate_api(messages, host=host, model=model, key=key)
            response = response.split("</think>")[-1]
            info = {"code": code_parse(response), "info": info_parse(response)}
            logger.info(f"完成0次代码生成")
            itea_max = settings.get("CodeGeneration", {}).get("itea")
            itea_count = 0
            for itea in range(itea_max):
                itea_count = itea
                if info["code"] == "" or info["info"] == "":
                    if info["code"] == "":
                        messages[-1][
                            "content"
                        ] += "你生成的内容中，C语言代码应该用```c和```包裹起来，记得遵守规则\n"
                    if info["info"] == "":
                        messages[-1][
                            "content"
                        ] += "你生成的内容中，资产复用说明应该用```info和```包裹起来，记得遵守规则\n"
                    logger.info(f"完成{itea+1}次信息解析")
                    response = generate_api(messages, host=host, model=model, key=key)
                    response = response.split("</think>")[-1]
                    logger.info(f"完成{itea+1}次信息修正")
                    info = {"code": code_parse(response), "info": info_parse(response)}
                    logger.info(f"完成{itea+1}次信息采集")
                else:
                    break
            if info["code"] == "" or info["info"] == "":
                info["code"] = response
                info["info"] = "复用情况分析失败，请参考代码生成结果"
            logger.info(f"完成生成")
            logger.info(f"迭代次数:{itea_count}")
            logger.info(f'生成代码\n{info["code"]}')
            logger.info(f"复用情况\n{info['info']}")
            logger.info(f"完成代码生成")

            item = CodeGenResult(
                id=req_id,
                content=req_content,
                code=info["code"],
                assets=example,
                info=info["info"],
            )
            result.append(item)
        except APITimeoutError as e:
            logger.error(e)
            item = CodeGenResult(
                id=req_id,
                content=req_content,
                code="服务器繁忙，生成失败，请稍后再试",
                assets=example,
                info="复用情况分析失败",
            )
            result.append(item)
        except Exception as e:
            logger.error(e)
            item = CodeGenResult(
                id=req_id,
                content=req_content,
                code="服务器繁忙，生成失败，请稍后再试",
                assets=example,
                info="复用情况分析失败",
            )
            result.append(item)
    return {"result": result}


@router.post("/editcode", response_model=EditCodeResponse)
async def edit_code(
    request: EditCodeRequest, settings: Dict[str, Any] = Depends(get_config)
):
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    logger = deepcopy(logger_global)
    logger.info("接收到代码优化请求")
    logger.info(f"接收到的需求:{request.content}")

    req_id = request.id
    req_content = request.content

    asset_info = asset_content(request.assets)
    prompt_templete = code_gen_edit
    prompt_templete.generate_prompt(
        user_param={
            "asset": asset_info,
            "requirement": req_content,
            "code": request.code,
            "edit_instruction": request.edit,
        }
    )
    messages = prompt_templete.generate_message()
    logger.info(f"完成提示词加载")
    logger.info(messages)
    result = ""
    try:
        host = settings.get("llm", {}).get("url")
        model = settings.get("llm", {}).get("model")
        key = settings.get("llm", {}).get("key")
        response = generate_api(messages, host=host, model=model, key=key)
        response = response.split("</think>")[-1]
        result = {"code": code_parse(response), "info": info_parse(response)}
        logger.info(f"完成0次代码生成")
        itea_max = settings.get("CodeGeneration", {}).get("itea")
        itea_count = 0
        for itea in range(itea_max):
            itea_count = itea
            if result["code"] == "" or result["info"] == "":
                if result["code"] == "":
                    messages[-1][
                        "content"
                    ] += "你生成的内容中，C语言代码应该用```c和```包裹起来，记得遵守规则\n"
                if result["info"] == "":
                    messages[-1][
                        "content"
                    ] += "你生成的内容中，资产复用说明应该用```info和```包裹起来，记得遵守规则\n"
                logger.info(f"完成{itea+1}次信息解析")
                response = generate_api(messages, host=host, model=model, key=key)
                response = response.split("</think>")[-1]
                logger.info(f"完成{itea+1}次信息修正")
                result = {"code": code_parse(response), "info": info_parse(response)}
                logger.info(f"完成{itea+1}次信息采集")
            else:
                break
        if result["code"] == "" or result["info"] == "":
            logger.info(f"信息采集存在问题")
            result = {}
            result["code"] = response
            result["info"] = "复用情况分析失败，请参考代码生成结果"
        logger.info(f"完成生成")
        logger.info(f"迭代次数:{itea_count}")
        logger.info(f"生成代码\n{result['code']}")
        logger.info(f"复用情况\n{result['info']}")
        logger.info(f"完成代码生成")
    except APITimeoutError:
        logger.error(f"API请求超时")
        return {"code": "服务器繁忙，生成失败，请稍后再试"}
    except Exception as e:
        logger.error(f"代码生成失败: {str(e)}")
        return {"code": "服务器繁忙，生成失败，请稍后再试"}
    return {"code": result["code"].strip(), "info": result["info"].strip()}


# 代码审查接口
@router.post("/review", response_model=ReviewResponse)
async def review(
    file: UploadFile=File(...), request: Dict[str, Any] = Form(...), settings: Dict[str, Any] = Depends(get_config)
):
    # 加载配置信息
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings

    # 声明logger对象
    logger = deepcopy(logger_global)
    logger.info(f"接收到代码审查请求")

    # 加载请求信息
    request_dict = json.loads(request)
    request = ReviewRequest(**request)
    file = request.file
    support = request.support
    end = request.end
    start = request.start

    # 加载工程目录
    project_dir = settings.get('CodeCheck', {}).get('projectPath')
    temp_project_file = os.path.join(project_dir, f'{datetime.now().strftime("%Y%m%d%H%M%S")}_{file.filename}')
    with open(temp_project_file, 'wb') as temp_project:
        content = await temp_project.read()
        temp_project.write(content)
    try:
        temp_project_dir = os.path.join(os.path.join(project_dir, f'{datetime.now().strftime("%Y%m%d%H%M%S")}_{file.filename.split('.')[0]}'))
        with zipfile.ZipFile(temp_project_file, 'r') as zip_ref:
            zip_ref.extractall(temp_project_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    # 审查代码
    code_file = os.path.join(temp_project_dir, file.filename)
    code = ''
    with open(code_file, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        # 确保行号在有效范围内
        start = max(0, start - 1)
        end = min(len(lines), end)
        code =  ''.join(lines[start:end])
    err_list = build_in_check(code=code, support=support)
    # 审查结果解析
    type = ""
    errors = []
    item = {"line": -1, "col": -1, "desp": "代码正确，并且符合规范"}
    if len(err_list) == 0:
        type = "right"
        item["line"] = -1
        item["col"] = -1
        item["desp"] = "代码正确，并且符合规范"
        errors.append(deepcopy(item))
    else:
        type = "semantic"
        errors = err_list_parse(err_list=err_list)

    # 日志记录
    logger.info(f"代码审查结果\n{type}")
    logger.info(f"代码审查详情\n{errors}")
    return {"type": type, "err": errors}


# 代码修正接口
@router.post("/fix", response_model=FixResponse)
async def fix(request: FixRequest, settings: Dict[str, Any] = Depends(get_config)):
    """
    代码修正接口

    Args:
        request (FixRequest): 代码修正接口请求数据
        settings (Dict[str, Any], optional): 接口依赖配置信息

    Returns:
        接口响应信息
    """
    # 加载请求参数
    code = request.code
    type = request.type
    err_list = request.err

    # 加载配置信息
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    itea = settings.get("CodeCheck", {}).get("itea")
    host = settings.get("llm", {}).get("url")
    model = settings.get("llm", {}).get("model")
    key = settings.get("llm", {}).get("key")

    # 声明logger对象
    logger = deepcopy(logger_global)
    logger.info(f"接收到代码修正请求")

    # 如果需要审查 ，则进行代码审查
    type = ""
    errors = []

    # 进行代码修正
    prompt = code_check
    snippet = deepcopy(code)
    err_info = ""
    i = 0

    # 判断是否需要修正
    if type == "right":
        info = {}
        fixed = True
        info["code"] = "无"
        info["type"] = "无"
        info["loc"] = "无"
        return {"result": snippet}
    else:
        for index, error in enumerate(err_list):
            err_info += f"{index+1}. 不符合代码规范, 错误位置:Line {error.line}, Col {error.col}, 错误信息: {error.desp}\n"
        logger.info(f" 当前代码存在异常\n{err_info}")
        prompt.generate_prompt(user_param={"code": snippet, "error": err_info})
        messages = prompt.generate_message()
        snippet = generate_api(messages, host=host, model=model, key=key)
        snippet = snippet.split("</think>")[-1]
        while i < itea:
            if ((not "```c" in snippet) and (not "```C" in snippet)) or (
                not "```" in snippet
            ):
                messages[-1][
                    "content"
                ] += "如果需要生成代码，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这句话"
                snippet = generate_api(messages, host=host, model=model, key=key)
                snippet = snippet.split("</think>")[-1]
                i += 1
            else:
                break

        snippet = code_parse(snippet)
        logger.info(f"修正后代码\n {snippet}")
        logger.info(f"完成代码修正")
        return {"result": snippet}


@router.post("/toollist", response_model=ToolListResponse)
async def tool_list(settings: Dict[str, Any] = Depends(get_config)):
    """
    获取代码审查工具列表

    Args:
        settings (Dict[str, Any], optional): 接口配置信息. Defaults to Depends(get_config).

    Returns:
        ToolListResponse: 工具列表响应信息
    """

    # 加载配置信息
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    tool_list = settings.get("CodeCheck", {}).get("tools", [])

    # 声明logger对象
    logger = deepcopy(logger_global)
    logger.info("接收到获取代码审查工具列表请求")

    # 获取工具列表
    result = []
    for tool in tool_list:
        result.append(
            {"name": tool["name"], "type": tool["type"], "endpoint": tool["endpoint"]}
        )
    logger.info(f"工具列表内容: {result}")
    logger.info(f"完成获取代码审查工具列表请求响应")
    return {"tools": result}


@router.post("/toolsupport", response_model=ToolSupportResponse)
async def tool_support(
    request: ToolSupportRequest, settings: Dict[str, Any] = Depends(get_config)
):
    """
    获取代码审查工具列表

    Args:
        settings (Dict[str, Any], optional): 接口配置信息. Defaults to Depends(get_config).

    Returns:
        ToolListResponse: 工具列表响应信息
    """

    # 加载配置信息
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    tool_list = settings.get("CodeCheck", {}).get("tools", [])

    # 声明logger对象
    logger = deepcopy(logger_global)
    logger.info("接收到获取代码审查工具支持审查标准列表请求")

    # 加载请求信息
    name = request.tool
    logger.info(f"请求工具名称:{name}")

    # 获取工具列表
    result = {}
    for tool in tool_list:
        if tool["name"] == name:
            result["support"] = tool["support"]
    logger.info(f"工具支持规则目录: {result}")
    logger.info(f"完成获取代码审查工具支持审查标准列表请求响应")
    return {"supports": result}


@router.post("/store", response_model=StoreResponse)
async def store_asset(
    request: StoreRequest, settings: Dict[str, Any] = Depends(get_config)
):
    """
    临时代码资产存储接口

    Args:
        request (StoreRequest): 接口请求信息

    """

    def single_clean(dataframe: pd.DataFrame):
        """
        处理同一资产签名下的文件名冲突问题

        Args:
            dataframe (pd.DataFrame): 资产目录

        Returns:
            DataFrame: 处理后的资产目录
        """
        updates = {}
        columns_to_check = ["repo_name", "file_path", "signature", "source_code"]
        dataframe = dataframe.drop_duplicates(subset=columns_to_check, keep="first")
        columns_to_check = ["repo_name", "file_path", "signature"]
        grouped = dataframe.groupby(columns_to_check)
        for name, group in grouped:
            if len(group) > 1:
                indices = group.index.tolist()
                base_name, ext = os.path.splitext(group.iloc[0]["file_path"])
                for i, idx in enumerate(indices):
                    if i == 0:
                        continue
                    else:
                        new_filename = f"{base_name}_{i}{ext}"
                        updates[idx] = new_filename
        for idx, new_path in updates.items():
            dataframe.loc[idx, "file_path"] = new_path
        dataframe = dataframe.drop_duplicates(subset=columns_to_check, keep="first")
        return dataframe

    # 加载配置信息
    settings = deepcopy(settings)["config"] if "config" in settings.keys() else settings
    temp_codebase_path = settings.get("codeBaseBuild", {}).get("tempCodebasePath")
    codebase_path = settings.get("codeBaseBuild", {}).get("codebasePath", "./data")
    stopword_path = settings.get("codeBaseBuild", {}).get("stopwordPath")
    repo_path = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
    emb_url = settings.get("nlp_emb", {}).get("url")
    host = settings.get("llm", {}).get("url")
    model = settings.get("llm", {}).get("model")
    key = settings.get("llm", {}).get("key")

    # 声明logger对象
    logger = deepcopy(logger_global)
    logger.info("接收到增加临时资产请求")

    # 加载请求信息
    lib = request.lib
    raw_asset_list = request.assets
    logger.info(f"临时资产库编号为:{lib}")

    # 声明必要变量
    item = {}
    new_asset = []
    u_conut = 0
    message = ""
    version = datetime.now().strftime("%Y%m%d%H%M%S")
    temp_asset_path = os.path.join(temp_codebase_path, f"{lib}.csv")
    if not os.path.exists(temp_asset_path):
        temp_asset = []
    else:
        try:
            temp_asset = pd.read_csv(temp_asset_path)
        except:
            logger.info("读取临时资产失败")
            os.remove(temp_asset_path)
            temp_asset = []

    # 检查是否为空
    if len(raw_asset_list) == 0:
        logger.info("没有需要增加的临时资产")
        if len(temp_asset) > 0:
            asset = temp_asset_from_df(temp_asset)
            asset = [item.dict() for item in asset]
        else:
            asset = []
        return {"message": "没有需要增加的临时资产", "assets": asset}

    # 逐个增加临时资产
    for index, asset in enumerate(raw_asset_list):

        logger.info(f"正在增加临时资产:{index+1}/{len(raw_asset_list)}")
        repo_path = settings.get("codeBaseBuild", {}).get("repoPath", "./repo")
        repo_path = os.path.join(repo_path, f"{asset.name}_{version}")
        code = asset.code
        # 检查某个资产是否为空
        if code == "":
            message += f"临时资产:{asset.name}没有源代码\n"
            continue

        # 处理临时资产
        asset_list = process_temp_asset(
            repo_path=repo_path,
            file_path=asset.module,
            code=asset.code,
            version=version,
            stopword_path=stopword_path,
            emb_url=emb_url,
            codebase_path=codebase_path,
            host=host,
            model=model,
            key=key,
        )

        # 检查当前代码片段是否含有相应资产
        if len(asset_list) == 0:
            message += f"临时资产:{asset.name}不包含函数\n"
            logger.info(f"增加临时资产失败:{asset.name}")
            continue

        # 资产信息保存
        asset_info = asset_list[0]
        item["id"] = str(uuid.uuid1()).replace("-", "")
        item["name"] = asset_info["name"]
        item["return_type"] = asset_info["return_type"]
        item["signature"] = asset_info["signature"]
        item["params"] = asset_info["params"]
        item["summary"] = asset_info["summary"]
        item["source_code"] = asset_info["source_code"]
        item["extent"] = asset_info["extent"]
        item["file_path"] = asset_info["file_path"]
        item["module"] = asset_info["module"]
        item["repo_name"] = asset.name
        item["sum_tokenize"] = asset_info["sum_tokenize"]
        item["sum_embedding"] = asset_info["sum_embedding"]
        item["raw_code"] = code
        new_asset.append(deepcopy(item))
        if len(asset_list) > 1:
            for i in range(1, len(asset_list)):
                asset_info = asset_list[i]
                a = {
                    "id": str(uuid.uuid1()).replace("-", ""),
                    "name": asset_info["name"],
                    "summary": asset_info["summary"],
                    "return_type": asset_info["return_type"],
                    "signature": asset_info["signature"],
                    "params": asset_info["params"],
                    "source_code": asset_info["source_code"],
                    "extent": asset_info["extent"],
                    "file_path": asset_info["file_path"],
                    "module": asset_info["module"],
                    "repo_name": asset.name,
                    "sum_tokenize": asset_info["sum_tokenize"],
                    "sum_embedding": asset_info["sum_embedding"],
                    "raw_code": code,
                }
                new_asset.append(deepcopy(a))

    if len(temp_asset) <= 0:
        temp_asset = pd.DataFrame(new_asset)
        temp_asset = single_clean(temp_asset)
        u_conut = len(temp_asset)

    elif len(new_asset) > 0:
        new_asset = pd.DataFrame(new_asset)
        new_asset = single_clean(new_asset)
        for col in ["repo_name", "file_path", "signature"]:
            new_asset[col] = new_asset[col].astype(str)
            temp_asset[col] = temp_asset[col].astype(str)
        merged_check = pd.merge(
            new_asset,
            temp_asset,
            on=["repo_name", "file_path", "signature"],
            how="left",
            indicator=True,
        )
        u_conut = (merged_check["_merge"] == "left_only").sum()

        temp_keys = temp_asset[["repo_name", "file_path", "signature"]].apply(
            tuple, axis=1
        )
        new_keys = new_asset[["repo_name", "file_path", "signature"]].apply(
            tuple, axis=1
        )
        keep_mask = ~temp_keys.isin(new_keys)
        merged = pd.concat([temp_asset[keep_mask], new_asset], ignore_index=True)
        temp_asset = merged
    if len(temp_asset) > 0:
        columns_to_check = ["repo_name", "file_path", "signature"]
        temp_asset = temp_asset.drop_duplicates(subset=columns_to_check, keep="first")
        temp_asset.to_csv(os.path.join(temp_codebase_path, f"{lib}.csv"), index=False)

    logger.info(f"临时资产库{request.lib}更新成功\n{temp_asset}")
    if len(temp_asset) > 0:
        asset = temp_asset_from_df(temp_asset)
        asset = [item.dict() for item in asset]
    else:
        asset = []
    message += f"完成新增临时资产，当前资产总数量：{len(temp_asset)}，新增数量{u_conut}"
    logger.info(message)
    return {
        "message": message,
        "assets": asset,
    }
