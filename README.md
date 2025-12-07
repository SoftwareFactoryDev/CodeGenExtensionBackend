# 代码生成插件使用教程

## 简介

当当前文档为代码生成插件的后端实现

## 环境要求：
* LLVM 19.7.1
* GCC 7.5.0
* Python 3.11.*

## 使用方法：

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 部署代码审查工具

从[链接](https://pan.baidu.com/s/14JFohl-MJKBrG0-a_gzN8A?pwd=sibt) 提取码: sibt
下载 analyzer.tar.gz 文件，并放到 ./client/CodeCheck 目录下，然后执行如下命令：

```bash
cd ./client/CodeCheck
tar -zxvf analyzer.tar.gz
```

3. 启动服务
首先激活执行当前服务对应的Python环境
```bash
cd ../..
nohup ./run_vscode_client.sh > /dev/null 2>&1 &
```

4. 查看进程执行状态
```bash
ps -aux | grep vscode_client
```