import pandas as pd
import sys
from pathlib import Path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.utils.config import config
def process_kaggle():
    logger.info("Starting Kaggle dataset processing...")
    raw_dir = Path(config['paths']['raw_data']['kaggle'])
    processed_dir = Path(config['paths']['processed_data']['static'])
    csv_path = raw_dir / "Malware_and_benign_recognition.csv"
    parquet_path = processed_dir / "kaggle_cleaned.parquet"
    processed_dir.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        logger.error(f"Could not find {csv_path}. Please check the file name!")
        return
    try:
        logger.info(f"Loading raw CSV into memory: {csv_path.name}")
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {df.shape[0]} rows and {df.shape[1]} columns.")
        df.columns = df.columns.str.strip().str.lower()
        missing_percentages = df.isnull().mean()
        cols_to_drop = missing_percentages[missing_percentages > 0.4].index
        if len(cols_to_drop) > 0:
            logger.info(f"Dropping columns with >40% missing data: {list(cols_to_drop)}")
            df = df.drop(columns=cols_to_drop)
        logger.info("Filling any remaining missing values with 0...")
        df = df.fillna(0)
        duplicates = df.duplicated().sum()
        if duplicates > 0:
            logger.info(f"Removing {duplicates} duplicate rows...")
            df = df.drop_duplicates()
        logger.info(f"Saving cleaned data to {parquet_path}...")
        df.to_parquet(parquet_path, engine='pyarrow', compression='snappy')
        logger.info(f"[DONE] Kaggle processing complete! Final shape: {df.shape[0]} rows, {df.shape[1]} columns.")
        del df
    except Exception as e:
        logger.error(f"Error processing Kaggle data: {e}")
if __name__ == "__main__":
    process_kaggle()
