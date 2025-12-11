import os
import json
import re
import glob
import shutil
import stat

from git import Repo
from copy import deepcopy
import jieba
import clang.cindex as cl
from concurrent.futures import ThreadPoolExecutor, as_completed

from client.CodeBaseBuild.CParser import CParser
from client.CodeBaseBuild.prompt import function_sum_template
from client.CodeBaseBuild.llm_gen import generate_api

import pandas as pd
import asyncio
import threading


thread_local = threading.local()

def get_parser():
    if not hasattr(thread_local, 'parser'):
        thread_local.parser = CParser()
    return thread_local.parser

async def parse_single_file(args):
    c_file, lib_path, repo_path = args
    loop = asyncio.get_event_loop()

    parser = get_parser()

    functions = await loop.run_in_executor(None, parser.parse_file, c_file)
    
    for func in functions:
        func["file_path"] = os.path.relpath(c_file, repo_path)
    return deepcopy(parser.functions)

async def repo_parse_multy(repo_path, lib_path, output_path, version, max_workers=4):
    if os.path.exists(output_path):
        result = (f'代码库{os.path.basename(repo_path)}_{version}已存在，跳过解析步骤，仅进行数据解析。')
    else:
        c_files = glob.glob(f"{repo_path}/**/*.c", recursive=True)
        h_files = glob.glob(f"{repo_path}/**/*.h", recursive=True)
        all_files = c_files + h_files
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            all_functions = []
            tasks = [(file, lib_path, repo_path) for file in all_files]
            async_tasks = [parse_single_file(task) for task in tasks]
            semaphore = asyncio.Semaphore(max_workers)
            async def process_with_semaphore(task):
                async with semaphore:
                    return await parse_single_file(task)
            results = await asyncio.gather(*[process_with_semaphore(task) for task in tasks], return_exceptions=True)
            
            for file, result in zip(all_files, results):
                if isinstance(result, Exception):
                    print(f'文件 {file} 处理时发生异常: {result}')
                else:
                    all_functions.extend(result)
                    print(f'已处理: {file}, 当前函数数量: {len(all_functions)}')
        
        df = pd.DataFrame(all_functions)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        result = f'代码库{os.path.basename(repo_path)}_{version}解析完成。'
    return result

def repo_parse_single(repo_path, lib_path, output_path, version):
    
    if os.path.exists(output_path):
        result = (f'代码库{os.path.basename(repo_path)}_{version}已存在，跳过解析步骤，仅进行数据解析。')
    else:
        c_files = glob.glob(f"{repo_path}/**/*.c", recursive=True)
        h_files = glob.glob(f"{repo_path}/**/*.h", recursive=True)

        c_parser = CParser()
        all_functions = []

        for index, c_file in enumerate((c_files + h_files)):
            print(f'processing File No{index+1}:{c_file}')
            try:
                c_parser.parse_file(c_file)
                for func in c_parser.functions:
                    func["file_path"] = os.path.relpath(c_file, repo_path)
                all_functions.extend(deepcopy(c_parser.functions))
            except Exception as e:
                print(f'解析文件 {c_file} 时发生异常: {e}')
        df = pd.DataFrame(all_functions)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        result = f'代码库{os.path.basename(repo_path)}_{version}解析完成。'
    return result

def gen_sum_single(codebase_path):

    prompt_template = function_sum_template

    try:
        codebase = pd.read_csv(codebase_path)
    except pd.errors.EmptyDataError as e:
        print(f'读取代码库{os.path.basename(codebase_path)}时发生异常: {e}')
        return f'代码库{os.path.basename(codebase_path)}不包含函数'
    if len(codebase) == 0:
        return f'代码库{os.path.basename(codebase_path)}为空，跳过摘要生成步骤。'

    for index, row in codebase.iterrows():
        print(f'processing Function No.{index+1}:{row["signature"]}')
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
        # print(f'【{index}/{len(codebase)}】【提示词】:{messages} \n 【回复】:{summary}')
        if not summary: summary = "摘要失败."
        row['summary'] = summary.strip()
    codebase.to_csv(codebase_path, index=True, encoding='utf-8')
    return f'成功生成代码库摘要'

def get_prompt_template():
    if not hasattr(thread_local, 'prompt_template'):
        thread_local.prompt_template = function_sum_template
    return thread_local.prompt_template

