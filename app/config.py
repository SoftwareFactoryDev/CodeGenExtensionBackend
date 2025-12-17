from copy import deepcopy
from functools import lru_cache
from typing import Dict, Any
import json

from app.util import get_encode
from app.logger import logger_global
logger = deepcopy(logger_global)
class Config:
    def __init__(self):
        self._path: str = ""
        self._data: Dict[str, Any] = {}

    def load(self):
        """
        自适应读取JSON文件，自动检测文件编码

        
        Returns:
            dict: 解析后的JSON数据ikm
        """
        file_path = self._path
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self._data =  json.load(f)
        except UnicodeDecodeError:
            encode = get_encode(file_path)
            try:
                # 使用检测到的编码读取文件
                with open(file_path, 'r', encoding=encode) as f:
                    self._data =  json.load(f)
            except Exception as e:
                logger.error(f"使用编码 {encode} 读取配置失败: {str(e)}")
                raise
    
    def set_path(self, file_path):
        """
        设置配置文件地址

        Args:
            file_path : 配置文件地址
        """
        self._path = file_path
    
    def get(self) -> Dict[str, Any]:
        """获取配置"""
        return self._data

# 创建全局配置实例
config = Config()
