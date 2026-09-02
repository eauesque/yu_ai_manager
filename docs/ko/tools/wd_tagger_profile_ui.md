# WD-Tagger 프로필 UI 사용 가이드

이 문서는 WD-Tagger **프로필 관리자 UI**(v4.197.0+ 추가)의 사용법을 설명합니다.

## 1. 개요

- **프로필(profile)**은 WD-Tagger의 모델 파일, 태그 정의, 임계값, 전처리 설정을 한 번에 묶어 관리합니다.
- Tools 페이지 → **WD-Tagger** 섹션에서 `프로필 관리...`를 눌러 모달을 엽니다.
- 모달 안에서 **목록(List)** 화면과 **폼(Form)** 화면을 오갑니다.

## 2. 목록 화면(List)

### 2.1 배지(Builtin / User)

- `builtin`: 내장 프로필(읽기 전용)
- `user`: 사용자 프로필(생성/편집/삭제 가능)
- `↻`: 같은 `id`의 내장 프로필을 **덮어쓰는** 프로필임을 의미합니다

### 2.2 필터(All / User / Builtin)

상단 필터 버튼:

- `전체`
- `사용자`
- `내장`

### 2.3 버튼(동작)

행 오른쪽 버튼:

- `복제`: 프로필을 복사하여 폼을 엽니다(내장 프로필을 수정하려면 이 방법을 사용)
- `편집`: 사용자 프로필 편집(내장은 편집 불가)
- `삭제`: 사용자 프로필 삭제(내장은 삭제 불가)
- `내보내기`: 프로필을 `.json`으로 다운로드
- `테스트(드라이런 다운로드)`: **실제 다운로드 없이**, HuggingFace에서 필요한 파일을 가져올 수 있는지 확인

오른쪽 위 버튼:

- `+ 새로 만들기`: 빈 새 프로필 생성
- `가져오기`: JSON에서 프로필 생성(업로드/붙여넣기)

## 3. 폼 화면(Form)

폼은 5개의 아코디언 섹션으로 구성됩니다.

### 3.1 Metadata

- `id`: 프로필 식별자(나중에 변경 불가)
- `표시 이름`: 목록에 표시되는 이름
- `profile_version`: 스키마 버전(대부분 그대로 두면 됩니다)

### 3.2 Model & Files

- `model_id`: HuggingFace 모델 id(예: `SmilingWolf/wd-swinv2-tagger-v3`)
- `adapter_family`, `backend`, `hf_subdir`: 필요한 경우에만 설정
- `파일`:
  - `name`: 다운로드 파일명(예: `model.onnx`)
  - `필수`: 체크 시 Test에서 필수 파일로 처리
  - `size_hint_mb`: 선택 사항
  - `+ 파일 추가` / `제거`: 행 추가/삭제

### 3.3 Tag source

태그 정의를 어디서 읽어올지 지정합니다.

- `csv`: 파일(file), 구분자(delimiter), 이름 열(name_col), 카테고리 열(category_col), 카테고리 매핑(category_map)
- `json_list`: 파일(file), 스키마(schema)
- `json_dict`: 파일(file), 매핑(mapping)
- `composite`: 소스(sources) 조합 규칙

### 3.4 Threshold source

임계값을 어디서 읽어올지 지정합니다.

- `global_per_category`: UI에서 분류별 임계값 직접 설정
- `per_tag`: 파일 참조 + 폴백 지정
  - 파일(file)
  - 폴백 모드(fallback.mode): `global` / `category_default`
  - 폴백 값(fallback.value)

### 3.5 Preprocess & Categories

- 전처리(`preprocess_spec`): `input_size`, `dtype`, `layout`, `channel_order`, `resize_strategy` (`letterbox` / `longest_side_pad` / `stretch`), `scale`, `mean`, `std`
- 카테고리:
  - `지원 카테고리`
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. 가져오기 / 내보내기(Import / Export)

### 4.1 가져오기(Import)

`가져오기`를 누르면 2개 탭이 있습니다.

- JSON 업로드: `.json` 파일 업로드
- JSON 붙여넣기: 텍스트 영역에 JSON 붙여넣기

가져오기 후 폼이 열리며, 내용을 확인/수정한 뒤 `저장`합니다.

### 4.2 내보내기(Export)

목록의 `내보내기`로 프로필 JSON을 다운로드합니다.

## 5. 테스트(dry-run download)

- `테스트`는 `files`에 지정된 파일을 **HuggingFace**에서 가져올 수 있는지 확인합니다.
- 성공 시 `다운로드 OK: {n}개 파일 ({total} MB)` 같은 배너가 표시될 수 있습니다.
- 실패 시 원인 메시지가 표시됩니다(다음 절).

## 6. 자주 보는 오류(짧은 설명)

- `id_conflict`: 같은 `id`의 사용자 프로필이 이미 존재
- `id_immutable`: `id`는 변경 불가(이름 변경은 복제 → 삭제)
- `in_use`: 현재 활성 프로필이라 삭제 불가
- `validation_failed`: 스키마 검증 실패(`{detail}`에 상세)
- `profile_too_large`: 가져온 JSON이 1MB 제한 초과
- `ssrf_blocked`: HuggingFace 외부 리디렉션 차단(SSRF 방지)
- `hf_unavailable`: HuggingFace 사용 불가/응답 이상
- `timeout`: 타임아웃(60s)
- `required_missing`: 필수 파일 누락(필수로 표시된 파일)

## 7. 제한 사항(중요)

- 내장(`builtin`) 프로필은 편집/삭제 불가입니다. `복제`로 사용자 복사본을 만드세요.
- `id`는 immutable입니다. 이름 변경: `복제` → 기존 항목 `삭제`.
- 가져오기 JSON은 **최대 1MB**입니다.
- `테스트`는 SSRF 방지를 위해 HuggingFace 도메인만 허용합니다:
  - `huggingface.co`
  - `hf.co`
