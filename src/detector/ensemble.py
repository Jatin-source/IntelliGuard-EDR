import os
import sys
import time
import pandas as pd
import xgboost as xgb
from pathlib import Path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.logger import logger
from src.features.pe_extractor import PEFeatureExtractor
MIN_MATCH_RATIO = 0.05  
EXPERT_AUTHORITY = {
    'EMBER': 2.5,   
    'BODMAS': 1.5,  
    'Kaggle': 0.8   
}
UNSIGNED_THRESHOLD = 0.65
SELF_SIGNED_THRESHOLD = 0.75
CA_SIGNED_THRESHOLD = 0.88
TRUSTED_PUBLISHERS = [
    'microsoft', 'google', 'mozilla', 'apple', 'adobe', 'intel', 'nvidia',
    'advanced micro devices', 'oracle', 'vmware', 'citrix', 'cisco',
    'cloudflare', 'python software foundation', 'valve', 'steam', 'epic games',
    'riot games', 'blizzard', 'electronic arts', 'samsung', 'lenovo', 'dell',
    'hp inc', 'hewlett-packard', 'asus', 'logitech', 'realtek', 'broadcom',
    'symantec', 'mcafee', 'kaspersky', 'malwarebytes', 'avast', 'avg', 'eset',
    'bitdefender', 'norton', 'slack', 'zoom', 'discord', 'spotify', 'dropbox',
    'github', 'jetbrains', 'notepad++', 'wireshark', 'videolan', 'audacity',
    '7-zip', 'winrar', 'rarlab', 'dotnet', 'open source developer', 'apache',
    'vs revo group' 
]
TRUSTED_SYSTEM_DIRS = [
    os.path.normcase(os.path.expandvars(p)) for p in [
        r'%SystemRoot%\System32', r'%SystemRoot%\SysWOW64', r'%SystemRoot%\WinSxS',
        r'%ProgramFiles%\Windows', r'%ProgramFiles(x86)%\Windows',
        r'%ProgramFiles%\Microsoft', r'%ProgramFiles(x86)%\Microsoft',
        r'%ProgramFiles%', r'%ProgramFiles(x86)%', r'%ProgramW6432%',
    ]
]
class IntelliGuardEnsemble:
    def __init__(self):
        logger.info("Waking up IntelliGuard AI Ensemble...")
        self.models = {}
        self._load_models()
    def _load_models(self):
        model_paths = {
            'Kaggle': Path("outputs/models/expert_kaggle.json"),
            'BODMAS': Path("outputs/models/expert_bodmas.json"),
            'EMBER':  Path("outputs/models/expert_ember.json")
        }
        for name, path in model_paths.items():
            if path.exists():
                bst = xgb.Booster()
                bst.load_model(path)
                self.models[name] = bst
                logger.info(f"✅ {name} Expert loaded successfully. (Base Weight: {EXPERT_AUTHORITY.get(name, 1.0)}x)")
            else:
                logger.error(f"❌ {name} Expert missing at {path}")
    def _is_trusted_publisher(self, signer: str) -> bool:
        signer_lower = signer.lower()
        return any(pub in signer_lower for pub in TRUSTED_PUBLISHERS)
    def scan_file(self, file_path):
        logger.info(f"Analyzing target: {file_path}")
        raw_features = None
        for i in range(3):
            try:
                extractor = PEFeatureExtractor(file_path)
                raw_features = extractor.extract()
                if raw_features is not None:
                    break
            except Exception:
                if i == 2:
                    return {"status": "error", "message": "File is busy or locked by the OS."}
            time.sleep(1.0)
        if raw_features is None:
            return {"status": "error", "message": "Failed to extract PE features."}
        extracted_cols = set(raw_features.columns)
        is_signed = False
        signer = ""
        if '_meta.is_validly_signed' in raw_features.columns:
            is_signed = bool(raw_features['_meta.is_validly_signed'].iloc[0])
        if '_meta.signer_subject' in raw_features.columns:
            signer = str(raw_features['_meta.signer_subject'].iloc[0])
        if is_signed:
            logger.info(f"🔏 Valid digital signature detected: {signer}")
        else:
            logger.info("⚠️ No valid digital signature found.")
        if is_signed and signer and self._is_trusted_publisher(signer):
            logger.info(f"🛡️ TRUSTED PUBLISHER: {signer} — auto-verdict: SAFE")
            votes = {name: {"malware": False, "confidence": 0.0, "status": "TRUSTED", "match_ratio": 1.0} for name in self.models}
            return self._build_result("SAFE", 0.0, is_signed, signer, votes, 0, f"Trusted Publisher: {signer}")
        resolved = os.path.normcase(os.path.realpath(file_path))
        if any(resolved.startswith(sd) for sd in TRUSTED_SYSTEM_DIRS):
            dir_match = next(sd for sd in TRUSTED_SYSTEM_DIRS if resolved.startswith(sd))
            logger.info(f"🛡️ SYSTEM DIRECTORY: {dir_match} — auto-verdict: SAFE")
            votes = {name: {"malware": False, "confidence": 0.0, "status": "TRUSTED", "match_ratio": 1.0} for name in self.models}
            return self._build_result("SAFE", 0.0, is_signed, f"OS System ({os.path.basename(dir_match)})", votes, 0, f"System Directory: {dir_match}")
        votes = {}
        weighted_scores = []
        malware_votes = 0
        safe_votes = 0
        participating_experts = 0
        for name, model in self.models.items():
            expected_cols = model.feature_names
            matched = extracted_cols.intersection(expected_cols)
            match_ratio = len(matched) / len(expected_cols) if expected_cols else 0
            if match_ratio < MIN_MATCH_RATIO:
                logger.warning(f"[{name}] ⏭️ SKIPPED — {match_ratio*100:.1f}% coverage is too low.")
                votes[name] = {"malware": None, "confidence": None, "status": "SKIPPED", "match_ratio": match_ratio}
                continue
            participating_experts += 1
            model_features = raw_features.drop(columns=[c for c in raw_features.columns if c.startswith('_meta.')], errors='ignore')
            aligned_df = model_features.reindex(columns=expected_cols, fill_value=0.0).astype('float32')
            dmatrix = xgb.DMatrix(aligned_df)
            prob = float(model.predict(dmatrix)[0])
            is_malware = prob > 0.5
            if is_malware:
                malware_votes += 1
            else:
                safe_votes += 1
            votes[name] = {
                "malware": bool(is_malware),
                "confidence": prob,
                "status": "VOTED",
                "match_ratio": match_ratio
            }
            authority = EXPERT_AUTHORITY.get(name, 1.0)
            weight = authority * match_ratio  
            weighted_scores.append((prob, weight))
            status = "🚨 MALWARE" if is_malware else "✅ SAFE"
            logger.info(f"[{name}] {status} (Prob: {prob:.4f}, Cov: {match_ratio*100:.1f}%, Final Weight: {weight:.2f})")
        if participating_experts == 0:
            return self._build_result("UNKNOWN", 0.0, is_signed, signer, votes, 0, "No experts had enough feature coverage")
        total_weight = sum(w for _, w in weighted_scores)
        fused_score = sum(p * w for p, w in weighted_scores) / total_weight if total_weight > 0 else 0.0
        majority_malware = malware_votes > safe_votes
        logger.info(f"[FUSION] Weighted Score: {fused_score:.4f} (Malware Votes: {malware_votes}, Safe Votes: {safe_votes})")
        if is_signed:
            is_self_signed = bool(raw_features.get('authenticode.self_signed', [0])[0])
            if is_self_signed:
                if fused_score >= SELF_SIGNED_THRESHOLD and majority_malware:
                    final_verdict = "MALWARE"
                    reason = f"Self-Signed Threat (Score {fused_score:.3f} >= {SELF_SIGNED_THRESHOLD})"
                else:
                    final_verdict = "SAFE"
                    reason = f"Self-Signed Safe (Failed threshold or majority)"
            else:
                if fused_score >= CA_SIGNED_THRESHOLD and malware_votes == participating_experts and participating_experts >= 2:
                    final_verdict = "MALWARE"
                    reason = f"CA-Signed Threat Override (Unanimous [{participating_experts} experts] + Score {fused_score:.3f} >= {CA_SIGNED_THRESHOLD})"
                else:
                    final_verdict = "SAFE"
                    if participating_experts < 2 and fused_score >= CA_SIGNED_THRESHOLD:
                         reason = "CA-Signed Safe (Signature prevailed. Single expert cannot override CA)"
                    else:
                         reason = "CA-Signed Safe (Signature prevailed over ML doubts)"
        else:
            if fused_score >= UNSIGNED_THRESHOLD and majority_malware:
                final_verdict = "MALWARE"
                reason = f"Unsigned Threat (Score {fused_score:.3f} >= {UNSIGNED_THRESHOLD} & Majority Agreed)"
            else:
                final_verdict = "SAFE"
                reason = f"Unsigned Safe (Failed threshold {UNSIGNED_THRESHOLD} or majority)"
        return self._build_result(final_verdict, fused_score, is_signed, signer, votes, participating_experts, reason)
    def _build_result(self, verdict, score, is_signed, signer, votes, experts, reason):
        logger.info("=" * 60)
        logger.info(f"{'🚨' if verdict == 'MALWARE' else '✅'} FINAL VERDICT: {verdict}")
        logger.info(f"    Fused Score : {score:.4f}")
        logger.info(f"    Reason      : {reason}")
        logger.info("=" * 60)
        return {
            "status": "success",
            "verdict": verdict,
            "fused_score": score,
            "is_signed": is_signed,
            "signer": signer,
            "votes": votes,
            "participating_experts": experts,
            "verdict_reason": reason,
        }
if __name__ == "__main__":
    engine = IntelliGuardEnsemble()
    test_target = sys.argv[1] if len(sys.argv) > 1 else sys.executable
    print(engine.scan_file(test_target))
