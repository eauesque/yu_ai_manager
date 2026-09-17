# CJK / 2바이트 인코딩 함정과 해결 방법

이 문서는 2바이트 문자 환경(주로 일본어 CP932/Shift-JIS)에서 발생하는 버그와 이 프로젝트에서 채택한 해결 방법을 정리한 것입니다. 유사한 문제를 겪는 개발자와 AI 에이전트를 위한 참고 자료입니다.

---

## 1. Windows 콘솔 cp932 크래시

### 증상

Windows `cmd.exe` / PowerShell / Git Bash의 기본 출력 인코딩은 **cp932 (Shift-JIS)** 입니다. cp932에 포함되지 않은 유니코드 문자를 `print()`로 출력하면 `UnicodeEncodeError`와 함께 즉시 크래시가 발생합니다.

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2014' in position 12
```

### 문제를 유발한 문자들

| 문자 | 이름 | 사용 맥락 |
|------|------|----------|
| `—` (U+2014) | em dash | 로그 출력 구분자 |
| `–` (U+2013) | en dash | 진행 상태 표시 |
| `✓ ✗ ✅ ❌ ⚠️` | 체크 마크 / 이모지 | 성공/실패 표시 |
| `🧹 📦 📁 🔍 🔧` | 이모지 | 작업 라벨 |
| `█ ░` | 블록 문자 | 프로그레스 바 |

### 해결 방법

- **`print()`에서 ASCII 안전 문자만 사용합니다**: `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-` 등.
- `logging` 핸들러에도 동일하게 적용됩니다. 인코딩이 cp932인 핸들러는 같은 문제가 발생합니다.
- `PYTHONIOENCODING=utf-8`을 설정하여 문제를 우회할 수 있지만, 사용자 환경에 의존하는 것은 불안정합니다. 방어적으로 ASCII를 사용하는 것이 더 안전합니다.

### 영향 범위

이 프로젝트에서는 **19개 파일**에 대한 일괄 수정이 필요했습니다 (v2.28.0). AI 코드 생성기(Claude/GPT)는 이모지와 em dash를 높은 빈도로 사용합니다. **AI 생성 코드를 리뷰할 때 가장 중요하게 확인해야 할 항목 중 하나입니다.**

---

## 2. ZIP 파일명 깨짐 (CP437)

### 증상

오래된 Windows 시스템(95/98/XP 시대)에서 만든 ZIP 파일은 파일명을 **Shift-JIS (CP932)** 로 저장하지만, ZIP 사양에는 인코딩 메타데이터가 없습니다. Python의 `zipfile` 모듈은 UTF-8 플래그(비트 11)가 설정되어 있지 않으면 파일명을 **CP437**로 디코딩합니다. 이로 인해 일본어 파일명이 `âwâCâèâb`와 같은 깨진 텍스트로 표시됩니다.

### 해결 방법: 10단계 폴백 체인

`core/infra_core/encoding.py`에 우선순위가 지정된 CJK 인코딩 목록이 정의되어 있습니다:

```
UTF-8 (zipfile이 먼저 시도) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- `chardet` / `cchardet`는 **사용하지 않습니다**: 짧은 파일명(10--30바이트)에서는 오탐이 너무 많습니다.
- 고정 우선순위 방식이 더 나은 재현성과 간단한 디버깅을 제공합니다.

### Python 3.11+의 `metadata_encoding` 파라미터

