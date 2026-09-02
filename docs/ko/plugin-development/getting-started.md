# 플러그인 개발 가이드

이 가이드는 YU AI Manager용 플러그인(Extension)을 개발하는 방법을 설명합니다.

## 최소 설정

`extensions/` 디렉토리 아래에 폴더를 만들고 두 개의 파일만 배치하면 플러그인이 동작합니다.

```
extensions/
  my-plugin/
    extension.json      # 매니페스트 (필수)
    my_plugin.py        # 엔트리 포인트 (필수)
```

### extension.json (최소)

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My first plugin",
  "entry": "my_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  }
}
```

### my_plugin.py (최소)

```python
"""My Plugin -- minimal example"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Extension 로더가 호출하는 엔트리 포인트."""
    return bp
```

Extension 시스템은 모듈이 `get_blueprint()`를 노출하기만 하면 자동으로 Blueprint를 등록합니다.

## API 라우트 추가

플러그인은 자체 API 엔드포인트를 추가할 수 있습니다.

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- 충돌을 피하기 위해 URL 접두사로 `/ext/<plugin-name>/`을 사용하는 것을 권장합니다.
- `extension.json`에 `"blueprint_prefix": "/ext/my-plugin"`을 설정하면 네비게이션에 링크가 자동으로 표시됩니다.

## 템플릿 (UI 페이지)

플러그인은 자체 HTML 페이지를 포함할 수 있습니다.

```
extensions/
  my-plugin/
    extension.json
    my_plugin.py
    templates/
      my_plugin/
        index.html
```

```python
from quart import Blueprint, render_template

bp = Blueprint(
    "my_plugin",
    __name__,
    template_folder="templates",
)

@bp.route("/ext/my-plugin/")
def index():
    return render_template("my_plugin/index.html")

def get_blueprint():
    return bp
```

템플릿은 기존 `_nav.html`을 확장하여 일관된 외관을 유지할 수 있습니다:

```html
{% extends "_nav.html" %}
{% block title %}My Plugin{% endblock %}
{% block content %}
<div class="container" style="padding:20px;">
  <h1>My Plugin</h1>
  <p>Your content here.</p>
</div>
{% endblock %}
```

## 설정 스키마 (config_schema)

`extension.json`에 `config_schema`를 정의하면 설정 > Extensions에서 플러그인 설정을 수정할 수 있습니다.

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Configurable plugin",
  "entry": "my_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  },
  "config_schema": {
    "greeting": { "type": "string", "default": "Hello" },
    "max_items": { "type": "number", "default": 10 },
    "verbose": { "type": "boolean", "default": false }
  }
}
```

Python에서 설정 값을 읽으려면:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## 후크

Extension은 특정 처리 지점에 후크할 수 있습니다.

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

Extension Manager가 Python 모듈에 정의된 후크 함수를 자동으로 발견합니다.

## 네비게이션 링크 추가

`extension.json`에 `nav` 필드를 추가하면 사이드바에 링크가 자동으로 표시됩니다.

```json
{
  "nav": {
    "label": "My Plugin",
    "icon": "🔌"
  },
  "has_blueprint": true,
  "blueprint_prefix": "/ext/my-plugin"
}
```

## Git 리포지토리를 통한 배포

플러그인을 Git 리포지토리로 공개하면, 사용자가 설정 > Extensions > Install에서 URL을 입력하여 설치할 수 있습니다.

### 리포지토리 구조

```
my-plugin/
  extension.json     # 루트에 배치
  my_plugin.py
  templates/
  README.md
```

### 설치 흐름

1. 사용자가 설정 > Extensions > Install에서 Git URL을 입력합니다.
2. 시스템이 `git clone --depth 1`로 리포지토리를 복제합니다.
3. `extension.json`을 검증합니다.
4. `extensions/` 디렉토리 아래에 플러그인을 배치합니다.
5. 서버 재시작으로 플러그인이 활성화됩니다.

### 마켓플레이스 등록

`config.json`의 `extension_index_url`에 인덱스 JSON의 URL을 설정하면, 사용자가 Marketplace 탭에서 플러그인을 검색하고 설치할 수 있습니다.

인덱스 JSON 형식:

```json
[
  {
    "name": "my-plugin",
    "description": "A useful plugin",
    "author": "Your Name",
    "version": "1.0.0",
    "url": "https://github.com/user/my-plugin.git"
  }
]
```

## CSS 접두사 규칙

스타일 충돌을 방지하기 위해 플러그인 전용 CSS 클래스 접두사를 사용하세요:

```css
.mp-container { ... }
.mp-card { ... }
```

## 보안 참고사항

- 사용자 입력을 SQL에 직접 임베드하지 마세요. `?` 플레이스홀더를 사용하세요.
- 파일 경로에 대한 경로 탐색 공격을 방지하세요.
- 외부 API 호출 시 User-Agent 헤더를 설정하세요.
- 기존 글로벌 인터셉터가 CSRF 헤더(`X-Requested-With`)를 자동으로 주입합니다.
