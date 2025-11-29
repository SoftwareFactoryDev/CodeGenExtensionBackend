import os 
import json
from datetime import datetime
import shutil

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn


from client.CodeBaseBuild.build_codebase import get_repository,repo_parse,sum_tokenize,gen_sum
from client.CodeSearch.code_search import code_search_custom
from client.CodeGeneration.generation import generate_api
from client.CodeGeneration.prompt import code_gen_instruct
from client.CodeGeneration.content_process import history_content
from client.CodeSearch.code_search import NlRetriever

app = FastAPI(title="Code Generation Server", version="1.0.0")

# 加载配置文件
config_path = 'config.json'
try:
    with open(config_path, 'r', encoding='utf-8') as file:
        config = json.load(file)
except Exception as e:
    print(f'配置文件加载出错: {e}, 请将配置文件放在安装目录下并检查配置文件格式')

# 加载检索器
retriever = NlRetriever()
codebase_path = config['codeBaseBuild']['codebasePath']
stopword_path = config['codeBaseBuild']['stopword_path']
data = []
retriever.load_stopwords(stopword_path)

class BuildRequest(BaseModel):
    repo_url: str

class BuildResponse(BaseModel):
    message: str

@app.post("/api/v1/bcb", response_model=BuildResponse)
def build(request: BuildRequest):
    
    print(f'********** 接收到代码库复用请求 {datetime.now()} **********')

    # 从 git地址克隆代码库
    try:
        distination = config['codeBaseBuild']['repoPath']
        repo_path,version = get_repository(request.repo_url, distination)
        print(f'********** 代码库克隆成功 {datetime.now()} **********')
    except Exception as e:
        print(f'********** 代码库克隆失败  {e} **********')
        return {"message": f'代码库克隆失败'}
    
    output_path=config['codeBaseBuild']['codebasePath']
    #解析代码库
    if os.path.exists(output_path) and os.path.isdir(output_path):
        output_path = os.path.join(output_path, f'{os.path.basename(repo_path)}_{version}.csv')
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f'********** 开始提取C语言函数 {datetime.now()} **********')
    result = repo_parse(repo_path=repo_path,lib_path=config['codeBaseBuild']['clang_Path'], output_path=output_path, version=version, max_workers=config['codeBaseBuild']['max_workers'])
    print(f'********** {result} **********')

    print(f'********** 开始生成代码库摘要 {datetime.now()} **********')
    result = gen_sum(codebase_path=output_path)
    print(f'********** {result} **********')

    print(f'********** 开始生成代码库摘要向量和分词 {datetime.now()} **********')
    result = sum_tokenize(codebase_path=output_path)
    print(f'********** {result} **********')
    print(f'********** 代码库构建完成 {datetime.now()} **********')
    repo_name = os.path.basename(repo_path)
    for file in os.listdir(os.path.dirname(output_path)):
        if repo_name in file and file.endswith('.csv') and file != os.path.basename(output_path):
            output_path = os.path.join(os.path.dirname(output_path), file)
            break
    codebase = pd.read_csv(output_path)
    return {"message": f'代码库构建完成: {os.path.basename(repo_path)}, 提交版本：{version}, 总共解析函数数目: {len(codebase)}'}

class GenerateRequest(BaseModel):
    prompt: str
    history: Optional[List[Dict[str, Any]]] = None
    # history 参考格式:{role:"assistant/user", message:"xxxx"}

class GenerateResponse(BaseModel):
    code: str

@app.post("/api/v1/gen", response_model=GenerateResponse, tags=["Generate"])
def generate(request: GenerateRequest):

    print(f'********** 接收到代码生成请求 {datetime.now()} **********')

    if not request.history:
        history = ''
    else:
        history = history_content(request.history)

    prompt_templete = code_gen_instruct
    prompt_templete.generate_prompt(user_param={'history':history, 'requirement': request.prompt})

    print(f'********** 完成提示词加载 {datetime.now()} **********')


    # reference_retrievel
    k = config['CodeGeneration']['topk']
    examples = code_search_custom(retriever=retriever, key_words=request.prompt, top_K=k, codebase_path=codebase_path)
    param_list = []
    result_list = []
    messages = prompt_templete.generate_message()
    for index,example in examples.iterrows():
        if float(example['bm25_score']) > 0:
            param_list.append({'requirement': example['summary']})
            result_list.append(example['source_code'])
    if len(result_list) > 0:
        messages = prompt_templete.add_example(param_list, result_list)    
    print(f'********** 完成检索  **********')
    print(f'检索结果: {result_list}')
    # code generation
    host = config['llm']['url']
    model = config['llm']['model']
    key = config['llm']['key']
    code = generate_api(messages, host=host, model=model, key=key)
    print(f'********** 完成生成 {datetime.now()} **********')
    print(f'--------------提示词-------\n{messages}')
    print(f'--------------生成结果-------\n{code}')

    return {"code":code}


# ==================== 主程序 ====================
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=14514
)