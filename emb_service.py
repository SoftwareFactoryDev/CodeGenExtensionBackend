import argparse
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from server.service.code_embedding import EmbeddingService
from server.util.config import load_config

# 定义请求体模型
class TextRequest(BaseModel):
    texts: List[str]

# 定义响应体模型
class EmbeddingResponse(BaseModel):
    embeddings: Optional[List[List[float]]] = None
    error: Optional[str] = None

def create_app(config: dict) -> FastAPI:

    app = FastAPI()
    
    # 创建嵌入服务实例
    embedding_service = EmbeddingService(config)

    @app.post("/codeEmb", response_model=EmbeddingResponse)
    async def get_embeddings_endpoint(request: TextRequest):
        try:
            embeddings = embedding_service.get_embeddings(request.texts)
            return EmbeddingResponse(embeddings=embeddings)
        except Exception as e:
            print('Error:', e)
            return EmbeddingResponse(error=str(e))
    return app

def main():
    parser = argparse.ArgumentParser(description='UniXcoder API Server')
    parser.add_argument('--config', type=str, required=True,help='Path to config.json file')
    parser.add_argument('--host', type=str, required=True,help='Path to config.json file')
    parser.add_argument('--port', type=str, required=True,help='Path to config.json file')
    args = parser.parse_args()

    config = load_config(args.config)
    
    app = create_app(config)
    
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == '__main__':
    main()
