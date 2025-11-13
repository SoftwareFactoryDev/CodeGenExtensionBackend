from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn
import subprocess
from datetime import datetime

app = FastAPI(title="Code Generation Server", version="1.0.0")

class BuildRequest(BaseModel):
    repo_url: str

class BuildResponse(BaseModel):
    message: str

class GenerateRequest(BaseModel):
    prompt: str
    template: Optional[str] = None

class GenerateResponse(BaseModel):
    code: str

@app.post("/cg/bcb", response_model=BuildResponse, tags=["Build"])
async def build(request: BuildRequest):
    pass

@app.post("/api/v1/generate", response_model=GenerateResponse, tags=["Generate"])
async def generate(request: GenerateRequest):
    """生成代码"""
    result = GenerateService.generate(
        request.prompt,
        request.language,
        request.template
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Generation failed"))
    
    return GenerateResponse(
        status=result["status"],
        code=result["code"],
        language=result["language"],
        timestamp=result["timestamp"]
    )

@app.get("/api/v1/templates", tags=["Generate"])
async def list_templates():
    """获取可用的代码模板"""
    return {
        "templates": list(GenerateService.templates.keys()),
        "timestamp": datetime.now().isoformat()
    }

# ==================== 主程序 ====================
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )