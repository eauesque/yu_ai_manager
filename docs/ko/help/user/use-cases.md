# 유스케이스 모음

YU AI Manager의 대표적인 사용법을 「이런 경우에는 이렇게 사용합니다」 형식으로 정리했습니다.

---

## 1. 대량의 AI 이미지를 정리하고 싶을 때

NovelAI나 Stable Diffusion으로 생성한 이미지가 수천 장이나 폴더에 쌓여 있어 다시 보기가 힘들 때.

### 절차

1. **Settings > Scan** 탭에서 스캔 폴더를 등록합니다 (여러 개 가능)
2. 폴더 추가 후 자동으로 스캔이 시작됩니다. ZIP/7z 내부도 스캔 가능합니다
3. 스캔 완료 후, 메인 페이지에서 태그 검색 (예: `1girl, blue_eyes`)이나 정렬로 이미지를 필터링합니다
4. 마음에 드는 이미지를 선택하고, 우클릭 > **컬렉션에 추가**로 그룹을 나눕니다
5. 컬렉션 사이드바에서 언제든 그룹 단위로 열람할 수 있습니다

### 팁

- 스캔 중에도 검색/열람이 가능합니다 (읽기 전용 DB 연결로 경합하지 않습니다)
- Auto Scan Watcher 확장을 활성화하면 폴더에 새로 추가된 파일을 자동 감지합니다
- 100만 건 규모에서도 Keyset Pagination으로 고속 페이지 이동이 가능합니다

---

## 2. 특정 프롬프트로 생성한 이미지를 찾고 싶을 때

「그때 그 구도의 프롬프트가 뭐였더라」하고 기억나지 않을 때.

### 절차

1. 검색 바의 검색 대상을 **in_prompt**로 전환합니다
2. 기억나는 키워드 (예: `cherry blossom`)를 입력하여 검색합니다
3. 정규 표현식을 사용하면 더 유연하게 필터링할 수 있습니다 (예: `masterpiece.*cherry`)

### 팁

- FTS (전문 검색)가 활성화된 경우 대량의 프롬프트에서도 고속으로 검색할 수 있습니다
- 날짜 범위나 파일 형식 필터와 조합하면 효과적입니다
- 정렬을 `random`으로 설정하면 잊고 있던 이미지를 재발견하는 데에도 활용할 수 있습니다

---

## 3. 비슷한 구도의 이미지를 찾고 싶을 때

「이 이미지와 비슷한 분위기의 이미지가 다른 곳에도 있었을 텐데」 하고 찾고 싶을 때.

### 절차 A: pHash 유사 검색 (구도/색상)

1. 이미지의 상세 모달을 엽니다
2. **유사 이미지 검색** 버튼을 클릭합니다
3. pHash (지각 해시)로 구도가 비슷한 이미지가 사이드 패널에 목록으로 표시됩니다

### 절차 B: CLIP 시맨틱 검색 (의미/개념)

1. 검색 바 오른쪽의 **시맨틱 검색** 버튼을 클릭합니다
2. 자연어로 설명을 입력합니다 (예: 「해변에 서 있는 소녀」 「석양의 거리 풍경」)
3. CLIP이 이미지의 의미를 이해하여 유사도 순으로 표시합니다

### 팁

- 시맨틱 검색에는 CLIP 모델 (ONNX 또는 Hailo-10H)의 사전 설정이 필요합니다
- 대규모 라이브러리 (10만 건 이상)에서는 `faiss-cpu`를 설치하면 검색 속도가 비약적으로 향상됩니다
- pHash는 구도의 일치, CLIP은 의미적 유사성으로 특기 분야가 다릅니다. 둘 다 시도하면 발견이 늘어납니다

---

## 4. 즐겨찾기 이미지를 관리하고 싶을 때

대량의 이미지 중에서 걸작만 바로 다시 볼 수 있도록 하고 싶을 때.

### 절차

1. 이미지 카드 또는 상세 모달의 **하트 버튼**으로 즐겨찾기 등록합니다
2. 상세 모달에서 **별 레이팅** (1~5단계)을 설정하여 품질을 평가합니다
3. **어노테이션**에 자유로운 메모를 남깁니다 (예: 「리테이크 후보」 「SNS 게시 완료」)
4. 검색 필터에서 「즐겨찾기만」 「별 4 이상」 등으로 필터링합니다

### 팁

- 평점순 정렬 (`rating_desc`)로 고평점 이미지를 모아서 열람할 수 있습니다
- 컨텍스트 메뉴 (우클릭)에서도 즐겨찾기/레이팅 조작이 가능합니다

