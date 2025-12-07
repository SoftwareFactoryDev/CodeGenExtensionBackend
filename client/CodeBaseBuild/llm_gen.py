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

messages = [{'role': 'system', 'content': '你是代码生成的专家助手。你的任务是实现一个完全满足用户需求的函数。在编写函数时，必须遵守CODE_RULES中的每条规则。\n    @CODE_RULE1: 不要更改你需要生成的函数的函数签名。\n    @CODE_RULE2: 确保你的代码实现时自包含的，它必须在不需要编写额外代码的情况下运行。\n    @CODE_RULE3: 最好选择标准库使用，如果第三方库的使用是不可避免的，把它们列在最上面。\n    @CODE_RULE4: 编写简洁、可读的**C语言**代码，但不要为了简洁而牺牲正确性。\n    @CODE_RULE5: 直接输出代码生成结果。\n    @CODE_RULE6: 如果我的需求中包含伪代码，自行解析伪代码的逻辑并为我生成代码。\n    @CODE_RULE7: 如果我的需求中包含多个需求，请帮我对需求进行拆分并为我生成代码。\n    @CODE_RULE8: 如果需要生成代码，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这条规则.\n    '}, {'role': 'user', 'content': '\n    这是我的需求，请根据它实现功能。\n    @REQUIREMENT:调整并限制高频滤波器增益，\n    该函数在遵守CODE_RULES的同时满足我的需求。\n'}, {'role': 'assistant', 'content': 'float my_hpf_limited(float T,float hz,float x,float zoom,float *zoom_adj)\n{\n\n\t\n\t*zoom_adj += ( 1 / ( 1 + 1 / ( hz *6.28f *T ) ) ) *(x - *zoom_adj);\n\t*zoom_adj = LIMIT(*zoom_adj,-zoom,zoom);\n\treturn (x - *zoom_adj);\n\n}'}, {'role': 'user', 'content': '\n    这是我的需求，请根据它实现功能。\n    @REQUIREMENT:初始化ICM20602的CS引脚，设置为输出模式并输出高电平，\n    该函数在遵守CODE_RULES的同时满足我的需求。\n'}, {'role': 'assistant', 'content': 'void Drv_Icm20602CSPin_Init(void)\n{\n    MAP_SysCtlPeripheralEnable(ICM20602_CS_SYSCTL);          // 开启传感器CS引脚对应时钟 CS:PN2\n    while(!(MAP_SysCtlPeripheralReady(ICM20602_CS_SYSCTL)))\n    {\n    }\n    \n    GPIOPinTypeGPIOOutput(ICM20602_CS_GPIO, ICM20602_CS_PIN);// 设置PN2模式为输出\n    \n    GPIOPinWrite(ICM20602_CS_GPIO, ICM20602_CS_PIN, ICM20602_CS_PIN); // 设置设置PN2输出1\n}'}, {'role': 'user', 'content': '\n    这是我的需求，请根据它实现功能。\n    @REQUIREMENT:向VL53L0X写入一个字节的数据。，\n    该函数在遵守CODE_RULES的同时满足我的需求。\n'}, {'role': 'assistant', 'content': 'int32_t VL53L0X_write_byte(uint8_t address, uint8_t index, uint8_t data)\n{\n    int32_t status = STATUS_OK;\n    const int32_t cbyte_count = 1;\n    status = VL53L0X_write_multi(address, index, &data, cbyte_count);\n    return status;\n}'}, {'role': 'user', 'content': '这是代码生成对话历史(可能没有)。\n    @HISTORY:* user : 为我写一段高通滤波算法\n* assistant : 请求失败：Request failed with status code 500\n* user : 为我写一段高通滤波算法\n\n    这是我的需求，请根据它实现功能，该函数在遵守CODE_RULES的同时满足我的需求\n    @REQUIREMENT:为我写一段高通滤波算法\n    请你自行根据我给你发送的内容，判断你要做的事情。\n    '}]

generate_api(messages)