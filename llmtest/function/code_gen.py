from copy import deepcopy
from datetime import datetime

from openai import APITimeoutError

from client.CodeGeneration.prompt import code_gen_instruct
from client.CodeGeneration.generation import generate_api
from client.CodeGeneration.content_process import json_parse,code_parse
from app.config import config

def generate_code(requirement, asset_info):

    config.load()
    config_info = config.get()
    prompt_templete = deepcopy(code_gen_instruct)
    prompt_templete.generate_prompt(
        user_param={"asset": asset_info, "requirement": requirement}
    )
    messages = prompt_templete.generate_message()
    try:
        # code generation
        host = config_info.get("llm", {}).get("url")
        model = config_info.get("llm", {}).get("model")
        key = config_info.get("llm", {}).get("key")
        print(f"--- 提示词 {datetime.now()} ---\n{messages}")
        code = generate_api(messages, host=host, model=model, key=key)
        code = code.split("</think>")[-1]
        result = json_parse(code)
        itea_max = config_info.get("CodeGeneration", {}).get("itea")
        itea_count = 0
        for itea in range(itea_max):
            itea_count = itea
            if not result:
                messages[-1][
                    "content"
                ] += "如果需要生成Json数据，请将Json数据包裹在```json  ```之间，如果不需要生成代码请忽略这句话"
                code = generate_api(messages, host=host, model=model, key=key)
            elif not ("code" in result.keys() and "info" in result.keys()):
                messages[-1][
                    "content"
                ] += "请严格按照Json格式输出生成结果，包含code和info两个字段，Json数据使用```json  ```包裹起来, code中的代码使用```c ```包裹起来."
                code = generate_api(messages, host=host, model=model, key=key)
            elif not('```c' in result["code"] and '```' in result["code"]) and not('```C' in result["code"] and '```' in result["code"]):
                messages[-1][
                    "content"
                ] += "请严格按照Json格式输出生成结果，包含code和info两个字段，Json数据使用```json  ```包裹起来, code中的代码使用```c ```包裹起来."
                code = generate_api(messages, host=host, model=model, key=key)
            else:
                break
        code = code_parse(result["code"])
        print(f"--- 完成生成 {datetime.now()} ---")
        print(f"********** 迭代次数:{itea_count} **********")
        print(f"--- 生成结果 ---\n{code}")
        print(f"--- 复用情况 ---\n{result['info']}")
        return {"code": f"{code}", "info": f"{result['info']}"}
    except APITimeoutError:
        return {"code": "服务器繁忙，请稍后再试", "info": "服务器繁忙，请稍后再试"}