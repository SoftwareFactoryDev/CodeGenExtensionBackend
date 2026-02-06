import re
import os
import json
import chardet
from copy import deepcopy

import pandas as pd

from app.models import TempAsset, Asset
from app.logger import logger_global
from function.CodeBaseBuild.build_codebase import gen_element_sum_single, repo_parse_parallel, code_sum_tokenize_single, sum_embedding, rm_repo
def get_encode(file_path):
    """
    获取文件的编码方式

    Args:
        path : 文件地址

    Returns:
        str: 解析到的文件编码方式
    """    
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        encoding = chardet.detect(raw_data)['encoding']
    return encoding

def temp_asset_from_df(df):

    result = []
    for index, row in df.iterrows():
        asset = TempAsset(
            id = str(row['id']),
            name = str(row['repo_name']),
            module = str(row['file_path']),
            signature = str(row['signature']),
            description = str(row['summary']),
            source_code = str(row['source_code'])
        )
        result.append(asset)
    return result

def asset_from_df(df):

    result = []
    for index, row in df.iterrows():
        asset = Asset(
            name = row['repo_name'],
            module = row['module'],
            signature = row['signature'],
            description = row['summary'],
            source_code = row['source_code']
        )
        result.append(asset)
    return result

def process_temp_asset(repo_path, file_path, code, codebase_path, version, stopword_path, emb_url, host, model, key):

    logger = deepcopy(logger_global)
    if file_path.startswith('/'):
        file_path = file_path[1:]
    elif file_path.startswith('./'):
        file_path = file_path[2:]
    if not file_path.endswith('.c'):
        file_path = os.path.join(file_path, 'main.c')
    os.makedirs(repo_path, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.join(repo_path, file_path)), exist_ok=True)
    with open(os.path.join(repo_path, file_path), "w") as f:
        f.write(code)
    logger.info(f"模拟代码库构建完成")

    # 提取代码资产
    logger.info(f"开始提取代码资产")
    if not (os.path.exists(codebase_path) and os.path.isdir(codebase_path)):
        os.makedirs(codebase_path, exist_ok=True)
    result = repo_parse_parallel(
        repo_path=repo_path, codebase_path=codebase_path, version=version, add=True
    )
    repo_name = os.path.basename(repo_path)
    asset_path = os.path.join(codebase_path, f"{repo_name}_assets_v_{version}.csv")
    info_path = os.path.join(codebase_path, f"{repo_name}_info_v_{version}.json")
    logger.info(f"{result}")
    logger.info(f"开始生成函数级资产摘要")
    result = gen_element_sum_single(element_path=asset_path, host=host, model=model, key=key)
    logger.info(f"{result}")
    logger.info(f"函数级资产摘要预分词")
    result = code_sum_tokenize_single(
        asset_path=asset_path, stopword_path=stopword_path
    )
    logger.info(f"{result}")
    logger.info(f"函数级资产摘要嵌入")
    sum_embedding(asset_path=asset_path, url=emb_url)
    logger.info(f"{result}")
    try:
        asset_info = pd.read_csv(asset_path).to_dict(orient='records')
        os.remove(asset_path)
        os.remove(info_path)
        rm_repo(repo_path)
        if not isinstance(asset_info, list):
                asset_info = [asset_info]
    except Exception as e:
        logger.error(f"代码资产提取失败")
        logger.error(e)
        asset_info = []
    finally:
        if os.path.exists(asset_path): os.remove(asset_path) 
        if os.path.exists(asset_path): os.remove(info_path)
        rm_repo(repo_path)
    return asset_info