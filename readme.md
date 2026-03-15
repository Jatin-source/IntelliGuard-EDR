# IntelliGuard — Complete Project Document

---

## What Is IntelliGuard

IntelliGuard is a background-running Windows application that watches a folder you choose, analyzes any new executable files using AI, and sends you a Windows notification if malware is detected — telling you exactly why it flagged the file and what type of malware it likely is.

It works like an antivirus running silently in the background, but instead of matching files against a known database, it uses machine learning to detect malware based on the file's structure and behavior patterns. This means it can detect new malware it has never seen before.

---

## The Problem Being Solved

Traditional antivirus software works by comparing files against a database of known malware signatures. If malware is new or slightly modified, it gets through. IntelliGuard solves this by learning the patterns of malicious behavior — structure, strings, API calls, entropy — so it can flag unknown threats too. It also explains every decision so you know exactly why something was flagged, not just that it was.

---

## End Goal — What The Finished Product Does

```
You drop a file into your watched folder
              ↓
IntelliGuard detects it automatically
              ↓
AI analyzes the file silently (no execution needed)
              ↓
If clean → logged quietly, no interruption
If malware → Windows notification appears:

┌──────────────────────────────────────────┐
│  ⚠️  IntelliGuard Alert                      │
│  File:    suspicious.exe                 │
│  Verdict: MALWARE (94% confidence)       │
│  Type:    Likely Ransomware              │
│  Reason:  Bitcoin wallet strings found,  │
│           extremely high entropy,        │
│           file deletion APIs detected    │
└──────────────────────────────────────────┘
```

---

## Datasets Being Used

### Static Analysis Datasets
These are used to train the model to detect malware by looking at file structure without running the file.

**Kaggle Malware Dataset**
Format: CSV. Contains pre-extracted PE header features from malware and benign files. Simple, clean, good starting point.

**EMBER 2024 (win32 + win64)**
Format: JSON files. The most comprehensive static analysis dataset available publicly. Contains byte patterns, string analysis, PE headers, import tables, entropy values, and MITRE ATT&CK behavioral tags. We use win32 and win64 subsets only (not dotnet) to keep size manageable.

**BODMAS**
Format: NPZ array + CSV. Contains 134,435 samples with 2,381 pre-extracted features per sample, plus malware family labels (ransomware, trojan, spyware etc). The family labels are used to build the malware type hint system.

### Dynamic Analysis Dataset
**CIC DIG 2025**
Format: NPZ embeddings + PKL graphs + CSV. Captures what malware does when it actually runs — file operations, registry changes, network connections, process injections — represented as behavior graphs. We use the pre-computed embedding vectors directly.

---

## Two Types of Analysis

### Static Analysis — Examining Without Running
We look at the file's structure the same way a forensic analyst reads a document without acting it out. Safe because the malware never executes.

What we examine:
- PE Header — how the file is structured in memory, entry point location, section count, security flags
- Section Entropy — how random/encrypted the data looks. Packed malware has very high entropy (7.8+ out of 8.0)
- String Extraction — URLs, IP addresses, Bitcoin wallet addresses, keywords like "delete", "encrypt", "cmd"
- Import Table — which Windows functions the file plans to call. WriteProcessMemory = process injection. CryptEncrypt = encryption. RegSetValueEx = persistence.
- Overlay Data — data appended after the file ends, a common hiding place for payloads

### Dynamic Analysis — Watching Behavior
We look at what the malware actually does when run in a controlled sandbox environment. Cannot hide behavior — actions speak louder than code.

What we watch:
- File creation and deletion events
- Registry modifications
- Network connection attempts
- Process injection attempts
- System calls and their sequences

---

## Machine Learning Approach

### Why Machine Learning Over Signatures
Signature-based detection: compare file hash against database. Fails on new or modified malware.
ML-based detection: learn patterns of malicious behavior. Works on never-before-seen malware.

### Models Used

**Random Forest — Baseline**
Builds 100 decision trees on random subsets of data, takes majority vote. Used first to understand which features matter most before moving to the primary model.

**XGBoost — Primary Model**
Builds trees sequentially where each tree corrects the mistakes of the previous one. State of the art for tabular data. Uses GPU acceleration on your NVIDIA card. Trains 5-10x faster than CPU.

**Logistic Regression — Fusion Layer**
A simple model that sits on top of both the static and dynamic XGBoost models. It takes both probability scores as input and produces a final combined prediction.

