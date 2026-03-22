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
def train_kaggle_expert():
    logger.info("Initializing Kaggle (PE Header) Expert AI Pipeline...")
    kaggle_file = Path(config['paths']['processed_data']['static']) / "kaggle_cleaned.parquet"
    if not kaggle_file.exists():
        logger.error("Kaggle data not found! Did preprocessing finish?")
        return
    logger.info("Loading Kaggle dataset into memory...")
    df = pd.read_parquet(kaggle_file)
    target_col = 'label' if 'label' in df.columns else 'malicious'
    logger.info("Splitting data into Training and Testing sets...")
    y = df[target_col].astype(int)
    cols_to_drop = ['label', 'malicious', 'family', 'hash', 'file']
    X = df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore')
    X = X.select_dtypes(include=['number'])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        tree_method='hist',
        device='cuda', 
        random_state=42
    )
    logger.info("Firing up the GTX 1650. Training Kaggle Expert...")
    model.fit(X_train, y_train)
    logger.info("Evaluating AI accuracy on hidden test data...")
    predictions = model.predict(X_test)
    acc = accuracy_score(y_test, predictions)
    logger.info(f"Kaggle Expert Accuracy: {acc * 100:.2f}%")
    logger.info("\n" + classification_report(y_test, predictions))
    model_dir = Path("outputs/models")
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "expert_kaggle.json"
    model.save_model(model_path)
    logger.info(f"[DONE] Kaggle Expert successfully saved to {model_path}")
if __name__ == "__main__":
    train_kaggle_expert()
