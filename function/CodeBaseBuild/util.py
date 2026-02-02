import os
import json
import re
from typing import Dict, Any, List

from copy import deepcopy

from function.CodeBaseBuild.prompt import code_sum_template
from function.CodeBaseBuild.llm_gen import generate_api
from app.logger import logger_global

def gen_code_sum(code, host, model, key):
    logger = deepcopy(logger_global)
    summary = ''
    prompt_template = deepcopy(code_sum_template)
    param = {
        "code": code
    }
    prompt_template.generate_prompt(user_param=param)
    messages = prompt_template.generate_message()
    ite = 0
    while True:
        response = generate_api(messages, host=host, model=model, key=key)
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
    result = summary.strip()
    return result

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

def asset_in_module(asset_list):
    
    asset_info =''
    for index, item in asset_list.iterrows():
        asset_info += f'* 函数名：{item["name"]} 所属文件:{item["file_path"]} 函数签名:{item["signature"]} 功能描述:{item["summary"]}\n'

    return asset_info

def module_in_repo(module_list):
    
    module_info =''
    for item in module_list:
        module_info += f'* 模块路径：{item["name"]}  功能描述:{item["description"]}\n'

    return module_info

def to_posix(path: str) -> str:
    """
    路径分隔符统一为/,便于展示
    """
    return path.replace("\\", "/")

def scan_repo_structure(repo_path: str) -> List[Dict[str, Any]]:
    """
    - path 为相对 repo 根目录的路径；根目录用空字符串 ""
    - files/dirs 为相对 repo 根目录的路径列表
    """
    directories: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(repo_path):
        # 忽略 .git
        dirs[:] = [d for d in dirs if d != ".git"]

        # 计算当前目录相对 repo 根目录路径
        rel_dir = os.path.relpath(root, repo_path)
        if rel_dir == ".":
            rel_dir = ""

        # 生成当前目录下的文件/子目录路径
        rel_files = []
        for f in files:
            fp = os.path.join(rel_dir, f) if rel_dir else f
            rel_files.append(to_posix(fp))

        rel_dirs = []
        for d in dirs:
            dp = os.path.join(rel_dir, d) if rel_dir else d
            rel_dirs.append(to_posix(dp))

        # 排序
        rel_files.sort()
        rel_dirs.sort()

        directories.append(
            {
                "path": to_posix(rel_dir),  # 根目录为 ""
                "files": rel_files,
                "dirs": rel_dirs,
            }
        )

    # 按 path 排序，根目录为第一条
    directories.sort(key=lambda x: x["path"])
    return directories