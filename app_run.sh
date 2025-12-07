timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
log_file="./logs/${timestamp}.txt"

echo "程序启动时间: $timestamp" > "$log_file"

nohup python3 vscode_client.py >> "$log_file" 2>&1 &

pid=$!

echo "进程ID: $pid" >> "$log_file"

echo "程序已在后台运行，进程ID: $pid"
echo "日志文件: $log_file"
