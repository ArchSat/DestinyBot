import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def create_logger(logger_name='BotLogger', log_level=logging.DEBUG, need_stdout=True):
    try:
        os.mkdir('logs')
    except:
        pass
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    if need_stdout:
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s %(levelname)s] (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"))
        logger.addHandler(stdout_handler)
    file_handler = RotatingFileHandler(filename=f'logs/{logger_name}_log.log', maxBytes=10000000, backupCount=2)
    file_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s %(levelname)s] (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"))
    logger.addHandler(file_handler)
    return logger
