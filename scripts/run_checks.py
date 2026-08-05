from __future__ import annotations
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def run(args: list[str]) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)

def main() -> int:
    run([sys.executable, "tools/console.py", "--check"])
    run([sys.executable, "tools/check_layering.py"])
    run([sys.executable, "-m", "pytest"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