```python
# Python 3.11+에서는 metadata_encoding으로 직접 지정 가능
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

이 방법은 CP932 이외의 인코딩으로 저장된 ZIP 파일을 처리하지 못합니다. 실패 시 `metadata_encoding` 없이 아카이브를 다시 열고 `repair_cp437_name()`을 통해 복구를 시도합니다.

### 7z 아카이브

7-Zip은 자체적인 파일명 처리 방식을 가지고 있습니다. 7z CLI를 통해 CP437 깨짐이 발생할 수 있으며, `repair_cp437_name()`이 동일한 복구 로직을 적용합니다.

---

## 3. 2바이트 파일명으로 인한 ZIP/7z 스캔 행

### 증상

`zipfile.ZipFile()`이 Shift-JIS로 인코딩된 오래된 ZIP의 중앙 디렉토리를 읽을 때 블로킹 I/O 상태에 빠져 행이 발생할 수 있습니다. 파일 수가 많은 아카이브에서 특히 발생하기 쉽습니다.

### 해결 방법

1. **타임아웃 보호**: `run_with_timeout()` 데몬 스레드 헬퍼를 도입했습니다.
   - 파일 목록 조회: 30초
   - 스캔 I/O: 60초
2. **scan_errors 테이블** (마이그레이션 v24): 타임아웃과 인코딩 오류가 DB에 저장됩니다.
   - 오류 유형 분류: `encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. SQLite FTS5 tokenchars 인용 부호 문제

### 증상

SQLite FTS5 `tokenize` 지시문에서 `tokenchars` 옵션에 사용하는 인용 부호 조합에 따라 구문 분석 오류가 발생할 수 있습니다.

```sql
-- NG: 외부 작은따옴표 + 내부 큰따옴표 → 구문 분석 오류
tokenize='unicode61 tokenchars "_:."'

-- OK: 외부 큰따옴표 + 내부 작은따옴표
tokenize="unicode61 tokenchars '_:.'"
```

### 원인

FTS5 토크나이저 파서가 작은따옴표 안에 중첩된 큰따옴표를 올바르게 구문 분석하지 못합니다. 버전별 동작 차이가 있을 수 있습니다 (SQLite 3.45.1에서 확인됨).

### 해결 방법

Python 삼중 따옴표 문자열을 사용하여 두 가지 SQL 인용 부호 유형을 모두 수용합니다:

