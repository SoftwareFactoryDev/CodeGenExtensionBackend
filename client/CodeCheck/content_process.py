import difflib
def err_parse(err_list):
    err_info = ''
    for index,err in enumerate(err_list):
        if isinstance(err, str):
            err_info += f'{index+1}, {err}\n'
        if 'error' in err.keys():
            err_info += f'{index+1}, 存在编译错误：{err}\n'
        else:
            err_info += f'{index+1}, 异常位置:{err["location"]},语句内容：{err["violated_code"]}，错误信息:{err["description"]}\n'
    return err_info

def compare_code(before: str, after: str) -> str:

    b_lines = before.splitlines()
    a_lines = after.splitlines()

    sm = difflib.SequenceMatcher(None, b_lines, a_lines)
    info = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        elif tag == 'delete':
            for row in range(i1 + 1, i2 + 1):
                info.append({"code": "before", "type": "delete", "loc": row})
        elif tag == 'insert':
            for row in range(j1 + 1, j2 + 1):
                info.append({"code": "after", "type": "new", "loc": row})
        elif tag == 'replace':
            for row in range(i1 + 1, i2 + 1):
                info.append({"code": "before", "type": "edit", "loc": row})
            for row in range(j1 + 1, j2 + 1):
                info.append({"code": "after", "type": "edit", "loc": row})

    return {"info":info}
    