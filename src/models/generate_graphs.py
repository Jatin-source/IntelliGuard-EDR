import sys
import re
import pandas as pd
import xgboost as xgb
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, roc_curve, auc, accuracy_score

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.utils.logger import logger
from src.utils.config import config

def plot_and_save(y_true, y_pred, y_prob, dataset_name, output_dir):
    """Generates and saves the Confusion Matrix and ROC Curve with Accuracy included."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Calculate the exact Accuracy Percentage
    acc = accuracy_score(y_true, y_pred) * 100
    
    # 1. Plot Confusion Matrix
    cm = confusion_matrix(y_true, y_pred)
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', cbar=False,
                xticklabels=['Safe', 'Malware'], yticklabels=['Safe', 'Malware'])
    
    # Inject Accuracy into the Title
    plt.title(f'{dataset_name} Expert - Confusion Matrix\nOverall Accuracy: {acc:.2f}%')
    plt.ylabel('Actual Label')
    plt.xlabel('AI Prediction')
    plt.tight_layout()
    
    cm_path = output_dir / f"{dataset_name.lower()}_confusion_matrix.png"
    plt.savefig(cm_path, dpi=300)
    plt.close()
    logger.info(f"Saved Confusion Matrix to {cm_path}")

    # 2. Plot ROC Curve
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    roc_auc = auc(fpr, tpr)
    
    plt.figure(figsize=(6, 5))
    plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (AUC = {roc_auc:.4f})')
    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate (Safe files blocked)')
    plt.ylabel('True Positive Rate (Malware caught)')
    plt.title(f'{dataset_name} Expert - ROC Curve\nOverall Accuracy: {acc:.2f}%')
    plt.legend(loc="lower right")
    plt.tight_layout()
    
    roc_path = output_dir / f"{dataset_name.lower()}_roc_curve.png"
    plt.savefig(roc_path, dpi=300)
    plt.close()
    logger.info(f"Saved ROC Curve to {roc_path}")

def evaluate_kaggle():
    logger.info("Generating graphs for Kaggle Expert...")
    kaggle_file = Path(config['paths']['processed_data']['static']) / "kaggle_cleaned.parquet"
    model_path = Path("outputs/models/expert_kaggle.json")
    
    if not kaggle_file.exists() or not model_path.exists():
        logger.error("Kaggle data or model missing. Skipping.")
        return

    df = pd.read_parquet(kaggle_file)
    target_col = 'label' if 'label' in df.columns else 'malicious'
    y = df[target_col].astype(int)
    cols_to_drop = ['label', 'malicious', 'family', 'hash', 'file']
    X = df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore').select_dtypes(include=['number'])
    
    # We need the exact test set we used during training
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model = xgb.XGBClassifier()
    model.load_model(model_path)
    
    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]
    
    out_dir = Path("outputs/visuals")
    plot_and_save(y_test, predictions, probabilities, "Kaggle", out_dir)

def evaluate_bodmas():
    logger.info("Generating graphs for BODMAS Expert...")
    # NOTE: Update this filename if your BODMAS file is named differently!
    bodmas_file = Path(config['paths']['processed_data']['static']) / "bodmas_cleaned.parquet" 
    model_path = Path("outputs/models/expert_bodmas.json")
    
    # Fallback to .npz if you used numpy arrays for BODMAS
    if not bodmas_file.exists():
        bodmas_file = Path(config['paths']['processed_data']['static']) / "bodmas.npz"

    if not bodmas_file.exists() or not model_path.exists():
        logger.error("BODMAS data or model missing. Skipping.")
        return

    # Assuming parquet format matching Kaggle's setup
    try:
        df = pd.read_parquet(bodmas_file)
        y = df['label'].astype(int)
        X = df.drop(columns=['label', 'file', 'hash', 'family'], errors='ignore').select_dtypes(include=['number'])
        _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    except Exception:
        import numpy as np
        logger.info("Loading BODMAS from .npz format...")
        data = np.load(bodmas_file)
        X = data['X']
        y = data['y']
        _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = xgb.XGBClassifier()
    model.load_model(model_path)
    
    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]
    
    out_dir = Path("outputs/visuals")
    plot_and_save(y_test, predictions, probabilities, "BODMAS", out_dir)

def evaluate_ember():
    logger.info("Generating graphs for EMBER Expert...")
    model_path = Path("outputs/models/expert_ember.json")
    ember_dir = Path(config['paths']['processed_data']['static']) / "ember"
    
    if not model_path.exists():
        logger.error("EMBER model missing. Skipping.")
        return

    # Grab the unseen test files
    test_files = list(ember_dir.rglob("*Win32_test*.parquet"))
    if not test_files:
        logger.error("No EMBER test chunks found! Skipping.")
        return

    test_file = test_files[0]
    logger.info(f"Loading unseen EMBER test file: {test_file.name}")

    # Load model and feature names using standard Booster (safest for EMBER)
    model = xgb.Booster()
    model.load_model(model_path)
    master_cols = model.feature_names

    # Load test data
    df = pd.read_parquet(test_file)
    y = df['label'].astype(int)

    cols_to_drop = ['label', 'file', 'hash', 'subset']
    X = df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore')
    X = X.select_dtypes(include=['number'])
    X.columns = [re.sub(r'[\[\]<>]', '_', str(c)) for c in X.columns]
    X = X.loc[:, ~X.columns.duplicated()]

    # Reindex to match the exact mathematical columns the model learned
    X = X.reindex(columns=master_cols).astype('float32')

    # Predict using DMatrix
    dtest = xgb.DMatrix(X)
    probabilities = model.predict(dtest)
    predictions = (probabilities > 0.5).astype(int)

    out_dir = Path("outputs/visuals")
    plot_and_save(y, predictions, probabilities, "EMBER", out_dir)

if __name__ == "__main__":
    evaluate_kaggle()
    evaluate_bodmas()
    evaluate_ember()
    logger.info("✅ All visual graphs successfully generated and saved to outputs/visuals!")