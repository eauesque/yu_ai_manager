# 스캔

## 스캔 폴더 등록

Settings > Scan 탭에서 스캔 대상 폴더를 추가합니다.

- 드래그 앤 드롭으로 정렬 가능
- 체크박스로 활성/비활성 전환
- 여러 폴더 등록 가능

## 스캔 실행

- 폴더 추가 후 자동으로 스캔 시작
- 수동 스캔은 Tools 페이지 또는 MCP의 `trigger_scan`으로 실행
- 스캔 중 진행 상황은 SSE로 실시간 알림

## 자동 스캔 (Watcher)

Auto Scan Watcher 확장 기능을 활성화하면, 등록된 폴더 내 파일 변경을 자동 감지하여 스캔합니다.

## 원격 파일 시스템

WSL / NAS / SMB 등의 원격 경로를 스캔하는 경우, Settings > Remote FS 탭에서 타임아웃 설정을 조정해 주세요.

## 대규모 라이브러리에서의 스캔

수십만~100만 건 이상의 파일을 스캔하는 경우 주의사항:

- **스캔 중에도 이미지 검색 가능**: 검색 API는 읽기 전용 DB 연결을 사용하므로 스캔 중 쓰기 잠금의 영향을 받지 않습니다
- **WAL 자동 관리**: 스캔 중에는 2000개 파일마다 WAL 체크포인트를 자동 실행하여 WAL 파일의 비대화를 방지합니다
- **scan.db_busy 이벤트**: 스캔 시작/완료 시 SSE 이벤트가 전송되므로 프론트엔드에서 바쁜 상태를 표시할 수 있습니다

## 스캔 워커 프로세스

v3.27.0 이후, 스캔은 web_ui.py와 독립된 별도 프로세스에서 실행됩니다.
이를 통해 **web_ui를 재시작해도 스캔이 중단되지 않습니다**.

### 동작 원리

- WebUI에서 스캔을 시작하면 백그라운드에서 워커 프로세스가 기동됩니다
- 워커는 `/tmp/yu-scan/`에 진행 파일 (JSON)과 PID 파일을 기록합니다
- WebUI는 이 진행 파일을 폴링하여 SSE로 프론트엔드에 중계합니다
- WebUI를 재시작하면 실행 중인 워커를 자동 감지하여 진행 표시를 재연결합니다

### CLI에서 조작하기

워커는 CLI에서도 직접 조작할 수 있습니다. WebUI가 중지된 상태에서도 사용 가능합니다.

```bash
# 상태 확인
python -m core.scan.scan_worker status

# 실행 중인 스캔 중지 (graceful shutdown — DB에 중단 위치 저장)
python -m core.scan.scan_worker stop

# CLI에서 직접 스캔 시작
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# 옵션
#   --recursive / --no-recursive  하위 디렉터리 포함 여부 (기본값: recursive)
#   --scan-zips                   ZIP/7z 내 이미지도 스캔
#   --force                       기존 파일도 재스캔
#   --resume                      중단된 스캔 재개
#   --config config.json          설정 파일 지정
```

### 안전 메커니즘

- **부모 프로세스 감시**: WebUI에서 시작된 워커는 WebUI 프로세스의 생존을 60초 간격으로 감시합니다. WebUI가 비정상 종료한 경우, 워커는 자동으로 중단 저장 후 정지합니다
- **SIGTERM 대응**: `stop` 명령이나 `kill`로 SIGTERM을 보내면, 현재 처리를 완료한 후 DB에 커밋하고 중단 위치를 저장하여 종료합니다
- **중복 방지**: 동시에 여러 워커가 기동되는 일은 없습니다

### 문제 해결

워커가 응답하지 않는 경우:

```bash
# PID 확인
cat /tmp/yu-scan/worker.pid

# 프로세스 강제 종료
kill -9 $(cat /tmp/yu-scan/worker.pid)

# 잔여 파일 정리
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## 스캔 오류

스캔 중 오류가 발생한 경우, MCP의 `get_scan_errors`로 확인할 수 있습니다.
