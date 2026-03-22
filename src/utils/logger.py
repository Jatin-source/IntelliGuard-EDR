import logging
import psutil
import os
from pathlib import Path
def setup_logger(name="MalSight"):
    log_dir = Path("outputs/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | RAM: %(memory)s | %(message)s', 
            datefmt='%H:%M:%S'
        )
        file_handler = logging.FileHandler(log_dir / "malsight.log", encoding='utf-8')
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        class MemoryFilter(logging.Filter):
            def filter(self, record):
                mem = psutil.virtual_memory()
                record.memory = f"{mem.percent:04.1f}%"
                return True
        logger.addFilter(MemoryFilter())
    return logger
logger = setup_logger()
if __name__ == "__main__":
    logger.info("Logger initialized successfully. Ready to build MalSight.")
    logger.warning("This is what a warning looks like.")
