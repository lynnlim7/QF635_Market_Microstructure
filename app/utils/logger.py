import logging 
import os 
import sys
from datetime import datetime 
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler


def setup_logger(
        logger_name: str,
        logger_path: str,
        level: str = logging.INFO,
        backup_count: int = int(os.environ.get("LOG_FILE_BACKUP_COUNT", 5)), # order history
        max_bytes: int = 10*1024*1024, # 10 mb default
        rotation_int: datetime|str = "midnight", 
        rotate_utc: bool = True, # universal time rotation
        log_type: str = None,
        enable_console: bool = False
) -> logging.Logger:
    log_file = logger_name + ".log"
    log_filepath = os.path.join(logger_path, log_file)
    os.makedirs(logger_path, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s") # trade formatter
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # log to console
    if not logger.hasHandlers():
        if enable_console:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        WRITE_LOG = os.environ.get("WRITE_LOG", "TRUE")
        TIMED_LOG = os.environ.get("TIMED_LOG", "TRUE")

        if WRITE_LOG == "TRUE":
            try:
                if TIMED_LOG == "TRUE":
                    if isinstance(rotation_int, str):
                        # file logging on disk - order and trade logging
                        file_handler = TimedRotatingFileHandler(log_filepath, when = rotation_int, utc = rotate_utc, backupCount=backup_count)
                    else:
                        file_handler = TimedRotatingFileHandler(log_filepath, atTime = rotation_int, utc = rotate_utc, backupCount=backup_count)
                else:
                    file_handler = RotatingFileHandler(log_filepath, maxBytes=max_bytes, backupCount=backup_count)
                
                
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            
            except Exception as file_error:
                logger.error(f"Failed to set up file logging: {str(file_error)}")

                # continue with console logging
        logger.setLevel(level)

        # prevent it from writing into the higher leve
        logger.propagate = False
        return logger


def set_basic_logger(_logger_name: str) -> logging.Logger:
    logger = setup_logger(
        logger_name=_logger_name,
        logger_path="./logs/",
        enable_console=True
    )
    # prevent duplicated logs
    logger.propagate = False
    return logger

main_logger = set_basic_logger("main")
