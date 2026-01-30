import os
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import uvicorn

# 配置
HOST = '0.0.0.0'
PORT = 14515
MODEL = '/data/zhouzl/code/Model/bge-large-zh-v1.5'
os.environ['CUDA_VISIBLE_DEVICES'] = "0, 1"

# 初始化模型
print('Loading BGE-Encoder ...')
model = SentenceTransformer(MODEL, device='cuda')
print('BGE-Encoder ready on', HOST, PORT)

# 创建FastAPI应用
app = FastAPI(title="Text Embedding API", version="1.0")

# 定义请求和响应模型
class TextRequest(BaseModel):
    texts: List[str]

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
# 推理接口
@app.post("/embeddings", response_model=EmbeddingResponse)
async def get_text_embeddings(request: TextRequest):

    try:
        # 获取嵌入向量
        embeddings = model.encode(request.texts, normalize_embeddings=True)
        
        # 返回结果
        return EmbeddingResponse(
            embeddings=embeddings.tolist()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)