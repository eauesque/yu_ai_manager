# Tag Database - 디버그 체크리스트

**우선순위순 디버그 목록**
**상태**: 레거시 (v2.5.x 시기에 기록됨. 모든 항목이 해결되었습니다)
**최종 업데이트**: 2026-02-13

---

## P0 (긴급): 즉시 수정 (사용성에 영향)

### 1. UI 레이아웃 정렬 불량 수정

**문제:**
```
검색 필드를 나란히 배치하면 오버플로우가 발생하여
버튼이 제 위치에서 벗어납니다.
```

**확인 방법:**
1. WebUI를 실행합니다
2. 브라우저 크기를 1366x768로 조정합니다
3. 검색 필드 정렬을 확인합니다

**수정 위치:** `templates/index.html`
```html
<!-- 수정 전 -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- 수정 후 -->
<div class="search-row">
  <!-- flex-wrap: wrap 추가 -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**검증:**
- [ ] 1920x1080에서 올바르게 표시됨
- [ ] 1366x768에서 올바르게 표시됨
- [ ] 768x1024(태블릿)에서 올바르게 표시됨

---

### 2. 태그 자동완성 중복 제거

**문제:**
```
자동완성 추천에 중복이 포함됩니다.

예:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ^ 공백만 다름
```

**확인 방법:**
1. 태그 입력 필드에 "sample_creator"를 입력합니다
2. 자동완성 추천을 확인합니다
3. 중복이 있는지 확인합니다

**수정 위치:** `static/js/main/main.js`
```javascript
// initTagAutocomplete() 내부
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // 정규화 및 중복 제거
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // 쉼표 뒤에 공백 추가
      .replace(/\s+/g, ' ')        // 연속 공백 축소
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // 카운트 병합
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**검증:**
- [ ] 중복이 남아 있지 않음
- [ ] 카운트가 올바르게 병합됨
- [ ] 성능 문제 없음

---

## P1 (높음): 개선 (기능에 영향)

### 3. 검색 시 괄호 정규화

**문제:**
```
\(tag\)와 (tag)가 동일하게 처리되는지 확인합니다.
```

**확인 방법:**
1. `\(emphasis\)` 태그가 있는 이미지를 준비합니다
2. 검색 필드에서 `(emphasis)`를 검색합니다
3. 해당 이미지가 결과에 나타나는지 확인합니다

**체크포인트:**
- [ ] `(tag)` 검색 시 `\(tag\)`도 매칭됨
- [ ] `\(tag\)` 검색 시 `(tag)`도 매칭됨
- [ ] 정규식 모드에서는 이 정규화가 적용되지 않음

**관련 코드:** `web_ui.py` - `normalize_tag_for_search()`

---

### 4. ZIP 내부 파일 읽기 테스트

**문제:**
```
ZIP 아카이브 내부의 이미지가 올바르게 표시되고
메타데이터가 올바르게 추출되는지 확인합니다.
```

**테스트 케이스:**

#### 테스트 1: 기본 동작
```bash
# 1. 테스트 ZIP 생성
zip test.zip image1.png image2.png

# 2. 스캔
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. 확인
python tagdb_tool.py search --db test.db --q "*"
```

**확인 사항:**
- [ ] ZIP 내부 파일이 `test.zip!image1.png`으로 등록됨
- [ ] 메타데이터가 추출됨
- [ ] 썸네일이 표시됨

#### 테스트 2: 추출 기능
```
1. WebUI에서 ZIP 내부 파일을 엽니다
2. "추출 후 편집" 버튼을 클릭합니다
3. 파일 관리자가 열리는지 확인합니다
4. 추출된 파일이 존재하는지 확인합니다
```

**확인 사항:**
- [ ] 추출 버튼이 보임
- [ ] 클릭하면 파일 관리자가 열림
- [ ] 파일이 extracted/ 디렉토리에 추출됨
- [ ] 추출된 파일이 DB에 등록됨

