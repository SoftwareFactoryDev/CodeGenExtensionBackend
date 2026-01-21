APP_LOG_FILE="./logs/$(date '+%Y-%m-%d_%H-%M-%S')_app.log"
WORKERS=4
echo "Starting server with $WORKERS workers..."
echo "Log file: $APP_LOG_FILE"
nohup python app_run.py > $APP_LOG_FILE 2>&1 &
echo "Server started with PID: $!"