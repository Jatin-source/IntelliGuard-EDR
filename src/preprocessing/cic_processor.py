import sys
import pandas as pd
import numpy as np
import torch
from pathlib import Path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.utils.config import config
def process_cic_dynamic():
    logger.info("Starting CIC Dynamic Analysis processing...")
    raw_dir = Path(config['paths']['raw_data']['cic'])
    processed_dir = Path(config['paths']['processed_data']['dynamic'])
    processed_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = processed_dir / "cic_dynamic_cleaned.parquet"
    csv_files = list(raw_dir.rglob("*.csv"))
    if not csv_files:
        logger.error("Could not find the cfg_map.csv file!")
        return
    csv_path = csv_files[0]
    logger.info(f"Loading metadata from {csv_path.name}...")
    df_meta = pd.read_csv(csv_path)
    processed_records = []
    pt_files = list(raw_dir.rglob("*.pt"))
    pt_dict = {f.stem: f for f in pt_files}
    logger.info(f"Extracting {len(pt_files)} PyTorch Geometric tensors...")
    for index, row in df_meta.iterrows():
        file_hash = str(row['hash'])
        if file_hash in pt_dict:
            try:
                tensor = torch.load(pt_dict[file_hash], weights_only=False, map_location=torch.device('cpu'))
                if hasattr(tensor, 'x') and tensor.x is not None:
                    arr = tensor.x.detach().cpu().numpy()
                elif isinstance(tensor, torch.Tensor):
                    arr = tensor.detach().cpu().numpy()
                else:
                    arr = np.array(tensor)
                if arr.ndim > 1:
                    arr = np.mean(arr, axis=0) 
                flat_vector = arr.flatten()
                record = {
                    'label': row['label'],
                    'number_nodes': row['number_nodes'],
                    'number_edges': row['number_edges'],
                    'number_components': row['number_weakly_connected_components'],
                    'file_size': row['file_size']
                }
                for i, val in enumerate(flat_vector):
                    record[f'emb_{i}'] = float(val)
                processed_records.append(record)
            except Exception as e:
                logger.warning(f"Failed to process tensor {file_hash}: {e}")
    if not processed_records:
        logger.error("Failed to process any embeddings. Check tensor formats.")
        return
    logger.info("Compiling final dynamic dataset...")
    df_final = pd.DataFrame(processed_records)
    logger.info(f"Saving dynamic behaviors to {parquet_path.name}...")
    df_final.to_parquet(parquet_path, engine='pyarrow', compression='snappy')
    logger.info(f"[DONE] CIC Dynamic processing complete! Final shape: {df_final.shape[0]} rows, {df_final.shape[1]} columns.")
if __name__ == "__main__":
    process_cic_dynamic()
