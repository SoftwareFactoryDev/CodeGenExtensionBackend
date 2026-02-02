import json
from function.CodeCheck.staticAnalyzer.analysis import run_analysis


def build_in_check(support, dir, file, start, end):
    err_info = run_analysis(project_dir = dir, target_file = file, start_line = start,end_line =  end, rules_str = support)
    return err_info['err']
