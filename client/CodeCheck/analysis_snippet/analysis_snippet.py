import os
import subprocess
import tempfile
import plistlib
import json
import shutil

# 脚本所在的绝对目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLANG_BIN = os.path.join(SCRIPT_DIR, "bin", "clang")
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")

# 动态库查找路径 (LD_LIBRARY_PATH)
ENV_VARS = os.environ.copy()
if os.path.exists(LIB_DIR):
    current_ld_path = ENV_VARS.get('LD_LIBRARY_PATH', '')
    ENV_VARS['LD_LIBRARY_PATH'] = f"{LIB_DIR}:{current_ld_path}"


class SnippetAnalyzer:
    def __init__(self):
        self._ensure_executable()

    def _ensure_executable(self):
        """确保 Clang 可执行"""
        if os.path.exists(CLANG_BIN) and not os.access(CLANG_BIN, os.X_OK):
            os.chmod(CLANG_BIN, 0o755)

    def _get_code_snippet(self, code_lines, start_line, end_line):
        """提取缺陷片段"""
        # 单行
        if start_line == end_line:
            idx = start_line - 1
            if 0 <= idx < len(code_lines):
                return code_lines[idx].strip()
        # 多行
        else:
            s_idx = max(0, start_line - 1)
            e_idx = min(len(code_lines), end_line)
            subset = code_lines[s_idx:e_idx]
            return "\n".join([line.strip() for line in subset])
        return ""

    def analyze(self, code_string):
        """接收 C 代码字符串，返回分析结果字符串"""
        if not code_string or not code_string.strip():
            return json.dumps({"error": "Empty code"}, ensure_ascii=False)

        # 脚本所在目录下创建临时文件夹
        temp_dir = tempfile.mkdtemp(prefix='temp_task_', dir=SCRIPT_DIR)
        src_path = os.path.join(temp_dir, "input.c")
        plist_path = os.path.join(temp_dir, "output.plist")

        results = []

        try:
            # 将代码片段写入 input.c
            with open(src_path, 'w', encoding='utf-8') as f:
                f.write(code_string)

            cmd = [
                CLANG_BIN, '--analyze',
                '-Xanalyzer', '-analyzer-output=plist',
                '-Xanalyzer', '-analyzer-checker=GJB8114',
                '-Xanalyzer', '-analyzer-config',
                '-Xanalyzer', 'path-diagnostics-in-system-headers=false',
                '-o', plist_path, src_path
            ]

            proc = subprocess.run(cmd, env=ENV_VARS, capture_output=True, text=True, timeout=60)

            # 解析plist文件
            if os.path.exists(plist_path) and os.path.getsize(plist_path) > 0:
                with open(plist_path, 'rb') as f:
                    try:
                        plist_data = plistlib.load(f)

                        code_lines = code_string.splitlines()

                        for diag in plist_data.get('diagnostics', []):
                            check_name = diag.get('check_name', '')
                            if not check_name.startswith("GJB8114"):
                                continue

                            rule_id = check_name.split('.')[-1]
                            description = diag.get('description', '')
                            description = description.split("所在函数：")[0].strip()

                            location = diag.get('location', {})
                            line = location.get('line', -1)
                            col = location.get('col', -1)

                            start_line = line
                            end_line = line

                            path_items = diag.get('path', [])
                            if path_items:
                                for item in reversed(path_items):
                                    if item.get('ranges'):
                                        current_range = item['ranges'][0]
                                        start_line = current_range[0].get('line', line)
                                        end_line = current_range[1].get('line', line)
                                        break
                            snippet = self._get_code_snippet(code_lines, start_line, end_line)

                            issue = {
                                "rule_id": rule_id,
                                "description": description,
                                "location": f"Line {line}, Col {col}",
                                "violated_code": snippet
                            }
                            results.append(issue)

                    except Exception as e:
                        return json.dumps({"error": f"Plist parse error: {str(e)}"}, ensure_ascii=False)
            else:
                # 语法错误导致编译失败，输出clang打印的报错信息
                if proc.returncode != 0:
                    error_lines = proc.stderr.strip().splitlines()
                    return json.dumps([{"error": "Compilation Failed", "detail": error_lines}], indent=2, ensure_ascii=False)

        finally:
            # 删除该临时文件夹
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

        return json.dumps(results, indent=2, ensure_ascii=False)


if __name__ == "__main__":

    sample_code = r"""
#include <stdio.h>

void bubble_sort(int arr[], int n) {
    for (int i = 0; i < n - 1; i++) {
        for (int j = 0; j < n - i - 1; j++) {
            if (arr[j] > arr[j + 1]) {
                int temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
        }
    }
}

int main() {
    int arr[] = {64, 34, 25, 12, 22, 11, 90};
    int n = sizeof(arr) / sizeof(arr[0]);
    bubble_sort(arr, n);
    return 0;
}
    """

    analyzer = SnippetAnalyzer()
    result_str = analyzer.analyze(sample_code)

    print(result_str)