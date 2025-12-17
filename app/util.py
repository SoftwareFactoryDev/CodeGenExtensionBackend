import json
import chardet

def get_encode(file_path):
    """
    获取文件的编码方式

    Args:
        path : 文件地址

    Returns:
        str: 解析到的文件编码方式
    """    
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        encoding = chardet.detect(raw_data)['encoding']
    return encoding