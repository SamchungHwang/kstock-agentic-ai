#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q tests/ch07
python tools/validate_ch7_policy.py
echo "Chapter 7 checks: PASS"
