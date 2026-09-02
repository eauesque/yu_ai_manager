# OS 수준 격리 가이드

이 기능은 운영체제 내장 보안 메커니즘을 활용하여 확장 기능(Extension)이 시스템에 미치는 영향을 제한합니다.

## 1. OS 격리란?

스마트폰에 앱을 설치할 때 "이 앱이 카메라 접근을 요청합니다"라는 메시지를 보셨을 것입니다. OS 격리는 동일한 원리입니다.

Extension이 선언한 권한(파일 읽기/쓰기, 네트워크 통신, 외부 명령 실행 등)에 따라 **OS 커널이 허가되지 않은 작업을 물리적으로 차단**합니다. Python 코드에서 어떤 기법을 사용하더라도 커널 수준의 제한은 우회할 수 없습니다.

> **참고**: 이 기능은 주로 서드파티 Extension을 안전하게 사용하기 위한 것입니다. `builtin-*` Extension은 신뢰됨(L0)으로 처리되어 제한 없이 동작합니다.

---

## 2. 지원 플랫폼

| OS | 격리 방식 | 성숙도 |
|----|---------|--------|
| **Linux** | AppArmor (강제 접근 제어) | 권장, 프로덕션 대응 |
| **macOS** | sandbox-exec (Seatbelt) | 실험적 (Apple이 지원 중단 표시) |
| **Windows** | Restricted Token + Job Object | 기본적인 리소스 제한 |

Linux의 AppArmor가 가장 완성도가 높으며 권장 환경입니다.

---

## 3. Linux 설정 (AppArmor)

### 3.1 AppArmor란?

AppArmor는 Linux 커널에 내장된 보안 모듈입니다. 프로세스별로 어떤 파일을 읽고 쓸 수 있는지, 네트워크 통신을 허용할지를 프로필로 정의하고 커널이 강제 적용합니다.

Ubuntu / Debian에서는 보통 기본적으로 활성화되어 있지만, Raspberry Pi OS 등 일부 배포판에서는 수동 활성화가 필요합니다.

### 3.2 자동 설정

제공된 설정 스크립트로 한 번에 구성할 수 있습니다.

```bash
sudo bash scripts/setup-apparmor.sh
```

이 스크립트는 다음을 수행합니다:

1. **AppArmor 패키지 확인/설치** — `apparmor`, `apparmor-utils` 미설치 시 자동 설치
2. **커널 파라미터 추가** — `/boot/firmware/cmdline.txt`에 `lsm=apparmor` 추가 (백업 포함)
3. **sudoers 규칙 설정** — `apparmor_parser` 명령만 비밀번호 없이 실행 가능하도록 설정 (최소 권한)
4. **AppArmor 서비스 활성화** — systemd로 자동 시작 설정

> **Raspberry Pi OS 이외의 환경**: GRUB을 사용하는 시스템에서는 `/etc/default/grub`의 `GRUB_CMDLINE_LINUX`에 `lsm=apparmor`를 수동으로 추가한 후 `sudo update-grub`를 실행하세요.

### 3.3 재부팅

커널 파라미터를 추가한 경우 재부팅이 필요합니다.

```bash
sudo reboot
```

### 3.4 확인

재부팅 후 AppArmor가 활성화되었는지 확인합니다.

```bash
# 커널 모듈 활성화 여부 확인
cat /sys/module/apparmor/parameters/enabled
# → "Y"가 표시되면 활성화됨

# 로드된 프로필 목록
sudo aa-status
```

### 3.5 config.json에서 활성화

AppArmor 정상 동작을 확인한 후 `config.json`에 다음을 추가합니다.

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    }
  }
}
```

이 설정으로 서드파티 Extension 시작 시 AppArmor 프로필이 자동 생성 및 로드됩니다.

---

## 4. 설정 항목 참조

`config.json`의 `os_isolation` 섹션으로 제어합니다.

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    },
    "macos": {
      "sandbox_exec": false
    },
    "windows": {
      "restricted_token": true,
      "job_object": true,
      "job_limits": {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10
      }
    }
  }
}
```

