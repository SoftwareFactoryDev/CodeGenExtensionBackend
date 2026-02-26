import uuid
import os
import json
import re
import glob
import shutil
import stat
import asyncio
import threading
from threading import Lock

from git import Repo
from copy import deepcopy
import jieba
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from function.CodeBaseBuild.CParser import CParser
from function.CodeBaseBuild.prompt import sum_prompt_lib
from function.CodeBaseBuild.llm_gen import generate_api
from function.CodeBaseBuild.util import asset_in_module
from function.CodeBaseBuild.util import module_in_repo
from function.CodeBaseBuild.prompt import module_sum_template
from function.CodeBaseBuild.prompt import repo_sum_template
from function.CodeBaseBuild.util import json_parse
from app.logger import logger_global


def repo_parse_single(
    repo_path,
    version,
    function_path,
    global_var_path,
    struct_path,
    macro_path,
    info_path,
    repeat_within=None,
    mask_dirs=[],
):
    """
    解析单个代码仓库，提取代码资产并生成代码库信息

    Args:
        repo_path (str): 代码仓库的路径
        codebase_path (str): 存储解析结果的代码库路径
        version (str): 代码仓库的版本号(commit hash)
        asset_path (str) : 存储代码资产的路径
        info_path (str): 存储代码库信息的路径
        repeat_within (dict, optional): 重复检测的配置信息. Defaults to None.
        mask_dirs (list, optional): 需要屏蔽的文件夹列表. Defaults to [].
        add (bool): 是否为增量添加模式，默认为False

    Returns:
        str: 处理结果的描述信息
    """
    # 创建日志记录器的深拷贝，避免影响全局日志记录器
    logger = deepcopy(logger_global)

    # 获取代码仓库名称（从路径中提取）
    repo_name = os.path.basename(repo_path)

    # 检查是否已经存在解析结果
    if (
        os.path.exists(function_path)
        and os.path.exists(info_path)
        and os.path.exists(global_var_path)
        and os.path.exists(struct_path)
        and os.path.exists(macro_path)
    ):
        result = f"代码库{repo_name}(Commit版本：{version})已存在，跳过提取代码资产步骤，仅进行代码库功能描述生成。"
    else:

        # 获取所有C语言源文件和头文件
        # 获取所有.c和.h文件
        c_files = glob.glob(f"{repo_path}/**/*.c", recursive=True)
        h_files = glob.glob(f"{repo_path}/**/*.h", recursive=True)
        all_files = c_files + h_files

        # 过滤mask_dirs：屏蔽指定文件夹路径下的文件
        abs_mask_dirs = []
        for md in mask_dirs:
            abs_md = os.path.abspath(os.path.join(repo_path, md))
            if not abs_md.endswith(os.sep):
                abs_md += os.sep
            abs_mask_dirs.append(abs_md)

        filtered_files = []
        for file_path in all_files:
            abs_file_path = os.path.abspath(file_path)
            if not any(abs_file_path.startswith(abs_md) for abs_md in abs_mask_dirs):
                filtered_files.append(file_path)

        # 若repeat_within存在，进一步筛选仅保留new_changed_files中的文件
        if repeat_within is not None:
            new_changed_files = repeat_within.get("new_changed_files", [])
            new_changed_abs_set = {
                os.path.abspath(os.path.join(repo_path, f)) for f in new_changed_files
            }
            all_files = [
                fp
                for fp in filtered_files
                if os.path.abspath(fp) in new_changed_abs_set
            ]
        else:
            all_files = filtered_files

        # 创建C语言解析器实例
        c_parser = CParser()

        # 初始化存储列表
        function_list = []
        globals_var_list = []
        macro_list = []
        struct_list = []
        module_list = []

        # 遍历所有文件进行解析
        for index, c_file in enumerate(all_files):

            logger.info(f"正在处理代码文件 No{index+1}:{c_file}")

            # 获取文件所属模块（从相对路径中提取目录）
            module = os.path.dirname(os.path.relpath(c_file, repo_path))

            # 记录模块
            if module.strip() == "":
                module = "根模块"
            if module not in module_list:
                module_list.append(module)

            # 获取文件相对路径
            file_path = os.path.relpath(c_file, repo_path)
            # 解析C语言文件
            try:
                c_parser.parse_file(c_file)
                for func in c_parser.functions:
                    func["file_path"] = file_path
                    func["module"] = module
                    func["repo_name"] = repo_name
                function_list.extend(deepcopy(c_parser.functions))
                for stru in c_parser.structs:
                    stru["file_path"] = file_path
                    stru["module"] = module
                    stru["repo_name"] = repo_name
                struct_list.extend(deepcopy(c_parser.globals))
                for global_var in c_parser.globals:
                    global_var["file_path"] = file_path
                    global_var["module"] = module
                    global_var["repo_name"] = repo_name
                globals_var_list.extend(deepcopy(c_parser.globals))
                for macro in c_parser.macros:
                    macro["file_path"] = file_path
                    macro["module"] = module
                    macro["repo_name"] = repo_name
                macro_list.extend(deepcopy(c_parser.macros))
                logger.info(f"完成解析代码文件 No{index+1}:{c_file}")
            except Exception as e:
                logger.error(f"解析文件 {c_file} 时发生异常: {e}")

        # 保存代码库信息
        system_id = str(uuid.uuid1()).replace("-", "")
        info = {
            "id": f"sys_{system_id}",
            "name": repo_name,
            "version": version,
            "description": "",
            "modules": [],
        }
        for module in module_list:
            module_id = str(uuid.uuid1()).replace("-", "")
            info["modules"].append(
                {
                    "id": f"module_{module_id}",
                    "name": module,
                    "description": "",
                    "repo": f"sys_{system_id}",
                }
            )
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=4)

        # 保存代码资产
        df = pd.DataFrame(function_list)
        df["module"] = f"module_{module_id}"
        df["repo"] = f"sys_{system_id}"
        df.to_csv(function_path, index=False, encoding="utf-8-sig")

        df = pd.DataFrame(globals_var_list)
        df["module"] = f"module_{module_id}"
        df["repo"] = f"sys_{system_id}"
        df.to_csv(global_var_path, index=False, encoding="utf-8-sig")

        df = pd.DataFrame(macro_list)
        df["module"] = f"module_{module_id}"
        df["repo"] = f"sys_{system_id}"
        df.to_csv(macro_path, index=False, encoding="utf-8-sig")

        df = pd.DataFrame(struct_list)
        df["module"] = f"module_{module_id}"
        df["repo"] = f"sys_{system_id}"
        df.to_csv(struct_path, index=False, encoding="utf-8-sig")

        result = f"代码库{os.path.basename(repo_path)}(Commit版本：{version})解析完成\n代码库信息：{info_path}\n代码资产：\n{function_path}\n{global_var_path}\n{macro_path}\n{struct_path}"

    return result


