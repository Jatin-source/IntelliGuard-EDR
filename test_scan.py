import sys
import os
from pathlib import Path
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.detector.ensemble import IntelliGuardEnsemble
import time
engine = IntelliGuardEnsemble()
targets = [
    sys.executable,                          
    r"C:\Windows\System32\notepad.exe",      
    r"C:\Windows\System32\cmd.exe",          
]
for target in targets:
    if not os.path.exists(target):
        print(f"\n[SKIP] {target} — not found")
        continue
    print(f"\n{'='*60}")
    print(f"TARGET: {target}")
    t0 = time.time()
    result = engine.scan_file(target)
    elapsed = time.time() - t0
    print(f"  Verdict:   {result['verdict']}")
    print(f"  Score:     {result.get('fused_score', 0):.3f}")
    print(f"  Signed:    {result.get('is_signed', False)}")
    print(f"  Signer:    {result.get('signer', '')[:80]}")
    print(f"  Trusted:   {result.get('trusted_publisher', False)}")
    print(f"  Time:      {elapsed:.2f}s")
    print(f"  Experts:   {result.get('participating_experts', 0)}")
    for name, vote in result.get("votes", {}).items():
        status = vote.get("status", "?")
        conf = vote.get("confidence")
        mal = vote.get("malware")
        conf_str = f"{conf*100:.1f}%" if conf is not None else "N/A"
        print(f"    [{name}] {status} | malware={mal} | conf={conf_str}")
