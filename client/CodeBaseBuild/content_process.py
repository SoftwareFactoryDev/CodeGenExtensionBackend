def asset_in_module(asset_list):
    
    asset_info =''
    for index, item in asset_list.iterrows():
        asset_info += f'* 函数名：{item["name"]} 所属文件:{item["file_path"]} 函数签名:{item["signature"]} 功能描述:{item["summary"]}\n'

    return asset_info

def module_in_repo(module_list):
    
    module_info =''
    for item in module_list:
        module_info += f'* 模块路径：{item["name"]}  功能描述:{item["description"]}\n'

    return module_info