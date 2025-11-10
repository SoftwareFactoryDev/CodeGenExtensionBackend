import os
import clang.cindex as cl
from CodeBaseBuild.llm_gen import generate_api

class CParser:

    def __init__(self, libclang_path):
        
        if libclang_path:
            cl.Config.set_library_file(libclang_path)
        else:
            raise ValueError("Please provide the path to libclang shared library -> libclang.dll.")
        self.index = cl.Index.create(excludeDecls=True)
        self.functions = []

    def parse_file(self, c_file_path):

        self.file_path = c_file_path
        
        if not os.path.isfile(c_file_path):
            raise FileNotFoundError(c_file_path)

        tu = self.index.parse(c_file_path)

        self.functions.clear()
        self._traverse(tu.cursor)
        return self.functions

    def _traverse(self, cursor: cl.Cursor):
        if cursor.kind.is_declaration() and cursor.kind == cl.CursorKind.FUNCTION_DECL:
            if not self._is_local_func(cursor):
                return
            if self._has_body(cursor):
                func_json = self.parse_func(cursor)
                if self.has_implementation(cursor):
                    self.functions.append(func_json)
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
            params.append({
                "name": parm.spelling,
                "type": parm.type.spelling
            })

        # 完整签名
        signature = f"{result_type} {func_name}(" + ", ".join(
            f"{p['type']} {p['name']}" for p in params) + ")"

        # 源码区间（ extents ）
        extent = cursor.extent
        start: cl.SourceLocation = extent.start
        end: cl.SourceLocation = extent.end
        source_code = ""
        with open(start.file.name, encoding="utf-8") as f:
            content =  f.readlines()
            for line in range(start.line-1, end.line):
                if line == start.line-1:
                    source_code = "".join(content[line][start.column-1:])
                elif line == end.line-1:
                    source_code += "".join(content[line][:end.column-1])
                else: 
                    source_code += content[line]
        return {
            "name": func_name,
            "return_type": result_type,
            "signature": signature,
            "params": params,
            "summary": 'Not Generated',
            "source_code": source_code,
            "extent": {
                "begin": {"line": start.line, "column": start.column},
                "end":   {"line": end.line,   "column": end.column}
            }
        }

    def has_implementation(self, cursor):
        return self._has_body(cursor)

    def _has_body(self, cursor):
        for child in cursor.get_children():
            if child.kind == cl.CursorKind.COMPOUND_STMT:
                return True
        return False

    def _is_local_func(self, cursor: cl.Cursor):
        cursor_loc =  cursor.location
        cursor_file = cursor_loc.file.name
        is_local_func  = os.path.samefile(cursor_file, self.file_path)
        return is_local_func
    
    def __del__(self):
        # 显式释放 Index 对象
        self.index = None
