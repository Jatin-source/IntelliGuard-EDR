import os
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# ── Paths ────────────────────────────────────────────────────────────────
DATA_PATH = r"outputs\dynamic_features.csv"
MODEL_OUT = r"outputs\models\expert_cic_dynamic.json"

def train_dynamic_model():
    print(f"[*] Loading flattened dynamic dataset from {DATA_PATH}...")
    try:
        df = pd.read_csv(DATA_PATH)
    except FileNotFoundError:
        print("❌ Error: dynamic_features.csv not found.")
        return
    
    if df.empty:
        print("❌ Error: Dataset is empty.")
        return

    # ── DATA DIAGNOSTICS (The Fix) ───────────────────────────────────────
    label_counts = df['label'].value_counts().to_dict()
    print("\n[*] 📊 DATASET BREAKDOWN:")
    print(f"    Safe (0):    {label_counts.get(0, 0)} files")
    print(f"    Malware (1): {label_counts.get(1, 0)} files")
    
    if len(label_counts) < 2:
        print("\n⚠️  CRITICAL WARNING: Your dataset only has ONE class!")
        print("⚠️  The AI cannot learn to distinguish between safe and malicious behavior.")
        print("⚠️  The model will train, but it will be biased.")
    print("────────────────────────────────────────────────────────────\n")

    X = df.drop(columns=['hash', 'label'])
    y = df['label']
    
    # If there is only 1 class, we cannot use 'stratify'
    do_stratify = y if len(label_counts) > 1 else None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=do_stratify
    )
    
    print("[*] Training the CIC-DIG-2025 Dynamic XGBoost Expert...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        tree_method='hist', 
        random_state=42,
        eval_metric='logloss'
    )
    
    model.fit(X_train, y_train)
    
    print("[*] Evaluating the Expert's Accuracy on unseen data...")
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    
    print("\n════════════════════════════════════════════════════════════")
    print(f"✅ Dynamic Expert Trained Successfully!")
    print(f"🎯 Accuracy on Unseen Test Data: {acc * 100:.2f}%")
    print("════════════════════════════════════════════════════════════\n")
    
    # Safely print the classification report without crashing
    present_classes = np.unique(y_test)
    all_names = {0: 'Safe (0)', 1: 'Malware (1)'}
    present_names = [all_names[c] for c in present_classes]
    
    print(classification_report(y_test, y_pred, labels=present_classes, target_names=present_names))
    
    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    model.save_model(MODEL_OUT)
    print(f"\n[*] 💾 Model saved to: {MODEL_OUT}")

if __name__ == "__main__":
    train_dynamic_model()