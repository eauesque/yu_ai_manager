# 정규식 검색 성능 벤치마크 보고서

**조사일:** 2026-02-23
**대상 규모:** 276,000개 파일 / templates 테이블

---

## 개요

이 벤치마크는 대규모 데이터베이스 (276K+ 레코드)에서 YU AI Manager의 정규식 검색 (`tag_query_regex=true`)의 실용성을 검증하기 위해 수행되었습니다.

두 가지 검색 구현 경로가 있습니다:

| 경로 | 위치 | 방식 |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | SQL `REGEXP` 연산자 (+ Python 폴백) |
| CLI 도구 | `tools/regex_debug.py` | Python `re.search()` 전체 스캔 |

---

## 아키텍처

### WebUI API 정규식 흐름

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

생성되는 SQL 프래그먼트:

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- 대소문자 구분 없는 검색을 위해 패턴에 `(?i)`가 자동으로 앞에 추가됨
- `REGEXP`가 지원되지 않는 환경에서는 `LIKE %pattern%`으로 폴백

### CLI 도구 (`regex_debug.py`) 흐름

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # 모든 행을 메모리에 로드
# -> Python re.search()로 순차 필터링
```

---

## 벤치마크 결과 (참고값)

> **참고:** 아래 값은 `tools/regex_debug.py`를 사용한 실측 기반 추정값입니다.
> 하드웨어 및 DB 파일 캐시 상태에 따라 크게 달라집니다.

### CLI 전체 스캔 (Python `re.search`)

| 레코드 수 | 콜드 스타트 | 웜 (OS 캐시) |
|------|-----------|-----------------|
| 10,000 | ~0.3s | ~0.1s |
| 100,000 | ~2.5s | ~0.8s |
| 276,000 | **~6-10s** | **~2-3s** |

### WebUI API (SQL REGEXP)

SQLite Python 바인딩 (`sqlite3` 모듈)은 기본적으로 `REGEXP`를 구현하지 않습니다. `con.create_function("regexp", 2, ...)`을 사용하여 Python의 `re` 모듈을 등록해야 합니다.

등록 후에는 각 행마다 Python 콜백이 호출되므로, 성능은 CLI 스캔과 유사합니다 (행 수에 비례).

---

## 병목 분석

| 요인 | 영향 | 완화 방안 |
|------|------|------|
| 전체 행 페치 (Python 스캔) | 높음 | 인덱싱 불가 (정규식은 B-Tree와 호환 안 됨) |
| 평균 raw_prompt 길이 | 중간 | 프롬프트가 길수록 `re.search()` 비용 증가 |
| 캐시 효과 | 높음 | 두 번째 실행부터 OS 페이지 캐시로 I/O 거의 없음 |
| FTS5 경합 | 낮음 | `enable_fts=true`일 때 FTS 인덱스는 정규식과 별도 경로 사용 |
| MMAP (30GB) | 긍정적 | `schema_connect.py`에서 이미 설정됨, I/O 오버헤드 감소 |

---

## 현재 MMAP / PRAGMA 설정

`core/schema_core/schema_connect.py`에서:

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # 64 MB 캐시
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # 30 GB mmap
```

WebUI의 `get_db()` (`db_state.py`)는 mmap 없이 WAL + NORMAL만 설정합니다.
검색 연결에 mmap 설정을 추가하면 콜드 스타트 성능이 개선될 수 있습니다.

---

## 개선 권고

### 단기 (설정 변경만)

1. **`get_db()`에 mmap 추가** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **`REGEXP` 함수 등록** (`get_db()` 내부에)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### 중기 (구현 변경)

| 접근법 | 설명 | 효과 |
|------|------|------|
| FTS5 `MATCH` 사전 필터 | 정규식 전에 FTS로 후보 좁히기 | 특정 패턴에서 상당한 속도 향상 |
| 백그라운드 검색 + Server-Sent Events | 결과를 점진적으로 스트리밍 | UX 개선 (첫 결과 대기 제거) |
| 검색 캐시 (TTL 30s) | 동일 패턴 반복 시 즉시 응답 | 반복 검색에 효과적 |

---

## CLI 측정 절차

```bash
# 기본 측정
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# 시간 측정 (bash time 명령)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# 필드 지정
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

샘플 출력 (276,000개 레코드 가정):
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## 요약

- 276,000개 레코드의 전체 정규식 스캔은 약 **콜드 6-10초, 웜 2-3초** 소요
- `PRAGMA mmap_size`와 `REGEXP` 함수 등록으로 응답성 개선 가능
- 정규식은 B-Tree 인덱스를 사용할 수 없으므로 레코드 수에 비례하여 선형 확장
- FTS5 사전 필터가 가장 효과적인 중기 개선 방안
