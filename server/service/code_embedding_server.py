#!/usr/bin/env python3
# server_roberta_fastapi.py
import os
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import uvicorn

from model.UniXcoder import UniXcoder, UniXcoder_tokenize, UniXcoder_encode

# 配置参数
HOST = '0.0.0.0'
PORT = 14515
MODEL = '/data/zhouzl/code/Model/unixcoder-base'

# 设置环境变量
os.environ['CUDA_VISIBLE_DEVICES'] = "1"

# 创建FastAPI应用
app = FastAPI()

# 加载模型
print('Loading UniXcoder ...')
model = UniXcoder(MODEL)
print('UniXcoder ready on', HOST, PORT)

# 定义请求体模型
class TextRequest(BaseModel):
    texts: List[str]

# 定义响应体模型
class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
    error: str = None

@app.post("/embeddings", response_model=EmbeddingResponse)
async def get_embeddings_endpoint(request: TextRequest):
    try:
        # 获取嵌入向量
        embeddings = get_embeddings(request.texts)
        return EmbeddingResponse(embeddings=embeddings)
    except Exception as e:
        print('Error:', e)
        return EmbeddingResponse(error=str(e))

@torch.no_grad()
def get_embeddings(texts):
    vec = UniXcoder_encode(model, texts, UniXcoder_tokenize)
    return vec

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == '__main__':
    uvicorn.run(app, host=HOST, port=PORT)
