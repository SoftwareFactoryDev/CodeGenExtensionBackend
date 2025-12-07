import difflib
def err_parse(err_list):
    err_info = ''
    for index,err in enumerate(err_list):
        if 'error' in err.keys():
            err_info += f'{index+1}, 存在编译错误：{err}\n'
        else:
            err_info += f'{index+1}, 异常位置:{err["location"]},语句内容：{err["violated_code"]}，错误信息:{err["description"]}\n'
    return err_info

def compare_code(old_code, new_code):

    fix_info = ''
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()

    differ = difflib.Differ()
    diff = list(differ.compare(old_lines, new_lines))

    pending_delete = None

    for line in diff:
        if line.startswith('- '):
            if pending_delete is not None:
                content = {pending_delete[2:].strip()}
                if len(content) > 0:
                    fix_info += f"\t[删除] {content}\n"
            pending_delete = line
        elif line.startswith('+ '):
            if pending_delete is not None:
                content1 = {pending_delete[2:].strip()}
                content2 = {line[2:].strip()}
                if len(content1) > 0 and len(content2) > 0:
                    fix_info += f"\t[更改] {pending_delete[2:].strip()}->{line[2:].strip()}\n"
                if len(content1) > 0 and len(content2) == 0:
                    fix_info += f"\t[删除] {pending_delete[2:].strip()}\n"
                if len(content1) == 0 and len(content2) > 0:
                    fix_info += f"\t[新增] {line[2:]}\n"
                pending_delete = None
            else:
                if len(line[2:].strip()) > 0:
                    fix_info += f"\t[新增] {line[2:]}\n"
        elif line.startswith('  '):
            if pending_delete is not None:
                if len(pending_delete[2:].strip()) > 0:
                    fix_info += f"\t[删除] {pending_delete[2:].strip()}\n"
                pending_delete = None
    if pending_delete is not None:
        if len(pending_delete[2:].strip()) > 0:
            fix_info += f"\t[删除] {pending_delete[2:].strip()}\n"
    
    return fix_info