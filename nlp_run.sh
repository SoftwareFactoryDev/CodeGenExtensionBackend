mkdir -p logs

LOG_FILE="logs/$(date '+%Y-%m-%d_%H-%M-%S')_app.log"

WORKERS=4

# 启动uvicorn服务器
echo "Starting server with $WORKERS workers..."
echo "Log file: $LOG_FILE"

nohup python nlp_embedding_server.py > $LOG_FILE 2>&1 &

echo "Server started with PID: $!"