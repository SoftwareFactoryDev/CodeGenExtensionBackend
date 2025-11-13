import os
import json
import re
import glob

from git import Repo
from copy import deepcopy

from CodeBaseBuild.CParser import CParser
from CodeBaseBuild.prompt import function_sum_template
from CodeBaseBuild.llm_gen import generate_api

import pandas as pd

def repo_parse(repo_path, lib_path, output_path):
    
    c_files = glob.glob(f"{repo_path}/**/*.c", recursive=True)
    h_files = glob.glob(f"{repo_path}/**/*.h", recursive=True)

    c_parser = CParser(lib_path)
    all_functions = []

    for index, c_file in enumerate((c_files + h_files)):
        print(f'processing{index+1}/{len((c_files + h_files))}:{c_file}')
        c_parser.parse_file(c_file)
        for func in c_parser.functions:
            func["file_path"] = os.path.relpath(c_file, repo_path)
        all_functions.extend(deepcopy(c_parser.functions))
    df = pd.DataFrame(all_functions)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    return f'成功建立代码库'

def gen_sum(codebase_path):

    prompt_template = function_sum_template

    codebase = pd.read_csv(codebase_path)

    for index, row in codebase.iterrows():
        
        if (row['summary'] is not None) and (row['summary'] != "Not Generated") and (len(row['summary']) < 300):
            continue
        param = {'name': row['name'], 'file_path': row['file_path'], 'source_code': row['source_code'], 'signature': row['signature']}
        prompt_template.generate_prompt(user_param=param)
        messages = prompt_template.generate_message()
        ite = 0

        while True:
            response = generate_api(messages)
            if not response or len(response.strip())==0:
                sum_data = None
            else:
                m = re.search(r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```", response, re.DOTALL)
                if m:
                    sum_data = json_parse(response)
                else:
                    sum_data = None
            if not sum_data : summary = response 
            elif 'summary' in sum_data.keys(): summary = sum_data['summary']
            else: summary = list(sum_data.values())[-1]
            if summary and len(summary)>10 and len(summary)<300:
                break
            elif summary is None or len(summary) == 0 :
                messages = prompt_template.generate_message()
                messages[1]['content'] += '. Do not outpout empty string.'
            elif ' ' not in summary:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({'role':'assistant', 'content': summary})
                messages.append({'role':'user', 'content': '重新生成摘要, 写成一段话并且遵守CODE_RULES.'})
            elif len(summary) >= 300:
                if len(messages) > 10:
                    messages = messages[:2] + messages[-2:]
                messages.append({'role':'assistant', 'content': summary})
                messages.append({'role':'user', 'content': '将摘要缩减至不超过50字, 不要包含当前函数所在的文件地址.'})
            elif len(summary) <= 10:
                messages[0] = {'role':'assistant', 'content': summary}
                messages[1] = {'role':'user', 'content': '扩展当前的摘要，要超过8个字, 并且遵守CODE_RULES'}
            ite += 1
            if ite > 10:
                break
        print(f'【{index}/{len(codebase)}】【提示词】:{messages} \n 【回复】:{summary}')
        if not summary: summary = "摘要失败."
        row['summary'] = summary.strip()
    codebase.to_csv(codebase_path, index=True, encoding='utf-8')

def sum_embedding(codebase_path):
    codebase = pd.read_csv(codebase_path)
    codebase['sum,_embedding'] = codebase['summary'].apply(lambda x: generate_api([{'role':'user', 'content': f'将摘要{str(x)}转化为向量'}]))

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

def build_code_base(repo_path, lib_path, output_path):
    
    if os.path.exists(output_path) and os.path.isdir(output_path):
        output_path = os.path.join(output_path, f'{os.path.basename(repo_path)}.csv')
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if os.path.exists(output_path):
        print(f'代码库{os.path.basename(repo_path)}已存在，跳过解析步骤。')
    else:
        result = repo_parse(repo_path, lib_path, output_path)
        print(result)
    gen_sum(codebase_path=output_path)
    sum_embedding(codebase_path=output_path)

def get_repository(repo_url, destination='./repos'):
    if not os.path.exists(destination):
        os.makedirs(destination)
    print('Start cloning repository...')
    Repo.clone_from(repo_url, destination)
    print('Repository cloned to', destination)
    return True

def main():

    repo_url = 'git@github.com:lyusupov/SoftRF.git'
    print(get_repository(repo_url, destination='./repos/SoftRF'))


if __name__ == '__main__':
    main()