### Why Not Deep Learning
Deep learning needs enormous amounts of data, GPU memory, and long training times, and is very hard to explain. XGBoost on well-engineered tabular features achieves better or equal accuracy for this type of problem, trains in minutes not hours, runs on CPU if needed, and SHAP explains it perfectly.

---

## Explainability — SHAP

SHAP (SHapley Additive exPlanations) tells us exactly why the model made each decision.

Without SHAP: "This file is 94% likely malware"
With SHAP: "This file is 94% likely malware because Bitcoin wallet strings pushed the score up by 31%, maximum section entropy pushed it up by 28%, file deletion API calls pushed it up by 22%, and the legitimate subsystem type pushed it down by 8%"

This is what powers the notification message — real reasons, not just a score.

---

## Malware Type Hint System

Not a separate classifier. A rule engine that reads the top SHAP features for each malware detection and matches them against behavior profiles.

```
Ransomware profile:
  Bitcoin wallet strings present
  + very high section entropy (encryption)
  + file deletion APIs
  → "Likely Ransomware"

Spyware/Keylogger profile:
  Keyboard capture strings
  + clipboard access strings
  + network communication
  → "Likely Spyware"

Trojan/RAT profile:
  Process injection APIs (WriteProcessMemory)
  + hidden strings
  + remote thread creation
  → "Likely Trojan / RAT"

Dropper/Downloader profile:
  High URL count
  + download APIs
  + file creation after network access
  → "Likely Dropper"

Rootkit profile:
  Kernel-level API calls
  + driver characteristics
  + low-level registry access
  → "Likely Rootkit"
```

---

## Late Fusion — Combining Static and Dynamic

Static analysis and dynamic analysis catch different things. Packed malware confuses static analysis but dynamic analysis sees the behavior clearly. Sandbox-evading malware hides its behavior but static analysis still sees the suspicious structure. Together they are much harder to fool.

```
File analyzed by static model  → 87% malware probability
File analyzed by dynamic model → 91% malware probability
                                          ↓
              Logistic Regression fusion layer
                                          ↓
                    Final: 94% malware probability
```

If both models agree strongly → high confidence result
If models disagree significantly → flagged for manual review

---

## Complete ML Pipeline Applied To Every Dataset

```
1. Load + Validate
   Confirm shape, types, labels, no corruption

2. Clean
   Drop columns with >40% missing values
   Fix wrong data types
   Remove duplicate rows
   Handle remaining nulls

3. Exploratory Data Analysis
   Class balance (malware vs benign ratio)
   Feature distributions
   Correlation heatmap
   All saved as PNG files

4. Preprocess
   Cap outliers at 1st and 99th percentile
   Fill remaining nulls with 0
   Drop near-zero variance features
   Drop highly correlated features (>0.95)

5. Feature Engineering
   Create new meaningful features
   Encode categorical columns

6. Train / Validation / Test Split
   70% training / 15% validation / 15% test
   Stratified split preserves class ratio
   Splits saved to disk, never recreated

7. Feature Scaling
   RobustScaler fitted on training set ONLY
   Applied identically to validation and test
   Scaler saved for use on real files later

8. Class Imbalance Handling
   Check malware vs benign ratio
   If ratio > 3:1 → apply SMOTE on training set only
   Validation and test sets never touched

9. Model Training
   Random Forest baseline first
   XGBoost primary model with GPU
   Early stopping on validation set

10. Evaluation
    Accuracy, Precision, Recall, F1 Score
    ROC-AUC curve
    False Negative Rate (most important metric)
    Confusion matrix
    All plots saved as PNG

11. Hyperparameter Tuning
    Optuna runs 50 trials automatically
    Finds best combination of parameters
    Model retrained with best parameters
    Final evaluation on test set (touched once only)

12. Explainability
    SHAP values computed on test set
    Global feature importance plot saved
    Per-sample explanation function ready
```

---

## Key ML Rules We Follow

**Train/Val/Test is sacred.** Test set is touched exactly once — at the very end. Never used for tuning anything.

**Fit on train, transform on all.** Scaler, imputer, SMOTE — all fitted on training data only, then applied identically to validation and test.

**RobustScaler not StandardScaler.** Malware data has extreme legitimate values. RobustScaler uses median and IQR so outliers don't distort the scaling.

**False Negative Rate is the key metric.** Missing real malware is far worse than a false alarm. Target FNR below 5%.

**No data leakage ever.** Detection ratio, family labels, hash values — none of these go into model training features.

---

## Security Rules Applied Throughout

**No hardcoded secrets.** All configuration in .env file, loaded via python-dotenv. Never in code.

**Input validation on all files.** Before any file is analyzed: check path for traversal attacks, confirm file exists, verify extension is .exe or .dll, check size is under 100MB.