def repo_parse_single_multithread(
    repo_path: str,
    version: str,
    function_path: str,
    global_var_path: str,
    struct_path: str,
    macro_path: str,
    info_path: str,
    repeat_within,
    mask_dirs,
    workers: int = 4,
) -> str:
    """
    多线程解析单个C语言代码仓库，提取代码资产并生成结构化信息

    Args:
        repo_path (str): 代码仓库的绝对路径
        version (str): 代码仓库的版本号(commit hash)
        function_path (str): 函数资产CSV输出路径
        global_var_path (str): 全局变量资产CSV输出路径
        struct_path (str): 结构体资产CSV输出路径
        macro_path (str): 宏定义资产CSV输出路径
        info_path (str): 代码库元信息JSON输出路径
        repeat_within (dict, optional): 增量解析配置，含"new_changed_files"字段. Defaults to None.
        mask_dirs (list, optional): 需屏蔽的目录相对路径列表. Defaults to [].
        workers (int, optional): 最大工作线程数(>=1). Defaults to 4.

    Returns:
        str: 处理结果描述信息

    Notes:
        - 线程安全设计：每个线程独立实例化解析器，结果合并由主线程完成
        - 资源冲突规避：无共享可变状态，避免锁竞争
        - 模块ID映射修正：修复原单线程版本中模块ID覆盖错误
        - 日志隔离：每个线程使用logger深拷贝，避免日志交错污染
    """
    # 参数标准化与校验
    if mask_dirs is None:
        mask_dirs = []
    if workers is None or workers < 1:
        workers = max(1, os.cpu_count() or 4)  # 安全回退

    # 主线程日志记录器（仅用于主流程）
    main_logger = deepcopy(logger_global)
    repo_name = os.path.basename(os.path.abspath(repo_path))

    # ========== 步骤1: 检查输出文件是否存在（短路逻辑）==========
    output_paths = [function_path, global_var_path, struct_path, macro_path, info_path]
    if all(os.path.exists(p) for p in output_paths):
        result_msg = (
            f"代码库{repo_name}(Commit版本：{version})解析结果已存在，跳过处理。"
        )
        main_logger.info(result_msg)
        return result_msg

    # ========== 步骤2: 文件发现与过滤 ==========
    c_files = glob.glob(os.path.join(repo_path, "**", "*.c"), recursive=True)
    h_files = glob.glob(os.path.join(repo_path, "**", "*.h"), recursive=True)
    all_files = c_files + h_files

    # 屏蔽目录标准化
    abs_mask_dirs = []
    for md in mask_dirs:
        abs_md = os.path.abspath(os.path.join(repo_path, md))
        if not abs_md.endswith(os.sep):
            abs_md += os.sep
        abs_mask_dirs.append(abs_md)

    # 过滤屏蔽目录
    filtered_files = [
        fp
        for fp in all_files
        if not any(os.path.abspath(fp).startswith(md) for md in abs_mask_dirs)
    ]

    # 增量解析过滤（如启用）
    if repeat_within and "new_changed_files" in repeat_within:
        new_changed_set = {
            os.path.abspath(os.path.join(repo_path, f))
            for f in repeat_within["new_changed_files"]
        }
        filtered_files = [
            fp for fp in filtered_files if os.path.abspath(fp) in new_changed_set
        ]

    if not filtered_files:
        main_logger.warning(
            f"代码库{repo_name}无有效C/H文件待解析（经屏蔽/增量过滤后）"
        )
        filtered_files = []  # 显式置空

    # ========== 步骤3: 多线程解析文件 ==========
    def _parse_single_file(file_abs_path: str):
        """线程安全的单文件解析任务（闭包捕获repo_path, repo_name）"""
        thread_logger = deepcopy(logger_global)  # 线程隔离日志
        try:
            # 计算模块路径与相对路径
            rel_path = os.path.relpath(file_abs_path, repo_path)
            module_dir = os.path.dirname(rel_path)
            module_name = module_dir if module_dir.strip() else "根模块"

            # 初始化解析器（线程私有实例）
            parser = CParser()
            parser.parse_file(file_abs_path)

            # 封装资产并注入元数据
            assets = {
                "functions": [],
                "globals": [],
                "structs": [],
                "macros": [],
                "module": module_name,
                "file_path": rel_path,
            }

            # 处理函数
            for item in parser.functions:
                item_copy = deepcopy(item)
                item_copy.update(
                    {
                        "file_path": rel_path,
                        "module": module_name,
                        "repo_name": repo_name,
                    }
                )
                assets["functions"].append(item_copy)

            # 处理结构体（修正原版错误：原误用globals）
            for item in parser.structs:
                item_copy = deepcopy(item)
                item_copy.update(
                    {
                        "file_path": rel_path,
                        "module": module_name,
                        "repo_name": repo_name,
                    }
                )
                assets["structs"].append(item_copy)

            # 处理全局变量
            for item in parser.globals:
                item_copy = deepcopy(item)
                item_copy.update(
                    {
                        "file_path": rel_path,
                        "module": module_name,
                        "repo_name": repo_name,
                    }
                )
                assets["globals"].append(item_copy)

            # 处理宏
            for item in parser.macros:
                item_copy = deepcopy(item)
                item_copy.update(
                    {
                        "file_path": rel_path,
                        "module": module_name,
                        "repo_name": repo_name,
                    }
                )
                assets["macros"].append(item_copy)

            thread_logger.info(f"✓ 完成解析: {rel_path}")
            return assets
        except Exception as e:
            thread_logger.error(f"✗ 解析失败 {file_abs_path}: {str(e)}", exc_info=True)
            return {
                "functions": [],
                "globals": [],
                "structs": [],
                "macros": [],
                "module": "",
                "file_path": "",
            }

    # 执行并发解析
    all_results = []
    if filtered_files:
        actual_workers = min(workers, len(filtered_files))
        main_logger.info(
            f"启动线程池 (workers={actual_workers}) 处理 {len(filtered_files)} 个文件"
        )

        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            # 提交任务并保留提交顺序（用于模块去重顺序）
            future_to_file = {
                executor.submit(_parse_single_file, fp): fp for fp in filtered_files
            }

            for future in as_completed(future_to_file):
                try:
                    result = future.result(timeout=300)  # 单文件超时保护
                    if result["module"]:  # 仅收集有效结果
                        all_results.append(result)
                except Exception as e:
                    fp = future_to_file[future]
                    main_logger.error(f"任务异常 {fp}: {str(e)}")

    # ========== 步骤4: 合并结果与构建模块列表（保留首次出现顺序）==========
    function_list, global_var_list, struct_list, macro_list = [], [], [], []
    module_list, seen_modules = [], set()

    for res in all_results:
        function_list.extend(res["functions"])
        global_var_list.extend(res["globals"])
        struct_list.extend(res["structs"])
        macro_list.extend(res["macros"])

        if res["module"] and res["module"] not in seen_modules:
            seen_modules.add(res["module"])
            module_list.append(res["module"])

    # ========== 步骤5: 生成仓库元信息与ID映射 ==========
    sys_uuid = str(uuid.uuid1()).replace("-", "")
    system_id = f"sys_{sys_uuid}"

    info = {
        "id": system_id,
        "name": repo_name,
        "version": version,
        "description": "",
        "modules": [],
    }

    module_id_map = {}  # 模块名 -> 模块ID映射（用于资产关联）
    for mod_name in module_list:
        mod_uuid = str(uuid.uuid1()).replace("-", "")
        mod_id = f"module_{mod_uuid}"
        info["modules"].append(
            {"id": mod_id, "name": mod_name, "description": "", "repo": system_id}
        )
        module_id_map[mod_name] = mod_id

    # 保存元信息
    os.makedirs(os.path.dirname(info_path), exist_ok=True)
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=4)

    # ========== 步骤6: 修正资产中的模块/仓库引用（关键修复）==========
    def _update_asset_refs(asset_list, mod_map, sys_id):
        """将资产中的module名替换为模块ID，repo_name替换为系统ID"""
        updated = []
        for asset in asset_list:
            # 保留原始repo_name字段（兼容性），新增标准化repo字段
            asset = deepcopy(asset)
            asset["repo"] = sys_id
            asset["module"] = mod_map.get(
                asset.get("module", ""), asset.get("module", "")
            )
            updated.append(asset)
        return updated

    function_list = _update_asset_refs(function_list, module_id_map, system_id)
    global_var_list = _update_asset_refs(global_var_list, module_id_map, system_id)
    struct_list = _update_asset_refs(struct_list, module_id_map, system_id)
    macro_list = _update_asset_refs(macro_list, module_id_map, system_id)

    # ========== 步骤7: 持久化代码资产 ==========
    def _save_assets(asset_list, output_path):
        """安全保存资产CSV（空列表生成空文件）"""
        df = pd.DataFrame(asset_list) if asset_list else pd.DataFrame()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")

    _save_assets(function_list, function_path)
    _save_assets(global_var_list, global_var_path)
    _save_assets(struct_list, struct_path)
    _save_assets(macro_list, macro_path)

    # ========== 步骤8: 生成结果摘要 ==========
    asset_count = (
        f"函数: {len(function_list)}, 全局变量: {len(global_var_list)}, "
        f"结构体: {len(struct_list)}, 宏: {len(macro_list)}"
    )
    result_msg = (
        f"✓ 代码库'{repo_name}'(版本: {version})解析完成\n"
        f"  模块数: {len(module_list)} | 资产统计: {asset_count}\n"
        f"  元信息: {info_path}\n"
        f"  资产路径:\n    - {function_path}\n    - {global_var_path}\n"
        f"    - {struct_path}\n    - {macro_path}"
    )
    main_logger.info(result_msg)
    return result_msg


