from function.CodeGeneration.prompt import code_gen_instruct
from function.CodeBaseBuild.llm_gen import generate_api
from function.CodeSearch.code_search import code_search_custom
def generate_rag(requirement, asset_info):
    
    prompt_tem = code_gen_instruct
    prompt_tem.generate_prompt(user_param={'requirement':requirement,'asset':asset_info})
    messages = prompt_tem.generate_message()
    result = generate_api(messages)

    return result
   
    return result

def generate_raw(requirement):
    
    prompt_tem = code_gen_instruct
    prompt_tem.generate_prompt(user_param={'requirement':requirement})
    messages = prompt_tem.generate_message()
    text = ''
    result = generate_api(messages)
    result = text + '\n【生成结果】:\n' + result
    return result

