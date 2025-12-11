import re

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
    
    return matches