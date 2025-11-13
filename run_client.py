import json

<<<<<<< HEAD:run.py
from CodeGeneration.prompt import code_gen_retlist
from CodeGeneration.content_process import req_list_content
from CodeGeneration.generation import generate_api
=======
from client.CodeGeneration.prompt import code_gen_retlist
from client.CodeGeneration.content_process import req_list_content
from client.CodeGeneration.generation import generate_api
>>>>>>> 72504d900d8a24a0134336e6d8240d78546d1e2b:run_client.py

def main():
    with open('requirements.json', 'r', encoding='utf-8') as f:
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
<<<<<<< HEAD:run.py
            response = generate_api(messages, host='http://127.0.0.1:14516/v1/')
=======
            response = generate_api(messages, host='http://10.13.1.104:14516/v1/')
>>>>>>> 72504d900d8a24a0134336e6d8240d78546d1e2b:run_client.py
            response = response.split('</think>')[-1]
            result.append(
                {
                    'req_list': req_cont,
                    'response': response,
                    'length' : len(req_cont)
                }
            )
            print(f"""
    【{index+1}/{len(req_list)}】
    {req_cont}
    {response}
                """)
<<<<<<< HEAD:run.py
        with open(f'result-{size}.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with open(f'result-{size}.txt', 'w', encoding='utf-8') as f:
=======
        with open(f'./result/result-{size}.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with open(f'./result/result-{size}.txt', 'w', encoding='utf-8') as f:
>>>>>>> 72504d900d8a24a0134336e6d8240d78546d1e2b:run_client.py
            for index, item in enumerate(result):
                f.write(f'【{index+1}/{len(req_list)}】{item["length"]}\n{item["req_list"]}\n{item["response"]}\n\n')

if __name__ == '__main__':
    main()