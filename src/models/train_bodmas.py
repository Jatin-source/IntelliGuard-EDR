import sys
import pandas as pd
import xgboost as xgb
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.utils.config import config
def train_bodmas_expert():
    logger.info("Initializing BODMAS Expert AI Pipeline...")
    bodmas_file = Path(config['paths']['processed_data']['static']) / "bodmas_cleaned.parquet"
    if not bodmas_file.exists():
        logger.error("BODMAS data not found!")
        return
    logger.info("Loading BODMAS dataset into memory...")
    df = pd.read_parquet(bodmas_file)
    logger.info("Splitting data into Training and Testing sets...")
    y = df['label'].astype(int)
    X = df.drop(columns=['label', 'family'], errors='ignore')
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        tree_method='hist',
        device='cuda', 
        random_state=42
    )
    logger.info("Firing up the GTX 1650. Training BODMAS Expert...")
    model.fit(X_train, y_train)
    logger.info("Evaluating AI accuracy on hidden test data...")
    predictions = model.predict(X_test)
    acc = accuracy_score(y_test, predictions)
    logger.info(f"BODMAS Expert Accuracy: {acc * 100:.2f}%")
    logger.info("\n" + classification_report(y_test, predictions))
    model_dir = Path("outputs/models")
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "expert_bodmas.json"
    model.save_model(model_path)
    logger.info(f"[DONE] BODMAS Expert successfully saved to {model_path}")
if __name__ == "__main__":
    train_bodmas_expert()
