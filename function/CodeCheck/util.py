import difflib
def err_parse(err_list):
    err_info = ''
    for index,err in enumerate(err_list):
        if isinstance(err, str):
            err_info += f'{index+1}, {err}\n'
        if 'error' in err.keys():
            err_info += f'{index+1}. 存在编译错误：{err}\n'
        else:
            err_info += f'{index+1}. 异常位置:{err["location"]},语句内容：{err["violated_code"]}，错误信息:{err["description"]}\n'
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
    
from copy import deepcopy


def err_list_parse(err_list):

    # 声明基础变量
    line = -1
    col = -1
    desp = ""
    item = {"line": -1, "col": -1, "desp": "代码正确，并且符合规范"}
    errors = []
    # 解析错误列表
    for index, err in enumerate(err_list):
        # 解析编译错误
        if "error" in err.keys():
            content = err["detail"]
            for index, string in enumerate(content):
                if (
                    "error:" in string
                    and ".c:" in string
                    and not string.startswith("   ")
                ):
                    l = deepcopy(line)
                    c = deepcopy(col)
                    line = int(string.split(":")[1].strip())
                    col = int(string.split(":")[2].strip())
                    if l != line:
                        if not (l == -1 or c == -1):
                            item["line"] = l
                            item["col"] = c
                            item["desp"] = desp
                            errors.append(deepcopy(item))
                        desp = (
                            "ERR_IINFO: " + string.split("error:", 4)[-1].strip() + "\n"
                        )
                    else:
                        desp += string.split("error:", 4)[-1].strip() + "\n"
            if not (line == -1 or col == -1):
                item["line"] = line
                item["col"] = col
                item["desp"] = desp
                errors.append(deepcopy(item))
        else:
            # 解析语法错误
            line = int(err["location"].split(",")[0].replace("Line", "").strip())
            col = int(err["location"].split(",")[1].replace("Col", "").strip())
            desp = err["description"]
            item["line"] = line
            item["col"] = col
            item["desp"] = desp
            errors.append(deepcopy(item))
    return errors
