import os
import logging
from logging.handlers import RotatingFileHandler
import datetime

def setup_logger(name='app'):

    os.makedirs('logs', exist_ok=True)
    
    log_file = os.environ['LOG_FILE']
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

logger_global = setup_logger()
