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

    def generate_message(self):

        self.messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": self.user_prompt}]
        return self.messages
    
code_gen_instruct = ChatPromptBase(
    system="""你是代码生成的专家助手。你的任务是实现一个完全满足用户需求的函数。在编写函数时，必须遵守CODE_RULES中的每条规则。
    @CODE_RULE1: 不要更改你需要生成的函数的函数签名。
    @CODE_RULE2: 确保你的代码实现时自包含的，它必须在不需要编写额外代码的情况下运行。
    @CODE_RULE3: 最好选择标准库使用，如果第三方库的使用是不可避免的，把它们列在最上面。
    @CODE_RULE4: 编写简洁、可读的**C语言**代码，但不要为了简洁而牺牲正确性。
    @CODE_RULE5: 直接输出代码生成结果。
    @CODE_RULE6: 如果我的需求中包含伪代码，自行解析伪代码的逻辑并为我生成代码。
    @CODE_RULE7: 如果我的需求中包含多个需求，请帮我对需求进行拆分并为我生成代码。
    """,
    user = """这是代码生成对话历史(可能没有)。
    @HISTORY:{history}
    这是我的需求，请根据它实现功能，该函数在遵守CODE_RULES的同时满足我的需求
    @REQUIREMENT:{requirement}
    请你自行根据我给你发送的内容，判断你要做的事情。
    """,
    example = """
    这是我的需求，请根据它实现功能。
    @REQUIREMENT:{requirement}，
    该函数在遵守CODE_RULES的同时满足我的需求。
""",
    user_input_var=["requirement", "history"],
    example_input_var=["requirement"]
)

# code_gen_pseudocode = ChatPromptBase(

#     system="""你是代码生成的专家助手。你的任务是根据我提供的伪代码生成可执行的代码。在编写代码时，必须遵守CODE_RULES中的每条规则。
#     @CODE_RULE1: 确保你的代码实现是自包含的，它必须在不需要编写额外代码的情况下运行。
#     @CODE_RULE2: 编写简洁、可读的**C语言**代码，但不要为了简洁而牺牲正确性。
#     @CODE_RULE3: 直接输出代码生成结果。
#     @CODE_RULE7: 我会为你提供这段代码的伪代码描述，请你在生成代码的同时生成包含详细信息的规范注释。
#     """,
#     user="""这是我提供的伪代码描述和代码生成对话历史(可能没有)，请根据它生成代码。
#     @HISTORY:{history}
#     @PseudoCode:{pseudocode}
#     请按照上述伪代码生成包含规范注释的**C语言**函数，该函数在遵守CODE_RULES的同时满足我的需求。
#     """,
#     example = """
#     这是我提供的伪代码描述，请根据它生成代码。
#     @PseudoCode:{pseudocode}
#     该函数在遵守CODE_RULES的同时满足我的需求。
# """,
#     user_input_var=["pseudocode", "history"],
#     example_input_var=["pseudocode"]
# )

# code_gen_retlist = ChatPromptBase(
#     system="""你是代码生成的专家助手。你的任务是实现根据我提供的多个规范字符串一次性生成多个函数的代码。在编写代码时，必须遵守CODE_RULES中的每条规则。
#     @CODE_RULE1: 确保每个函数的代码实现都是自包含的，它们必须在不需要编写额外代码的情况下运行。
#     @CODE_RULE2: 编写简洁、可读的C语言代码，但不要为了简洁而牺牲正确性。
#     @CODE_RULE3: 直接输出所有函数的代码生成结果，按顺序排列。
#     @CODE_RULE4: 为每个需求生成单独的函数，为每个函数生成独立的、完整的代码实现。
#     @CODE_RULE5: 确保函数之间的接口清晰，避免命名冲突。
#     @CODE_RULE6: 如果函数之间存在调用关系，请确保调用顺序正确。
#     @CODE_RULE7: 我会为你提供多个函数的需求描述，请你自行梳理都有哪些需求条目。
#     @CODE_RULE8: 生成的代码必须符合GJB8114规范。
#     """,
#     user="""这是我提供给你的多个需求内容和代码生成对话历史(可能没有)，请根据它们一次性生成所有函数的代码。
#     @req_list:{req_list}
#     @HISTORY:{history}
#     请按照上述规范注释一次性生成包含所有函数的C语言代码，并在遵守CODE_RULES的同时满足我的需求。
#     请按顺序输出所有函数的完整代码实现，并且通过代码注释为我指明需求和代码之间的对应关系。
#     """,
#     example = """
#     这是我提供的伪代码描述，请根据它生成代码。
#     @PseudoCode:{req_list}
#     该函数在遵守CODE_RULES的同时满足我的需求。
# """,
#     user_input_var=["req_list", "history"],
#     example_input_var=["req_list"]
# )