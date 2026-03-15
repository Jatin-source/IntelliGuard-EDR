import numpy as np
import pandas as pd
import scipy.sparse
import sys
import gc
from pathlib import Path

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.utils.logger import logger
from src.utils.config import config

def process_bodmas():
    """Loads the BODMAS NPZ matrix, attaches metadata labels, and saves as Parquet."""
    
    logger.info("Starting BODMAS dataset processing...")
    
    raw_dir = Path(config['paths']['raw_data']['bodmas'])
    processed_dir = Path(config['paths']['processed_data']['static'])
    
    npz_path = raw_dir / "bodmas.npz"
    metadata_path = raw_dir / "bodmas_metadata.csv"
    parquet_path = processed_dir / "bodmas_cleaned.parquet"
    
    if not npz_path.exists() or not metadata_path.exists():
        logger.error("Could not find BODMAS .npz or metadata files!")
        return
        
    try:
        # 1. Load the NPZ matrix
        logger.info(f"Loading raw NPZ matrix into memory: {npz_path.name}")
        # BODMAS is usually saved as a compressed numpy array
        npz_file = np.load(npz_path, allow_pickle=True)
        
        # Extract features (X) and labels (y)
        X = npz_file['X']
        y = npz_file['y']
        
        # If it's a sparse matrix (to save space), convert it to a dense matrix
        if scipy.sparse.issparse(X):
            logger.info("Converting sparse matrix to dense array...")
            X = X.toarray()
            
        logger.info(f"NPZ loaded. Shape: {X.shape[0]} rows, {X.shape[1]} features.")
        
        # 2. Convert to Pandas DataFrame
        # Since BODMAS features are anonymous (f1, f2, etc.), we generate generic column names
        feature_cols = [f"feature_{i}" for i in range(X.shape[1])]
        df = pd.DataFrame(X, columns=feature_cols)
        
        # Downcast floats to save RAM
        df = df.astype('float32')
        
        # Add the target label (0 = benign, 1 = malware)
        df['label'] = y
        
        # Free up the raw matrix from RAM immediately
        del X
        del y
        del npz_file
        gc.collect()
        
        # 3. Load and attach Metadata (Family labels for our Hint System later)
        logger.info(f"Loading metadata: {metadata_path.name}")
        meta_df = pd.read_csv(metadata_path)
        
        # We only need the family category for the malware
        if 'family' in meta_df.columns:
            df['family'] = meta_df['family']
            logger.info("Successfully attached malware family labels.")
        
        # 4. Save as highly compressed Parquet
        logger.info(f"Saving cleaned BODMAS data to {parquet_path.name}...")
        df.to_parquet(parquet_path, engine='pyarrow', compression='snappy')
        
        logger.info(f"[DONE] BODMAS processing complete! Final shape: {df.shape[0]} rows, {df.shape[1]} columns.")
        
    except Exception as e:
        logger.error(f"Error processing BODMAS data: {e}")

if __name__ == "__main__":
    process_bodmas()