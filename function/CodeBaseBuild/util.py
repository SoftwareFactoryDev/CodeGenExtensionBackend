import os
import json
import re
import subprocess
import tempfile
import shutil
import sys
from typing import Dict, Any, List, Tuple, List, Set, Optional
from copy import deepcopy

from function.CodeBaseBuild.prompt import code_sum_template
from function.CodeBaseBuild.llm_gen import generate_api
from app.logger import logger_global


def gen_code_sum(code, host, model, key):
    logger = deepcopy(logger_global)
    summary = ""
    prompt_template = deepcopy(code_sum_template)
    param = {"code": code}
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


def asset_in_module(function_list, global_var_list, macro_list, struct_list):

    asset_info = ""
    for index, item in function_list.iterrows():
        asset_info += f'* 函数名：{item["name"]} 所属文件:{item["file_path"]} 函数签名:{item["signature"]} 功能描述:{item["description"]}\n'
    for index, item in global_var_list.iterrows():
        asset_info += f'* 函数名：{item["name"]} 所属文件:{item["file_path"]} 声明语句:{item["source_code"]} 属性描述:{item["description"]}\n'
    for index, item in macro_list.iterrows():
        asset_info += f'* 函数名：{item["name"]} 所属文件:{item["file_path"]} 声明语句:{item["source_code"]} 属性描述:{item["description"]}\n'
    for index, item in struct_list.iterrows():
        asset_info += f'* 函数名：{item["name"]} 所属文件:{item["file_path"]} 声明语句:{item["source_code"]} 属性描述:{item["description"]}\n'
    return asset_info


def module_in_repo(module_list):

    module_info = ""
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

        rel_dir = os.path.relpath(root, repo_path)
        if rel_dir == ".":
            rel_dir = ""

        rel_files = []
        for f in files:
            if f.endswith(".h") or f.endswith(".c"):
                fp = os.path.join(rel_dir, f) if rel_dir else f
                rel_files.append(to_posix(fp))

        rel_dirs = []
        for d in dirs:
            dp = os.path.join(rel_dir, d) if rel_dir else d
            rel_dirs.append(to_posix(dp))

        rel_files.sort()
        rel_dirs.sort()

        if len(rel_files) > 0 or len(rel_dirs) > 0:
            directories.append(
                {
                    "path": to_posix(rel_dir),  # 根目录为 ""
                    "files": rel_files,
                    "dirs": rel_dirs,
                }
            )

    directories.sort(key=lambda x: x["path"])
    return directories

def get_repo_change_sets(
    old_repo_url: str,
    old_commit: str,
    new_repo_local_path: str,
    new_commit: str = "HEAD"
) -> Dict[str, List[str]]:
    """
    精准返回新旧仓库各自涉及变更的文件与目录（严格按文件存在性分离）
    
    Args:
        old_repo_url (str): 旧仓库的 URL
        old_commit (str): 旧仓库的 Commit
        new_repo_local_path (str): 新仓库的本地路径
        new_commit (str, optional): 新仓库的 Commit. Defaults to "HEAD".

    Returns:
        old_changed_files(List[str]) : 旧Commit中存在且变更的文件（M/D/T状态）
        old_changed_directories(List[str]) : 对应目录（根目录用'.'表示）
        new_changed_files(List[str]) : 新Commit中存在且变更的文件（M/A/T状态）
        new_changed_directories(List[str]) : 对应目录
    """
    # ===== 验证仓库路径 =====
    if not os.path.isdir(new_repo_local_path):
        raise ValueError(f"路径不存在: {new_repo_local_path}")
    if not os.path.isdir(os.path.join(new_repo_local_path, ".git")):
        raise ValueError(f"非有效 Git 仓库: {new_repo_local_path}")
    
    def _git(cmd: List[str], error_msg: str) -> str:
        try:
            result = subprocess.run(
                ["git"] + cmd,
                cwd=new_repo_local_path,
                capture_output=True,
                text=True,
                timeout=180,
                check=True
            )
            return result.stdout.strip()
        except FileNotFoundError:
            raise RuntimeError("系统未安装 Git。请安装 Git 并确保在 PATH 中。")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git 命令超时: {' '.join(cmd)}")
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or e.stdout or "").strip()
            hints = []
            if "Authentication" in stderr or "Permission denied" in stderr:
                hints.append("请检查 SSH 密钥或 Git 凭据配置")
            if f"unknown revision '{old_commit}'" in stderr:
                hints.append(f"尝试从 {old_repo_url} 拉取该 Commit")
            raise RuntimeError(
                f"{error_msg}\nGit 错误: {stderr}" + 
                (f"\n提示: {'; '.join(hints)}" if hints else "")
            )
    
    _git(["rev-parse", "--verify", f"{new_commit}^{{commit}}"], 
         f"新 Commit 不存在于本地仓库: {new_commit}")
    
    try:
        _git(["rev-parse", "--verify", f"{old_commit}^{{commit}}"], "")
    except RuntimeError:
        _git(
            ["fetch", "--depth=1", "--no-tags", old_repo_url, old_commit],
            f"无法从 {old_repo_url} 拉取旧 Commit {old_commit}"
        )
    
    try:
        diff_raw = _git(
            ["diff", "--name-status", "--no-renames", old_commit, new_commit],
            "计算差异失败（确认两 Commit 属于同一项目历史）"
        )
    except RuntimeError as e:
        if "--no-renames" in str(e) and "unknown option" in str(e).lower():
            # 兼容旧版 Git (<2.9)：降级使用基础命令（重命名视为删除+新增）
            diff_raw = _git(
                ["diff", "--name-status", old_commit, new_commit],
                "计算差异失败（确认两 Commit 属于同一项目历史）"
            )
        else:
            raise
    
    old_files, new_files = set(), set()
    for line in diff_raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        status, filepath = parts[0].strip()[0], parts[1].strip()
        
        if status in ("M", "D", "T"):
            old_files.add(filepath)
        if status in ("M", "A", "T"):
            new_files.add(filepath)
    
    def _extract_dirs(files: set) -> List[str]:
        dirs = {os.path.dirname(f) or "." for f in files}
        return sorted(dirs)
    
    return {
        "old_changed_files": sorted(old_files),
        "old_changed_directories": _extract_dirs(old_files),
        "new_changed_files": sorted(new_files),
        "new_changed_directories": _extract_dirs(new_files)
    }

