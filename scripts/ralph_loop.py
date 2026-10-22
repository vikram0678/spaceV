#!/usr/bin/env python3
"""
Ralph Loop Runner for SpaceV.
Executes automated test verification and lint evaluation loops.
"""
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd_list, desc):
    print(f"\n🔄 [Ralph Loop] Running: {desc}...")
    res = subprocess.run(cmd_list, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ [Ralph Loop] {desc} passed successfully.")
        return True, res.stdout
    else:
        print(f"❌ [Ralph Loop] {desc} reported issues (code {res.returncode}):")
        print(res.stdout[-1500:] if len(res.stdout) > 1500 else res.stdout)
        if res.stderr:
            print(res.stderr[-1000:])
        return False, res.stdout + "\n" + res.stderr


def main():
    print("=" * 60)
    print(" 🔁 SpaceV Ralph Loop Autonomous Verification")
    print("=" * 60)

    # 1. Run Ruff Linter
    lint_ok, _ = run_cmd([sys.executable, "-m", "ruff", "check", "core/run_ledger.py", "tools/sandbox_tools.py", "tests/test_phase7_run_ledger.py"], "Ruff Lint Check")

    # 2. Run Pytest Suite
    test_ok, out = run_cmd([sys.executable, "-m", "pytest", "tests/", "-q"], "Pytest Test Suite (58 Tests)")

    if lint_ok and test_ok:
        print("\n" + "=" * 60)
        print(" 🎉 RALPH LOOP SUCCESS: All tests & linter are 100% GREEN!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print(" ⚠️ RALPH LOOP DETECTED REGRESSION: Fix required.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
