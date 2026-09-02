# extension.json 매니페스트 레퍼런스

이 매니페스트 파일은 Extension의 메타데이터와 설정을 정의합니다. `extensions/<name>/extension.json`에 배치하세요.

## 필수 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | Extension의 고유 식별자. 디렉토리 이름과 일치해야 합니다 |
| `version` | string | 시맨틱 버전 (예: `"1.0.0"`) |
| `entry` | string | Python 엔트리 포인트 파일명 (예: `"my_plugin.py"`) |

## 선택 필드

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `description` | string | `""` | 짧은 설명 (UI 카드에 표시) |
| `author` | string | `""` | 작성자 이름 |
| `type` | string | `"general"` | Extension 타입: `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | 사용할 후크 포인트 이름 배열 |
| `has_blueprint` | bool | `false` | Extension에 Flask Blueprint가 있으면 true로 설정 |
| `blueprint_prefix` | string | `""` | Blueprint의 URL 접두사 (예: `"/ext/my-plugin"`) |
| `nav` | object | `null` | 네비게이션 링크 설정 |
| `config` | object | `{}` | 기본 설정 |
| `config_schema` | object | `{}` | 사용자용 설정 스키마 |

## `config` 객체

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `enabled` | bool | `true` | 초기 활성화 상태 |
| `priority` | int | `500` | 로드 순서 (낮은 값이 먼저 로드) |

## `nav` 객체

| 필드 | 타입 | 설명 |
|------|------|------|
| `label` | string | 네비게이션에 표시되는 레이블 |
| `icon` | string | 이모지 아이콘 (예: `"🔌"`) |

`nav`를 설정할 때는 `has_blueprint: true`와 `blueprint_prefix`도 함께 설정해야 합니다.

## `config_schema` 객체

설정 UI에서 접근 가능한 사용자 편집 가능 설정을 정의합니다. 각 키가 설정 필드가 됩니다.

```json
{
  "config_schema": {
    "field_name": {
      "type": "string",
      "default": "value",
      "label": "Display Name",
      "description": "Help text for this field"
    }
  }
}
```

### 필드 정의

| 속성 | 타입 | 설명 |
|------|------|------|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | 기본값 |
| `label` | string | UI에서의 표시 이름 (생략 시 키 이름으로 폴백) |
| `description` | string | 도움말 텍스트 |

### 설정 값 읽기 및 쓰기

Python:
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# 읽기
val = get_extension_config_value("my-plugin", "field_name", "default")

# 쓰기
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API:
```
GET  /api/extensions/<name>/config    -- 스키마와 현재 값 조회
POST /api/extensions/<name>/config    -- {"values": {"key": "val"}}로 저장
```

## 전체 예시

```json
{
  "name": "my-awesome-plugin",
  "version": "1.2.0",
  "description": "An awesome plugin that does amazing things",
  "author": "Your Name",
  "type": "ui_widget",
  "entry": "awesome_plugin.py",
  "hooks": ["after_scan"],
  "has_blueprint": true,
  "blueprint_prefix": "/ext/awesome",
  "nav": {
    "label": "Awesome",
    "icon": "✨"
  },
  "config": {
    "enabled": true,
    "priority": 400
  },
  "config_schema": {
    "api_url": {
      "type": "string",
      "default": "",
      "label": "API URL",
      "description": "External API endpoint URL"
    },
    "max_results": {
      "type": "integer",
      "default": 20,
      "label": "Max Results",
      "description": "Maximum number of results to display"
    },
    "auto_refresh": {
      "type": "boolean",
      "default": true,
      "label": "Auto Refresh",
      "description": "Automatically refresh data on page load"
    }
  }
}
```
