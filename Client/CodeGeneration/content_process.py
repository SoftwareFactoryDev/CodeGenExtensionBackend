def history_content(history):
    content = ''
    for record in history[-3:]:
        content += f"* {record['role']} : {record['message']}\n"
    return content

def req_list_content(req_list):
    content = ''
    for req in req_list:
        content += f"* {req['ID']} : {req['Content']}\n"