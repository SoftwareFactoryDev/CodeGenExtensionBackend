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


class NLPEmbedding:
    """NLP Embedding API封装类"""
    
    def __init__(self, api_url: str):
        """
        初始化embedding API
        
        Args:
            api_url: embedding服务的API地址
        """
        self.api_url = api_url
    
    def __call__(self, texts):
        """
        计算文本的embedding向量
        
        Args:
            texts: 单个文本或文本列表
            
        Returns:
            单个文本的embedding向量或文本列表的embedding向量列表
        """
        if isinstance(texts, str):
            req_texts = [texts]
        else:
            req_texts = texts
            
        try:
            response = requests.post(
                self.api_url,
                json={"texts": req_texts},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status() 
            
            result = response.json()
            embeddings = np.array(result["embeddings"]).tolist()
            
            if isinstance(texts, str):
                return embeddings[0]
            return embeddings
            
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(f"API请求失败: {str(e)}")
        except KeyError as e:
            raise ValueError(f"API返回格式错误: 缺少字段 {str(e)}")
        except Exception as e:
            raise ValueError(f"处理响应时出错: {str(e)}")
        
class CodeEmbedding:
    """Code Embedding API封装类"""
    
    def __init__(self, api_url: str):
        """
        初始化embedding API
        
        Args:
            api_url: embedding服务的API地址
        """
        self.api_url = api_url
    
    def __call__(self, code):
        """
        计算文本的embedding向量
        
        Args:
            code: 单个代码片段
            
        Returns:
            单个代码的embedding向量
        """
        logger = deepcopy(logger_global)
        headers = {"Content-Type": "application/json"}
        data = {"texts": code}
        
        try:
            response = requests.post(
                self.api_url,
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