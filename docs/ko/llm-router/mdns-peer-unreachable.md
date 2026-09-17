# mDNS 백엔드가 '연결 불가' 상태에서 회복되지 않는 경우

LLM Router의 mDNS 자동 발견으로 추가된 백엔드가 「연결 불가 (unreachable)」
상태에서 회복되지 않는 경우의 원인·진단·대처를 정리합니다.

---

## 구조 개요

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← /api/mdns/identity 를 HTTP로 확인
            ├─ _apply_peer_to_catalog()  ← BackendCatalog 에 등록
            ├─ _enter_cooldown() / _in_cooldown()  ← 실패 후 재시도 제한
            └─ retry_pending_peers()  ← 60초 주기 스윕（v4.91.15〜）
```

**중요한 흐름**:

1. zeroconf가 피어 감지 → `on_peer_added` 호출
2. `_verify()`가 `/api/mdns/identity`를 호출하여 `node_id`와 `product` 검증
3. 성공 → `_apply_peer_to_catalog()`로 백엔드를 catalog에 추가
4. 실패 → 60초 cooldown 진입, 같은 `node_id`의 이벤트 무시
5. **v4.91.15〜**: 60초마다의 스윕 태스크가 cooldown 만료 후 미도달 피어를 재시도

---

## 「연결 불가」가 되는 주요 패턴

### 패턴 A — 초회 verify 실패 → cooldown으로 침묵

**증상**: LLM Router에 백엔드가 표시되지만 status=unreachable.  
**원인**:
- 상대 노드 기동 직후 아직 HTTP 서버가 올라오지 않았음
- 자신의 포트가 변경되었는데 피어가 구 TXT를 참조하고 있음（v4.91.14 이전의
  `--port` override 버그: 35a3679a에서 수정）

**동작 (v4.91.14 이전)**: cooldown（60초）이 끝나면 다음 `on_peer_updated`
이벤트를 기다리지만, 그 이벤트가 발생하지 않으면 영구히 회복되지 않음.

**동작 (v4.91.15〜)**: cooldown 만료 후 다음 스윕 tick（최대 60초 후）에서
자동 재시도 → 성공하면 catalog에 반영.

---

### 패턴 B — zeroconf가 `ServiceStateChange.Updated`를 발생시키지 않음

**증상**: 피어가 재시작했는데 LLM Router가 구 상태인 채로 유지.  
**원인**: zeroconf의 캐시 상태에 따라 TXT 변경 시 `Updated` 이벤트가
발생하지 않는 경우가 있음（zeroconf 라이브러리의 기지 동작）.  
**대처**: v4.91.15의 스윕 태스크가 60초 이내에 감지.

---

### 패턴 C — 상대 노드의 포트가 광고 값과 다름

**증상**: curl로는 도달할 수 있지만 verify timeout이 계속됨.  
**원인**: `--port` CLI 플래그를 사용하면서 config.json의 `server.port`가
구 값인 채로 → mDNS TXT에 잘못된 포트가 광고됨.  
**수정**: v4.91.14 (35a3679a)에서 `config["server"]["port"]`를 실효 포트로
덮어쓰도록 수정됨. 구 기동 스크립트가 config.json을 직접 덮어쓰는 경우는
설정 파일도 확인할 것.

---

### 패턴 D — trusted_peer_registry에 등록되지 않음

**증상**: LLM Router는「ready」인데 `/ext/<name>/v1/*`으로의 프록시가 403.  
**원인**: verify 성공으로 catalog에는 들어갔지만 `_apply_peer_to_catalog()`가
호출되기 전에 프로세스가 재시작되었거나, `service_kind != "yu"`로
registry 등록이 스킵됨（bare Ollama 피어는 등록하지 않는 사양）.  
**확인**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## 진단 순서

### 1. 피어의 현재 상태 확인

```bash
# 자신이 알고 있는 피어 목록
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# LLM Router 백엔드 목록（mDNS 유래는 alias가 "mdns-"로 시작）
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. 상대 노드에서 자신의 identity 엔드포인트에 도달할 수 있는지 확인

상대 노드에서:
```bash
curl -v http://<자신의LAN-IP>:<PORT>/api/mdns/identity
```

예상 응답:
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

실패하는 경우:
- 방화벽 / 라우팅 문제
- 포트가 실효 값과 광고 값에서 불일치（`--port`로 기동하고 있는지 확인）

### 3. 자신이 광고하고 있는 포트 확인

```bash
# 기동 로그에 "web_port"가 표시됨
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# 또는 settings API
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. cooldown 상태 확인

GUI: **LLM Router** > 백엔드 카드 > 상세에 `last_error`와
`last_seen_at`이 표시됨. 에러가 "identity verification failed"이면
verify는 도달했지만 내용 불일치（node_id / product 불일치）.
에러가 "timeout"이면 HTTP 자체가 도달하지 않는 것.

### 5. 스윕 로그 확인

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8문자>`가 출력되면 스윕으로 회복된 것을 나타냄.

---

## 강제 복구（수동）

스윕을 기다리지 않고 지금 바로 회복하고 싶은 경우:

### 방법 1: 상대 노드 재시작

재시작하면 zeroconf가 `ServiceStateChange.Removed` + `Added`를 발생 →
`on_peer_removed`가 cooldown을 클리어 → `on_peer_added`로 즉시 재검증.

### 방법 2: mDNS 서비스 재시작 API（설정 화면에서）

**설정** > **LLM Router** > **mDNS 재시작** 버튼（존재하는 경우）.

### 방법 3: 앱 재시작

cooldown은 메모리 상에만 존재. 재시작하면 전체 cooldown이 리셋되고,
기동 직후에 전체 피어를 재검증.

---

## 재발 방지 포인트

| 체크 항목 | 확인 방법 |
|---|---|
| `--port` 사용 시 config.json의 `server.port`도 같은 값인지 | config.json 참조 |
| 방화벽에서 `PORT`의 inbound가 허용되어 있는지 | `sudo ufw status` / macOS 설정 |
| 복수 NIC 환경에서 올바른 LAN 인터페이스에 bind하고 있는지 | `config.json`의 `mdns.bind_address` |
| v4.91.15 이후를 사용하고 있는지（스윕 태스크 탑재） | `curl .../api/server/info` |

---

## 관련 파일

| 파일 | 역할 |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`·cooldown·retry_pending_peers |
| `core/web/runtime_mdns.py` | 스윕 태스크 기동·정지 |
| `core/mdns/service.py` | zeroconf 래퍼·`list_peers()` |
| `core/web/trusted_peer_registry.py` | 크로스 노드 `/ext/*` 인증 |
