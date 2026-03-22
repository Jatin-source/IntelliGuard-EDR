import pandas as pd
import json
import sys
import gc
from pathlib import Path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.utils.config import config
def process_full_ember():
    logger.info("Starting full EMBER processing pipeline...")
    raw_ember_dir = Path(config['paths']['raw_data']['ember'])
    processed_ember_dir = Path(config['paths']['processed_data']['static']) / "ember"
    json_files = list(raw_ember_dir.rglob("*.json*"))
    total_files = len(json_files)
    if total_files == 0:
        logger.error("No JSON files found!")
        return
    leakage_cols = ['md5', 'sha1', 'sha256', 'tlsh', 'first_submission_date', 
                    'last_analysis_date', 'detection_ratio', 'family']
    for idx, file_path in enumerate(json_files, 1):
        logger.info(f"Processing chunk {idx}/{total_files}: {file_path.name}")
        relative_path = file_path.parent.name
        output_dir = processed_ember_dir / relative_path
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{file_path.stem}.parquet"
        if out_file.exists():
            logger.info(f"Skipping {out_file.name}, already processed.")
            continue
        records = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    records.append(json.loads(line.strip()))
            if not records:
                continue
            df = pd.json_normalize(records)
            cols_to_drop = [c for c in leakage_cols if c in df.columns]
            df.drop(columns=cols_to_drop, inplace=True)
            float_cols = df.select_dtypes(include=['float64']).columns
            df[float_cols] = df[float_cols].astype('float32')
            df.to_parquet(out_file, engine='pyarrow', compression='snappy')
            del df
            del records
            gc.collect()
            logger.info(f"Saved optimized parquet: {out_file.name} | RAM: OK")
        except Exception as e:
            logger.error(f"Failed on {file_path.name}: {e}")
    logger.info("[DONE] All EMBER chunks successfully processed and compressed!")
if __name__ == "__main__":
    process_full_ember()
