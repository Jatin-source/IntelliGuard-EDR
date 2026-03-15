import sys
import gc
import re
import random
import pandas as pd
import xgboost as xgb
from pathlib import Path
import pyarrow.parquet as pq

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.utils.logger import logger
from src.utils.config import config


def get_ember_columns(file_paths):
    logger.info("Scanning EMBER chunks for Master Schema...")
    master_cols = set()

    for f in file_paths:
        schema = pq.read_schema(f)
        for name, pa_type in zip(schema.names, schema.types):
            type_str = str(pa_type).lower()
            if type_str not in ['string', 'binary', 'object']:
                clean_name = re.sub(r'[\[\]<>]', '_', str(name))
                master_cols.add(clean_name)

    for col in ['label', 'file', 'hash', 'subset']:
        master_cols.discard(col)

    return sorted(list(master_cols))


def train_ember_expert():

    logger.info("Initializing MICRO-BATCHED EMBER Expert AI Pipeline...")

    ember_dir = Path(config['paths']['processed_data']['static']) / "ember"
    all_ember_files = list(ember_dir.rglob("*Win32_train*.parquet"))

    if not all_ember_files:
        logger.error("No EMBER Parquet chunks found!")
        return

    num_files_to_use = min(30, len(all_ember_files))
    ember_files = random.sample(all_ember_files, num_files_to_use)

    logger.info(f"Training on {num_files_to_use} random Win32 EMBER train chunks.")

    master_cols = get_ember_columns(ember_files)

    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'tree_method': 'hist',
        'device': 'cuda',        
        'max_depth': 6,
        'learning_rate': 0.05,   
        'subsample': 0.8
    }

    logger.info("Starting GPU Incremental Micro-Batch Training...")

    model = None
    epochs = 1
    boost_rounds_per_batch = 2  # Keep this low because we are looping many batches

    for epoch in range(1, epochs + 1):
        logger.info(f"\n--- Epoch {epoch}/{epochs} ---")

        for i, file_path in enumerate(ember_files):
            logger.info(f"Opening File {i+1}/{len(ember_files)} : {file_path.name}")

            pf = pq.ParquetFile(file_path)
            
            # ✅ THE FIX: Read only 5000 rows at a time (Uses ~1.2GB RAM instead of 13.2GB)
            for batch_idx, batch in enumerate(pf.iter_batches(batch_size=5000)):
                
                df = batch.to_pandas()
                y = df['label'].astype(int)

                cols_to_drop = ['label', 'file', 'hash', 'subset']
                X = df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore')

                X = X.select_dtypes(include=['number'])
                X.columns = [re.sub(r'[\[\]<>]', '_', str(c)) for c in X.columns]
                X = X.loc[:, ~X.columns.duplicated()]

                # fill_value=0 ensures missing columns default to 0, saving RAM and preventing NaN bugs
                X = X.reindex(columns=master_cols, fill_value=0).astype('float32')

                dtrain = xgb.DMatrix(X, label=y)

                # Train incrementally on the micro-batch
                model = xgb.train(
                    params,
                    dtrain,
                    num_boost_round=boost_rounds_per_batch,
                    xgb_model=model
                )

                del df, X, y, dtrain, batch
                gc.collect()
                
            logger.info(f" -> Successfully finished all micro-batches in File {i+1}")

    model_dir = Path("outputs/models")
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "expert_ember.json"

    model.save_model(model_path)
    logger.info(f"[DONE] EMBER Expert saved to {model_path}")


if __name__ == "__main__":
    train_ember_expert()