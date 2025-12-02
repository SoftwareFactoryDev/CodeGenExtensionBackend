from openai import OpenAI
def generate_api(messages, host='http://10.13.1.102:8021/v1', model = 'deepseek-ai/DeepSeek-R1', key='103', top_p=0.9, temperature=0.6, stream=False, timeout=30):
    
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

def embedding_api(texts, host='10.13.1.104'):
    """
    我现在有一个软件文档，这个软件文档是docx格式的，请你为我提取一下相关内容：
    * 提取范围: 文档中会多次出现条目化需求的标题，请你为我提取每个条目需求化标题开始，到下一个标题之间的内容，内容主要是需求条目
    * 提取内容: 条目化需求的编号格式为: 若干个字母-RES-若干个数字，提取内容时候，一个条目化需求的编号开始，到下一个条目化需求或者标题结束，每个需求编号是单独的一段
    * 结果格式: 提取结果以Json格式的形式保存，Json内容为：ID-条目化需求编号，Content-条目化需求内容
    """