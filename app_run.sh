mkdir -p logs

APP_LOG_FILE="logs/$(date '+%Y-%m-%d_%H-%M-%S')_app.log"

WORKERS=4

# 启动uvicorn服务器
echo "Starting server with $WORKERS workers..."
echo "Log file: $LOG_FILE"

uvicorn app_run:app --host 0.0.0.0 --port 14514 --workers $WORKERS --log-level info --access-log > $LOG_FILE 2>&1 &

echo "Server started with PID: $!"