from client.CodeGeneration.prompt import code_gen_instruct
from client.CodeBaseBuild.llm_gen import generate_api
from client.CodeSearch.code_search import code_search_custom
def generate_raw(requirement):
    
    prompt_tem = code_gen_instruct
    prompt_tem.generate_prompt(user_param={'requirement':requirement})
    messages = prompt_tem.generate_message()
    ref_sol = code_search_custom(key_words=requirement, top_K=3)
    param_list = []
    result_list = []
    if len(ref_sol) > 0:
        for index, row in ref_sol.iterrows():
            param_list.append({'requirement':row['summary']})
            result_list.append(row['source_code'])
        messages = prompt_tem.add_example(param_list=param_list, result_list=result_list)
    result = generate_api(messages)
    text = '【检索结果】:\n'
    if len(ref_sol) > 0:
        for index, row in ref_sol.iterrows():
            text += f"""【{index+1}】\n{row['summary']}\n{row['signature']}\n"""
    else:
        text += '未检索到相关代码示例。\n'
    result = text + '\n【生成结果】:\n' + result
    return result

def generate_raw(requirement):
    
    prompt_tem = code_gen_instruct
    prompt_tem.generate_prompt(user_param={'requirement':requirement})
    messages = prompt_tem.generate_message()
    text = ''
    # ref_sol = code_search(key_words=requirement, top_K=3)
    # param_list = []
    # result_list = []
    # for index, row in ref_sol.iterrows():
    #     param_list.append({'requirement':row['summary']})
    #     result_list.append(row['source_code'])
    # messages = prompt_tem.add_example(param_list=param_list, result_list=result_list)
    # text = '【检索结果】:\n'
    # for index, row in ref_sol.iterrows():
    #     text += f"""【{index+1}】\n{row['summary']}\n{row['signature']}\n"""
    result = generate_api(messages)
    result = text + '\n【生成结果】:\n' + result
    return result

