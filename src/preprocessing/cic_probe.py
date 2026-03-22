import sys
import pandas as pd
import numpy as np
from pathlib import Path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.utils.config import config
def probe_cic_dataset():
    logger.info("Initializing CIC Dynamic dataset probe...")
    raw_dir = Path(config['paths']['raw_data']['cic'])
    if not raw_dir.exists():
        logger.error(f"Cannot find directory: {raw_dir}")
        return
    all_files = list(raw_dir.rglob("*.*"))
    logger.info(f"Found {len(all_files)} total files in the CIC folder.")
    ext_counts = {}
    for f in all_files:
        ext = f.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    logger.info(f"File breakdown: {ext_counts}")
    csv_files = list(raw_dir.rglob("*.csv"))
    if csv_files:
        test_csv = csv_files[0]
        logger.info(f"Peeking into CSV: {test_csv.name}")
        df = pd.read_csv(test_csv, nrows=5)
        logger.info(f"CSV Columns: {list(df.columns)}")
    npz_files = list(raw_dir.rglob("*.npz"))
    if npz_files:
        test_npz = npz_files[0]
        logger.info(f"Peeking into NPZ: {test_npz.name}")
        data = np.load(test_npz, allow_pickle=True)
        logger.info(f"NPZ Arrays inside: {data.files}")
    logger.info("✅ CIC Probe complete.")
if __name__ == "__main__":
    probe_cic_dataset()