#### 테스트 3: 대용량 ZIP
```bash
# 1) 1.1 GB ZIP (Zip64) 생성
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) ZIP 스캔
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**확인 사항:**
- [x] 메모리 사용량이 정상 범위 내
- [x] 스캔이 허용 가능한 시간 내에 완료됨 (5분 이내)
- [x] 오류 없음

**측정 결과 (2026-02-17):**
- ZIP 크기: `1,153,433,914 bytes` (약 1.1 GB)
- 소요 시간: `elapsed=0:00.14`
- 최대 RSS: `maxrss_kb=23864`
- DB 레코드: `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### 5. 체크포인트 검색 테스트

**문제:**
```
모델 이름이 올바르게 추출되고 검색 가능한지 확인합니다.
```

**테스트 케이스:**

#### 테스트 1: 모델 이름 추출
```python
# 각 형식별 추출 확인

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**확인 사항:**
- [ ] NovelAI 형식에서 추출 작동
- [ ] SD 형식에서 추출 작동
- [ ] ComfyUI 형식에서 추출 작동

#### 테스트 2: 검색 기능
```
1. WebUI에서 체크포인트 입력 필드를 클릭합니다
2. 자동완성이 나타나는지 확인합니다
3. "animagine"을 검색합니다
4. 해당 모델의 이미지만 표시되는지 확인합니다
```

**확인 사항:**
- [ ] 자동완성이 작동함
- [ ] 부분 매칭이 작동함
- [ ] 결과가 사용 빈도순으로 정렬됨

---

## P2 (보통): 향후 작업 (성능 개선)

### 6. 썸네일 캐시 구현

**문제:**
```
ZIP 내부 파일의 썸네일이 매 요청마다 다시 생성됩니다.
속도가 느립니다.
```

**제안 구현:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # 캐시 경로 생성
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # 캐시된 버전이 있으면 반환
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # 없으면 생성
    thumbnail = generate_thumbnail(...)

    # 캐시에 저장
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**검증:**
- [ ] 두 번째 접근이 눈에 띄게 빠름
- [ ] 디스크 사용량이 허용 범위 내
- [ ] 캐시 삭제가 작동함

---

### 7. 대규모 성능 측정

**테스트 케이스:**

#### 테스트 1: 100,000개 파일
```bash
# 스캔 시간 측정
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# 검색 시간 측정
time python tagdb_tool.py search --db large.db --q "1girl"
```

**목표:**
- [ ] 스캔: 시간당 최소 50,000개 파일
- [ ] 검색: 1초 이내 (100,000개 파일 중)

#### 테스트 2: WebUI 응답성
```
1. 100,000개 파일 DB로 WebUI를 실행합니다
2. 검색을 실행합니다
3. 결과를 스크롤합니다
```

**확인 사항:**
- [ ] 검색 결과가 3초 이내에 표시됨
- [ ] 스크롤이 부드러움
- [ ] 브라우저가 멈추지 않음

---

## 테스트 실행 체크리스트

### 환경 설정
- [ ] Python 3.8+ 설치됨
- [ ] 종속성 설치됨
- [ ] 테스트 데이터 준비됨 (각 형식의 이미지)

### 기능 테스트
- [ ] ZIP 읽기
- [ ] 다중 디렉토리 스캔
- [ ] 태그 정규화
- [ ] 체크포인트 검색
- [ ] 모델 필터링

### UI/UX 테스트
- [ ] 레이아웃 (다중 해상도)
- [ ] 다크 모드
- [ ] 키보드 단축키
- [ ] 자동완성

### 성능 테스트
- [ ] 10,000개 파일
- [ ] 50,000개 파일
- [ ] 100,000개 파일
- [ ] 대용량 ZIP (500 MB+)

### 브라우저 호환성
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### OS 호환성
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## 디버그 도구

### 로깅 활성화
```bash
# tagdb_tool.py 상단에 추가
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 성능 측정
```python
import time

start = time.time()
# ... 처리 ...
print(f"Time: {time.time() - start:.2f}s")
```

### 메모리 사용량 확인
```python
import tracemalloc

tracemalloc.start()
# ... 처리 ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**작성일:** 2026-02-13
**우선순위:** P0 → P1 → P2
**참고:** 이 체크리스트는 v2.5.x 시기에 작성되었습니다. 나열된 모든 항목이 해결되었습니다.
