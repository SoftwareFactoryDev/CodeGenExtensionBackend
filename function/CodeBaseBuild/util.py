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


def asset_in_module(asset_list):

    asset_info = ""
    for index, item in asset_list.iterrows():
        asset_info += f'* 函数名：{item["name"]} 所属文件:{item["file_path"]} 函数签名:{item["signature"]} 功能描述:{item["summary"]}\n'

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


def get_changed_files_and_dirs(
    old_repo_url: str,
    old_commit: str,
    new_repo_url: str,
    new_commit: str,
    temp_dir: Optional[str] = None,
    keep_temp: bool = False
) -> Tuple[List[Tuple[str, str]], Set[str]]:
    """
    获取两个 Git 仓库指定 Commit 之间的变更文件与目录（仅下载必要对象，节约克隆成本）
    
    Args:
        old_repo_url: 旧版本仓库 URL
        old_commit: 旧版本 Commit 哈希（完整或足够唯一前缀）
        new_repo_url: 新版本仓库 URL
        new_commit: 新版本 Commit 哈希
        temp_dir: 可选，指定临时工作目录（调试用）
        keep_temp: 是否保留临时目录（默认 False）
    
    Returns:
        Tuple[
            List[Tuple[str, str]]: 变更文件列表 [(状态, 路径), ...] 
                状态: 'A'=新增, 'M'=修改, 'D'=删除, 'R'=重命名(拆分为D+A), 'C'=复制(拆分为保留+新增)
            Set[str]: 变更文件所在目录集合（相对路径，根目录用'.'表示）
        ]
    
    Raises:
        RuntimeError: Git 未安装或命令执行失败
        ValueError: Commit 哈希格式无效
    """
    # === 1. 环境校验 ===
    try:
        subprocess.run(
            ["git", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError("Git 未安装或不在系统 PATH 中，请先安装 Git")
    
    if not (old_commit.strip() and new_commit.strip()):
        raise ValueError("Commit 哈希不能为空")
    
    # === 2. 临时目录管理 ===
    cleanup_needed = False
    working_dir = temp_dir
    if working_dir is None:
        working_dir = tempfile.mkdtemp(prefix="git_diff_")
        cleanup_needed = True
    else:
        os.makedirs(working_dir, exist_ok=True)
    
    try:
        # === 3. 初始化最小化仓库 ===
        subprocess.run(["git", "init", "-q"], cwd=working_dir, check=True, capture_output=True)
        # 避免 Git 警告（非必须但提升稳定性）
        subprocess.run(["git", "config", "user.email", "ci-bot@local"], cwd=working_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "CI Bot"], cwd=working_dir, capture_output=True)
        
        # === 4. 精准获取目标 Commit（核心：--depth=1 + 直接指定 Commit）===
        # 优势：仅下载目标 Commit 及其树对象，避免拉取整个分支历史
        remotes = [("old_remote", old_repo_url, old_commit), ("new_remote", new_repo_url, new_commit)]
        for remote_name, url, commit in remotes:
            subprocess.run(["git", "remote", "add", remote_name, url], cwd=working_dir, check=True, capture_output=True)
            # --filter=blob:none 进一步减少下载（仅元数据，无文件内容），Git 2.19+ 支持
            fetch_cmd = [
                "git", "fetch", "--depth=1", "--filter=blob:none",
                remote_name, commit
            ]
            result = subprocess.run(fetch_cmd, cwd=working_dir, capture_output=True, text=True)
            if result.returncode != 0:
                # 回退方案：部分旧版 Git 不支持 --filter，移除后重试
                if "--filter=blob:none" in result.stderr:
                    fetch_cmd = ["git", "fetch", "--depth=1", remote_name, commit]
                    subprocess.run(fetch_cmd, cwd=working_dir, check=True, capture_output=True)
                else:
                    raise RuntimeError(f"Fetch 失败 ({remote_name}): {result.stderr.strip()}")
        
        # === 5. 获取差异（仅文件路径与状态）===
        diff_result = subprocess.run(
            ["git", "diff", "--name-status", old_commit, new_commit],
            cwd=working_dir,
            check=True,
            capture_output=True,
            text=True
        )
        
        # === 6. 智能解析 diff 输出 ===
        changed_files = []
        for line in diff_result.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            
            status_raw = parts[0].strip()
            main_status = status_raw[0]
            
            # 处理单路径变更 (A, M, D, T...)
            if main_status in {"A", "M", "D", "T"} and len(parts) >= 2:
                path = parts[1].strip().strip('"')
                changed_files.append((main_status, path))
            
            # 处理重命名/复制 (R/C + 相似度 + 旧路径 + 新路径)
            elif main_status in {"R", "C"} and len(parts) >= 3:
                old_path = parts[1].strip().strip('"')
                new_path = parts[2].strip().strip('"')
                # 语义拆分：重命名 = 删除旧路径 + 新增新路径；复制 = 保留旧路径(视为M) + 新增新路径
                changed_files.append(("D" if main_status == "R" else "M", old_path))
                changed_files.append(("A", new_path))
        
        # === 7. 提取变更目录（仅直接父目录，避免冗余）===
        changed_dirs = set()
        for _, path in changed_files:
            dir_path = os.path.dirname(path) or "."  # 根目录文件归为"."
            changed_dirs.add(dir_path)
        
        return changed_files, changed_dirs
    
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.strip() if e.stderr else "Unknown error"
        raise RuntimeError(f"Git 命令执行失败: {stderr_msg}\nCommand: {' '.join(e.cmd)}") from e
    finally:
        # 安全清理临时资源
        if cleanup_needed and not keep_temp and os.path.exists(working_dir):
            try:
                shutil.rmtree(working_dir)
            except Exception as cleanup_err:
                print(f"警告：临时目录清理失败 ({working_dir}): {cleanup_err}", file=sys.stderr)