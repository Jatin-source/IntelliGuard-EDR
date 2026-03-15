import pandas as pd
import sys
from pathlib import Path

# Ensure project root is on sys.path so this works when run directly
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.utils.logger import logger
from src.utils.config import config

def process_kaggle():
    """Loads the raw Kaggle CSV, cleans it, and saves it as a fast Parquet file."""
    
    logger.info("Starting Kaggle dataset processing...")
    
    # Get paths from our config file
    raw_dir = Path(config['paths']['raw_data']['kaggle'])
    processed_dir = Path(config['paths']['processed_data']['static'])
    
    # The main combined file from your screenshot
    csv_path = raw_dir / "Malware_and_benign_recognition.csv"
    parquet_path = processed_dir / "kaggle_cleaned.parquet"
    
    # Ensure the output directory exists before we try to save anything
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    if not csv_path.exists():
        logger.error(f"Could not find {csv_path}. Please check the file name!")
        return
        
    try:
        # 1. Load the CSV
        logger.info(f"Loading raw CSV into memory: {csv_path.name}")
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {df.shape[0]} rows and {df.shape[1]} columns.")
        
        # 2. Clean up column names (strip spaces, make lowercase for consistency)
        df.columns = df.columns.str.strip().str.lower()
        
        # 3. Handle missing values (Drop columns with >40% nulls, fill rest with 0)
        missing_percentages = df.isnull().mean()
        cols_to_drop = missing_percentages[missing_percentages > 0.4].index
        
        if len(cols_to_drop) > 0:
            logger.info(f"Dropping columns with >40% missing data: {list(cols_to_drop)}")
            df = df.drop(columns=cols_to_drop)
            
        logger.info("Filling any remaining missing values with 0...")
        df = df.fillna(0)
        
        # 4. Remove exact duplicate rows to prevent model bias
        duplicates = df.duplicated().sum()
        if duplicates > 0:
            logger.info(f"Removing {duplicates} duplicate rows...")
            df = df.drop_duplicates()
            
        # 5. Save as highly compressed Parquet
        logger.info(f"Saving cleaned data to {parquet_path}...")
        df.to_parquet(parquet_path, engine='pyarrow', compression='snappy')
        
        logger.info(f"[DONE] Kaggle processing complete! Final shape: {df.shape[0]} rows, {df.shape[1]} columns.")
        
        # Free up memory explicitly
        del df
        
    except Exception as e:
        logger.error(f"Error processing Kaggle data: {e}")

if __name__ == "__main__":
    process_kaggle()