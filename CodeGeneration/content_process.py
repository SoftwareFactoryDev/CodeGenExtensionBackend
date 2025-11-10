def req_list_content(req_list):
    content = ''
    for req in req_list:
        content += f"* {req['ID']} : {req['Content']}\n"
    return content