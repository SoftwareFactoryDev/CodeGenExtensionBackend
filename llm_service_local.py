# serve_openai.py
import os
import json
import time
import torch
import uvicorn
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from transformers import AutoTokenizer, AutoModelForCausalLM, GenerationConfig

os.environ['CUDA_VISIBLE_DEVICES'] = "0,1,2,3"
MODEL_PATH = "/data/zhouzl/code/Model/DeepseekR1-32B"
DEVICE = "cuda"
MAX_NEW_TOKENS = 4096000
TEMPERATURE = 0.7
TOP_P = 0.95

print("Loading tokenizer & model...")
tok = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True
)
gen_config = GenerationConfig(
    max_new_tokens=MAX_NEW_TOKENS,
    temperature=TEMPERATURE,
    top_p=TOP_P,
    do_sample=True,
    eos_token_id=tok.eos_token_id,
    pad_token_id=tok.eos_token_id,
)

app = FastAPI(title="LLM-Local-Service ")

# ---------- Pydantic 模型（与 OpenAI 一致） ----------
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionReq(BaseModel):
    model: str = "qwen2.5-7b"          # 客户端可填任意，仅做透传
    messages: List[Message]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.95
    max_tokens: Optional[int] = MAX_NEW_TOKENS
    stream: Optional[bool] = False

class ChatChoice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: Optional[str] = "stop"

class ChatCompletionResp(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatChoice]

# ---------- 辅助函数 ----------
def build_prompt(messages: List[Message]) -> str:
    """把 OpenAI 风格数组拼成模型需要的单条字符串"""
    # Qwen 系列支持 <Im_start|im_end> 特殊 token，也可以用 chat_template
    prompt = ""
    for m in messages:
        prompt += f"<|im_start|>{m.role}\n{m.content}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"
    return prompt

def generate_once(prompt: str) -> str:
    # inputs = tok(prompt, return_tensors="pt").to(model.device)
    inputs = tok.apply_chat_template(prompt, tokenize=True, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            # **inputs,
            inputs,
            generation_config=gen_config,
            use_cache=True
        )
    # 去掉 prompt 本身
    # generated = tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    generated = tok.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
    return generated

# ---------- 路由 ----------
@app.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionReq):
    # prompt = build_prompt(body.messages)
    prompt = body.messages
    if not body.stream:
        text = generate_once(prompt).strip()
        return ChatCompletionResp(
            id=str(uuid.uuid4()),
            model=body.model,
            choices=[ChatChoice(message=Message(role="assistant", content=text))]
        )
    # ---- SSE 流式 ----
    def gen():
        # 这里为了演示，把一次性生成的结果按字节流式吐出
        text = generate_once(prompt).strip()
        for i, ch in enumerate(text):
            chunk = {
                "id": str(uuid.uuid4()),
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": body.model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": ch},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        # 结束标志
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/plain")

@app.get("/v1/models")
def list_models():
    # 只暴露一个模型，可扩展成多个
    return {
        "object": "list",
        "data": [{
            "id": "Deepseek-R1",
            "object": "model",
            "owned_by": "local",
            "permission": []
        }]
    }

# ---------- 入口 ----------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=14516)