import json
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn
from client.CodeBaseBuild.build_codebase import get_repository,build_code_base

from client.CodeSearch.code_search import code_search
from client.CodeGeneration.generation import generate_api
from client.CodeGeneration.prompt import code_gen_instruct
from client.CodeGeneration.content_process import history_content

app = FastAPI(title="Code Generation Server", version="1.0.0")

# 加载配置文件
config_path = 'config.json'
try:
    with open(config_path, 'r', encoding='utf-8') as file:
        config = json.load(file)
except Exception as e:
    print(f'配置文件加载出错: {e}, 请将配置文件放在安装目录下并检查配置文件格式')

class BuildRequest(BaseModel):
    repo_url: str

class BuildResponse(BaseModel):
    message: str

@app.post("/api/v1/bcb", response_model=BuildResponse)
def build(request: BuildRequest):
    
    # 从 git地址克隆代码库
    try:
        distination = config['codeBaseBuild']['repoPath']
        repo_path = get_repository(request.repo_url, distination)
    except Exception as e:
        print(f'【Error】代码库克隆失败\n{e}')
    
    #解析代码库
    result = build_code_base(repo_path=repo_path, lib_path=config['codeBaseBuild']['clang_Path'], output_path=config['codeBaseBuild']['codebasePath'])

    return result

class GenerateRequest(BaseModel):
    prompt: str
    history: Optional[List[Dict[str, Any]]] = None
    # history 参考格式:{role:"assistant/user", message:"xxxx"}

class GenerateResponse(BaseModel):
    code: str

@app.post("/api/v1/gen", response_model=GenerateResponse, tags=["Generate"])
def generate(request: GenerateRequest):
    if not request.history:
        history = ''
    else:
        history = history_content(request.history)

    prompt_templete = code_gen_instruct
    prompt_templete.generate_prompt(user_param={'history':history, 'requirement': request.prompt})

    # reference_retrievel
    examples = code_search(codebase_path=config['codeBaseBuild']['codebasePath'], key_words=request.prompt, top_K=5)
    param_list = []
    result_list = []
    for example in examples.iterrows():
        param_list.append({'requirement': example['summary']})
        result_list.append(example['source_code'])
    prompt_templete.add_example(param_list, result_list)    

    # code generation
    messages = prompt_templete.generate_message()
    host = config['llm']['url']
    model = config['llm']['model']
    key = config['llm']['key']
    code = generate_api(messages, host=host, model=model, key=key)
    return {"code":code}

# ==================== 主程序 ====================
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
)