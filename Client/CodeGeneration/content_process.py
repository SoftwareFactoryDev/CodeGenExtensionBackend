def history_content(history):
    content = ''
    for record in history:
        content += f"* {record['role']} : {record['message']}\n"
    return content