# Architecture

```text
사용자
  ↓ 클릭·직접 입력
tools/console.py
  ↓ CommandSpec 조회
tools/console_commands.py
  ↓ subprocess.Popen(argv, shell=False)
python -m kstock.cli ...
  ↓
Application Service / Domain / Guard / Adapter
  ↓
내부 원장·감사 저장소·OpenDART·한국투자증권
```

`tools/console.py`와 `tools/console_commands.py`는 `kstock`을 임포트하지 않는다.
콘솔은 투자 계층이 아니라 검증된 명령을 요청하는 운영 표면이다.