```python
# OK: Python '''로 SQL의 "와 ' 모두 감쌈
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### 발견 경위

이 문제는 FTS5 테이블을 재구축하는 마이그레이션 29에서 발견되었습니다. AI 생성 코드가 작은따옴표-외부 구문을 사용했습니다. SQLite 3.45.1에서 서버 시작 시 크래시가 발생했습니다 (v2.70.1에서 수정됨).

---

## 5. UTF-16 인코딩의 WebP EXIF

### 증상

일부 이미지 생성 도구(특히 NAI 계열 도구)는 WebP EXIF 메타데이터를 **UTF-16 (BOM 포함)** 으로 저장합니다. 표준 UTF-8 디코딩을 사용하면 텍스트가 깨집니다.

### 해결 방법

- BOM (Byte Order Mark)을 감지하여 UTF-16 BE/LE를 판별합니다.
- BOM이 없는 경우 휴리스틱으로 BE/LE를 추정합니다.
- UTF-8, latin-1 순서로 폴백합니다.

---

## 6. PNG tEXt 청크 인코딩

### 증상

PNG 사양은 tEXt 청크를 **Latin-1 (ISO-8859-1)** 으로 정의하고 있지만, 대부분의 AI 이미지 생성 도구는 UTF-8로 인코딩된 문자열을 직접 기록합니다. `latin-1`로 디코딩하면 일본어 텍스트가 깨집니다.

### 해결 방법

먼저 UTF-8로 디코딩하고, 실패 시 latin-1로 폴백합니다:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. config.json의 Windows 경로 백슬래시

### 증상

Windows 파일 경로에는 백슬래시(`\`)가 포함됩니다. JSON 파일에 경로를 수동으로 입력하면 잘못된 이스케이프 시퀀스가 생성됩니다.

```json
{"scan_roots": ["C:\Users\test"]}  // \U와 \t가 이스케이프 시퀀스가 됨
```

### 해결 방법

- `_repair_json_backslashes()`가 서버 시작 시 경로를 자동 복구합니다.
- 저장 전에 경로가 내부적으로 정규화됩니다.

---

## 8. pathlib과 WSL UNC 경로

### 증상

WSL (Windows Subsystem for Linux) 환경에서 UNC 경로(`\\server\share\...`)에 대해 `pathlib.Path.exists()`가 잘못된 결과를 반환할 수 있습니다.

### 해결 방법

- UNC 경로의 존재 여부 확인에는 `os.path.exists()`를 사용합니다.
- `pathlib`은 편리하지만 네트워크 경로에서는 신뢰할 수 없습니다.

---

## 9. CSV 내보내기의 UTF-8 BOM

### 증상

Excel은 BOM이 없는 UTF-8 CSV 파일을 깨진 텍스트로 표시합니다. Excel은 BOM이 없는 UTF-8을 ANSI(일본어 환경에서는 CP932)로 해석합니다.

### 해결 방법

```python
buf.write("\ufeff")  # Excel 호환성을 위한 UTF-8 BOM
```

CSV 출력에 BOM (`\ufeff`)을 앞에 추가합니다. 이렇게 하면 Excel이 파일을 UTF-8로 인식합니다.

---

## 10. JSON 출력에서의 `ensure_ascii=False`

### 증상

Python의 `json.dumps()`는 기본적으로 비ASCII 문자를 `\uXXXX`로 이스케이프합니다. 일본어 태그 이름이나 파일 경로를 포함하는 MCP 도구 응답이 `\u30bf\u30b0`으로 표시되어 AI 에이전트가 내용을 이해하기 어렵게 됩니다.

### 해결 방법

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

이 프로젝트에서는 모든 MCP 도구 모듈(10개 파일)에서 이 설정을 일관되게 사용합니다.

---

## 11. 폴더 선택 대화상자 출력 디코딩

### 증상

Windows의 PowerShell 폴더 선택 대화상자는 `subprocess` 출력을 CP932로 인코딩합니다. 기본 UTF-8 디코딩은 `UnicodeDecodeError`를 발생시킵니다.

### 해결 방법

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

`errors='replace'` 플래그는 디코딩 실패 시에도 안전한 처리를 보장합니다.

---

## AI 에이전트를 위한 참고 사항

위의 문제들 중 상당수는 **AI 코드 생성기가 간과하기 쉬운 패턴**입니다:

1. **`print()`에서 이모지나 장식 문자를 사용하지 마십시오** -- AI 생성기는 시각적 효과를 위해 이를 자주 사용합니다.
2. **파일명 인코딩을 가정하지 마십시오** -- UTF-8을 전제로 작성된 코드는 CP932 환경에서 작동하지 않습니다.
3. **실제 런타임에서 SQLite 인용 부호를 테스트하십시오** -- 문서에 맞는 구문이라도 실제로는 실패할 수 있습니다.
4. **`json.dumps()`에 항상 `ensure_ascii=False`를 전달하십시오** -- 일본어 데이터를 처리할 때 필수입니다.
5. **환경의 인코딩으로 subprocess 출력을 디코딩하십시오** -- Windows는 일반적으로 CP932를 사용합니다.
6. **CSV 출력에 BOM을 포함하십시오** -- Excel 호환성을 위해 필요합니다.

---

## 참고: 이 프로젝트의 관련 파일

| 파일 | 설명 |
|------|------|
| `core/infra_core/encoding.py` | CJK 폴백 체인, CP437 깨짐 복구 |
| `core/schema_core/schema_migrate_steps_29.py` | 올바른 FTS5 tokenchars 인용 |
| `core/tools/fs_dialog.py` | 폴더 선택 대화상자 CP932 디코딩 |
| `core/configuration/json_rw.py` | config.json 백슬래시 복구 |
| `routes/collections.py` | CSV 내보내기 BOM 삽입 |
| `CLAUDE.md` | "Windows 환경 주의사항 > 콘솔 출력" 섹션 |