def gen_module_sum_multy(
    function_path,
    global_var_path,
    macro_path,
    struct_path,
    info_path,
    target_module=None,
    host="http://10.13.1.102:8021/v1",
    model="deepseek-ai/DeepSeek-R1",
    key="103",
    workers=None,
):
    """
    生成模块级代码资产功能描述（多线程版本）

    Args:
        function_path: 函数定义CSV路径
        global_var_path: 全局变量CSV路径
        macro_path: 宏定义CSV路径
        struct_path: 结构体CSV路径
        info_path: 仓库信息JSON路径
        target_module: 目标模块名称（可选）
        host: API服务地址
        model: 使用的AI模型
        key: API密钥
        workers: 最大工作线程数（None时自动设置）

    Returns:
        str: 执行结果描述
    """
    logger = deepcopy(logger_global)
    write_lock = Lock()  # 文件写入锁

    try:
        # 1. 读取基础数据（主线程执行，避免文件竞争）
        with open(info_path, "r", encoding="utf-8") as f:
            repo_info = json.load(f)

        function_list = pd.read_csv(function_path)
        global_var_list = pd.read_csv(global_var_path)
        macro_list = pd.read_csv(macro_path)
        struct_list = pd.read_csv(struct_path)
        module_list = repo_info.get("modules", [])
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(function_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(function_path)}不包含函数"
    except Exception as e:
        logger.error(f"初始化失败: {str(e)}")
        return f"初始化失败: {str(e)}"

    # 2. 预处理模块列表
    if len(function_list) == 0:
        return f"代码库{os.path.basename(function_path)}为空，跳过功能描述生成步骤。"

    if target_module and not any(d.get("name") == target_module for d in module_list):
        module_list.append({"name": target_module, "description": ""})

    # 3. 筛选需要处理的模块
    filtered_modules = []
    for module in module_list:
        if not target_module:
            filtered_modules.append(module)
            continue

        # 保留目标模块（精确匹配或包含关系）
        if target_module in module["name"] or module["name"] in target_module:
            filtered_modules.append(module)

    if not filtered_modules:
        return f"未找到匹配目标模块 '{target_module}' 的有效模块"

    # 4. 设置工作线程数
    max_workers = workers or min(32, (os.cpu_count() or 1) * 4)
    max_workers = max(
        1, min(max_workers, len(filtered_modules))
    )  # 确保至少1线程且不超过模块数

    logger.info(
        f"启动多线程处理，共 {len(filtered_modules)} 个模块，使用 {max_workers} 个工作线程"
    )

    # 5. 定义模块处理函数（线程安全）
    def process_module(module):
        """处理单个模块的线程安全函数"""
        try:
            # 创建独立数据副本（避免线程间数据污染）
            func_df = deepcopy(function_list)
            global_df = deepcopy(global_var_list)
            macro_df = deepcopy(macro_list)
            struct_df = deepcopy(struct_list)

            # 筛选当前模块资产
            masks = {
                "func": func_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
                "global": global_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
                "macro": macro_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
                "struct": struct_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
            }

            asset_info = asset_in_module(
                function_list=func_df[masks["func"]],
                global_var_list=global_df[masks["global"]],
                macro_list=macro_df[masks["macro"]],
                struct_list=struct_df[masks["struct"]],
            )

            # 生成提示
            prompt_template = deepcopy(module_sum_template)
            prompt_template.generate_prompt(
                user_param={"path": module["name"], "assets": asset_info}
            )
            messages = prompt_template.generate_message()

            # 重试逻辑
            description = ""
            for ite in range(11):  # 最多重试10次
                response = generate_api(messages, host=host, model=model, key=key)
                sum_data = json_parse(response) if response else None

                # 解析响应
                if not sum_data:
                    description = response or ""
                elif "description" in sum_data:
                    description = sum_data["description"]
                else:
                    description = list(sum_data.values())[-1] if sum_data else ""

                # 验证描述质量
                desc_len = len(description.strip())
                if 10 < desc_len < 300 and " " in description:
                    break

                # 优化提示
                if not description or desc_len == 0:
                    messages[1]["content"] += " 不要输出空的功能描述."
                elif " " not in description:
                    messages = messages[-2:] if len(messages) > 10 else messages
                    messages.extend(
                        [
                            {"role": "assistant", "content": description},
                            {
                                "role": "user",
                                "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                            },
                        ]
                    )
                elif desc_len >= 300:
                    messages = messages[-2:] if len(messages) > 10 else messages
                    messages.extend(
                        [
                            {"role": "assistant", "content": description},
                            {"role": "user", "content": "将功能描述缩减至不超过50字."},
                        ]
                    )
                elif desc_len <= 10:
                    messages = [
                        {"role": "assistant", "content": description},
                        {
                            "role": "user",
                            "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                        },
                    ]
            else:
                description = "功能描述生成失败（超过最大重试次数）"

            # 返回结果
            return {
                "name": module["name"],
                "description": description.strip() or "功能描述失败",
            }

        except Exception as e:
            logger.error(f"模块 '{module['name']}' 处理异常: {str(e)}", exc_info=True)
            return {"name": module["name"], "description": f"处理异常: {str(e)}"}

    # 6. 并发处理模块
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_module = {
            executor.submit(process_module, module): module["name"]
            for module in filtered_modules
        }

        for future in as_completed(future_to_module):
            module_name = future_to_module[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(
                    f"完成模块: {module_name} -> {result['description'][:30]}..."
                )
            except Exception as e:
                logger.error(f"模块 '{module_name}' 任务异常: {str(e)}")
                results.append(
                    {"name": module_name, "description": f"任务异常: {str(e)}"}
                )

    # 7. 更新仓库信息（主线程安全写入）
    module_dict = {m["name"]: m for m in module_list}
    for res in results:
        if res["name"] in module_dict:
            module_dict[res["name"]]["description"] = res["description"]
        else:
            module_dict[res["name"]] = {
                "name": res["name"],
                "description": res["description"],
            }

    repo_info["modules"] = list(module_dict.values())

    # 8. 安全写入结果文件
    try:
        with write_lock:
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(repo_info, f, ensure_ascii=False, indent=4)
        return f"成功生成 {len(results)} 个模块的功能描述，结果已保存至 {os.path.basename(info_path)}"
    except Exception as e:
        logger.error(f"保存结果失败: {str(e)}")
        return f"处理完成但保存失败: {str(e)}"

def gen_element_sum_single(
    asset_path,
    type,
    host="http://10.13.1.102:8021/v1",
    model="deepseek-ai/DeepSeek-R1",
    key="103",
):
    logger = deepcopy(logger_global)
    prompt_template = deepcopy(sum_prompt_lib[type])

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
            (row["description"] is not None)
            and (row["description"] != "功能描述失败")
            and (row["description"] != "Not Generated")
            and (len(row["description"]) < 300)
        ):
            continue
        param_list = prompt_template.user_prompt_template.input_variables
        param = {k: row[k] for k in param_list}
        prompt_template.generate_prompt(user_param=param)
        messages = prompt_template.generate_message()
        ite = 0

        while True:
            response = generate_api(messages, host=host, model=model, key=key)
            if not response or len(response.strip()) == 0:
                sum_data = None
            else:
                sum_data = json_parse(response)
            if not sum_data:
                description = response
            elif "description" in sum_data.keys():
                description = sum_data["description"]
            else:
                description = list(sum_data.values())[-1]
            if description and len(description) > 10 and len(description) < 300:
                break
            elif description is None or len(description) == 0:
                messages = prompt_template.generate_message()
                messages[1]["content"] += ". Do not outpout empty string."
            elif " " not in description:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": description})
                messages.append(
                    {
                        "role": "user",
                        "content": "重新生成功能描述, 写成一段话并且遵守相应规则.",
                    }
                )
            elif len(description) >= 300:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": description})
                messages.append(
                    {
                        "role": "user",
                        "content": "将功能描述缩减至不超过20字, 不要包含当前函数所在的文件地址.",
                    }
                )
            elif len(description) <= 10:
                messages[0] = {"role": "assistant", "content": description}
                messages[1] = {
                    "role": "user",
                    "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                }
            ite += 1
            if ite > 5:
                break
        if not description:
            description = "功能描述失败."
        row["description"] = description.strip()
    codebase.to_csv(asset_path, index=False, encoding="utf-8")
    return f"成功生成{type}类资产功能描述"

def gen_element_sum_parallel(
    asset_path: str,
    type: str,
    host: str = "http://10.13.1.102:8021/v1",
    model: str = "deepseek-ai/DeepSeek-R1",
    key: str = "103",
    workers: int = 4,  # 新增workers参数，默认4线程
) -> str:
    """
    多线程版本的资产功能描述生成器

    Args:
        asset_path: 资产CSV文件路径
        type: 资产类型
        host: API服务地址
        model: 使用的模型名称
        key: API密钥
        workers: 最大工作线程数 (默认4)

    Returns:
        str: 处理结果摘要
    """
    # 输入验证
    if not os.path.exists(asset_path):
        return f"错误: 文件不存在 - {asset_path}"
    if workers < 1:
        workers = 1
    # 初始化线程安全组件
    file_lock = threading.Lock()  # 文件写入锁
    progress_lock = threading.Lock()  # 进度计数锁
    processed_count = 0  # 已处理函数计数
    total_functions = 0  # 总函数数
    try:
        # 读取数据 (主线程操作，避免多线程文件读取冲突)
        codebase = pd.read_csv(asset_path)
    except pd.errors.EmptyDataError as e:
        logger = deepcopy(logger_global)
        logger.error(f"读取代码库{os.path.basename(asset_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(asset_path)}不包含函数"
    if len(codebase) == 0:
        return f"代码库{os.path.basename(asset_path)}为空，跳过功能描述生成步骤。"
    # 预计算需要处理的行
    rows_to_process = []
    for idx, row in codebase.iterrows():
        if not (
            (row["description"] is not None)
            and (row["description"] != "功能描述失败")
            and (row["description"] != "Not Generated")
            and (len(str(row["description"])) < 300)
        ):
            rows_to_process.append((idx, row))
    total_functions = len(rows_to_process)
    if total_functions == 0:
        return f"代码库{os.path.basename(asset_path)}中所有函数已有有效描述，无需处理。"
    logger_global.info(
        f"开始处理 {os.path.basename(asset_path)}: 共 {total_functions} 个函数需要生成描述"
    )

    def process_single_row(row_data):
        """处理单行数据的线程任务函数"""
        nonlocal processed_count
        row_idx, row = row_data
        # 创建线程独立的logger和prompt模板
        thread_logger = deepcopy(logger_global)
        thread_prompt = deepcopy(sum_prompt_lib[type])
        thread_logger.info(
            f'线程{threading.get_ident()}处理 Function No.{row_idx+1}: {row["signature"]}'
        )
        param_list = thread_prompt.user_prompt_template.input_variables
        param = {k: row[k] for k in param_list}
        thread_prompt.generate_prompt(user_param=param)
        messages = thread_prompt.generate_message()
        ite = 0
        description = None
        # 重试逻辑
        while ite <= 5:
            try:
                response = generate_api(messages, host=host, model=model, key=key)
                if not response or len(response.strip()) == 0:
                    sum_data = None
                else:
                    sum_data = json_parse(response)

                if not sum_data:
                    description = response
                elif "description" in sum_data:
                    description = sum_data["description"]
                else:
                    description = list(sum_data.values())[-1]
                # 验证结果
                desc_str = str(description).strip() if description else ""
                if 10 < len(desc_str) < 300:
                    break
                # 重试策略
                if not desc_str:
                    messages = thread_prompt.generate_message()
                    messages[1]["content"] += ". Do not output empty string."
                elif " " not in desc_str:
                    if len(messages) > 10:
                        messages = messages[:2] + messages[-2:]
                    messages.append({"role": "assistant", "content": desc_str})
                    messages.append(
                        {
                            "role": "user",
                            "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                        }
                    )
                elif len(desc_str) >= 300:
                    if len(messages) > 10:
                        messages = messages[:2] + messages[-2:]
                    messages.append({"role": "assistant", "content": desc_str})
                    messages.append(
                        {
                            "role": "user",
                            "content": "将功能描述缩减至不超过20字, 不要包含当前函数所在的文件地址.",
                        }
                    )
                elif len(desc_str) <= 10:
                    messages[0] = {"role": "assistant", "content": desc_str}
                    messages[1] = {
                        "role": "user",
                        "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                    }
                ite += 1
            except Exception as e:
                thread_logger.error(f"处理行 {row_idx} 时出错: {str(e)}")
                ite += 1
        # 设置最终描述
        final_desc = (
            description.strip()
            if description and description.strip()
            else "功能描述失败."
        )
        # 线程安全地更新进度
        with progress_lock:
            nonlocal processed_count
            processed_count += 1
            progress = processed_count / total_functions * 100
            thread_logger.info(
                f"进度: {progress:.1f}% ({processed_count}/{total_functions}) - {row['signature']}"
            )

        return row_idx, final_desc

    # 创建线程池并提交任务
    max_workers = min(workers, total_functions)
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_idx = {
            executor.submit(process_single_row, row_data): row_idx
            for row_idx, row_data in enumerate(rows_to_process)
        }
        # 收集结果
        for future in as_completed(future_to_idx):
            row_idx = future_to_idx[future]
            try:
                orig_idx, description = future.result()
                results[orig_idx] = description
            except Exception as e:
                logger_global.error(f"行处理任务失败 (索引 {row_idx}): {str(e)}")
    # 应用结果到DataFrame (主线程操作)
    for orig_idx, desc in results.items():
        codebase.at[orig_idx, "description"] = desc
    # 线程安全的文件写入
    with file_lock:
        codebase.to_csv(asset_path, index=False, encoding="utf-8")
    success_count = sum(1 for desc in results.values() if desc != "功能描述失败.")
    return (
        f"成功生成{type}类资产功能描述: "
        f"{success_count}/{total_functions} 个函数成功, "
        f"{total_functions - success_count} 个失败"
    )

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

def gen_module_sum_single(
    function_path,
    global_var_path,
    macro_path,
    struct_path,
    info_path,
    target_module=None,
    host="http://10.13.1.102:8021/v1",
    model="deepseek-ai/DeepSeek-R1",
    key="103",
):
    logger = deepcopy(logger_global)

    try:
        with open(info_path, "r", encoding="utf-8") as f:
            repo_info = json.load(f)
        function_list = pd.read_csv(function_path)
        global_var_list = pd.read_csv(global_var_path)
        macro_list = pd.read_csv(macro_path)
        struct_list = pd.read_csv(struct_path)
        module_list = repo_info.get("modules", [])
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(function_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(function_path)}不包含函数"
    if len(function_list) == 0:
        return f"代码库{os.path.basename(function_path)}为空，跳过功能描述生成步骤。"

    if target_module and not (target_module in [d.get("name") for d in module_list]):
        module_list.append({"name": target_module, "description": ""})

    prompt_template = deepcopy(module_sum_template)
    module_sum_list = []
    raw_function_list = deepcopy(function_list)
    raw_macro_list = deepcopy(macro_list)
    raw_global_var_list = deepcopy(global_var_list)
    raw_struct_list = deepcopy(struct_list)
    for module in module_list:
        function_list = deepcopy(raw_function_list)
        raw_macro_list = deepcopy(raw_macro_list)
        global_var_list = deepcopy(raw_global_var_list)
        struct_list = deepcopy(raw_struct_list)
        if target_module:
            a = not module["name"] in target_module
            b = not target_module in module["name"]
            if a and b:
                continue
        function_mask = function_list["module"].str.contains(
            str(module["name"]), na=False, regex=False
        )
        global_var_mask = global_var_list["module"].str.contains(
            str(module["name"]), na=False, regex=False
        )
        macro_mask = macro_list["module"].str.contains(
            str(module["name"]), na=False, regex=False
        )
        struct_mask = struct_list["module"].str.contains(
            str(module["name"]), na=False, regex=False
        )
        match_function = function_list[function_mask]
        match_global_var = global_var_list[global_var_mask]
        match_macro = macro_list[macro_mask]
        match_struct = struct_list[struct_mask]
        asset_info = asset_in_module(
            function_list=function_list,
            global_var_list=match_global_var,
            macro_list=match_macro,
            struct_list=match_struct,
        )
        user_param = {"path": module["name"], "assets": asset_info}
        prompt_template.generate_prompt(user_param=user_param)
        messages = prompt_template.generate_message()

        ite = 0
        while True:
            response = generate_api(messages, host=host, model=model, key=key)
            if not response or len(response.strip()) == 0:
                sum_data = None
            else:
                sum_data = json_parse(response)
            if not sum_data:
                description = response
            elif "description" in sum_data.keys():
                description = sum_data["description"]
            else:
                description = list(sum_data.values())[-1]
            if description and len(description) > 10 and len(description) < 300:
                break
            elif description is None or len(description) == 0:
                messages = prompt_template.generate_message()
                messages[1]["content"] += " 不要输出空的功能描述."
            elif " " not in description:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": description})
                messages.append(
                    {
                        "role": "user",
                        "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                    }
                )
            elif len(description) >= 300:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({"role": "assistant", "content": description})
                messages.append(
                    {
                        "role": "user",
                        "content": "将功能描述缩减至不超过50字.",
                    }
                )
            elif len(description) <= 10:
                messages[0] = {"role": "assistant", "content": description}
                messages[1] = {
                    "role": "user",
                    "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                }
            ite += 1
            if ite > 10:
                break
        if not description:
            description = "功能描述失败."
        module["description"] = description.strip()
        module_sum_list.append(deepcopy(module))
    repo_info["modules"] = module_sum_list
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(repo_info, f, ensure_ascii=False, indent=4)
    return f"成功生成模块级代码资产功能描述"

def gen_module_sum_parallel(
    function_path,
    global_var_path,
    macro_path,
    struct_path,
    info_path,
    target_module=None,
    host="http://10.13.1.102:8021/v1",
    model="deepseek-ai/DeepSeek-R1",
    key="103",
    workers=None,
):
    """
    生成模块级代码资产功能描述（多线程版本）

    Args:
        function_path: 函数定义CSV路径
        global_var_path: 全局变量CSV路径
        macro_path: 宏定义CSV路径
        struct_path: 结构体CSV路径
        info_path: 仓库信息JSON路径
        target_module: 目标模块名称（可选）
        host: API服务地址
        model: 使用的AI模型
        key: API密钥
        workers: 最大工作线程数（None时自动设置）

    Returns:
        str: 执行结果描述
    """
    logger = deepcopy(logger_global)
    write_lock = Lock()  # 文件写入锁

    try:
        # 1. 读取基础数据（主线程执行，避免文件竞争）
        with open(info_path, "r", encoding="utf-8") as f:
            repo_info = json.load(f)

        function_list = pd.read_csv(function_path)
        global_var_list = pd.read_csv(global_var_path)
        macro_list = pd.read_csv(macro_path)
        struct_list = pd.read_csv(struct_path)
        module_list = repo_info.get("modules", [])
    except pd.errors.EmptyDataError as e:
        logger.error(f"读取代码库{os.path.basename(function_path)}时发生异常: {e}")
        return f"代码库{os.path.basename(function_path)}不包含函数"
    except Exception as e:
        logger.error(f"初始化失败: {str(e)}")
        return f"初始化失败: {str(e)}"

    # 2. 预处理模块列表
    if len(function_list) == 0:
        return f"代码库{os.path.basename(function_path)}为空，跳过功能描述生成步骤。"

    if target_module and not any(d.get("name") == target_module for d in module_list):
        module_list.append({"name": target_module, "description": ""})

    # 3. 筛选需要处理的模块
    filtered_modules = []
    for module in module_list:
        if not target_module:
            filtered_modules.append(module)
            continue

        # 保留目标模块（精确匹配或包含关系）
        if target_module in module["name"] or module["name"] in target_module:
            filtered_modules.append(module)

    if not filtered_modules:
        return f"未找到匹配目标模块 '{target_module}' 的有效模块"

    # 4. 设置工作线程数
    max_workers = workers or min(32, (os.cpu_count() or 1) * 4)
    max_workers = max(
        1, min(max_workers, len(filtered_modules))
    )  # 确保至少1线程且不超过模块数

    logger.info(
        f"启动多线程处理，共 {len(filtered_modules)} 个模块，使用 {max_workers} 个工作线程"
    )

    # 5. 定义模块处理函数（线程安全）
    def process_module(module):
        """处理单个模块的线程安全函数"""
        try:
            # 创建独立数据副本（避免线程间数据污染）
            func_df = deepcopy(function_list)
            global_df = deepcopy(global_var_list)
            macro_df = deepcopy(macro_list)
            struct_df = deepcopy(struct_list)

            # 筛选当前模块资产
            masks = {
                "func": func_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
                "global": global_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
                "macro": macro_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
                "struct": struct_df["module"].str.contains(
                    str(module["name"]), na=False, regex=False
                ),
            }

            asset_info = asset_in_module(
                function_list=func_df[masks["func"]],
                global_var_list=global_df[masks["global"]],
                macro_list=macro_df[masks["macro"]],
                struct_list=struct_df[masks["struct"]],
            )

            # 生成提示
            prompt_template = deepcopy(module_sum_template)
            prompt_template.generate_prompt(
                user_param={"path": module["name"], "assets": asset_info}
            )
            messages = prompt_template.generate_message()

            # 重试逻辑
            description = ""
            for ite in range(5):  # 最多重试10次
                response = generate_api(messages, host=host, model=model, key=key)
                sum_data = json_parse(response) if response else None

                # 解析响应
                if not sum_data:
                    description = response or ""
                elif "description" in sum_data:
                    description = sum_data["description"]
                else:
                    description = list(sum_data.values())[-1] if sum_data else ""

                # 验证描述质量
                desc_len = len(description.strip())
                if 10 < desc_len < 300 and " " in description:
                    break

                # 优化提示
                if not description or desc_len == 0:
                    messages[1]["content"] += " 不要输出空的功能描述."
                elif " " not in description:
                    messages = messages[-2:] if len(messages) > 10 else messages
                    messages.extend(
                        [
                            {"role": "assistant", "content": description},
                            {
                                "role": "user",
                                "content": "重新生成功能描述, 写成一段话并且遵守CODE_RULES.",
                            },
                        ]
                    )
                elif desc_len >= 300:
                    messages = messages[-2:] if len(messages) > 10 else messages
                    messages.extend(
                        [
                            {"role": "assistant", "content": description},
                            {"role": "user", "content": "将功能描述缩减至不超过50字."},
                        ]
                    )
                elif desc_len <= 10:
                    messages = [
                        {"role": "assistant", "content": description},
                        {
                            "role": "user",
                            "content": "扩展当前的功能描述，要超过8个字, 并且遵守CODE_RULES",
                        },
                    ]
            else:
                description = "功能描述生成失败（超过最大重试次数）"

            # 返回结果
            return {
                "name": module["name"],
                "description": description.strip() or "功能描述失败",
            }

        except Exception as e:
            logger.error(f"模块 '{module['name']}' 处理异常: {str(e)}", exc_info=True)
            return {"name": module["name"], "description": f"处理异常: {str(e)}"}

    # 6. 并发处理模块
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_module = {
            executor.submit(process_module, module): module["name"]
            for module in filtered_modules
        }

        for future in as_completed(future_to_module):
            module_name = future_to_module[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(
                    f"完成模块: {module_name} -> {result['description'][:30]}..."
                )
            except Exception as e:
                logger.error(f"模块 '{module_name}' 任务异常: {str(e)}")
                results.append(
                    {"name": module_name, "description": f"任务异常: {str(e)}"}
                )

    # 7. 更新仓库信息（主线程安全写入）
    module_dict = {m["name"]: m for m in module_list}
    for res in results:
        if res["name"] in module_dict:
            module_dict[res["name"]]["description"] = res["description"]
        else:
            module_dict[res["name"]] = {
                "name": res["name"],
                "description": res["description"],
            }

    repo_info["modules"] = list(module_dict.values())

    # 8. 安全写入结果文件
    try:
        with write_lock:
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(repo_info, f, ensure_ascii=False, indent=4)
        return f"成功生成 {len(results)} 个模块的功能描述，结果已保存至 {os.path.basename(info_path)}"
    except Exception as e:
        logger.error(f"保存结果失败: {str(e)}")
        return f"处理完成但保存失败: {str(e)}"

def gen_repo_sum_single(
    info_path,
    host="http://10.13.1.102:8021/v1",
    model="deepseek-ai/DeepSeek-R1",
    key="103",
):

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
        response = generate_api(messages, host=host, model=model, key=key)
        if not response or len(response.strip()) == 0:
            sum_data = None
        else:
            sum_data = json_parse(response)
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
