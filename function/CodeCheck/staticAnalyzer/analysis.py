import os
import subprocess
import tempfile
import json
import re
import argparse


script_dir = os.path.dirname(os.path.abspath(__file__))
clang_exe = os.path.join(script_dir, "bin", "clang.exe")


def parse_clang_output(stderr_output, target_file_path, start_line, end_line):
    """
    解析 Clang 的 stderr 输出，并进行格式化和过滤
    """
    errors = []
    pattern = re.compile(r'(.*?):(\d+):(\d+): warning: (.+?) \[(.+?)\]')

    abs_target_path = os.path.abspath(target_file_path)
    lines = stderr_output.splitlines()
    for line_content in lines:
        match = pattern.search(line_content)
        if match:
            file_path = match.group(1)
            line_num = int(match.group(2))
            col_num = int(match.group(3))
            raw_msg = match.group(4)
            checker_name = match.group(5)

            # 过滤非GJB8114规则集的缺陷
            if not checker_name.startswith("GJB8114"):
                continue

            # 过滤头文件报错
            if os.path.abspath(file_path) != abs_target_path:
                continue

            # 起始行-终止行的范围过滤
            if not (start_line <= line_num <= end_line):
                continue

            clean_msg = raw_msg.split(" 所在函数：")[0]

            clean_checker = checker_name.replace("GJB8114.", "").replace("_", "-")
            desp_str = f"{clean_checker} {clean_msg}"

            errors.append({
                "desp": desp_str,
                "line": str(line_num),
                "col": str(col_num)
            })

    return errors


def run_analysis(project_dir, target_file, start_line, end_line, rules_str=None):
    # 扫描头文件路径
    include_paths = set()
    for root, dirs, files in os.walk(project_dir):
        clean_path = root.replace(os.sep, '/')
        include_paths.add(f"-I{clean_path}")

    # 创建临时 .rsp 文件
    rsp_file_path = ""
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.rsp', encoding='utf-8') as rsp:
            rsp_file_path = rsp.name
            rsp.write("\n".join(include_paths))

        cmd = [
            clang_exe,  # 使用本地 bin 下的 clang
            "-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH",
            "--analyze",
        ]

        # 只启动目标规则
        if rules_str and rules_str.strip():
            rule_list = rules_str.split(',')
            for rule in rule_list:
                clean_rule = rule.strip()
                if clean_rule:
                    cmd.extend(["-Xanalyzer", f"-analyzer-checker=GJB8114.{clean_rule}"])
        else:
            # 如果没传规则，默认开启 GJB8114 下的所有规则
            cmd.extend(["-Xanalyzer", "-analyzer-checker=GJB8114"])

        cmd.extend([
            "-Wno-macro-redefined",
            "-Wno-builtin-macro-redefined",
            f"@{rsp_file_path}",
            "-o", "NUL",
            target_file
        ])

        # 执行命令并捕获输出
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # 解析输出
        parsed_errors = parse_clang_output(result.stderr, target_file, start_line, end_line)

        if not parsed_errors:
            final_output = {"type": "right","err": []}
        else:
            final_output = {
                "type": "semantic",
                "err": parsed_errors
            }

        return final_output

    except Exception as e:
        err_json = {
            "type": "semantic",
            "err": [{"desp": f"Script Error: {str(e)}", "line": "0", "col": "0"}]
        }
        return err_json

    finally:
        if os.path.exists(rsp_file_path):
            os.remove(rsp_file_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GJB8114 Clang Static Analysis Wrapper")

    # 定义参数
    parser.add_argument("project_dir", help="项目根目录路径")
    parser.add_argument("target_file", help="待测文件路径")
    parser.add_argument("start_line", type=int, help="起始行号")
    parser.add_argument("end_line", type=int, help="终止行号")
    parser.add_argument("--rules", help="逗号分隔的规则列表", default="")

    args = parser.parse_args()

    run_analysis(
        args.project_dir,
        args.target_file,
        args.start_line,
        args.end_line,
        args.rules
    )