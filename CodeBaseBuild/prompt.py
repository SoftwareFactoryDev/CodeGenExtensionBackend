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
    system="""你是一个专业的程序员，你应该生成函数的摘要，当你生成摘要时，你应该遵守以下规则。
    @规则1：摘要应该主要描述函数是如何工作的，以及函数的用法。
    @规则2：摘要应简洁明了，长度不超过20字。
    @规则3：摘要应用中文书写。
    @规则4：你应该只生成函数的摘要，不要生成任何其他内容。
    @规则5：直接输出摘要，不要进行思考。""",
    user = """有一个函数：{name}
    @函数签名：函数的签名为：
    {signature}
    @源代码: 函数源代码为：
    {source_code}
    请按照上述规则生成函数：{name}的摘要。结果应该是Json格式：name：函数名，summary：生成的函数摘要
""",
    user_input_var=["name", "signature", "source_code"]
)