**Rate limiting on analysis.** Maximum one file analyzed per second. Prevents resource exhaustion if many files drop at once.

**Allowed extensions only.** Watcher only triggers on .exe, .dll, .sys, .scr files. Everything else ignored.

---

## Project Structure

```
intelliguard\
│
├── data\
│   ├── raw\
│   │   ├── kaggle\          ← place kaggle CSV here
│   │   ├── ember\           ← place ember JSON folders here
│   │   ├── bodmas\          ← place bodmas files here
│   │   └── cic\             ← place CIC DIG 2025 files here
│   └── processed\
│       ├── static\          ← cleaned static features saved here
│       ├── dynamic\         ← cleaned dynamic features saved here
│       └── splits\          ← train/val/test splits saved here
│
├── src\
│   ├── utils\               ← config, logger, memory, metrics
│   ├── preprocessing\       ← one processor per dataset
│   ├── features\            ← feature engineering and scaling
│   ├── models\              ← Random Forest, XGBoost, fusion
│   ├── explainability\      ← SHAP and type hint engine
│   └── detector\            ← file watcher, notifier, analysis engine
│
├── outputs\
│   ├── models\              ← trained model files (.pkl)
│   ├── scalers\             ← fitted scaler files (.pkl)
│   ├── shap\                ← SHAP plots and values
│   ├── metrics\             ← evaluation results (JSON + PNG)
│   └── logs\                ← analysis history
│
├── tests\                   ← unit tests for each module
├── .env                     ← secrets (never committed to git)
├── .gitignore
├── config.yaml              ← all project settings
├── requirements.txt         ← all packages
└── main.py                  ← start IntelliGuard from here
```

---

## Step By Step Build Order

```
STEP 0  → Project setup
          Folders, venv, packages, base files, verify

STEP 1  → Utils
          Config loader, logger, memory monitor,
          metrics calculator, input validator

STEP 2  → Kaggle pipeline
          Load, validate, clean, EDA, preprocess,
          feature engineering, split, scale, imbalance

STEP 3  → EMBER pipeline
          Same as Kaggle but chunked (large data)

STEP 4  → BODMAS pipeline
          NPZ loading, variance filter, family labels

STEP 5  → CIC pipeline
          Dynamic graph embeddings, scalar features

STEP 6  → Static feature merging
          Align and combine all three static datasets

STEP 7  → Baseline model
          Random Forest, feature importance analysis

STEP 8  → Primary static model
          XGBoost with GPU, early stopping, save model

STEP 9  → Model evaluation
          All metrics, all plots, saved to outputs

STEP 10 → Hyperparameter tuning
          Optuna 50 trials, retrain, final test evaluation

STEP 11 → Dynamic model
          Same XGBoost pipeline on CIC features

STEP 12 → Late fusion
          Combine static and dynamic predictions

STEP 13 → SHAP explainability
          Global plots, per-sample explanation function

STEP 14 → Malware type hint engine
          Rule profiles, match against SHAP features

STEP 15 → Static analysis engine
          Extract PE features from any real .exe file

STEP 16 → File watcher
          Monitor chosen folder using watchdog library

STEP 17 → Notification system
          Windows toast popup with full verdict

STEP 18 → Analysis logger
          Save every result to local history file

STEP 19 → Main runner
          Ties everything together, runs in background

STEP 20 → Startup script
          Optional: run IntelliGuard on Windows boot
```

---

## Technology Stack

```
Language:        Python 3.10+
ML Models:       XGBoost (GPU), Random Forest, Logistic Regression
Explainability:  SHAP
Data:            pandas, numpy, scipy
Storage:         parquet (fast, compressed)
Imbalance:       imbalanced-learn (SMOTE)
Tuning:          Optuna
PE Analysis:     pefile
File Watching:   watchdog
Notifications:   win10toast
Visualization:   matplotlib, seaborn
Config:          pyyaml, python-dotenv
```

---

## Machine Specifications and Optimizations

```
Your machine:
  OS:    Windows
  RAM:   16GB
  GPU:   NVIDIA
  Drive: SSD

Optimizations applied:
  EMBER processed in chunks of 10,000 (never full load)
  Parquet format used everywhere (3x smaller than CSV)
  RobustScaler handles extreme malware feature values
  XGBoost uses NVIDIA GPU (tree_method=hist, device=cuda)
  n_jobs=4 for sklearn (safer than -1 on Windows)
  RAM monitored after every major processing step
  Variables deleted and garbage collected after each chunk
```

---