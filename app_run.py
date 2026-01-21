import argparse
import  multiprocessing
import uvicorn

parser = argparse.ArgumentParser(description='这是一个示例程序，用于演示 argparse 的基本用法')
parser.add_argument('--workers', default=4,help='并发数量')
parser.add_argument('--host', default="0.0.0.0", help='服务器主机地址')
parser.add_argument('--port', type=int, default=14514, help='服务器端口')
args = parser.parse_args()

if __name__ == "__main__":
    uvicorn.run(
        "app_create:app",
        host=args.host,
        port=args.port,
        workers=args.workers
    )

# import os
# import sys
# import argparse
# import uvicorn

# def parse_args():
#     parser = argparse.ArgumentParser(description='FastAPI应用启动参数')
#     parser.add_argument('--workers', type=int, default=4, help='工作进程并发数量')
#     parser.add_argument('--host', type=str, default="0.0.0.0", help='服务器主机地址')
#     parser.add_argument('--port', type=int, default=14514, help='服务器端口')
#     return parser.parse_args()

# def get_config_path():

#     exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
#     external_config_file = os.path.join(exe_dir, 'config.json')
#     if os.path.exists(external_config_file):
#         return external_config_file
#     else:
#         return os.path.join(os.path.dirname(__file__), 'config.json')

# def main():

#     try:
#         args = parse_args()

#         config_file = get_config_path()

#         sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

#         from app_create import create_app
#         app = create_app(config_path=config_file)
#         uvicorn_config = uvicorn.Config(
#             app=app,
#             host=args.host,
#             port=args.port,
#             workers=args.workers,
#             log_level="info",
#         )
#         server = uvicorn.Server(uvicorn_config)
#         print(f"启动服务器: {args.host}:{args.port}, 工作进程: {args.workers}")
#         server.run()
#     except Exception as e:
#         print(f"启动应用失败: {e}")
#         sys.exit(1)

# if __name__ == "__main__":
#     main()