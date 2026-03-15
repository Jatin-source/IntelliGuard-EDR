import sys
import time
import pandas as pd
import xgboost as xgb
from pathlib import Path

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.utils.logger import logger
from src.features.pe_extractor import PEFeatureExtractor

# ── Configuration ─────────────────────────────────────────
# Minimum percentage of feature columns an expert must match to vote.
# Below this, the expert is SKIPPED (predictions on mostly zero-filled data = garbage).
MIN_MATCH_RATIO = 0.10  # 10%

# Experts exempt from the threshold (EMBER one-hot imports are *designed* to be sparse).
EXEMPT_FROM_THRESHOLD = {'EMBER'}

# If a file has a valid digital signature, apply a safe-bias.
# The weighted malware score must exceed this to override the trust.
SIGNED_TRUST_THRESHOLD = 0.85


class IntelliGuardEnsemble:
    def __init__(self):
        logger.info("Waking up IntelliGuard AI Ensemble...")
        self.models = {}
        self._load_models()

    def _load_models(self):
        """Loads Kaggle, BODMAS, and EMBER into memory."""
        model_paths = {
            'Kaggle': Path("outputs/models/expert_kaggle.json"),
            'BODMAS': Path("outputs/models/expert_bodmas.json"),
            'EMBER': Path("outputs/models/expert_ember.json")
        }

        for name, path in model_paths.items():
            if path.exists():
                bst = xgb.Booster()
                bst.load_model(path)
                self.models[name] = bst
                logger.info(f"✅ {name} Expert loaded successfully.")
            else:
                logger.error(f"❌ {name} Expert missing at {path}")

    def scan_file(self, file_path):
        """Extracts features, queries all experts, and fuses their votes."""
        logger.info(f"Analyzing target: {file_path}")
        
        # 1. Run the Feature Extractor with Retry Logic for File Locks (Downloads)
        max_retries = 3
        raw_features = None
        for i in range(max_retries):
            try:
                extractor = PEFeatureExtractor(file_path)
                raw_features = extractor.extract()
                if raw_features is not None:
                    break
            except Exception:
                if i == max_retries - 1:
                    return {"status": "error", "message": "File is busy or locked by the OS."}
            time.sleep(1.5)
        
        if raw_features is None:
            return {"status": "error", "message": "Failed to extract PE features."}

        extracted_cols = set(raw_features.columns)

        # ── Check digital signature ───────────────────────
        is_signed = False
        signer = ""
        if '_meta.is_validly_signed' in raw_features.columns:
            is_signed = bool(raw_features['_meta.is_validly_signed'].iloc[0])
        if '_meta.signer_subject' in raw_features.columns:
            signer = str(raw_features['_meta.signer_subject'].iloc[0])

        if is_signed:
            logger.info(f"🔏 Valid digital signature detected: {signer}")
        else:
            logger.info("⚠️  No valid digital signature found.")

        votes = {}
        weighted_scores = []
        participating_experts = 0

        # 2. Get predictions from all experts
        for name, model in self.models.items():
            expected_cols = model.feature_names
            
            matched = extracted_cols.intersection(expected_cols)
            missing = set(expected_cols) - extracted_cols
            match_ratio = len(matched) / len(expected_cols) if expected_cols else 0
            logger.info(f"[{name}] Feature coverage: {len(matched)}/{len(expected_cols)} ({match_ratio:.1%})")

            # ── Minimum-Match Gate ────────────────────────
            if match_ratio < MIN_MATCH_RATIO and name not in EXEMPT_FROM_THRESHOLD:
                logger.warning(
                    f"[{name}] ⏭️ SKIPPED — only {match_ratio:.1%} coverage "
                    f"(need ≥{MIN_MATCH_RATIO:.0%}). Incompatible feature schema."
                )
                votes[name] = {"malware": None, "confidence": None, "status": "SKIPPED",
                               "match_ratio": match_ratio}
                continue

            # ── Run Prediction ────────────────────────────
            participating_experts += 1

            # Drop _meta columns before aligning (they're not model features)
            model_features = raw_features.drop(
                columns=[c for c in raw_features.columns if c.startswith('_meta.')],
                errors='ignore'
            )
            aligned_df = model_features.reindex(columns=expected_cols, fill_value=0.0).astype('float32')
            
            dmatrix = xgb.DMatrix(aligned_df)
            prob = float(model.predict(dmatrix)[0])
            
            is_malware = prob > 0.5
            votes[name] = {"malware": bool(is_malware), "confidence": prob, "status": "VOTED",
                           "match_ratio": match_ratio}

            # Weight = confidence × feature coverage (capped at 1.0)
            # EMBER is exempt from coverage weighting (sparse by design)
            weight = min(match_ratio, 1.0) if name not in EXEMPT_FROM_THRESHOLD else 1.0
            weighted_scores.append((prob, weight))
            
            status = "🚨 MALWARE" if is_malware else "✅ SAFE"
            logger.info(f"[{name} Expert] -> {status} (Confidence: {prob:.4f}, Weight: {weight:.2f})")

        # 3. Fused Verdict
        if participating_experts == 0:
            final_verdict = "UNKNOWN"
            fused_score = 0.0
            logger.warning("No experts had enough feature coverage to vote!")
        else:
            # Weighted average of malware probabilities
            total_weight = sum(w for _, w in weighted_scores)
            fused_score = sum(p * w for p, w in weighted_scores) / total_weight if total_weight > 0 else 0.0

            # ── Digital Signature Trust Logic ─────────────
            # A valid, non-self-signed certificate from a real CA is extremely
            # strong evidence that a file is legitimate.  To override that trust,
            # EVERY participating expert must UNANIMOUSLY agree with very high
            # individual confidence (>0.95).  This prevents false positives on
            # signed system tools (python.exe, etc.) while still catching truly
            # malicious signed binaries that trip every expert.
            if is_signed:
                is_self_signed = False
                if '_meta.is_validly_signed' in raw_features.columns:
                    # Check authenticode.self_signed feature
                    for v in votes.values():
                        pass  # we already know it's signed
                # Check if self-signed from extracted features
                if 'authenticode.self_signed' in raw_features.columns:
                    is_self_signed = bool(raw_features['authenticode.self_signed'].iloc[0])

                if is_self_signed:
                    # Self-signed certs get less trust — use normal threshold
                    final_verdict = "MALWARE" if fused_score > 0.7 else "SAFE"
                    logger.info(f"⚠️  Self-signed certificate — using elevated threshold 0.70")
                else:
                    # CA-signed binary: require unanimous high confidence
                    active_votes = [v for v in votes.values() if v.get("status") == "VOTED"]
                    all_flag_malware = all(v["confidence"] > 0.95 for v in active_votes)
                    unanimous = all(v["malware"] for v in active_votes)

                    if unanimous and all_flag_malware and len(active_votes) >= 2:
                        final_verdict = "MALWARE"
                        logger.warning(
                            f"🚨 Signed binary flagged — ALL {len(active_votes)} experts "
                            f"unanimously agree (>{0.95:.0%} each)"
                        )
                    else:
                        final_verdict = "SAFE"
                        logger.info(
                            f"🔏 Signature trust prevails — CA-Signed binary overrides models. "
                            f"(Fused: {fused_score:.3f}, Active: {len(active_votes)})"
                        )
            else:
                final_verdict = "MALWARE" if fused_score > 0.5 else "SAFE"

        # ── Summary ───────────────────────────────────────
        logger.info("=" * 55)
        icon = "🚨" if final_verdict == "MALWARE" else "✅"
        logger.info(f"{icon} FINAL VERDICT: {final_verdict} "
                     f"(Fused Score: {fused_score:.3f}, "
                     f"Experts: {participating_experts})")
        if is_signed:
            logger.info(f"🔏 Signed by: {signer}")
        logger.info("=" * 55)

        return {
            "status": "success",
            "verdict": final_verdict,
            "fused_score": fused_score,
            "is_signed": is_signed,
            "signer": signer,
            "votes": votes,
            "participating_experts": participating_experts
        }


if __name__ == "__main__":
    engine = IntelliGuardEnsemble()
    test_target = sys.argv[1] if len(sys.argv) > 1 else sys.executable
    engine.scan_file(test_target)