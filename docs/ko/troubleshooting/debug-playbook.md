# YU AI Manager 디버그 플레이북

## 빠른 시작

```bash
# 전체 진단 실행
python debug_check.py

# DB 지정
python debug_check.py --db /path/to/tags.db

# 간이 체크 (구문/Extension 생략)
python debug_check.py --quick
```

---

## 자주 발생하는 문제와 대처법

### 1. config.json이 깨짐 (백슬래시 문제)

**증상:** 서버 시작 시 JSONDecodeError
**원인:** Windows 경로를 수동 입력할 때 `\U`, `\w` 등이 잘못된 이스케이프가 됨
**대처:** 서버 시작 시 자동 복구됩니다. 수동으로 복구하려면:
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. scan-all에서 특정 폴더가 건너뛰어짐

**증상:** "전체 폴더 스캔"에서 일부 폴더가 처리되지 않음
**확인 절차:**
```bash
# scan_roots 내용 확인
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**체크 항목:**
- 경로가 너무 짧지 않은지 (`\\wsl.localhost\`만 되어 있지 않은지)
- 끝에 `\`가 없는지
- `os.path.exists(path)`가 True를 반환하는지

### 3. QR 공유에서 "내용이 없습니다"

**증상:** QR 공유 버튼 → Positive/Negative가 비어 있음
**원인 후보:**
1. `templates` 테이블에 레코드가 없음 (meta_source=unknown)
2. API 응답의 키 불일치 (v2.7.0에서 수정됨)

**확인:**
```bash
# 파일 ID의 템플릿 존재 확인
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # 문제의 ID
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. WSL/UNC 경로에서 스캔 실패

**증상:** `\\wsl.localhost\...` 경로에서 프로브 실패
**확인:**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**주의:** `pathlib.Path.exists()`는 WSL UNC 경로에서 버그가 있습니다. `os.path.exists()`를 사용하십시오.

### 5. Extension이 로드되지 않음

**증상:** Extension 목록에 표시되지 않음
**확인:**
```bash
python debug_check.py  # Extension 체크 섹션 확인
```
**체크 항목:**
- `extension.json` 또는 `extension.yml`이 존재하는지
- JSON/YAML이 유효한지 (`safe_load_config`로 확인)
- `name` 필드가 존재하는지

### 6. PIN 인증에서 잠김

**증상:** 5회 실패 → 60초 잠금
**대처:** 60초 기다리거나 서버를 재시작하여 리셋합니다.
**확인:** 브라우저 개발자 도구 → Network → `/_pin_check` 응답에서 오류 메시지를 확인합니다

---

## 디버그 로그 읽는 방법

### 서버 콘솔 출력

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → config.json의 백슬래시 자동 복구가 실행됨

[DEBUG] scan/start: raw=..., sanitized=...
  → 스캔 시작 시 경로 (원본 값 → 새니타이즈 후)

[DEBUG] scan-all root 0: repr=..., len=...
  → 전체 폴더 스캔 시 각 루트 경로 상세

[Scan] Auto-registered scan root: /path/to/dir
  → 스캔 성공 시 자동 등록

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → QR 공유 API: 파일은 존재하지만 템플릿이 없음

[ERROR] file.json: JSON parse failed: ...
  → safe_load_json에서의 파싱 오류 (앱은 크래시하지 않음)
```

---

## 파일 구성과 디버그 대상

```
web_ui.py          ← 엔트리 포인트 (서버 시작)
core/
  config.py        ← 설정 관리, safe_load_*
  server.py        ← PIN 인증, QuickLock
  scanner.py       ← 스캔 엔진
  extensions.py    ← Extension 로딩
  db.py            ← DB 연결 관리
  schema.py        ← 테이블 정의
routes/
  scan.py          ← 스캔 API
  search.py        ← 검색 API
  share.py         ← QR 공유 API
  tools.py         ← 도구 API + Inspect API
  debug.py         ← 디버그 API
  pages.py         ← 페이지 라우팅
static/js/
  main.js          ← 메인 UI (검색, 모달, QR, 키보드)
  scan-banner.js   ← 스캔 진행률 + 스크롤 탑 (전체 페이지)
```
