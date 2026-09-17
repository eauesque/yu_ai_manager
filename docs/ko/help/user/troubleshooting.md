# 문제 해결

## 자주 발생하는 문제

### 서버가 시작되지 않는 경우

- Python 가상환경이 활성화되어 있는지 확인합니다: `source venv/bin/activate`
- 의존 패키지가 설치되어 있는지 확인합니다: `uv pip install -r requirements.txt`
- 포트가 사용 중이 아닌지 확인합니다: `ss -tlnp | grep 5000`

### 이미지가 표시되지 않는 경우

- 썸네일 API는 이미지 파일의 실체가 필요합니다
- `files` 테이블의 경로가 실제 파일 경로와 일치하는지 확인합니다
- 스캔 루트의 경로가 올바른지 확인합니다

### LAN에서 접속할 수 없는 경우

- Settings > Server에서 「LAN Access」가 ON으로 설정되어 있는지 확인합니다
- PIN 인증이 설정되어 있는지 확인합니다 (LAN 공개 시 필수)
- 방화벽에서 해당 포트가 개방되어 있는지 확인합니다
- 서버의 IP 주소가 올바른지 확인합니다

### MCP 연결 오류

- `YU_BASE_URL`이 올바른지 확인합니다
- 서버가 실행 중인지 확인합니다
- API 키가 유효한지 확인합니다
- LAN 경유의 경우, HTTP/SSE 엔드포인트 (`/mcp`)가 사용 가능한지 확인합니다

### 스캔이 느린 경우

- `compute_hash`를 OFF로 설정하면 속도가 향상됩니다
- 원격 경로의 경우, Remote FS의 타임아웃 설정을 조정합니다
- 파일이 대량으로 있는 경우, 첫 스캔에는 시간이 소요됩니다

### 썸네일 생성이 느린 경우

- 스캔 중에는 디스크 I/O가 포화 상태가 되므로 썸네일 생성이 느려집니다. 스캔 완료 후 프리웜이 자동 실행됩니다
- **pyvips (옵션)**: 큰 JPEG 이미지가 많은 경우, libvips의 shrink-on-load로 가속화됩니다
  - Linux: `sudo apt install libvips-dev && uv pip install pyvips`
  - macOS: `brew install vips && uv pip install pyvips`
  - Windows: [libvips 릴리스 페이지](https://github.com/libvips/libvips/releases)에서 DLL을 다운로드하여 PATH에 추가한 후 `uv pip install pyvips`
  - 설치되어 있으면 자동 감지됩니다. 없어도 Pillow로 동작합니다
- **Pillow-SIMD (옵션)**: ARM NEON / x86 AVX2로 이미지 리사이즈를 2-4배 가속화합니다
  - `uv pip install pillow-simd` (Pillow와 대체되는 drop-in replacement)
  - ARM NEON 최적화 빌드: `CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - wheel이 없는 환경에서는 빌드 도구 (gcc 등)가 필요합니다

## 디버그

- Settings > Logs 탭에서 서버 로그를 확인합니다
- MCP 디버그 모드: `YU_DEBUG_MODE=1`로 추가 도구를 사용할 수 있습니다
- DB 무결성 검사: `python db_health.py`
