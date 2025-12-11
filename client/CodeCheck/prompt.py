from langchain_core.prompts import PromptTemplate
class ChatPromptBase:

    def __init__(self, system='', user='', system_input_var=None, user_input_var=None, example = '', example_input_var = None):

        self.system_prompt_template = PromptTemplate.from_template(system)
        self.user_prompt_template = PromptTemplate.from_template(user)
        self.system_prompt_template.input_variables = system_input_var if system_input_var else []
        self.user_prompt_template.input_variables = user_input_var if user_input_var else []
        self.example_prompt_template = PromptTemplate.from_template(example)
        self.example_prompt_template.input_variables = example_input_var if example_input_var else []


    def generate_prompt(self, system_param =None, user_param = None):

        self.system_prompt = self.system_prompt_template.invoke(system_param).text if system_param else self.system_prompt_template.template
        self.user_prompt = self.user_prompt_template.invoke(user_param).text if user_param else self.user_prompt_template.template_format

    def generate_message(self):

        self.messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": self.user_prompt}]
        return self.messages

    def set_input_var(self, system_input_var=None, user_input_var=None):

        self.system_prompt_template.input_variables = system_input_var if system_input_var else []
        self.user_prompt_template.input_variables = user_input_var if user_input_var else []
    
    def add_example(self, param_list, result_list):
        example=[0,0]
        for param,result in zip(param_list, result_list):
            example[0] = {'role': 'user', 'content': self.example_prompt_template.invoke(param).text}
            example[1] = {'role': 'assistant', 'content': result}
            self.messages[-1:-1]= example
        return self.messages

    def add_chat(self, role, content):
        self.messages.append({"role": role, "content": content})
        return self.messages
    
code_check = ChatPromptBase(
    system="""你是根据GJB8114标准编写代码的专家。你的任务是对一段代码进行修改，以使其符合GJB114规范。在修改代码时，必须遵守CODE_RULES中的每条规则。
    @CODE_RULE1: 不要更改函数中的关键变量命名和关键函数的签名
    @CODE_RULE2: 确保你的代码实现时自包含的，它必须在不需要编写额外代码的情况下运行。
    @CODE_RULE3: 最好选择标准库使用，如果第三方库的使用是不可避免的，把它们列在最上面。
    @CODE_RULE4: 编写简洁、可读的**C语言**代码，但不要为了简洁而牺牲正确性。
    @CODE_RULE5: 输出你修改后的完整代码，不要仅仅输出修改过后的部分。
    @CODE_RULE6: 修改后的代码的功能实现逻辑要和修改之前的代码保持严格一致。
    @CODE_RULE7: 你必须确保修改后的代码的正确性，不能有语法错误，不能有逻辑错误，不能有运行错误。
    @CODE_RULE8: 如果需要生成代码，请将C语言代码包裹在```c  ```之间，如果不需要生成代码请忽略这条规则.
    """,
    user = """
    * 这是你要修改的代码。
    @CODE:{code}
    * 这是这段代码的错误信息，我将为你提供一条或者多条错误的具体内容：包括错误描述、错误涉及到的语句：
    @ERROR:{error}
    请你自行根据我给你发送的内容，对代码进行修改，修改的结果不允许出现问题，直接输出更改之后的代码。
    """,
    example = """
    * 这是你要修改的代码。
    @CODE:{code}
    * 这是这段代码的错误信息，我将为你提供一条或者多条错误的具体内容：包括错误描述、错误涉及到的语句：
    @ERROR:{error}
    请你自行根据我给你发送的内容，对代码进行修改，输出你修改后的完整代码，不要仅仅输出修改过后的部分。
""",
    user_input_var=["code", "error"],
    example_input_var=["code", "error"]
)