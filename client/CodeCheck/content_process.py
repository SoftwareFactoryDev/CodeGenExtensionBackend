def err_parse(err_list):
    err_info = ''
    for index,err in enumerate(err_list):
        err_info += f'{index+1}, 异常位置:{err["location"]},语句内容：{err["violated_code"]}，错误信息:{err["description"]}\n'
    return err_info