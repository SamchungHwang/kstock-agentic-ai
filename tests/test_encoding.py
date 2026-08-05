from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from kstock.cli_support import JsonlEmitter
from kstock.models import ResultStatus


def test_jsonl_wire_is_ascii_safe_and_restores_korean() -> None:
    stream = io.StringIO()
    with redirect_stdout(stream):
        code = JsonlEmitter("corr_encoding").result(
            ResultStatus.ERROR,
            "TEST_ERROR",
            "한글 오류 메시지",
            {"next": "점검하십시오"},
        )

    raw = stream.getvalue().strip()
    raw.encode("ascii")  # wire format contains ASCII only
    event = json.loads(raw)
    assert event["message"] == "한글 오류 메시지"
    assert event["payload"]["next"] == "점검하십시오"
    assert code == 1
