from openai import OpenAI
def generate_api(messages, host='http://10.13.1.102:8021/v1', model = 'deepseek-ai/DeepSeek-R1', key='103', top_p=0.9, temperature=0.6, stream=False):
    
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
        )
    return result.choices[0].message.content
"""
消息示例
messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
返回值：
直接返回大模型生成的字符串
"""