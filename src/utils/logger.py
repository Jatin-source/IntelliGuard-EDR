import logging
import psutil
import os
from pathlib import Path

def setup_logger(name="MalSight"):
    """Sets up a custom logger that tracks memory usage to prevent crashes."""
    
    # Make sure the logs directory exists
    log_dir = Path("outputs/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(name)
    
    # Only set it up if it hasn't been set up already
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # The format: Time | Level | RAM Usage % | Message
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | RAM: %(memory)s | %(message)s', 
            datefmt='%H:%M:%S'
        )
        
        # Save to file
        file_handler = logging.FileHandler(log_dir / "malsight.log", encoding='utf-8')
        file_handler.setFormatter(formatter)
        
        # Print to terminal
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # This custom filter injects your live RAM % into the log message
        class MemoryFilter(logging.Filter):
            def filter(self, record):
                mem = psutil.virtual_memory()
                record.memory = f"{mem.percent:04.1f}%"
                return True
                
        logger.addFilter(MemoryFilter())
        
    return logger

# Create the main logger object that we will import into our other files
logger = setup_logger()

# Quick test function
if __name__ == "__main__":
    logger.info("Logger initialized successfully. Ready to build MalSight.")
    logger.warning("This is what a warning looks like.")