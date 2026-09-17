# MCP 도구 레퍼런스

YU AI Manager MCP (Model Context Protocol) 서버에서 제공하는 도구의 전체 목록입니다.
Claude Desktop 및 기타 MCP 클라이언트에서 이 도구들을 호출하여 라이브러리 관리, 분석, 생성을 자동화할 수 있습니다.

**총 도구 수: 521**

## 목차

- [검색 및 탐색 (10)](#검색--탐색-10)
- [컬렉션 (7)](#컬렉션-7)
- [평점 및 태그 (5)](#평점--태그-5)
- [즐겨찾기 (8)](#즐겨찾기-8)
- [어노테이션 (4)](#어노테이션-4)
- [스캔 (14)](#스캔-14)
- [스캔 루트 (9)](#스캔-루트-9)
- [해시 및 중복 (7)](#해시--중복-7)
- [대기 / 진행 상황 (2)](#대기--진행-상황-2)
- [AI 분석 (25)](#ai-분석-25)
- [WD-Tagger (15)](#wd-tagger-14)
- [시맨틱 검색 / CLIP (12)](#시맨틱-검색--clip-12)
- [YOLO 객체 감지 (17)](#yolo-객체-감지-17)
- [OCR (19)](#ocr-19)
- [SD WebUI Bridge (14)](#sd-webui-bridge-14)
- [ComfyUI Bridge (13)](#comfyui-bridge-13)
- [NovelAI Bridge (8)](#novelai-bridge-8)
- [Hailo GenAI (10)](#hailo-genai-10)
- [Hailo Chat (7)](#hailo-chat-7)
- [Hailo Remote Tagger (7)](#hailo-remote-tagger-7)
- [Tagger Server Registry (13)](#tagger-server-registry-13)
- [프롬프트 라이브러리 (21)](#프롬프트-라이브러리-21)
- [프롬프트 시뮬레이터 (6)](#프롬프트-시뮬레이터-6)
- [프롬프트 구문 (1)](#프롬프트-구문-1)
- [SD/NAI 변환 (3)](#sdnai-변환-3)
- [채팅 로그 (16)](#채팅-로그-16)
- [Markdown 뷰어 (8)](#markdown-뷰어-8)
- [Freeze & Pull-back (6)](#freeze--pull-back-6)
- [음성-텍스트 변환 (8)](#음성-텍스트-변환-8)
- [통계 (6)](#통계-6)
- [프로필 (11)](#프로필-11)
- [파일 작업 (4)](#파일-작업-4)
- [SVG 래스터화 (2)](#svg-래스터화-2)
- [다운로드 (1)](#다운로드-1)
- [동영상 분석 (3)](#동영상-분석-3)
- [백업 (5)](#백업-5)
- [아카이브 정리 (7)](#아카이브-정리-7)
- [자동 스캔 감시 (3)](#자동-스캔-감시-3)
- [스케줄러 (6)](#스케줄러-6)
- [웹훅 (9)](#웹훅-9)
- [확장 프로그램 (25)](#확장-프로그램-25)
- [UI 관리 (4)](#ui-관리-4)
- [설정 (18)](#설정-18)
- [SNS 공유 (15)](#sns-공유-15)
- [LAN 공유 (2)](#lan-공유-2)
- [MCP 클라이언트 (8)](#mcp-클라이언트-8)
- [Cross Search (9)](#cross-search-9)
- [태그 사전 (6)](#태그-사전-6)
- [트로피 (1)](#트로피-1)
- [소스 코드 탐색 (3)](#소스-코드-탐색-3)
- [도움말 (3)](#도움말-3)
- [시스템 정보 (3)](#시스템-정보-3)
- [시스템 업데이트 (5)](#시스템-업데이트-5)
- [제안 (4)](#제안-4)
- [로그 및 디버그 (9)](#로그--디버그-9)
- [에이전트 안전 게이트웨이 (25)](#에이전트-안전-게이트웨이-25)
- [GitHub Integration (12)](#github-integration-12)
- [디버그 도구 (9)](#디버그-도구-9)
- [LoRA Dataset Manager (15)](#lora-dataset-manager-14)
- [LLM 엔드포인트 (5)](#llm-엔드포인트-5)
- [LLM 채팅 (1)](#llm-채팅-1)
- [서버 모드 (1)](#서버-모드-1)

---

## 설정

### 환경 변수

| 변수 | 설명 | 기본값 |
|----------|-------------|---------|
| `YU_BASE_URL` | YU AI Manager 서버 URL | `http://localhost:5000` |
| `YU_API_KEY` | API Key (Bearer 인증) | (없음) |
| `YU_DEBUG_MODE` | `1`로 설정하면 디버그 도구 활성화 | `0` |

### Claude Desktop 설정 예시 (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### 진행 알림

`wait_for_scan` / `wait_for_batch` 도구는 MCP Notifications를 지원합니다:
- **progressToken을 지원하는 클라이언트**: `notifications/progress`를 통해 실시간 진행 상황을 수신합니다.
- **미지원 클라이언트**: 완료될 때까지 호출이 차단되고 최종 결과를 반환합니다.

---

## 검색 및 탐색 (10)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `search_images` | 다양한 필터로 이미지 검색 | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | 디렉토리 그룹별 이미지 검색 | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | 여러 쿼리의 통합 검색 | `queries`: list |
| `get_image_detail` | 이미지의 전체 메타데이터 조회 | `file_id`: int |
| `get_library_stats` | 라이브러리 통계 | -- |
| `get_file_info` | 파일 경로 및 메타데이터 정보 | `file_id`: int |
| `get_groups_index` | 디렉토리 그룹 인덱스 | -- |
| `get_group_members` | 그룹 내 멤버 목록 | `group`: str |
| `get_container_members` | ZIP/RAR 컨테이너 내 멤버 목록 | `file_id`: int |
| `file_search` | 데이터베이스에서 파일을 경로/이름으로 검색 | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## 컬렉션 (7)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_collections` | 모든 컬렉션 나열 | -- |
| `create_collection` | 컬렉션 생성 | `name`: str |
| `rename_collection` | 컬렉션 이름 변경 | `collection_id`: int, `name`: str |
| `delete_collection` | 컬렉션 삭제 | `collection_id`: int |
| `reorder_collections` | 컬렉션 순서 변경 | `order`: list |
| `add_to_collection` | 컬렉션에 이미지 추가 | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | 컬렉션에서 이미지 제거 | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## 평점 및 태그 (5)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `rate_images` | 여러 이미지의 평점 일괄 설정 | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | 파일 평점 조회 | `file_ids`: str |
| `get_ratings_stats` | 평점 통계 | -- |
| `set_tags` | 여러 이미지의 사용자 태그 추가/삭제 | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | 데이터베이스 태그 정규화 | -- |

## 즐겨찾기 (8)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `toggle_favorite` | 즐겨찾기 상태 토글 | `file_id`: int |
| `check_favorite` | 즐겨찾기 상태 확인 | `file_id`: int |
| `check_favorite_collections` | 즐겨찾기된 파일의 컬렉션 멤버십 확인 | `file_id`: int |
| `list_favorites` | 즐겨찾기 목록 | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | 여러 파일을 즐겨찾기에 일괄 추가 | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | 여러 파일을 즐겨찾기에서 일괄 제거 | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | 즐겨찾기를 서버 폴더로 내보내기 | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | 즐겨찾기 컬렉션 이미지 목록 | `collection_id`: int = 0 |

## 어노테이션 (4)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `set_annotations` | 어노테이션 저장 (upsert) | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | 이미지의 어노테이션 조회 | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | 파일 전체에서 어노테이션 검색 | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | 어노테이션 삭제 | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## 스캔 (14)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `trigger_scan` | 모든 스캔 루트 스캔 시작 | -- |
| `start_scan` | 지정 경로 또는 전체 루트 스캔 시작 | `path`: str = '' |
| `get_scan_status` | 스캔 진행 상황 조회 | -- |
| `cancel_scan` | 스캔 취소 | -- |
| `resume_scan` | 중단된 스캔 재개 | -- |
| `dismiss_interrupted_scan` | 중단 상태 폐기 | -- |
| `get_scan_interrupted` | 중단된 스캔 정보 조회 | -- |
| `get_scan_errors` | 스캔 오류 목록 | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | 오류를 해결됨으로 표시 | `error_id`: int |
| `clear_scan_errors` | 해결된 오류 정리 | -- |
| `get_scanned_roots` | 스캔된 루트 목록 | -- |
| `scan_queue_list` | 스캔 큐 대기 항목 목록 | -- |
| `scan_queue_remove` | 스캔 큐에서 항목 제거 | `queue_id`: str |
| `scan_queue_clear` | 스캔 큐 전체 초기화 | -- |

## 스캔 루트 (9)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_scan_roots` | 스캔 루트 목록 | -- |
| `add_scan_root` | 스캔 루트 추가 | `path`: str |
| `edit_scan_root` | 스캔 루트 경로 편집 | `index`: int, `path`: str |
| `remove_scan_root` | 스캔 루트 제거 | `index`: int |
| `toggle_scan_root` | 스캔 루트 활성화/비활성화 토글 | `index`: int |
| `reorder_scan_roots` | 스캔 루트 순서 변경 | `order`: list |
| `scan_directory` | 특정 디렉토리 스캔 | `path`: str |
| `get_checkpoints` | 사용 가능한 모델 체크포인트 목록 | -- |
| `purge_scanned_roots` | 스캔된 루트 레코드 퍼지 | -- |

## 해시 및 중복 (7)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `find_duplicates` | 중복 파일 감지 | `method`: str = 'hash' |
| `find_similar` | 지각 해시로 유사 이미지 검색 | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | 파일 해시 계산 작업 시작 | `hash_type`: str = 'both' |
| `delete_duplicates` | 중복 파일 삭제 | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | 미계산 해시 일괄 계산 시작 | -- |
| `cancel_hash_backfill` | 해시 계산 취소 | -- |
| `get_hash_backfill_status` | 해시 계산 진행 상황 조회 | -- |

## 대기 / 진행 상황 (2)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `wait_for_scan` | 스캔 완료까지 대기 (진행 알림 지원) | `timeout`: int = 600 |
| `wait_for_batch` | 배치 작업 완료까지 대기 (진행 알림 지원) | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI 분석 (25)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `analyze_image` | 단일 이미지 AI 분석 | `file_id`: int |
| `analyze_batch` | 여러 이미지 일괄 AI 분석 | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | 실행 중인 AI 분석 배치 작업 취소 | -- |
| `get_analysis_result` | 분석 결과 조회 | `file_id`: int |
| `get_analysis_stats` | 분석 통계 | -- |
| `get_analysis_config` | 분석 설정 조회 | -- |
| `save_analysis_config` | 분석 설정 저장 | `config`: dict |
| `get_available_engines` | 사용 가능한 엔진 목록 | -- |
| `get_ollama_models` | Ollama 모델 목록 | -- |
| `test_ollama_connection` | Ollama 연결 테스트 | -- |
| `get_openai_compat_models` | OpenAI 호환 API 모델 목록 | -- |
| `test_openai_compat_connection` | OpenAI 호환 API 연결 테스트 | -- |
| `list_ai_servers` | 등록된 AI 서버 목록 | -- |
| `add_ai_server` | AI 서버 등록 | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | AI 서버 설정 업데이트 | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | AI 서버 제거 | `server_id`: str |
| `set_active_ai_server` | 활성 서버 전환 | `server_id`: str |
| `test_ai_server` | AI 서버 연결 테스트 | `server_id`: str |
| `reorder_ai_servers` | 서버 우선순위 변경 | `order`: list |
| `migrate_ai_servers` | 레거시 설정에서 마이그레이션 | -- |
| `analyze_prompt_trends` | 프롬프트 트렌드 분석 | `limit`: int = 100 |
| `get_trend_history` | 트렌드 분석 이력 조회 | `limit`: int = 20 |
| `delete_trend_history` | 트렌드 이력 삭제 | `history_id`: int |
| `analyze_video` | 멀티 키프레임 동영상 분석 (Vision LLM) | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | Whisper로 오디오/동영상 파일 전사 | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | 오디오 분석 가용 상태 확인 | -- |

## WD-Tagger (15)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `wd_tagger_tag_file` | 단일 파일 태그 추론 실행 | `file_id`: int |
| `wd_tagger_batch` | 여러 파일 일괄 태그 추론 | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | 실행 중인 WD-Tagger 배치 작업 취소 | -- |
| `wd_tagger_get_tags` | 파일의 WD-Tagger 태그 조회 | `file_id`: int |
| `wd_tagger_delete_tags` | 파일의 WD-Tagger 태그 삭제 | `file_id`: int |
| `wd_tagger_delete_tags_batch` | 여러 파일의 WD-Tagger 태그 일괄 삭제 | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | XMP 메타데이터 조회 | `file_id`: int |
| `wd_tagger_stats` | 태그 통계 | -- |
| `wd_tagger_untagged` | 태그 없는 파일 목록 | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | 설정 조회 | -- |
| `wd_tagger_save_config` | 설정 저장 | `config`: dict |
| `wd_tagger_model_status` | 모델 다운로드 상태 | -- |
| `wd_tagger_download_model` | 모델 다운로드 | -- |
| `wd_tagger_vlm_test` | VLM 서버 연결 테스트 | `url`: str |
| `wd_tagger_vlm_models` | VLM 서버 모델 목록 | `url`: str |

## 시맨틱 검색 / CLIP (12)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `semantic_search` | 자연어 텍스트로 이미지 검색 | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | 확장 프로그램 상태 | -- |
| `semantic_backend_info` | CLIP 백엔드 정보 | -- |
| `semantic_model_status` | 모델 상태 | -- |
| `semantic_model_download` | CLIP 모델 다운로드 | -- |
| `semantic_index_start` | 인덱스 구축 시작 | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | 인덱스 진행 상황 | -- |
| `semantic_index_stop` | 인덱스 구축 중지 | -- |
| `semantic_index_clear` | 인덱스 삭제 | -- |
| `semantic_caption_start` | 일괄 캡션 생성 시작 | `batch_size`: int = 50 |
| `semantic_caption_status` | 캡션 진행 상황 | -- |
| `semantic_caption_stop` | 캡셔닝 중지 | -- |

## YOLO 객체 감지 (17)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `yolo_status` | 확장 프로그램 상태 | -- |
| `yolo_detect_start` | 객체 감지 시작 | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | 감지 작업 진행 상황 | -- |
| `yolo_detect_stop` | 감지 중지 | -- |
| `yolo_get_results` | 파일의 감지 결과 조회 | `file_id`: int |
| `yolo_search` | 감지 레이블로 이미지 검색 | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | 감지 결과 삭제 | `file_ids`: list = None |
| `yolo_model_status` | 모델 상태 | -- |
| `yolo_model_download` | YOLO HEF 모델 다운로드 | -- |
| `yolo_list_labels` | 감지된 레이블 목록 | -- |
| `yolo_stream_sources` | 스트림 소스 목록 및 상태 | -- |
| `yolo_stream_start` | 스트림 소스 시작 | `source_id`: str |
| `yolo_stream_stop` | 스트림 소스 정지 | `source_id`: str |
| `yolo_stream_add_source` | 스트림 소스 추가 | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | 감지 규칙 목록 | -- |
| `yolo_stream_add_rule` | 감지 규칙 추가 | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | 스트림 전체 상태 (파이프라인, 소스, 규칙, 녹화) | -- |

## OCR (19)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `ocr_extract` | 이미지에서 OCR 텍스트 추출 | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | 여러 파일에 OCR 실행 | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | 파일의 OCR 결과 조회 | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | 파일의 OCR 결과 삭제 | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | OCR 결과를 지정 형식으로 내보내기 | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | OCR 결과 번역 | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | 파일의 번역 결과 조회 | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | 동영상 키프레임에 OCR 실행 | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | OCR 결과 바운딩 박스 검출 | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | OCR 오버레이 이미지 생성 | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | OCR 결과 일괄 내보내기 | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | PDF 문서에 OCR 실행 | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | 사용 가능한 OCR 엔진 및 능력 점수 목록 | -- |
| `ocr_profiles` | 전체 모델 능력 프로필 목록 | -- |
| `ocr_profiles_fetch` | URL에서 커뮤니티 모델 프로필 가져오기/병합 | `url`: str |
| `ocr_profile_update` | 모델 능력 점수 수동 업데이트 | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | OCR 벤치마크로 정확도 측정 | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | 사용 가능한 벤치마크 테스트 케이스 목록 | `benchmark_dir`: str = "" |
| `ocr_npu_status` | NPU 가용 상태 및 최적화 제안 확인 | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `sd_test_connection` | 연결 테스트 | -- |
| `sd_generate` | txt2img 이미지 생성 | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | 생성 진행 상황 | -- |
| `sd_cancel` | 생성 취소 | -- |
| `sd_list_models` | 체크포인트 모델 목록 | -- |
| `sd_list_samplers` | 샘플러 목록 | -- |
| `sd_list_loras` | LoRA 목록 | `q`: str = '' |
| `sd_list_embeddings` | 임베딩 목록 | `q`: str = '' |
| `sd_list_scripts` | 스크립트 목록 | -- |
| `sd_get_script_info` | 스크립트 상세 정보 | -- |
| `sd_list_extensions` | 확장 프로그램 목록 | -- |
| `sd_list_upscalers` | 업스케일러 목록 | -- |
| `sd_get_config` | 설정 조회 | -- |
| `sd_save_config` | 설정 저장 | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `comfyui_test_connection` | 연결 테스트 | -- |
| `comfyui_generate` | txt2img 이미지 생성 | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | JSON 워크플로우로 생성 | `workflow`: str |
| `comfyui_get_progress` | 생성 진행 상황 | -- |
| `comfyui_cancel` | 생성 취소 | -- |
| `comfyui_list_models` | 체크포인트 모델 목록 | -- |
| `comfyui_list_samplers` | 샘플러 목록 | -- |
| `comfyui_list_schedulers` | 스케줄러 목록 | -- |
| `comfyui_list_loras` | LoRA 목록 | `q`: str = '' |
| `comfyui_list_embeddings` | 임베딩 목록 | `q`: str = '' |
| `comfyui_list_custom_nodes` | 커스텀 노드 목록 | `q`: str = '' |
| `comfyui_get_config` | 설정 조회 | -- |
| `comfyui_save_config` | 설정 저장 | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `nai_test_connection` | 연결 테스트 | -- |
| `nai_get_anlas` | Anlas 잔액 조회 | -- |
| `nai_generate` | 이미지 생성 | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | 모델 목록 | -- |
| `nai_list_samplers` | 샘플러 목록 | -- |
| `nai_list_noise_schedules` | 노이즈 스케줄 목록 | -- |
| `nai_get_config` | 설정 조회 | -- |
| `nai_save_config` | 설정 저장 | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `hailo_genai_status` | 확장 프로그램 상태 | -- |
| `hailo_genai_model_status` | 모델 로드 상태 | -- |
| `hailo_genai_model_download` | 모델 다운로드 | `model_name`: str = '' |
| `hailo_genai_model_unload` | 모델 언로드 | -- |
| `hailo_llm_generate` | LLM 텍스트 생성 | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | LLM 컨텍스트 초기화 | -- |
| `hailo_vlm_generate` | VLM 이미지-텍스트 생성 | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | Hailo LLM 성능 벤치마크 실행 | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Hailo vs Ollama LLM 성능 비교 | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | Hailo GenAI OpenAI 호환 API 엔드포인트 정보 | -- |

## Hailo Chat (7)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `hailo_chat_new` | 새 Hailo Chat 대화 생성 | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | Hailo Chat 대화 목록 | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | 전체 메시지 포함 대화 조회 | `conversation_id`: int |
| `hailo_chat_active` | 현재 활성 대화 ID 조회 | -- |
| `hailo_chat_search` | DuckDuckGo 웹 검색 (컨텍스트 주입용) | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | 대화 이름 변경 | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | 대화 삭제 | `conversation_id`: int |

## Hailo Remote Tagger (7)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `hailo_tagger_tag_file` | Hailo 원격 태거로 단일 파일 태그 부여 | `file_id`: int |
| `hailo_tagger_batch` | 여러 파일 일괄 태그 부여 (최대 500) | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | Hailo 원격 태거 연결 상태 확인 | -- |
| `hailo_tagger_get_config` | Hailo 원격 태거 설정 가져오기 | -- |
| `hailo_tagger_save_config` | Hailo 원격 태거 설정 저장 | `config`: dict |
| `hailo_tagger_get_tags` | 파일의 Hailo 태그 가져오기 | `file_id`: int |
| `hailo_tagger_delete_tags` | 파일의 Hailo 태그 삭제 | `file_id`: int |

## Tagger Server Registry (13)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `tagger_servers_list` | 등록된 태거 서버 목록 및 분산 모드 조회 | -- |
| `tagger_servers_add` | 태거 서버 추가 | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | 태거 서버 설정 업데이트 | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | 태거 서버 삭제 | `server_id`: str |
| `tagger_servers_test` | 태거 서버 연결 테스트 | `server_id`: str |
| `tagger_servers_health` | 모든 활성 서버 상태 확인 | -- |
| `tagger_servers_set_mode` | 분산 모드 설정 (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | 분산 배치 태깅 (공유 큐 워크스틸링) | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | 실행 중인 태거 클러스터 배치 작업 취소 | -- |
| `tagger_servers_tags` | 파일의 태거 태그 조회 | `file_id`: int |
| `tagger_servers_delete_tags` | 파일의 태거 태그 삭제 | `file_id`: int |
| `tagger_servers_stats` | 태거 통계 (미태깅 파일 수) | -- |
| `tagger_servers_migrate_legacy` | 레거시 hailo_tagger 설정을 레지스트리 형식으로 마이그레이션 | -- |

## 프롬프트 라이브러리 (21)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `search_prompts` | 프롬프트 검색 | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | 프롬프트 상세 조회 | `prompt_id`: int |
| `create_prompt` | 프롬프트 생성 | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | 이미지 메타데이터로 프롬프트 생성 | `file_id`: int |
| `update_prompt` | 프롬프트 업데이트 (부분 업데이트) | `prompt_id`: int, ... |
| `delete_prompt` | 프롬프트 삭제 | `prompt_id`: int |
| `list_prompt_folders` | 폴더 목록 | -- |
| `create_prompt_folder` | 폴더 생성 | `name`: str |
| `update_prompt_folder` | 폴더 이름 변경 | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | 폴더 삭제 | `folder_id`: int |
| `move_prompt_to_folder` | 프롬프트를 폴더로 이동 | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | 폴더에서 제거 (루트로 이동) | `prompt_id`: int |
| `list_prompt_tags` | 태그 목록 | -- |
| `create_prompt_tag` | 태그 생성 | `name`: str |
| `delete_prompt_tag` | 태그 삭제 | `tag_id`: int |
| `set_prompt_tags` | 프롬프트에 태그 설정 | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | 일괄 삭제 | `prompt_ids`: list |
| `bulk_move_prompts` | 일괄 이동 | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | 일괄 태그 | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | 모든 프롬프트 JSON 내보내기 | -- |
| `import_prompts` | JSON에서 프롬프트 가져오기 | `data`: dict |

## 프롬프트 시뮬레이터 (6)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `prompt_dp_analyze` | Dynamic Prompts 구문 분석 | `text`: str |
| `prompt_emphasis` | 강조 구문 변환 | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | A1111 <-> NAI 형식 변환 | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | 와일드카드 목록 | -- |
| `prompt_set_wildcard_dirs` | 와일드카드 디렉토리 설정 | `dirs`: list |
| `prompt_danbooru_autocomplete` | Danbooru 태그 자동완성 | `q`: str |

## 프롬프트 구문 (1)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `analyze_prompt_syntax` | 프롬프트 구문 분석 (토큰 정보) | `text`: str, `engine`: str = 'a1111' |

## SD/NAI 변환 (3)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `convert_sd_to_nai` | SD에서 NAI로 프롬프트 변환 | `text`: str |
| `convert_nai_to_sd` | NAI에서 SD로 프롬프트 변환 | `text`: str |
| `convert_prompt_batch` | 일괄 프롬프트 변환 | `items`: list, `direction`: str = 'sd-to-nai' |

## 채팅 로그 (16)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `search_chat_logs` | FTS5 전문 검색 | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | 대화별 그룹 검색 | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | 대화 상세 (전체 메시지) | `conversation_id`: int |
| `get_chat_full` | get_conversation의 별칭 | `conversation_id`: int |
| `get_chat_summary` | AI 생성 요약 | `conversation_id`: int |
| `get_chat_decisions` | AI 추출 결정 사항 | `conversation_id`: int |
| `get_related_conversations` | 관련 대화 | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | 엔티티로 대화 검색 | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | 주제별 검색 | `topic`: str, `limit`: int = 50 |
| `search_decisions` | 대화 전체에서 결정 사항 검색 | `query`: str, `limit`: int = 50 |
| `import_chat_log` | 로컬 파일에서 가져오기 | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | 가져오기 진행 상황 | -- |
| `get_chatlog_stats` | 채팅 로그 통계 | -- |
| `delete_conversation` | 대화 삭제 | `conversation_id`: int |
| `reprocess_chat_logs` | AI 재처리 | `target`: str = 'unprocessed' |
| `text_search` | MD/채팅/프롬프트 교차 검색 | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown 뷰어 (8)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `search_md_files` | Markdown 파일 검색 | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | 파일 내용 조회 | `file_id`: int |
| `get_md_scan_roots` | 스캔 루트 목록 | -- |
| `set_md_scan_roots` | 스캔 루트 설정 | `roots`: list |
| `remove_md_scan_root` | 스캔 루트 제거 | `index`: int |
| `trigger_md_scan` | 스캔 시작 | -- |
| `get_md_scan_status` | 스캔 진행 상황 | -- |
| `get_md_stats` | 통계 | -- |

## Freeze & Pull-back (6)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `generate_freeze_pullback` | Ken Burns 동영상 생성 | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | 렌더 작업 상태 | -- |
| `fpb_check` | 사전 요구사항 확인 (ffmpeg 등) | -- |
| `fpb_cancel` | 생성 취소 | -- |
| `fpb_list_outputs` | 출력 파일 목록 | -- |
| `fpb_delete_output` | 출력 파일 삭제 | `filename`: str |

## 음성-텍스트 변환 (8)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `s2t_status` | 백엔드 상태 | -- |
| `s2t_transcribe_video` | 동영상/오디오 음성 인식 | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | 일괄 음성 인식 | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | 저장된 음성 인식 결과 조회 | `file_id`: int |
| `s2t_stream_start` | 스트림 음성 인식 시작 | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | 스트림 음성 인식 중지 | -- |
| `s2t_stream_status` | 스트림 상태 조회 | -- |
| `s2t_stream_transcript` | 스트림 음성 인식 결과 조회 | -- |

## 통계 (6)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `get_stats_timeline` | 타임라인 통계 | `period`: str = 'daily' |
| `get_stats_hourly` | 시간대별 통계 | -- |
| `get_stats_models` | 모델 사용 통계 | -- |
| `get_stats_resolutions` | 해상도 분포 통계 | -- |
| `get_stats_story` | 라이브러리 스토리 내러티브 | -- |
| `get_monthly_report` | 월간 보고서 | `month`: str = '' |

## 프로필 (11)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_profiles` | 프로필 목록 | -- |
| `get_profile` | 프로필 조회 | `name`: str |
| `create_profile` | 프로필 생성 | `name`: str, `description`: str = '' |
| `update_profile` | 프로필 업데이트 | `name`: str, `settings`: dict |
| `delete_profile` | 프로필 삭제 | `name`: str |
| `duplicate_profile` | 프로필 복제 | `name`: str, `new_name`: str |
| `rename_profile` | 프로필 이름 변경 | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | 즐겨찾기 토글 | `name`: str |
| `export_profile` | 프로필 내보내기 | `name`: str |
| `import_profile` | 내보내기 데이터에서 프로필 가져오기 | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | 프로필 가져오기 미리보기 | `qr_data`: str |

## 파일 작업 (4)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `convert_image` | 이미지 형식 변환 | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | ZIP에서 파일 추출 | `file_id`: int, `members`: list |
| `inspect_metadata` | 원본 메타데이터 검사 | `file_id`: int |
| `get_share_link` | 공유 링크 생성 | `file_id`: int |

## SVG 래스터화 (2)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `svg_info` | SVG 래스터화 가용성 및 백엔드 정보 확인 | — |
| `svg_rasterize` | SVG를 PNG/WebP 비트맵으로 래스터화. 반환된 base64는 img2img 입력으로 직접 사용 가능 | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## 다운로드 (1)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `batch_download_zip` | 여러 이미지를 ZIP으로 다운로드 | `file_ids`: list, `expected_count`: int = 0 |

## 동영상 분석 (3)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `get_video_analysis_config` | 동영상 분석 설정 조회 | -- |
| `save_video_analysis_config` | 동영상 분석 설정 저장 | `config`: dict |
| `get_video_analysis_status` | 동영상 분석 상태 | -- |

## 백업 (5)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_backups` | 백업 목록 | -- |
| `create_backup` | 백업 생성 | -- |
| `restore_backup` | 백업 복원 | `filename`: str |
| `delete_backup` | 백업 삭제 | `filename`: str |
| `get_backup_status` | 백업 상태 | -- |

## 아카이브 정리 (7)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `archive_cleanup_scan` | 아카이브 쌍 스캔 | `path`: str = '' |
| `archive_cleanup_execute` | 정리 실행 | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | LLM으로 작업 검증 (단일) | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | LLM으로 작업 검증 (일괄) | `items`: list |
| `archive_cleanup_get_llm_config` | LLM 설정 조회 | -- |
| `archive_cleanup_save_llm_config` | LLM 설정 저장 | `config`: dict |
| `archive_cleanup_list_models` | 사용 가능한 LLM 모델 목록 | -- |

## 자동 스캔 감시 (3)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `auto_scan_info` | 감시 상태 | -- |
| `auto_scan_start` | 파일 감시 시작 | -- |
| `auto_scan_stop` | 파일 감시 중지 | -- |

## 스케줄러 (6)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `get_scheduler_status` | 태스크 스케줄러 상태 및 등록 작업 조회 | -- |
| `list_scheduled_jobs` | 전체 스케줄 작업의 트리거 및 다음 실행 시간 | -- |
| `trigger_scheduled_job` | 스케줄 작업 즉시 실행 트리거 | `job_id`: str |
| `pause_scheduled_job` | 스케줄 작업 일시 중지 | `job_id`: str |
| `resume_scheduled_job` | 일시 중지된 스케줄 작업 재개 | `job_id`: str |
| `get_scheduler_history` | 스케줄 작업 최근 실행 이력 조회 | -- |

## 웹훅 (9)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_webhooks` | 웹훅 목록 | -- |
| `create_webhook` | 웹훅 생성 | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | 웹훅 업데이트 | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | 웹훅 삭제 | `webhook_id`: str |
| `test_webhook` | 테스트 이벤트 전송 | `webhook_id`: str |
| `get_webhook_deliveries` | 전달 이력 | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | 외부 트리거용 inbound webhook 생성. token URL 반환. | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | 등록된 inbound webhook 목록 조회. | — |
| `delete_inbound_webhook` | inbound webhook 삭제. | `webhook_id`: str |

## 확장 프로그램 (25)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_extensions` | 확장 프로그램 목록 | -- |
| `get_extension_detail` | 확장 프로그램 상세 정보 | `name`: str |
| `toggle_extension` | 활성화/비활성화 토글 | `name`: str, `enabled`: bool |
| `install_extension` | Git 저장소에서 설치 | `url`: str |
| `update_extension` | 확장 프로그램 업데이트 | `name`: str |
| `update_all_extensions` | 모든 확장 프로그램 일괄 업데이트 | -- |
| `uninstall_extension` | 확장 프로그램 제거 | `name`: str |
| `search_marketplace` | 마켓플레이스 검색 | `query`: str = '' |
| `refresh_marketplace` | 마켓플레이스 카탈로그 새로고침 | -- |
| `get_extension_config` | 설정 조회 | `name`: str |
| `set_extension_config` | 설정 업데이트 | `name`: str, `values`: dict |
| `get_extension_permissions` | 권한 정보 조회 | `name`: str |
| `approve_extension_permissions` | 권한 승인/거부 | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | 정적 코드 분석 | `name`: str |
| `rescan_extension` | 코드 재스캔 | `name`: str |
| `get_extension_tokens` | 기능 토큰 상태 | `name`: str |
| `get_extension_integrity` | 파일 무결성 및 모니터링 상태 | `name`: str |
| `get_extension_hooks` | 등록된 훅 목록 | -- |
| `get_extension_isolation_status` | 프로세스 격리 상태 | -- |
| `get_extension_os_isolation_status` | OS 수준 격리 상태 | -- |
| `create_extension` | 스캐폴드 포함 커스텀 Extension 생성 | `name`: str, `description`: str = "" |
| `validate_extension` | Extension 매니페스트 및 코드 검증 | `extension_name`: str |
| `list_extension_files` | 커스텀 Extension 파일 목록 | `extension_name`: str |
| `read_extension_file` | 커스텀 Extension 파일 읽기 | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | 커스텀 Extension에 파일 쓰기 | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI 관리 (4)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_uis` | UI 목록 | -- |
| `switch_ui` | 활성 UI 전환 | `name`: str |
| `install_ui` | UI 설치 | `url`: str |
| `uninstall_ui` | UI 제거 | `name`: str |

## 설정 (18)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `settings_get_schema` | 설정 스키마 조회 | -- |
| `settings_get_all` | 모든 설정 조회 | -- |
| `settings_get` | 단일 설정 조회 | `key`: str |
| `settings_set` | 설정 업데이트 | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | 레거시 config.json 조회 | -- |
| `save_legacy_config` | 레거시 config.json 저장 | `config`: dict |
| `secrets_status` | 암호화 키 상태 | -- |
| `secrets_export` | 암호화 키 내보내기 | `password`: str |
| `secrets_import` | 암호화 키 가져오기 | `export_json`: str, `password`: str |
| `get_op_status` | 1Password CLI 상태 | -- |
| `delete_op_mapping` | 1Password 매핑 삭제 | `key`: str |
| `migrate_secrets_to_keychain` | OS 키체인으로 마이그레이션 | -- |
| `get_bw_status` | Bitwarden CLI 통합 상태 | -- |
| `list_bw_folders` | Bitwarden 폴더 목록 | -- |
| `delete_bw_mapping` | Bitwarden 필드 매핑 삭제 | `key`: str |
| `list_op_vaults` | 1Password Vault 목록 | -- |
| `push_secrets_to_1password` | 모든 시크릿을 1Password에 푸시하고 op_secrets 매핑 자동 연결 | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | 모든 시크릿을 Bitwarden에 푸시하고 매핑 자동 연결 | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS 공유 (15)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `share_to_bluesky` | Bluesky에 포스트 | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | Bluesky 연결 테스트 | -- |
| `get_x_share_url` | X (Twitter) 공유 URL 조회 | `file_id`: int |
| `get_sns_preview` | SNS 공유 미리보기 | `file_id`: int |
| `get_sns_config` | SNS 설정 조회 | -- |
| `save_sns_config` | SNS 설정 저장 | `config`: dict |
| `bsky_get_pending_notifications` | 큐에서 미읽은 Bluesky 알림 가져오기 | -- |
| `bsky_get_notification_queue` | 필터 적용 알림 큐 항목 | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | Bluesky 알림 즉시 폴링 | -- |
| `bsky_triage_notification` | 알림 분류 결과 설정 | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | 멘션/답글/인용에 자동 응답 전송 | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | Bluesky 모니터 설정 가져오기 | -- |
| `bsky_save_monitor_config` | Bluesky 모니터 설정 저장 | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | Bluesky 분류 프롬프트 및 템플릿 가져오기 | -- |
| `bsky_save_triage_prompts` | Bluesky 분류 프롬프트 저장 | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN 공유 (2)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `create_lan_share` | LAN 공유 토큰 생성 | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | 공유 토큰 취소 | `token`: str |

## MCP 클라이언트 (8)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_mcp_connections` | MCP 연결 목록 | -- |
| `create_mcp_connection` | MCP 연결 생성 | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | MCP 연결 업데이트 | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | MCP 연결 삭제 | `connection_id`: str |
| `connect_mcp_server` | MCP 서버에 연결 | `connection_id`: str |
| `disconnect_mcp_server` | MCP 서버에서 연결 해제 | `connection_id`: str |
| `get_mcp_connection_tools` | 연결된 서버의 도구 목록 | `connection_id`: str |
| `call_mcp_tool` | 연결된 서버의 도구 호출 | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `cross_search_get_scan_roots` | Cross Search 스캔 루트 디렉토리 조회 | -- |
| `cross_search_set_scan_roots` | Cross Search 스캔 루트 디렉토리 설정 | `roots`: list |
| `cross_search_delete_scan_root` | 인덱스로 스캔 루트 삭제 | `index`: int |
| `cross_search_scan` | Cross Search 텍스트 파일 스캔 시작 | -- |
| `cross_search_scan_stop` | 실행 중인 스캔 중지 | -- |
| `cross_search_scan_status` | 스캔 진행 상태 조회 | -- |
| `cross_search_get_txt` | 인덱스된 파일의 텍스트 내용 조회 | `file_id`: int |
| `cross_search_open_file` | 시스템 파일 관리자에서 파일 열기 | `path`: str |
| `cross_search_stats` | Cross Search 통계 조회 | -- |

## 태그 사전 (6)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `search_tag_dictionary` | 태그 사전 검색 | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | 태그 사전 통계 | -- |
| `split_tags` | 연결된 태그 분리 | `text`: str |
| `import_tag_dictionary` | 태그 사전 가져오기 | `data`: dict |
| `clear_tag_dictionary` | 태그 사전 초기화 | -- |
| `get_tag_dict_info` | 단일 태그 상세 정보 조회 | `tag`: str |

## 트로피 (1)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `list_trophies` | 트로피 목록 | -- |

## 소스 코드 탐색 (3)

프로젝트 소스 코드를 읽기 전용으로 안전하게 탐색하기 위한 도구입니다.
세 가지 보안 계층이 접근을 보호합니다: 경로 정규화, 확장자 화이트리스트, 민감 파일 차단 목록.
자세한 내용은 [`docs/api/source.md`](source.md)를 참조하십시오.

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `source_tree` | 디렉토리 트리 표시 | `path`: str = '', `depth`: int = 3 |
| `source_read` | 파일 내용 읽기 (줄 번호 포함) | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | 텍스트로 소스 코드 검색 | `query`: str, `glob`: str = '', `limit`: int = 30 |

## 도움말 (3)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `help_toc` | 도움말 목차 | -- |
| `help_get_section` | 섹션 내용 조회 | `section`: str |
| `help_search` | 도움말 검색 | `query`: str, `limit`: int = 5 |

## 시스템 정보 (3)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `get_server_info` | 서버 정보 | -- |
| `get_inference_info` | 추론 엔진 정보 | -- |
| `get_market_quotes` | 시장 정보 | -- |

## 시스템 업데이트 (5)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `check_for_update` | GitHub에서 새 버전 사용 가능 여부 확인 | -- |
| `get_update_status` | 현재 설치 방식과 버전 조회 | -- |
| `apply_system_update` | 사용 가능한 업데이트 적용 (git/portable만 해당) | `confirm`: str |
| `check_unified_updates` | 시스템 + 모든 확장의 업데이트 상태를 일괄 확인 | `force`: bool (optional) |
| `apply_unified_updates` | 시스템 + 확장을 일괄 업데이트 (설정 자동 백업) | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## 제안 (4)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `get_suggestions` | 태그/프롬프트 자동완성 | `q`: str, `limit`: int = 10 |
| `suggest_tags` | 태그 자동완성 | `q`: str, `limit`: int = 10 |
| `suggest_lora` | LoRA 이름 자동완성 | `q`: str = '' |
| `suggest_embedding` | 임베딩 이름 자동완성 | `q`: str = '' |

## 로그 및 디버그 (9)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `get_recent_logs` | 최근 로그 조회 | `limit`: int = 100 |
| `get_debug_log` | 디버그 로그 출력 | `lines`: int = 200 |
| `clear_debug_log` | 디버그 로그 삭제 | -- |
| `get_cache_info` | 캐시 통계 | -- |
| `clear_cache` | 캐시 삭제 | -- |
| `rebuild_groups` | 디렉토리 그룹 재구성 | -- |
| `list_dirs` | 디렉토리 목록 | `path`: str = '' |
| `debug_file_meta` | 파일 디버그 메타데이터 | `file_id`: int |
| `debug_model_check` | 모델 사용 가능 여부 확인 | -- |

## 에이전트 안전 게이트웨이 (25)

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `agent_status` | 전체 안전 기능 상태 | -- |
| `agent_kill` | Kill Switch 활성화 (모든 도구 즉시 차단) | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | Kill Switch 비활성화 | -- |
| `agent_circuit_breaker_status` | Circuit Breaker 상태 | -- |
| `agent_circuit_breaker_reset` | Circuit Breaker 초기화 | -- |
| `agent_budget_status` | Budget Tracker 상태 | -- |
| `agent_budget_reset` | Budget Tracker 초기화 | -- |
| `agent_approval_status` | 보류 중인 승인 요청 목록 | -- |
| `agent_approval_respond` | 승인 요청에 응답 | `request_id`: str, `action`: str |
| `agent_approval_history` | 승인 이력 | `limit`: int = 50 |
| `agent_scope_status` | Scope Fence 상태 | -- |
| `agent_scope_get` | 세션 범위 조회 | `session_id`: str |
| `agent_scope_set` | 세션 범위 설정 | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | 세션 범위 삭제 | `session_id`: str |
| `agent_tool_level` | 도구 안전 레벨 확인 | `tool_name`: str = '' |
| `agent_auto_approve_list` | 자동 승인 규칙 목록 | -- |
| `agent_auto_approve_add` | 자동 승인 규칙 추가 | `tool_name`: str |
| `agent_auto_approve_remove` | 자동 승인 규칙 삭제 | `index`: int |
| `agent_undo` | 작업 실행 취소 | `journal_id`: int |
| `agent_undoable` | 실행 취소 가능한 작업 목록 | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | 작업 저널 검색 | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | 저널 통계 | -- |
| `agent_anomaly_status` | 이상 감지 상태 | -- |
| `agent_anomaly_alerts` | 이상 알림 이력 | `limit`: int = 50 |
| `agent_anomaly_reset` | 이상 감지 초기화 | -- |

---

## GitHub Integration (12)

GitHub 계정의 Issue 모니터링, 분류 및 보고.

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `github_list_accounts` | 등록된 GitHub 계정 목록 (토큰 마스킹) | — |
| `github_fetch_issues` | 계정 저장소의 Issue 가져오기 | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | Issue를 가져와 분류 (valid_bug / skip / needs_info), 우선순위 보고서 반환 | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | Claude Code 분석용 Issue 상세 정보 (댓글 포함) | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | GitHub API 속도 제한 확인 | `account_label`: str |
| `github_get_pending_issues` | 로컬 큐에서 미처리 이슈 가져오기 | -- |
| `github_get_issue_queue` | 상태 필터 적용 이슈 큐 항목 | `status`: str = "" |
| `github_poll_issues` | GitHub 이슈 즉시 폴링 | -- |
| `github_triage_queue_item` | 큐 이슈 분류 결과 설정 | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | 큐 이슈 해제 (선택적 자동 close) | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | 이슈/PR/Discussion 분류 프롬프트 가져오기 | `repo`: str = "" |
| `github_save_triage_prompts` | 분류 프롬프트 저장 | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## 디버그 도구 (9)

시스템 검증 및 디버깅을 위한 도구입니다. `YU_DEBUG_MODE=1`로 활성화됩니다.

| 도구 | 설명 | 파라미터 |
|------|-------------|------------|
| `debug_health_check` | 시스템 헬스 체크: Flask, DB 테이블, 스키마 | -- |
| `debug_validate_counts` | API 통계와 DB 카운트 교차 검증 | -- |
| `debug_validate_search` | 테스트 패턴으로 검색 API 검증 | `patterns`: str = "all" |
| `debug_validate_collection` | 컬렉션 캐시 카운트와 DB 검증 | -- |
| `debug_validate_annotations` | 어노테이션 데이터 무결성 검증 | -- |
| `debug_sample_files` | 랜덤 파일 샘플링 및 필드 완전성 보고 | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | 쓰기-읽기-업데이트-삭제 왕복 테스트 | -- |
| `debug_readonly_query` | 읽기 전용 SQL 쿼리 실행 | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | 전체 디버그 검증 일괄 실행 | -- |

---

## LoRA Dataset Manager (15)

| 도구 | 설명 | 파라미터 |
|------|------|----------|
| `list_lora_projects` | 프로젝트 목록 | -- |
| `get_lora_project` | 프로젝트 상세 조회 | `project_id`: int |
| `create_lora_project` | 프로젝트 생성 | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | 프로젝트 업데이트 | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | 프로젝트 삭제 | `project_id`: int |
| `get_lora_project_tags` | 태그 집계 조회 | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | 캡션 미리보기 | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | 데이터셋 내보내기 | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | 내보내기 진행 상황 확인 | `project_id`: int |
| `list_lora_checkpoints` | Checkpoint 파일 목록 | -- |
| `preview_lora_train_command` | 학습 명령어 미리보기 (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | LoRA 학습 시작 | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | 학습 상태 및 로그 조회 | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | 태그 제외 프리셋 목록 | -- |
| `create_lora_tag_preset` | 태그 제외 프리셋 생성 | `name`: str, `tags`: list |

## LLM 엔드포인트 (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `llm-endpoints-list` | 구성된 LLM 엔드포인트 목록 | — |
| `llm-endpoints-set` | LLM 엔드포인트 추가 또는 업데이트 | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | LLM 엔드포인트 제거 | `category`: str |
| `llm-endpoints-test` | LLM 엔드포인트 연결 테스트 | `category`: str |
| `llm-chat` | 구성된 LLM에 채팅 위임 | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## 서버 모드 (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `server-mode-get` | 현재 서버 모드 조회 | — |
| `server-subsystems-status` | 서브시스템 상태 목록 | — |

## MCP를 통해 사용할 수 없는 기능

다음 기능은 MCP의 제한 사항으로 인해 도구로 노출되지 않습니다:

- **바이너리 응답**: 썸네일 (`/api/thumbnail/`), 원본 이미지 (`/api/original/`), ZIP 다운로드, 동영상 파일
- **OS 대화 상자**: 폴더 선택 대화 상자 (`/api/tools/select-folder`), 파일 관리자 실행 (`/api/open-folder/`)
- **SSE 스트림**: 로그 스트리밍 (`/api/logs/stream`)
- **인증 페이지**: PIN 입력 화면, LAN Share 게스트 페이지
