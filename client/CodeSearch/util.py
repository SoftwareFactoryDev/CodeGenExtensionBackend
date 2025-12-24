from copy import deepcopy
import json

from app.logger import logger_global

def check_repo_json(file_path):
    
    logger = deepcopy(logger_global)
    logger.info(f"系统级代码资产信息校验：{file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        logger.warning("JSON文件格式不正确，无法解析")
        return False
    except FileNotFoundError:
        logger.warning("错误：文件未找到")
        return False
    except Exception as e:
        logger.warning(f"错误：{str(e)}")
        return False

    # 检查顶级字段
    required_fields = ['name', 'version', 'description', 'modules', "desp_emb"]
    for field in required_fields:
        if field not in data:
            logger.warning(f"缺少必需字段 '{field}'")
            return False
        if not data[field]:
            logger.warning(f"字段 '{field}' 不能为空")
            return False

    # 检查modules字段中的每个module
    if not isinstance(data['modules'], list):
        logger.warning("modules字段不是数组类型") 
        return False
    for i, module in enumerate(data['modules']):
        if not isinstance(module, dict):
            logger.warning(f"modules[{i}] 必须是对象类型") 
            return False

        # 检查module中的必需字段
        module_required_fields = ['name', 'description', 'desp_emb']
        for field in module_required_fields:
            if field not in module:
                logger.warning(f"modules[{i}] 缺少必需字段 '{field}'") 
                return False
            if not module[field]:
                logger.warning(f"modules[{i}] 的字段 '{field}' 不能为空") 
                return False

        # 检查desp_emb是否为数组
        if not isinstance(module['desp_emb'], list):
            logger.warning(f"modules[{i}] 的 desp_emb 必须是数组类型") 
            return False

    return True
