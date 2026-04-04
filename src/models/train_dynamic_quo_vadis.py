import os
import json
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from tqdm import tqdm
import concurrent.futures

# --- Configuration ---
BASE_PATH = r"D:\IntelliGuard\data\raw\Quo Vadis\windows_emulation_trainset"
MODEL_OUTPUT = r"models\expert_quo_vadis_dynamic.json"

# --- High-Risk API Signatures (The Pro Heuristics) ---
INJECTION_APIS = {'VirtualAllocEx', 'WriteProcessMemory', 'CreateRemoteThread', 'NtMapViewOfSection'}
EVASION_APIS = {'IsDebuggerPresent', 'CheckRemoteDebuggerPresent', 'Sleep', 'NtDelayExecution'}
RANSOMWARE_APIS = {'CryptEncrypt', 'vssadmin.exe', 'bcdedit.exe'}

def process_single_json(file_info):
    file_path, label = file_info
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # THE FIX: If it's a list, grab the first item (the main dictionary)
        if isinstance(data, list) and len(data) > 0:
            main_dict = data[0]
        elif isinstance(data, dict):
            main_dict = data
        else:
            return None # Skip weird files
        
        # Convert whole JSON to string once for ultra-fast keyword searching
        raw_data_str = json.dumps(data).lower()
        
        # Extract base metrics safely using the new main_dict
        features = {
            'num_api_calls': len(main_dict.get('apis', [])),
            'num_dynamic_segments': len(main_dict.get('dynamic_code_segments', [])),
            
            # Pro-Level Heuristics: Sniping specific malicious intents
            'has_injection': int(any(api.lower() in raw_data_str for api in INJECTION_APIS)),
            'has_evasion': int(any(api.lower() in raw_data_str for api in EVASION_APIS)),
            'has_crypto_ransom': int(any(api.lower() in raw_data_str for api in RANSOMWARE_APIS)),
            
            'label': label
        }
        return features
    except Exception:
        # Silently skip corrupted JSONs so the pipeline doesn't crash
        return None

def build_dynamic_model():
    print("[*] Initializing IntelliGuard Dynamic Extraction Pipeline (PRO MODE)...")
    
    tasks = []
    if not os.path.exists(BASE_PATH):
        print(f"❌ ERROR: Cannot find folder at {BASE_PATH}")
        return

    # 1. Map out the battleground
    folders = os.listdir(BASE_PATH)
    for folder in folders:
        folder_path = os.path.join(BASE_PATH, folder)
        if not os.path.isdir(folder_path): 
            continue
        
        # Ground Truth: Clean folder = 0 (Safe), Everything else = 1 (Malware)
        label = 0 if 'clean' in folder.lower() else 1
        
        for json_file in os.listdir(folder_path):
            if json_file.endswith('.json'):
                tasks.append((os.path.join(folder_path, json_file), label))
                
    print(f"[*] Found {len(tasks)} JSON Emulation Reports. Engaging Multi-Threading...")

    # 2. Multi-threaded processing for massive speed boost
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(tqdm(executor.map(process_single_json, tasks), total=len(tasks), desc="Parsing JSONs"))
        
    # Filter out any failed reads
    dataset = [res for res in results if res is not None]

    # 3. Build the Tabular Dataset
    print("\n[*] Crushing JSONs into Tabular Data...")
    df = pd.DataFrame(dataset)
    
    if df.empty:
        print("❌ ERROR: No data was extracted. Check your JSON format.")
        return

    X = df.drop('label', axis=1)
    y = df['label']

    print(f"[*] Training Dynamic Behavioral Expert on {len(df)} samples...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 4. Train XGBoost (Pro Configuration)
    model = xgb.XGBClassifier(
        n_estimators=200, 
        max_depth=6, 
        learning_rate=0.1, 
        n_jobs=-1 # Forces XGBoost to use all CPU threads
    )
    model.fit(X_train, y_train)
    
    # 5. Evaluate and Save
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    
    print("\n════════════════════════════════════════════════════════════")
    print(f"✅ DYNAMIC EXPERT TRAINED SUCCESSFULLY")
    print(f"📊 True Accuracy: {acc * 100:.2f}%")
    print("════════════════════════════════════════════════════════════")
    
    os.makedirs('models', exist_ok=True)
    model.save_model(MODEL_OUTPUT)
    print(f"[*] Core brain saved to: {MODEL_OUTPUT}")

if __name__ == "__main__":
    build_dynamic_model()