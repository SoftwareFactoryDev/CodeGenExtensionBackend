import json
import re

from copy import deepcopy

from function.CodeBaseBuild.prompt import code_sum_template
from function.CodeBaseBuild.llm_gen import generate_api
from app.logger import logger_global

def gen_code_sum(code, host, model, key):
    logger = deepcopy(logger_global)
    summary = ''
    prompt_template = deepcopy(code_sum_template)
    param = {
        "code": code
    }
    prompt_template.generate_prompt(user_param=param)
    messages = prompt_template.generate_message()
    ite = 0
    while True:
        response = generate_api(messages, host=host, model=model, key=key)
        if not response or len(response.strip()) == 0:
            sum_data = None
        else:
            m = re.search(
                r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```",
                response,
                re.DOTALL,
            )
            if m:
                sum_data = json_parse(response)
            else:
                sum_data = None
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
            messages[1]["content"] += ". Do not outpout empty string."
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
                    "content": "将功能描述缩减至不超过50字, 不要包含当前函数所在的文件地址.",
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
    result = summary.strip()
    return result

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