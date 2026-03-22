import shutil
from pathlib import Path

def build_innovative_structure():
    print("🚀 Reorganizing MalSight structure...")
    
    # 1. Create the necessary skeleton
    directories = [
        "data/raw", "data/processed/static", "data/processed/dynamic", "data/processed/splits",
        "src/utils", "src/preprocessing", "src/features", "src/models", 
        "src/explainability", "src/detector",
        "outputs/models", "outputs/scalers", "outputs/shap", "outputs/metrics", "outputs/logs",
        "tests"
    ]

    for d in directories:
        Path(d).mkdir(parents=True, exist_ok=True)
        # Add __init__.py to make Python recognize these as modules
        if "src" in d or "tests" in d:
            (Path(d) / "__init__.py").touch()

    # 2. Move your existing dataset folders into data/raw/
    moves = {
        "Bodmas": "data/raw/bodmas",
        "CIC DGG 2025": "data/raw/cic",
        "Ember": "data/raw/ember",
        "Kaggle": "data/raw/kaggle"
    }

    for old_name, new_path in moves.items():
        if Path(old_name).exists():
            print(f"📦 Moving '{old_name}' -> '{new_path}'")
            shutil.move(old_name, new_path)

    # 3. Create base config files
    for f in [".env", ".gitignore", "config.yaml", "requirements.txt", "main.py"]:
        Path(f).touch()

    print("✅ Project structure successfully modernized and rebuilt!")

if __name__ == "__main__":
    build_innovative_structure()