---

## 5. 이미지의 프롬프트를 다른 도구로 보내고 싶을 때

과거에 만든 이미지의 프롬프트를 재활용하여 다른 도구에서 재생성이나 바리에이션을 만들고 싶을 때.

### 절차

1. 이미지의 상세 모달을 열고 프롬프트 정보를 확인합니다
2. **SD WebUI에 보내기** / **ComfyUI에 보내기** / **NAI에 보내기** 버튼을 클릭합니다
3. Bridge 페이지가 열리고 프롬프트가 자동 입력됩니다
4. 필요에 따라 프롬프트를 편집하고 생성 도구 측에서 실행합니다

### 팁

- SD ↔ NAI 간에는 `()`와 `{}`의 가중치 구문이 자동 변환됩니다
- Bridge 툴바의 **QP** 버튼으로 품질 프리셋을 원클릭 삽입할 수 있습니다
- Prompt Converter나 Prompt Simulator에서도 각 Bridge로 전송할 수 있습니다

---

## 6. ZIP/7z 아카이브 내 이미지를 열람하고 싶을 때

다운로드한 이미지 세트가 ZIP으로 묶여 있어 압축을 풀지 않고 내용을 확인하고 싶을 때.

### 절차

1. Settings > Scan에서 ZIP/7z 파일이 포함된 폴더를 등록합니다
2. 스캔 옵션에서 **ZIP/7z 내 스캔**을 활성화합니다
3. 스캔 완료 후, 아카이브 내 이미지도 메인 페이지에서 일반 이미지와 동일하게 검색/열람할 수 있습니다
4. 상세 모달에서는 아카이브 이름과 아카이브 내 경로가 표시됩니다

### 팁

- 아카이브 내 동영상은 임시 캐시 (LRU 2GB)에 풀어서 저장되므로 반복 재생도 원활합니다
- 중첩 ZIP (ZIP-in-ZIP)에도 대응합니다
- 배치 다운로드 기능으로 아카이브 내 이미지를 새로운 ZIP으로 다시 묶을 수도 있습니다

---

## 7. 팀이나 가족과 이미지를 공유하고 싶을 때

같은 Wi-Fi 내의 다른 기기 (스마트폰/태블릿 등)에서 이미지를 열람할 수 있게 하고 싶을 때.

### 절차

1. **Settings > Server** 탭에서 「LAN Access」를 ON으로 설정합니다
2. **PIN 코드**를 설정합니다 (LAN 공개 시 필수)
3. 서버를 재시작합니다
4. LAN 내의 다른 기기에서 `http://<서버 IP>:5000`에 접속합니다
5. PIN을 입력하여 로그인합니다

### 팁

- **LAN Share 토큰** (`/s/` 경로)을 발행하면 PIN 없이 게스트 접속 링크를 공유할 수 있습니다
- 서버 화면에 QR 코드가 표시되므로 스마트폰의 카메라로 스캔하기만 하면 접속할 수 있습니다
- 리버스 프록시 경유의 Trusted Proxy 인증에도 대응합니다

---

## 8. 자동으로 태그를 붙이고 싶을 때

수동으로 태그를 붙이기 번거로울 때, AI에 이미지를 분석시켜 태그를 자동 부여하고 싶을 때.

### 절차 A: WD-Tagger (고속/태그 특화)

1. **Settings**에서 WD-Tagger ONNX 모델을 다운로드합니다
2. Tools 페이지 또는 상세 모달에서 **WD-Tagger 실행**을 클릭합니다
3. Danbooru 스타일의 태그가 자동 부여됩니다

### 절차 B: AI Analysis (자연어/고정밀)

1. **Settings > AI Analysis**에서 Ollama 또는 OpenAI 호환 서버를 추가합니다
2. 이미지의 상세 모달의 **AI Analysis 탭**에서 분석을 실행합니다
3. 자연어로 된 이미지 설명이 생성됩니다

### 팁

- WD-Tagger는 VLM 엔진 (OpenAI API 호환)과의 복합 모드에도 대응합니다
- NSFW 필터나 태그 정규화 등의 후처리가 자동 적용됩니다
- XMP 메타데이터에 태그를 쓰는 기능도 지원하여 다른 도구와의 연동이 용이합니다

---

## 9. 통계/리포트를 보고 싶을 때

자신의 이미지 라이브러리의 경향과 성장 추이를 파악하고 싶을 때.

### 절차

