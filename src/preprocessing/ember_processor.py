import pandas as pd
import json
import sys
import gc
from pathlib import Path

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.utils.logger import logger
from src.utils.config import config

def process_full_ember():
    """Processes the entire EMBER dataset, drops data leakage columns, and saves as Parquet."""
    
    logger.info("Starting full EMBER processing pipeline...")
    
    raw_ember_dir = Path(config['paths']['raw_data']['ember'])
    processed_ember_dir = Path(config['paths']['processed_data']['static']) / "ember"
    
    # We will look for all JSONL files
    json_files = list(raw_ember_dir.rglob("*.json*"))
    total_files = len(json_files)
    
    if total_files == 0:
        logger.error("No JSON files found!")
        return

    # Columns that cause Data Leakage or are useless for structural ML
    leakage_cols = ['md5', 'sha1', 'sha256', 'tlsh', 'first_submission_date', 
                    'last_analysis_date', 'detection_ratio', 'family']
                    
    for idx, file_path in enumerate(json_files, 1):
        logger.info(f"Processing chunk {idx}/{total_files}: {file_path.name}")
        
        # Recreate the folder structure (e.g., Win32_train) inside the processed_data folder
        relative_path = file_path.parent.name
        output_dir = processed_ember_dir / relative_path
        output_dir.mkdir(parents=True, exist_ok=True)
        
        out_file = output_dir / f"{file_path.stem}.parquet"
        
        # Innovative touch: Skip if already processed so we can resume if the script is ever stopped!
        if out_file.exists():
            logger.info(f"Skipping {out_file.name}, already processed.")
            continue
            
        records = []
        try:
            # Load the individual chunk file
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    records.append(json.loads(line.strip()))
                    
            if not records:
                continue
                
            # Flatten the JSON structure into tabular columns
            df = pd.json_normalize(records)
            
            # Prevent Data Leakage
            cols_to_drop = [c for c in leakage_cols if c in df.columns]
            df.drop(columns=cols_to_drop, inplace=True)
            
            # RAM Optimization: Downcast 64-bit floats to 32-bit
            float_cols = df.select_dtypes(include=['float64']).columns
            df[float_cols] = df[float_cols].astype('float32')
            
            # Save as highly compressed Parquet
            df.to_parquet(out_file, engine='pyarrow', compression='snappy')
            
            # Aggressive Memory Wipe
            del df
            del records
            gc.collect()
            
            logger.info(f"Saved optimized parquet: {out_file.name} | RAM: OK")
            
        except Exception as e:
            logger.error(f"Failed on {file_path.name}: {e}")

    logger.info("[DONE] All EMBER chunks successfully processed and compressed!")

if __name__ == "__main__":
    process_full_ember()