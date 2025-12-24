import re
import json 

def history_content(history):
    content = ''
    for record in history[-3:]:
        content += f"* {record['role']} : {record['message'].split('=============')[0]}\n"
    return content

def req_list_content(req_list):
    content = ''
    for req in req_list:
        content += f"* {req['ID']} : {req['Content']}\n"
    return content

def code_parse(string):

    # 使用正则表达式匹配代码块，同时支持```c和```C
    pattern = r'```[cC](.*?)```'
    matches = re.findall(pattern, string, re.DOTALL)
    
    result = ''
    for i in matches:
        result += f'{i}\n'
    return result

def asset_content(asset_list):
    asset_info = ''
    for index,asset in enumerate(asset_list):
        asset_info += f'{index+1}. 资产来源：{asset.name} 所属模块：{asset.module}  资产概述:{asset.description}  资产源代码：```c{asset.source_code}```\n'
    
    return asset_info

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

def c_parse(content):

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