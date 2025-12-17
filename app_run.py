import argparse
import multiprocessing
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import clang.cindex as cl
from copy import deepcopy
from app.config import config
from app.routes import router
from app.logger import logger_global
def create_app(config_path: str = './config.json'):
    logger = deepcopy(logger_global)
    config.set_path(config_path)
    config.load()
    lib_path = config._data.get("codeBaseBuild", {}).get("clangPath")
    if lib_path:
        cl.Config.set_library_file(lib_path)
    else:
        logger.error("clangPath is not set in config.json")
        exit(1)

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

# 创建应用实例
app = create_app()

# if __name__ == '__main__':
#     uvicorn.run(app, host='0.0.0.0', port=14514)