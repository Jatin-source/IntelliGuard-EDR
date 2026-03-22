import yaml
from pathlib import Path
from src.utils.logger import logger
def load_config(config_path="config.yaml"):
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Config file not found at {config_path}! Did you delete it?")
        raise FileNotFoundError(f"Missing {config_path}")
    try:
        with open(path, "r") as file:
            config_data = yaml.safe_load(file)
            return config_data
    except Exception as e:
        logger.error(f"Failed to parse the YAML file: {e}")
        raise
config = load_config()
if __name__ == "__main__":
    project_name = config.get("project", {}).get("name", "Unknown")
    logger.info(f"Config loaded successfully! Project Name: {project_name}")
