from copy import deepcopy
import socket
import json
import struct

import requests
import numpy as np
from openai import OpenAI
from app.logger import logger_global
def generate_api(messages, host='http://10.13.1.102:8021/v1', model = 'deepseek-ai/DeepSeek-R1', key='103', top_p=0.9, temperature=0.6, stream=False, timeout=600):
    
    client = OpenAI(base_url=host,api_key=key)
    result = client.chat.completions.create(
            model=model,
            top_p=top_p,
            temperature=temperature,
            stream=stream,
            messages=messages,
            extra_body={
                "enable_enhancement": True,
            },
            timeout=timeout
        )
    return result.choices[0].message.content

def code_emb_api(texts, host='10.13.1.104:14515/codeEmb'):

    logger = deepcopy(logger_global)
    headers = {"Content-Type": "application/json"}
    data = {"texts": texts}
    
    try:
        response = requests.post(
            host,
            headers=headers,
            json=data
        )
        
        result = response.json()
        if "error" in result:
            logger.info(f"API Error: {result['error']}")
            return None
            
        return result["embeddings"]
        
    except requests.exceptions.RequestException as e:
        return f"请求失败: {str(e)}"
    except json.JSONDecodeError as e:
        return f"响应格式错误: {str(e)}"

def nlp_emb_api(texts, url):
    
    if isinstance(texts, str):
        req_texts = [texts]
    else:
        req_texts = texts
    try:
        # 发送请求
        response = requests.post(
            url,
            json={"texts": req_texts},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status() 
        
        result = response.json()
        
        embeddings = np.array(result["embeddings"]).tolist()
        if isinstance(texts, str):
            embeddings = embeddings[0]
        return embeddings
        
    except requests.exceptions.RequestException as e:
        raise requests.exceptions.RequestException(f"API请求失败: {str(e)}")
    except KeyError as e:
        raise ValueError(f"API返回格式错误: 缺少字段 {str(e)}")
    except Exception as e:
        raise ValueError(f"处理响应时出错: {str(e)}")