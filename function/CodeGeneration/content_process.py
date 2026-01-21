import re
import json
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple

from docx.oxml.ns import qn
import docx
from docx.document import Document


def history_content(history):
    content = ""
    for record in history[-3:]:
        content += (
            f"* {record['role']} : {record['message'].split('=============')[0]}\n"
        )
    return content


def req_list_content(req_list):
    content = ""
    for req in req_list:
        content += f"* {req['ID']} : {req['Content']}\n"
    return content


def code_parse(string):

    # 使用正则表达式匹配代码块，同时支持```c和```C
    pattern = r"```[cC](.*?)```"
    matches = re.findall(pattern, string, re.DOTALL)

    result = ""
    for i in matches:
        result += f"{i}\n"
    return result

def info_parse(string):

    # 使用正则表达式匹配代码块，同时支持```c和```C
    pattern = r"```[iI][nN][fF][oO](.*?)```"
    matches = re.findall(pattern, string, re.DOTALL)

    result = ""
    for i in matches:
        result += f"{i}\n"
    return result

def asset_content(asset_list):
    asset_info = ""
    for index, asset in enumerate(asset_list):
        asset_info += f"{index+1}. 资产来源：{asset.name} 所属模块：{asset.module}  资产概述:{asset.description}  资产源代码：```c{asset.source_code}```\n"

    return asset_info


