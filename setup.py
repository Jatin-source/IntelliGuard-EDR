import shutil
from pathlib import Path
def build_innovative_structure():
    print("🚀 Reorganizing MalSight structure...")
    directories = [
        "data/raw", "data/processed/static", "data/processed/dynamic", "data/processed/splits",
        "src/utils", "src/preprocessing", "src/features", "src/models", 
        "src/explainability", "src/detector",
        "outputs/models", "outputs/scalers", "outputs/shap", "outputs/metrics", "outputs/logs",
        "tests"
    ]
    for d in directories:
        Path(d).mkdir(parents=True, exist_ok=True)
        if "src" in d or "tests" in d:
            (Path(d) / "__init__.py").touch()
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
    for f in [".env", ".gitignore", "config.yaml", "requirements.txt", "main.py"]:
        Path(f).touch()
    print("✅ Project structure successfully modernized and rebuilt!")
if __name__ == "__main__":
    build_innovative_structure()
