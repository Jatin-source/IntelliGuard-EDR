import sys
import re
import pandas as pd
import xgboost as xgb
from pathlib import Path
import pyarrow.parquet as pq
from sklearn.metrics import accuracy_score, roc_auc_score
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.utils.config import config
def evaluate_ember():
    logger.info("Initializing EMBER Final Exam...")
    model_path = Path("outputs/models/expert_ember.json")
    if not model_path.exists():
        logger.error("Model not found! Check your paths.")
        return
    logger.info("Loading expert_ember.json into memory...")
    model = xgb.Booster()
    model.load_model(model_path)
    master_cols = model.feature_names
    ember_dir = Path(config['paths']['processed_data']['static']) / "ember"
    test_files = list(ember_dir.rglob("*Win32_test*.parquet"))
    if not test_files:
        logger.error("No test chunks found!")
        return
    test_file = test_files[0]
    logger.info(f"Grading AI against unseen test file: {test_file.name}")
    df = pq.read_table(test_file).to_pandas()
    y_true = df['label'].astype(int)
    cols_to_drop = ['label', 'file', 'hash', 'subset']
    X = df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore')
    X = X.select_dtypes(include=['number'])
    X.columns = [re.sub(r'[\[\]<>]', '_', str(c)) for c in X.columns]
    X = X.loc[:, ~X.columns.duplicated()]
    X = X.reindex(columns=master_cols).astype('float32')
    dtest = xgb.DMatrix(X)
    logger.info("Predicting malware signatures...")
    y_pred_prob = model.predict(dtest)
    y_pred_binary = (y_pred_prob > 0.5).astype(int)
    accuracy = accuracy_score(y_true, y_pred_binary) * 100
    auc = roc_auc_score(y_true, y_pred_prob)
    logger.info("=====================================")
    logger.info(f"🏆 FINAL EMBER ACCURACY: {accuracy:.2f}%")
    logger.info(f"📊 ROC-AUC SCORE: {auc:.4f}")
    logger.info("=====================================")
if __name__ == "__main__":
    evaluate_ember()