| 키 | 타입 | 기본값 | 설명 |
|----|------|--------|------|
| `enabled` | bool | `false` | OS 격리 기능 전체 활성화/비활성화 |
| `linux.apparmor` | bool | `true` | AppArmor 프로필 사용 |
| `macos.sandbox_exec` | bool | `false` | macOS sandbox-exec 사용 (실험적) |
| `windows.restricted_token` | bool | `true` | 제한된 토큰으로 프로세스 시작 |
| `windows.job_object` | bool | `true` | Job Object로 리소스 제한 |
| `windows.job_limits.memory_mb` | int | `512` | Extension당 최대 메모리 (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | Extension당 CPU 사용률 상한 (%) |
| `windows.job_limits.max_processes` | int | `10` | Extension이 생성할 수 있는 최대 프로세스 수 |

---

## 5. Extension 권한과 AppArmor 규칙의 대응

Extension의 `extension.json`에 선언된 권한에 따라 AppArmor 프로필이 자동 생성됩니다.

| Extension 권한 | AppArmor 제어 |
|---------------|--------------|
| `db:read` | `data/` 디렉토리 읽기만 허용 |
| `db:write` | `data/` 디렉토리 읽기/쓰기 허용 |
| `fs:read:scan_roots` | 설정된 스캔 루트의 읽기 허용 |
| `fs:write:any` | 모든 경로의 읽기/쓰기 허용 |
| `network:local` | TCP/Unix 소켓 허용 (UDP 거부) |
| `network:internet` | TCP/UDP/Unix 소켓 모두 허용 |
| `subprocess` | `/usr/bin/`, `/bin/` 등의 실행 허용 |
| 네트워크 권한 없음 | TCP/UDP 명시적 거부, IPC용 Unix 소켓만 허용 |
| subprocess 권한 없음 | `/usr/bin/`, `/bin/` 등의 실행 명시적 거부 |

Extension 자체 디렉토리(`extensions/<name>/`)는 항상 읽기/쓰기가 가능합니다.

---

## 6. API로 상태 확인

OS 격리 상태는 API를 통해 조회할 수 있습니다.

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

응답 예시 (Linux / AppArmor 활성화 시):

```json
{
  "platform": "linux",
  "available": true,
  "method": "apparmor",
  "details": {
    "apparmor_kernel": "enabled",
    "apparmor_tools": true,
    "apparmor_sudoers": true,
    "aa_exec_path": "/usr/sbin/aa-exec"
  }
}
```

`available`이 `false`인 경우 응답에 `setup` 필드가 포함되어 설정 절차를 안내합니다.

---

## 7. 문제 해결

### AppArmor가 활성화되지 않음

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" 또는 파일이 존재하지 않음
```

**원인**: 커널 파라미터가 적용되지 않았습니다.

**해결 방법**:
- Raspberry Pi OS: `/boot/firmware/cmdline.txt`에 `lsm=apparmor`가 있는지 확인 후 재부팅
- GRUB 환경: `/etc/default/grub`에서 `GRUB_CMDLINE_LINUX="... lsm=apparmor"` 확인 후 `sudo update-grub && sudo reboot` 실행

### Extension 시작 시 "sudoers not configured" 표시

**원인**: `apparmor_parser`의 NOPASSWD sudoers 규칙이 설정되지 않았습니다.

**해결 방법**:
```bash
sudo bash scripts/setup-apparmor.sh
```

스크립트가 `/etc/sudoers.d/yu-ai-apparmor`에 필요한 규칙을 설치합니다.

### Extension이 권한 부족으로 동작하지 않음

**원인**: Extension의 `extension.json`에 필요한 권한이 선언되지 않았습니다.

**해결 방법**: Extension의 `extension.json`의 `permissions.required`에 필요한 권한을 추가하거나, 설정 > 확장 기능에서 수동으로 권한을 부여하세요.

### AppArmor 프로필 수동 확인

생성된 프로필은 `/tmp/yu_ai_apparmor/`에 저장됩니다.

```bash
# 프로필 내용 확인
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>

# 현재 로드된 YU AI Manager 프로필 목록
sudo aa-status | grep yu_ai_ext
```

---

## 8. 보안 관련 참고사항

OS 격리는 심층 방어 전략의 일부입니다. YU AI Manager는 다층 보안을 제공합니다:

1. **정적 분석** (Phase 1) — 설치 시 Extension 코드를 AST 분석하여 위험한 import 감지
2. **권한 게이트키퍼** (Phase 2-3) — ServiceRegistry를 통한 접근을 권한 검사 Proxy로 제어
3. **OS 격리** (Phase 4) — 커널 수준에서 파일, 네트워크, 프로세스 실행을 강제 제한

OS 격리만으로 모든 위험을 제거할 수는 없지만, 다른 방어 계층과 결합하면 서드파티 Extension을 안전하게 사용할 수 있는 환경을 제공합니다.

신뢰할 수 없는 Extension을 사용하는 경우, OS 격리가 활성화된 Linux 환경에서의 사용을 권장합니다.
