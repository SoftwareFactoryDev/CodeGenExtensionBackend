from copy import deepcopy
import uuid
import os
import clang.cindex as cl
from function.CodeBaseBuild.llm_gen import generate_api
from app.logger import logger_global


class CParser:

    def __init__(self):
        self.index = cl.Index.create(excludeDecls=True)
        self.functions = []
        self.structs = []
        self.globals = []
        self.macros = []

    def parse_file(self, c_file_path):
        logger = deepcopy(logger_global)
        self.file_path = c_file_path

        if not os.path.isfile(c_file_path):
            raise FileNotFoundError(c_file_path)

        tu = self.index.parse(c_file_path)

        # 清空所有资产列表
        self.functions.clear()
        self.structs.clear()
        self.globals.clear()
        self.macros.clear()

        self._traverse(tu.cursor)
        logger.info(
            f"Parsing {c_file_path} finished, "
            f"funcs:{len(self.functions)}, structs:{len(self.structs)}, "
            f"globals:{len(self.globals)}, macros:{len(self.macros)}"
        )
        # 返回四种资产的字典结构
        return {
            "functions": self.functions,
            "structs": self.structs,
            "globals": self.globals,
            "macros": self.macros,
        }

    def _traverse(self, cursor: cl.Cursor):
        # 跳过无文件位置的节点
        if cursor.location.file is None:
            for child in cursor.get_children():
                self._traverse(child)
            return

        # 仅处理当前文件中的节点
        if not self._is_local_cursor(cursor):
            for child in cursor.get_children():
                self._traverse(child)
            return

        # 函数资产：保留原有实现判断逻辑
        if cursor.kind == cl.CursorKind.FUNCTION_DECL and self._has_body(cursor):
            func_json = self.parse_func(cursor)
            if func_json:
                self.functions.append(func_json)

        # 数据结构资产（STRUCT/UNION/ENUM定义）
        elif cursor.kind in (
            cl.CursorKind.STRUCT_DECL,
            cl.CursorKind.UNION_DECL,
            cl.CursorKind.ENUM_DECL,
        ):
            if self._is_definition(cursor):
                struct_json = self.parse_struct(cursor)
                if struct_json:
                    self.structs.append(struct_json)

        # 全局变量资产（文件作用域VAR_DECL）
        elif cursor.kind == cl.CursorKind.VAR_DECL:
            if (
                cursor.semantic_parent
                and cursor.semantic_parent.kind == cl.CursorKind.TRANSLATION_UNIT
            ):
                global_json = self.parse_global(cursor)
                if global_json:
                    self.globals.append(global_json)

        # 宏定义资产
        elif cursor.kind == cl.CursorKind.MACRO_DEFINITION:
            macro_json = self.parse_macro(cursor)
            if macro_json:
                self.macros.append(macro_json)

        # 递归子节点
        for child in cursor.get_children():
            self._traverse(child)

    def parse_func(self, cursor):
        # 返回类型
        result_type = cursor.result_type.spelling or "int"  # 默认 int（K&R 风格）

        # 函数名
        func_name = cursor.spelling

        # 形参列表
        params = []
        for parm in cursor.get_arguments():
            params.append({"name": parm.spelling, "type": parm.type.spelling})

        # 完整签名
        signature = (
            f"{result_type} {func_name}("
            + ", ".join(f"{p['type']} {p['name']}" for p in params)
            + ")"
        )

        # 源码区间（ extents ）
        extent = cursor.extent
        start: cl.SourceLocation = extent.start
        end: cl.SourceLocation = extent.end
        with open(start.file.name, encoding="utf-8") as f:
            content = f.readlines()
            for line in range(start.line - 1, end.line):
                if line == start.line - 1:
                    source_code = "".join(content[line][start.column - 1 :])
                elif line == end.line - 1:
                    source_code += "".join(content[line][: end.column - 1])
                else:
                    source_code += content[line]
        id = str(uuid.uuid1()).replace("-", "")
        return {
            "id": f"func_{id}",
            "name": func_name,
            "class": "function",
            "return_type": result_type,
            "signature": signature,
            "params": [
                f"{p['type']}-{p['name']}" for p in params
            ],  # 转换为"类型-变量名"格式
            "description": "",  # 预留字段（后续可集成LLM生成）
            "source_code": source_code,
            "docstring": (cursor.raw_comment.strip() if cursor.raw_comment else ""),
            "extent": f"{start.line}-{end.line}",  # 转换为"起始行-结束行"字符串
            "file_path": self.file_path,
            "module": "",  # 预留（由上层填充）
            "repo": "",  # 预留（由上层填充）
        }

    def parse_struct(self, cursor):
        asset_type_map = {
            cl.CursorKind.STRUCT_DECL: "STRUCT",
            cl.CursorKind.UNION_DECL: "UNION",
            cl.CursorKind.ENUM_DECL: "ENUM",
        }
        asset_type = asset_type_map.get(cursor.kind, "UNKNOWN")
        name = cursor.spelling or ""
        tag = name if name else "-"

        # 提取成员信息
        members = []
        for child in cursor.get_children():
            if (
                asset_type in ("STRUCT", "UNION")
                and child.kind == cl.CursorKind.FIELD_DECL
            ):
                members.append(f"{child.spelling}-{child.type.spelling}")
            elif (
                asset_type == "ENUM" and child.kind == cl.CursorKind.ENUM_CONSTANT_DECL
            ):
                val = (
                    str(child.enum_value)
                    if hasattr(child, "enum_value")
                    else child.spelling
                )
                members.append(f"{child.spelling}-{val}")

        source_code = self._extract_source_code(cursor.extent.start, cursor.extent.end)
        id = str(uuid.uuid1()).replace("-", "")
        return {
            "id": f"struct_{id}",
            "name": name,
            "type": asset_type,
            "class": "struct",
            "tag": tag,
            "description": "",
            "source_code": source_code,
            "member": members,
            "extent": f"{cursor.extent.start.line}-{cursor.extent.end.line}",
            "docstring": (cursor.raw_comment.strip() if cursor.raw_comment else ""),
            "file_path": self.file_path,
            "module": "",
            "repo": "",
        }

    def parse_global(self, cursor):
        source_code = self._extract_source_code(cursor.extent.start, cursor.extent.end)
        id = str(uuid.uuid1()).replace("-", "")
        return {
            "id": f"global_{id}",
            "name": cursor.spelling,
            "type": cursor.type.spelling,
            "description": "",
            "class":"global_var",
            "source_code": source_code,
            "extent": f"{cursor.extent.start.line}-{cursor.extent.end.line}",
            "file_path": self.file_path,
            "docstring": (cursor.raw_comment.strip() if cursor.raw_comment else ""),
            "module": "",
            "repo": "",
        }

    def parse_macro(self, cursor):
        source_code = self._extract_source_code(cursor.extent.start, cursor.extent.end)
        # 简化提取：移除#define和宏名后的剩余部分作为value
        lines = source_code.strip().splitlines()
        value = ""
        if lines and lines[0].startswith("#define"):
            rest = lines[0][len("#define") :].strip()
            parts = rest.split(None, 1)
            value = parts[1].strip() if len(parts) > 1 else ""
            if len(lines) > 1:
                value += "\n" + "\n".join(lines[1:])

        id = str(uuid.uuid1()).replace("-", "")
        return {
            "id": f"macro_{id}",
            "name": cursor.spelling,
            "value": value,
            "description": "",
            "class":"macro",
            "source_code": source_code,
            "docstring": (cursor.raw_comment.strip() if cursor.raw_comment else ""),
            "extent": f"{cursor.extent.start.line}-{cursor.extent.end.line}",
            "file_path": self.file_path,
            "module": "",
            "repo": "",
        }

    def _extract_source_code(self, start, end):
        """安全提取节点源码（保留原parse_func的列处理逻辑）"""
        try:
            with open(start.file.name, encoding="utf-8") as f:
                content = f.readlines()
                source = ""
                for line_idx in range(start.line - 1, end.line):
                    if line_idx == start.line - 1:
                        source = content[line_idx][start.column - 1 :]
                    elif line_idx == end.line - 1:
                        source += content[line_idx][: end.column - 1]  # 保留原逻辑
                    else:
                        source += content[line_idx]
                return source
        except (IOError, IndexError):
            return ""

    def has_implementation(self, cursor):
        return self._has_body(cursor)

    def _has_body(self, cursor):
        for child in cursor.get_children():
            if child.kind == cl.CursorKind.COMPOUND_STMT:
                return True
        return False

    def _is_local_cursor(self, cursor: cl.Cursor) -> bool:
        """判断节点是否属于当前解析文件"""
        if cursor.location.file is None:
            return False
        try:
            return os.path.samefile(cursor.location.file.name, self.file_path)
        except (OSError, ValueError):
            return False

    def __del__(self):
        # 显式释放 Index 对象
        self.index = None

    def _is_definition(self, cursor) -> bool:
        """判断STRUCT/UNION/ENUM是否为定义（非前向声明）"""
        if hasattr(cursor, "is_definition") and cursor.is_definition:
            return True
        # 回退方案：检查是否有有效子节点（字段/枚举值）
        return any(
            child.kind
            not in (
                cl.CursorKind.INVALID_FILE,
                cl.CursorKind.TYPE_REF,
                cl.CursorKind.NAMESPACE_REF,
            )
            for child in cursor.get_children()
        )
