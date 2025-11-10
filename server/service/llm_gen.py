from openai import OpenAI
client = OpenAI(api_key="dummy", base_url="http://localhost:14516/v1")
rsp = client.chat.completions.create(
    model="qwen2.5-7b",
    messages=[{"role": "user", "content": "用一句话解释牛顿第二定律"}],
    stream=False
)
print(rsp.choices[0].message.content)