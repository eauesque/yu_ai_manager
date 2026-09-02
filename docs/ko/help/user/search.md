# 검색

## 기본 검색

검색 바에 태그를 쉼표로 구분하여 입력합니다.

```
1girl, blue_eyes, school_uniform
```

## 검색 필터

| 필터 | 설명 |
|------|------|
| 날짜 범위 | 시작일~종료일로 필터링 |
| 파일 형식 | PNG / WebP / JPG / GIF |
| 평점 | 별 1~5로 필터링 |
| 즐겨찾기 | 즐겨찾기에 등록된 항목만 표시 |
| 컬렉션 | 특정 컬렉션 내의 항목만 표시 |

## 프롬프트 내 검색

「in_prompt」 필드를 사용하면 이미지의 프롬프트 텍스트 내에서 전문 검색이 가능합니다.
FTS (Full-Text Search)가 활성화된 경우 고속으로 검색할 수 있습니다.

## 정렬 순서

| 정렬 | 설명 |
|------|------|
| date | 등록일 (최신순) |
| date_old | 등록일 (오래된순) |
| folder | 폴더순 |
| path | 경로순 |
| random | 랜덤 |
| rating_desc | 평점 (높은순) |
| rating_asc | 평점 (낮은순) |

## 시맨틱 검색

Hailo-10H 또는 ONNX CLIP 모델이 설정되어 있는 경우, 자연어로 이미지를 검색할 수 있습니다.
검색 바 오른쪽에 있는 시맨틱 검색 버튼을 사용해 주세요.

### FAISS를 통한 가속화 (권장)

시맨틱 검색은 기본적으로 NumPy를 사용한 브루트포스 검색을 사용하지만,
**FAISS를 설치하면 대폭 가속화**됩니다.

| 라이브러리 수 | NumPy (기본) | FAISS (권장) |
|-------------|-------------|-------------|
| 1만 건 이하 | 수십ms | 수ms |
| 10만 건 | 1~3초 | 수십ms |
| 100만 건 이상 | 10초 이상 | 100ms 이하 |

FAISS는 검색 대상 규모에 따라 자동으로 최적의 인덱스를 선택합니다:
- **5만 건 미만**: IndexFlatIP (정확한 전수 검색, 충분히 빠름)
- **5만 건 이상**: IndexIVFFlat (근사 최근접 이웃 검색, 대규모에서도 고속)

#### 설치 방법

```bash
# venv를 활성화한 후 설치
source venv/bin/activate

# x86_64 (Intel/AMD) — pip로 직접 설치 가능
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — pip로 설치가 안 되는 경우
# 방법 1: conda 경유
conda install -c conda-forge faiss-cpu

# 방법 2: 소스에서 빌드
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

설치 후에는 서버를 재시작하기만 하면 자동으로 감지됩니다.
시작 로그에 다음이 표시되면 FAISS가 활성화된 것입니다:

```
FAISS x.x.x detected — using accelerated vector search
```

FAISS가 설치되어 있지 않은 경우에도 기존대로 NumPy로 동작합니다.
