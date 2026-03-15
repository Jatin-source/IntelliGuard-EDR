import yaml
from pathlib import Path
from src.utils.logger import logger

def load_config(config_path="config.yaml"):
    """Reads our central settings file so we never have to hardcode paths."""
    
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Config file not found at {config_path}! Did you delete it?")
        raise FileNotFoundError(f"Missing {config_path}")

    try:
        with open(path, "r") as file:
            config_data = yaml.safe_load(file)
            # We won't log this every single time it's imported to avoid spamming the terminal,
            # but it will silently hold our settings in memory.
            return config_data
            
    except Exception as e:
        logger.error(f"Failed to parse the YAML file: {e}")
        raise

# We instantiate it once here. 
# Now, any other file can just say: `from src.utils.config import config`
config = load_config()

if __name__ == "__main__":
    # Let's test if it can read the project name we set in Step 0
    project_name = config.get("project", {}).get("name", "Unknown")
    logger.info(f"Config loaded successfully! Project Name: {project_name}")