import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import sys
from pathlib import Path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.utils.config import config
def run_kaggle_eda():
    logger.info("Starting Exploratory Data Analysis for Kaggle...")
    processed_dir = Path(config['paths']['processed_data']['static'])
    metrics_dir = Path(config['paths']['outputs']['metrics'])
    metrics_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = processed_dir / "kaggle_cleaned.parquet"
    if not parquet_path.exists():
        logger.error(f"Cannot find {parquet_path}. Run the processor first!")
        return
    logger.info("Loading Parquet file...")
    df = pd.read_parquet(parquet_path)
    logger.info(f"Columns available: {list(df.columns)}")
    target_col = None
    for col in ['class', 'label', 'legitimate', 'classification', 'malicious']:
        if col in df.columns:
            target_col = col
            break
    if not target_col:
        logger.warning("Could not automatically find the target/label column. Skipping class balance plot.")
    else:
        logger.info(f"Found target column: '{target_col}'. Plotting class balance...")
        plt.figure(figsize=(8, 6))
        ax = sns.countplot(data=df, x=target_col, palette="Set2")
        plt.title("Malware vs Benign File Count")
        plt.xlabel("Class (0 = Benign, 1 = Malware)")
        plt.ylabel("Count")
        for p in ax.patches:
            ax.annotate(f'{p.get_height()}', (p.get_x() + p.get_width() / 2., p.get_height()),
                        ha='center', va='bottom', fontsize=12, color='black', xytext=(0, 5),
                        textcoords='offset points')
        plt.tight_layout()
        balance_path = metrics_dir / "kaggle_class_balance.png"
        plt.savefig(balance_path)
        logger.info(f"Saved class balance plot to {balance_path}")
    logger.info("Calculating feature correlations...")
    plt.figure(figsize=(12, 10))
    corr_matrix = df.corr(numeric_only=True)
    sns.heatmap(corr_matrix, cmap="coolwarm", annot=False, fmt=".2f", linewidths=0.5)
    plt.title("Feature Correlation Heatmap")
    plt.tight_layout()
    heatmap_path = metrics_dir / "kaggle_correlation_heatmap.png"
    plt.savefig(heatmap_path)
    logger.info(f"Saved correlation heatmap to {heatmap_path}")
    logger.info("[DONE] EDA Complete! Check your outputs/metrics folder for the PNG files.")
if __name__ == "__main__":
    run_kaggle_eda()