def json_parse(content):

    def try_load(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    out = try_load(content.strip())
    if out is not None:
        return out
    m = re.search(r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```", content, re.DOTALL)
    if m:
        candidate = m.group(1)
        out = try_load(candidate)
        if out is not None:
            return out
        return None
    return None


def c_parse(content):

    def try_load(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    out = try_load(content.strip())
    if out is not None:
        return out
    m = re.search(r"```[Jj][Ss][Oo][Nn]\s*(\{.*?\}|\[.*?\])\s*```", content, re.DOTALL)
    if m:
        candidate = m.group(1)
        out = try_load(candidate)
        if out is not None:
            return out
        return None
    return None


def requirement_extract(doc_path):
    class LineType(Enum):
        INDEX = "需求索引行"
        CONTENT = "需求内容行"
        TITLE = "需求标题行"
        OTHER = "其他行"
        UNKNOWN = "未知行"

    def classify_line(line_text: str) -> Tuple[LineType, Optional[str]]:

        if not line_text or not line_text.strip():
            return LineType.UNKNOWN, None

        text = line_text.strip()

        # 1. 检查是否为需求索引行 (全大写字母+数字，用-分割)
        index_pattern = r"^[A-Z]+(?:-[A-Z]+)*-\d+$"
        if re.fullmatch(index_pattern, text):
            return LineType.INDEX, text

        # 2. 检查是否为需求标题行 (纯编号内容只有条目化需求)
        if text == "条目化需求":
            return LineType.TITLE, text

        # 2. 检查是否为需求标题行 (数字.开头且为条目化需求)
        title_pattern = r"^(\d+(?:\.\d+)*\.[\s\t]*(.+))$"
        title_match = re.match(title_pattern, text)
        if title_match:
            full_match = title_match.group(1)
            content_after_number = title_match.group(2)

            # 判断是否为条目化需求 (这里简化判断：包含"需求"、"要求"等关键词)
            requirement_keywords = "条目化需求"
            if requirement_keywords in content_after_number.replace(" ", "").replace(
                "\t", ""
            ):
                return LineType.TITLE, full_match
            else:
                return LineType.OTHER, full_match

        return LineType.CONTENT, text

    def extract_table_content(table) -> str:
        table_content = []
        for i, row in enumerate(table.rows):
            row_cells = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    row_cells.append(cell_text)

            if row_cells:
                # 用制表符分隔单元格，模拟表格结构
                table_content.append("\t".join(row_cells))

        return "\n".join(table_content) if table_content else ""

    def handle_bracket_references(
        current_content: str, all_requirements: Dict[str, Dict[str, Any]]
    ) -> str:

        if not current_content:
            return current_content

        # 匹配中英文括号中的内容
        bracket_patterns = [
            r"（([^）]+)）",  # 中文圆括号
            r"\(([^)]+)\)",  # 英文圆括号
        ]

        result_content = current_content
        id_list = []
        for pattern in bracket_patterns:
            matches = re.findall(pattern, current_content)
            for match in matches:
                # 检查这个括号内容是否包含了某个需求标题
                for req_id, req_info in all_requirements.items():
                    req_title = req_info.get("id", "")
                    if req_title and req_title in match:
                        # 找到被引用的需求，将其内容附加
                        referenced_content = req_info.get("full_content", "")
                        if referenced_content:
                            result_content += (
                                f"\n[引用 {req_id} 的内容]-{referenced_content}-[引用 {req_id} 的内容]\n"
                            )
                            id_list.append(req_id)
                        break
        return result_content, id_list

    try:
        doc: Document = docx.Document(doc_path)
    except Exception as e:
        return f"无法打开Word文档: {str(e)}"

    all_requirements_dict = {}

    current_state = "WAITING_FOR_TITLE"
    current_requirement = None
    current_index = None
    current_content_lines = []
    current_title = None

    # 逐段落处理
    for para in doc.paragraphs:

        line_text = para.text.strip()
        if not line_text:
            continue

        
        num_pr = para._p.pPr.numPr if hasattr(para._p, 'pPr') and para._p.pPr is not None else None
        if num_pr is not None and num_pr.numId is not None:
            ilvl = num_pr.find(qn('w:ilvl'))
            if not ilvl.val == 0:
                line_text = '1.1.1' + line_text
        if para.style.name.startswith('Heading'):
            line_text = '1.1.1' + line_text
        line_type, matched_content = classify_line(line_text)

        # 处理表格
        table_content = ""
        if para._element.xpath(".//w:tbl"):  # 检查段落是否包含表格
            # 获取表格对象
            for table in doc.tables:
                # 简化处理：如果表格在附近，提取内容
                table_content = extract_table_content(table)
                if table_content:
                    break

        # 状态机逻辑
        if line_type == LineType.TITLE:
            # 遇到需求标题行
            if current_state == "COLLECTING" and current_requirement is not None:
                # 保存上一个需求
                full_content = (
                    "\n".join(current_content_lines) if current_content_lines else ""
                )
                all_requirements_dict[current_index] = {
                    "id": current_index,
                    "content": full_content,
                    "title": current_title,
                    "full_content": full_content,
                }
                current_content_lines = []
            # 开始新的收集
            current_state = "COLLECTING"
            current_title = matched_content
            current_index = None
            current_content_lines = []
            current_requirement = {"title": current_title}

        elif line_type == LineType.INDEX and current_state == "COLLECTING":
            # 收集状态下的需求索引行
            if current_requirement is not None and current_index:
                # 保存当前需求
                full_content = (
                    "\n".join(current_content_lines) if current_content_lines else ""
                )
                all_requirements_dict[current_index] = {
                    "id": current_index,
                    "content": full_content,
                    "title": current_title,
                    "full_content": full_content,
                }
                current_content_lines = []

            current_index = matched_content
            current_requirement["id"] = current_index

        elif (
            line_type == LineType.CONTENT
            and current_state == "COLLECTING"
            and current_index
        ):
            # 收集状态下的需求内容行
            content = matched_content
            if table_content:
                content += f"\n[表格内容]:\n{table_content}"
            current_content_lines.append(content)

        elif line_type == LineType.OTHER and current_state == "COLLECTING":
            # 遇到其他行，暂停收集
            if current_requirement is not None and current_index:
                # 保存当前需求
                full_content = (
                    "\n".join(current_content_lines) if current_content_lines else ""
                )
                all_requirements_dict[current_index] = {
                    "id": current_index,
                    "content": full_content,
                    "title": current_title,
                    "full_content": full_content,
                }
                current_content_lines = []

            current_state = "PAUSED"
            current_requirement = None
            current_index = None
            current_content_lines = []

    # 处理最后一个需求
    if (
        current_state == "COLLECTING"
        and current_requirement is not None
        and current_index
    ):
        full_content = "\n".join(current_content_lines) if current_content_lines else ""
        all_requirements_dict[current_index] = {
            "id": current_index,
            "content": full_content,
            "title": current_title,
            "full_content": full_content,
        }
        current_content_lines = []

    for key in all_requirements_dict.keys():
        value = all_requirements_dict[key]
        req_id = key
        original_content = value["content"]
        processed_content = original_content

        # 检查当前需求是否调用其他需求的内容
        processed_content,id_list = handle_bracket_references(
            original_content, all_requirements_dict
        )
        if processed_content != original_content:
            all_requirements_dict[req_id]["content"] = processed_content
            all_requirements_dict[req_id]["full_content"] = processed_content
            all_requirements_dict[req_id]['use'] = id_list
            # 检查是否有其他需求的内容需要更新
            for k, v in all_requirements_dict.items():
                if 'content' in v and req_id in v['content']:
                    all_requirements_dict[k]['content'] = re.sub(rf'\[引用 {req_id} 的内容\]-.*?-\[引用 {req_id} 的内容\]', f'[引用 {req_id} 的内容]-{processed_content}-[引用 {req_id} 的内容]', v['content'])
                    all_requirements_dict[k]['full_content'] = re.sub(rf'\[引用 {req_id} 的内容\]-.*?-\[引用 {req_id} 的内容\]', f'[引用 {req_id} 的内容]-{processed_content}-[引用 {req_id} 的内容]', v['content'])

    requirements = [{'id': k, 'content': v.get('content', '')} for k, v in all_requirements_dict.items()]

    return requirements
