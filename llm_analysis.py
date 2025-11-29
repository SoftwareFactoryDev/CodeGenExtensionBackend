import os
import shutil
import json

from client.CodeGeneration.prompt import code_gen_retlist
from client.CodeGeneration.content_process import req_list_content
from client.CodeGeneration.generation import generate_api

def generation():
    with open('./client/requirements.json', 'r', encoding='utf-8') as f:
        req_list = json.load(f)

    group_size = 5

    result = []

    for size in range(5, len(req_list), group_size):
        for index in range(0, len(req_list), size):
            req_group = req_list[index:index+size]
            req_cont = req_list_content(req_group)
            prompt = code_gen_retlist
            prompt.generate_prompt(user_param={'req_list':req_cont})
            messages = prompt.generate_message()
            response = generate_api(messages, host='http://10.13.1.104:14516/v1/')
            response = response.split('</think>')[-1]
            result.append(
                {
                    'req_list': req_cont,
                    'response': response,
                    'length' :  len(prompt.system_prompt) + len(prompt.user_prompt)
                }
            )
            result = []
            print(f"""
    【{index+1}/{len(req_list)}】
    {req_cont}
    {response}
                """)

        with open(f'E:/Work/lab/20250320-20251201-AI赋能机载软件研发三年规划/20251030-20251130-产品研发/Result/result-{size}.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with open(f'E:/Work/lab/20250320-20251201-AI赋能机载软件研发三年规划/20251030-20251130-产品研发/Result/result-{size}.txt', 'w', encoding='utf-8') as f:
            for index, item in enumerate(result):
                f.write(f'【{index+1}/{len(req_list)}】{item["length"]}\n{item["req_list"]}\n{item["response"]}\n\n')

def data_clean(source_path):

    prompt = code_gen_retlist
    for size in range(10,5, -5):
        with open(os.path.join(source_path, f"result-{size}.json"), 'r', encoding='utf-8') as f:
          data_l = json.load(f)
        with open(os.path.join(source_path, f"result-{size-5}.json"), 'r', encoding='utf-8') as f:
            data_s = json.load(f)
        data_l = data_l[len(data_s):]
        for item in data_l:
            prompt.generate_prompt(user_param={'req_list': item['req_list']})
            item['length'] = len(prompt.system_prompt) + len(prompt.user_prompt)
        os.remove(os.path.join(source_path, f"result-{size}.txt"))
        with open(os.path.join(source_path, f"result-{size}.txt"), 'w', encoding='utf-8') as f:
            for index, item in enumerate(data_l):
                f.write(f'=========================\n【{index+1}/{len(data_l)}】{item["length"]}\n【需求列表】\n{item["req_list"]}\n【生成结果】\n{item["response"]}\n\n')
        with open(os.path.join(source_path, f"result-{size}.json"), 'w', encoding='utf-8') as f:
            json.dump(data_l, f, ensure_ascii=False, indent=2)
    
if __name__ == '__main__':
    generation()