1. 내비게이션에서 **Stats** 페이지를 열고 전체 통계를 확인합니다
2. **Monthly Report** 페이지에서 월별 상세 리포트를 열람합니다
   - 월간 파일 수/전월 대비, TOP 20 태그, 신규 태그, 소스 분포, 일별 카운트
3. **Trophies** 섹션에서 실적 트로피를 확인합니다

### 팁

- 트로피는 6개 카테고리 (milestone / streak / diversity / source / hidden), 4개 티어 (bronze~platinum)로 단계적으로 해제됩니다
- 타임존 설정 (Settings > Appearance)을 올바르게 설정하면 일별 통계가 정확해집니다

---

## 10. MCP로 AI 에이전트와 연동하고 싶을 때

Claude Desktop이나 다른 MCP 호환 AI 도구에서 이미지 라이브러리를 조작하고 싶을 때.

### 절차

1. MCP 클라이언트 (Claude Desktop 등)의 설정에 YU AI Manager의 MCP 서버를 등록합니다
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. AI에게 「이미지를 검색해 줘」 「즐겨찾기에 추가해 줘」 등 자연어로 지시합니다
3. `search_images`, `add_favorite`, `trigger_scan` 등 60개 이상의 도구를 사용할 수 있습니다

### 팁

- MCP 클라이언트 확장에서는 외부 MCP 서버 (stdio / SSE / Streamable HTTP)에도 연결할 수 있습니다
- API Key 인증을 설정하면 CSRF 헤더 없이 외부 도구에서 REST API를 직접 호출할 수도 있습니다
- Hailo GenAI 확장을 사용하면 OpenAI SDK 호환 엔드포인트 경유로도 연동이 가능합니다

---

## 11. Hailo-10H를 OpenAI 호환 서버로 사용하기

Hailo-10H NPU가 탑재된 환경에서 OpenAI SDK와 완전 호환되는 로컬 AI 서버로 활용할 수 있습니다. Open WebUI, Continue.dev, 커스텀 스크립트 등 외부 도구에서 Hailo의 LLM / VLM / 음성 인식 / CLIP 임베딩을 직접 이용할 수 있습니다.

### 지원 엔드포인트

| 엔드포인트 | 기능 | 대응하는 OpenAI API |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | 다운로드된 모델 목록 | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | 텍스트 생성 및 이미지 이해 (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | 음성-텍스트 변환 | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | 텍스트→벡터 변환 (CLIP) | Embeddings |

### 절차

1. **Extensions > GenAI** 페이지에서 Hailo GenAI 확장이 활성화되어 있는지 확인
2. 필요한 모델 다운로드 (LLM: `qwen2.5-1.5b-chat` 등, VLM: `llava-v1.6-vicuna-7b` 등)
3. 외부 도구의 연결 설정에서 **Base URL**을 다음으로 설정:
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   (포트 번호는 YU AI Manager의 시작 설정에 맞게 변경)
4. 로컬 액세스에는 API Key가 필요 없습니다. 도구가 필수로 요구하면 더미 값 (예: `dummy`)을 입력

### 외부 도구 연결 예시

#### Open WebUI

Settings > Connections > OpenAI API에서 추가:
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev (VS Code AI 어시스턴트)

`~/.continue/config.json`에 추가:
```json
{
  "models": [{
    "title": "Hailo Qwen2.5",
    "provider": "openai",
    "model": "qwen2.5-1.5b-chat",
    "apiBase": "http://localhost:5000/ext/hailo-genai/v1",
    "apiKey": "dummy"
  }]
}
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# 텍스트 생성
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# 음성-텍스트 변환
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# 텍스트 임베딩 (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### 지원 파라미터

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input` (문자열 또는 문자열 배열)
- **모델 별칭**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### 주의사항

- **디바이스 배타성**: Hailo-10H는 동시에 1개의 GenAI 모델 (LLM 또는 VLM 또는 S2T)만 로드할 수 있습니다. GenAI 페이지에서 모드를 전환하세요
- **이미지 URL 제한**: 보안상 `http://` 이미지 URL은 차단됩니다. `data:image/...;base64,...` 형식 또는 YU AI Manager의 `file_id:` 형식을 사용하세요
- **CLIP 임베딩**: 텍스트→벡터 변환만 지원합니다. 이미지→벡터는 `/api/semantic/` 엔드포인트를 이용하세요
- **오디오 형식**: WAV 이외의 형식 (MP3, M4A, OGG 등)은 ffmpeg 설치가 필요합니다
- **`usage` 필드**: 토큰 카운트는 항상 0이 반환됩니다 (Hailo NPU 제약)
