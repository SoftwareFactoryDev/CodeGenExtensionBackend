from langchain_core.prompts import PromptTemplate
class SystemPromptBase:

    def __init__(self, system='', user='', system_input_var=None, user_input_var=None):

        self.system_prompt_template = PromptTemplate.from_template(system)
        self.user_prompt_template = PromptTemplate.from_template(user)
        self.system_prompt_template.input_variables = system_input_var if system_input_var else []
        self.user_prompt_template.input_variables = user_input_var if user_input_var else []


    def generate_prompt(self, system_param =None, user_param = None):

        self.system_prompt = self.system_prompt_template.invoke(system_param).text if system_param else self.system_prompt_template.template
        self.user_prompt = self.user_prompt_template.invoke(user_param).text if user_param else self.user_prompt_template.template_format
    
    def set_input_var(self, system_input_var=None, user_input_var=None):

        self.system_prompt_template.input_variables = system_input_var if system_input_var else []
        self.user_prompt_template.input_variables = user_input_var if user_input_var else []
    

    def generate_message(self):

        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": self.user_prompt}]
        return messages
    
function_sum_template = SystemPromptBase(
    system="""你是一个专业的程序员，你应该生成函数的功能描述，当你生成功能描述时，你应该遵守以下规则。
    * 规则1：功能描述应该主要描述函数是如何工作的，以及函数的用法。
    * 规则2：功能描述应简洁明了，长度不超过20字。
    * 规则3：功能描述应用中文书写。
    * 规则4：你应该只生成函数的功能描述，不要生成任何其他内容。
    * 规则5：直接输出功能描述，不要进行思考。""",
    user = """有一个函数：{name}
    # 函数签名
    {signature}
    # 源代码
    {source_code}
    请按照上述规则生成函数：{name}的功能描述。结果应该是Json格式：name：函数名，description：生成的函数功能描述
""",
    user_input_var=["name", "signature", "source_code"]
)

struct_sum_template = SystemPromptBase(
    system="""你是一个专业的程序员，你应该生成数据结构的属性描述，当你生成属性描述时，你应该遵守以下规则。
    * 规则1：属性描述应该主要描述数据结构定义了怎样的数据，主要包含什么内容。
    * 规则2：属性描述应简洁明了，长度不超过20字。
    * 规则3：属性描述应用中文书写。
    * 规则4：你应该只生成数据结构的属性描述，不要生成任何其他内容。""",
    user = """有一个数据结构：{name}
    # 基本信息
    这个数据结构的类型是{type}
    # 源代码
    数据结构定义的源代码为：
    {source_code}
    请按照上述规则生成数据结构：{name}的属性描述。结果应该是Json格式：name：数据结构名，description：生成的数据结构属性描述。
""",
    user_input_var=["name", "type","source_code"]
)

global_var_sum_template = SystemPromptBase(
    system="""你是一个专业的程序员，你应该生成全局变量的属性描述，当你生成属性描述时，你应该遵守以下规则。
    * 规则1：属性描述应该主要描述全局变量定义了怎样的数据，主要包含什么内容。
    * 规则2：属性描述应简洁明了，长度不超过20字。
    * 规则3：属性描述应用中文书写。
    * 规则4：你应该只生成全局变量的属性描述，不要生成任何其他内容。""",
    user = """有一个全局变量：{name}
    # 所在位置
    这个全局变量所在的位置为
    {localtion}
    # 源代码:
    全局变量定义的源代码为：
    {source_code}
    请按照上述规则生成全局变量：{name}的属性描述。结果应该是Json格式：name：变量名，description：生成的变量属性描述。
""",
    user_input_var=["name", "source_code", 'location']
)

macro_sum_template = SystemPromptBase(
    system="""你是一个专业的程序员，你应该生成宏定义的属性描述，当你生成属性描述时，你应该遵守以下规则。
    * 规则1：属性描述应该主要描述全局变量定义了怎样的数据，主要包含什么内容。
    * 规则2：属性描述应简洁明了，长度不超过20字。
    * 规则3：属性描述应用中文书写。
    * 规则4：你应该只生成宏定义的属性描述，不要生成任何其他内容。""",
    user = """有一个宏定义：{name}
    # 源代码:
    宏定义定义的源代码为：
    {source_code}
    请按照上述规则生成宏定义：{name}的属性描述。结果应该是Json格式：name：变量名，description：生成的变量属性描述。
""",
    user_input_var=["name", "source_code"]
)

module_sum_template = SystemPromptBase(
    system="""
你是一个专业的程序员，你现在需要为一个系统模块写功能描述，当你生成功能描述时，你应该遵守以下规则。
* 规则1：功能描述应该主要描述系统的作用。
* 规则2：功能描述应简洁明了，长度不超过20字。
* 规则3：功能描述应用中文书写。
* 规则4：结果应该是Json格式：description：生成的系统模块功能描述
""",
    user = """
这个模块在系统中的相对路径为：{path}
这个模块主要包含以下资产：
{assets}
请按照我所讲述的规则生成该功能模块的功能描述。
""",
    user_input_var=["path", "assets"]
)

repo_sum_template = SystemPromptBase(
    system="""
你是一个专业的程序员，你现在需要为一个系统写功能描述，当你生成功能描述时，你应该遵守以下规则。
* 规则1：功能描述应该主要描述系统的作用。
* 规则2：功能描述应简洁明了，长度不超过20字。
* 规则3：功能描述应用中文书写。
* 规则4：结果应该是Json格式：description：生成的系统功能描述
""",
    user = """
这个系统主要包含以下模块：
{modules}
请按照我所讲述的规则生成该系统的功能描述。
""",
    user_input_var=["modules"]
)

sum_prompt_lib = {
    "function_sum": function_sum_template,
    "struct_sum": struct_sum_template,
    "global_var_sum": global_var_sum_template,
    "macro_sum": macro_sum_template,
    "module_sum": module_sum_template,
    "repo_sum": repo_sum_template
}