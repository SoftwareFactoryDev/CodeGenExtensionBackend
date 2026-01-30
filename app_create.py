import os
from copy import deepcopy

from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import clang.cindex as cl

os.environ["LOG_FILE"] = os.path.join('logs', f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_service.txt")

from app.logger import logger_global
from app.config import config
from app.routes import router

def create_app(config_path: str = './config.json'):

    # 声明logger对象
    logger = deepcopy(logger_global)

    # 初始化配置信息
    config.set_path(config_path)
    config.load()
    logger_global.info(config.get())

    # 设置clang信息
    lib_path = config._data.get("codeBaseBuild", {}).get("clangPath")
    if lib_path:
        cl.Config.set_library_file(lib_path)
    else:
        logger.error("clangPath is not set in config.json")
        exit(1)

    # 创建FastAPI应用
    app = FastAPI(title="Asset Management API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app