def process_single_row(args):

    index, row, codebase_path = args
    prompt_template = get_prompt_template()
    
    print(f'processing Function No.{index+1}: {row["signature"]}')
    
    # 检查是否需要生成摘要
    if (row['summary'] is not None) and (row['summary'] != "Not Generated") and (len(row['summary']) < 300):
        return index, row['summary']
    
    param = {
        'name': row['name'],
        'file_path': row['file_path'],
        'source_code': row['source_code'],
        'signature': row['signature']
    }
    
    prompt_template.generate_prompt(user_param=param)
    messages = prompt_template.generate_message()
    ite = 0

    while True:
        response = generate_api(messages)
        if not response or len(response.strip()) == 0:
            sum_data = None
        else:
            m = re.search(r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```", response, re.DOTALL)
            if m:
                sum_data = json_parse(response)
            else:
                sum_data = None
        
        if not sum_data:
            summary = response
        elif 'summary' in sum_data.keys():
            summary = sum_data['summary']
        else:
            summary = list(sum_data.values())[-1]
        
        if summary and len(summary) > 10 and len(summary) < 300:
            break
        elif summary is None or len(summary) == 0:
            messages = prompt_template.generate_message()
            messages[1]['content'] += '. Do not output empty string.'
        elif ' ' not in summary:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({'role': 'assistant', 'content': summary})
            messages.append({'role': 'user', 'content': '重新生成摘要, 写成一段话并且遵守CODE_RULES.'})
        elif len(summary) >= 300:
            if len(messages) > 10:
                messages = messages[:2] + messages[-2:]
            messages.append({'role': 'assistant', 'content': summary})
            messages.append({'role': 'user', 'content': '将摘要缩减至不超过50字, 不要包含当前函数所在的文件地址.'})
        elif len(summary) <= 10:
            messages[0] = {'role': 'assistant', 'content': summary}
            messages[1] = {'role': 'user', 'content': '扩展当前的摘要，要超过8个字, 并且遵守CODE_RULES'}
        
        ite += 1
        if ite > 10:
            break
    
    if not summary:
        summary = "摘要失败."
    
    return index, summary.strip()

async def gen_sum_multy(codebase_path, max_workers=4):
    try:
        codebase = pd.read_csv(codebase_path)
    except pd.errors.EmptyDataError as e:
        print(f'读取代码库{os.path.basename(codebase_path)}时发生异常: {e}')
        return f'代码库{os.path.basename(codebase_path)}不包含函数'
    
    if len(codebase) == 0:
        return f'代码库{os.path.basename(codebase_path)}为空，跳过摘要生成步骤。'
    tasks = [(index, row, codebase_path) for index, row in codebase.iterrows()]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(process_single_row, task): task[0] for task in tasks}
        
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                row_index, summary = future.result()
                codebase.at[row_index, 'summary'] = summary
                print(f'已完成处理: Function No.{row_index+1}')
            except Exception as exc:
                print(f'处理第 {index} 行时发生异常: {exc}')
                codebase.at[index, 'summary'] = "处理失败."

    codebase.to_csv(codebase_path, index=True, encoding='utf-8')
    return f'成功生成代码库摘要'

def sum_embedding(codebase_path):
    try:
        codebase = pd.read_csv(codebase_path)
    except pd.errors.EmptyDataError as e:
        print(f'读取代码库{os.path.basename(codebase_path)}时发生异常: {e}')
        return f'代码库{os.path.basename(codebase_path)}不包含函数'
    codebase['sum_embedding'] = codebase['summary'].apply(lambda x: generate_api([{'role':'user', 'content': f'将摘要{str(x)}转化为向量'}]))
    codebase.to_csv(codebase_path, index=True, encoding='utf-8')
    return f'成功生成摘要向量'

def sum_tokenize(codebase_path, stopword_path=None):
    try:
        codebase = pd.read_csv(codebase_path)
    except pd.errors.EmptyDataError as e:
        print(f'读取代码库{os.path.basename(codebase_path)}时发生异常: {e}')
        return f'代码库{os.path.basename(codebase_path)}不包含函数'
    if len(codebase) == 0:
        return f'代码库{os.path.basename(codebase_path)}为空，跳过摘要分词步骤。'
    if not stopword_path:
        codebase['sum_tokenize'] = codebase['summary'].apply(lambda x: list(jieba.cut_for_search(x)))
    else:
        with open(stopword_path, 'r', encoding='utf-8') as f:
            stopwords = f.read().splitlines()
        codebase['sum_tokenize'] = codebase['summary'].apply(lambda x: list(jieba.cut_for_search(x)))
        codebase['sum_tokenize'] = codebase['summary'].apply(lambda x: [token for token in x if token not in stopwords])
    codebase.to_csv(codebase_path, index=True, encoding='utf-8')
    return f'成功预分词'
    

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


def force_remove_readonly(func, path, excinfo):
    """处理只读文件的删除"""
    os.chmod(path, stat.S_IWRITE)
    func(path)

def get_repository(repo_url, destination='./repos'):
    if not os.path.exists(destination):
        os.makedirs(destination)
    destination = os.path.join(destination, repo_url.split('/')[-1].split('.')[0])
    print(f'开始克隆代码库 {repo_url}')
    
    if os.path.exists(destination):
        rm_repo(destination)
    repo = Repo.clone_from(repo_url, destination)
    version = repo.head.commit.hexsha
    print('代码库克隆到', destination)
    repo.close()
    repo.git.clear_cache()
    return destination, version

def rm_repo(repo_path):
    for root, dirs, files in os.walk(repo_path):  
        for dir in dirs:
            os.chmod(os.path.join(root, dir), stat.S_IRWXU)
        for file in files:
            os.chmod(os.path.join(root, file), stat.S_IRWXU)
    shutil.rmtree(repo_path)

# def create_bm25_retriever(data, init=False):
    
    