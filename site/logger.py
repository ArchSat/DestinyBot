import logging
import os
import sys


def create_logger(logger_name='BotLogger'):
    try:
        os.mkdir('logs')
    except:
        pass
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s %(levelname)s] (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"))
    logger.addHandler(stdout_handler)
    file_handler = logging.FileHandler(filename=f'logs/{logger_name}_log.log', mode='a')
    file_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s %(levelname)s] (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"))
    logger.addHandler(file_handler)
    return logger
