import json
from function.CodeCheck.analysis_snippet.analysis_snippet import SnippetAnalyzer

def build_in_check(code, support):
    """
    调用内置工具进行代码审查

    Args:
        code (_type_): 拟审查代码
        support (_type_): 支持的规则数组

    Returns:
        List[dict] : 审查结果
    """
    analyzer = SnippetAnalyzer()
    result_str = analyzer.analyze(code_string=code, rules=support)
    if len(result_str.strip()) > 0:
        err_list = json.loads(result_str)
    else:
        err_list = []
    return err_list