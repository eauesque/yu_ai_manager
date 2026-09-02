# Custom UI Development Guide

This guide covers the custom UI system that allows full replacement of the YU AI Manager frontend.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Getting Started](quickstart.md) -- Create a minimal custom UI
- [Design Guide](design-guide.md) -- CSS design, themes, responsive layout, components
- [Templates Guide](templates.md) -- Jinja2 patterns, i18n, page structure
- [Advanced Features](advanced.md) -- SSE real-time updates, batch operations, security
- [API Reference](api-reference.md) -- Links to full API documentation

## Overview

YU AI Manager keeps its backend API fully separated from the frontend. It is straightforward to swap the frontend with a custom implementation. A custom UI becomes active simply by placing it in a `ui/<name>/` directory.

### Capabilities

- **Full UI replacement**: Replace every page -- search, stats, settings, and more -- with your own design
- **Theme customization**: Override CSS variables alone to change the color scheme
- **Partial replacement**: Customize only the pages you need; the rest fall back to the default UI
- **AI-generated UI**: Hand the API documentation to Claude or ChatGPT and let it generate a UI automatically

### Architecture

```
yu_ai_manager/
├── ui/
│   ├── default/              # Reference UI (built-in)
│   │   ├── manifest.json     # UI metadata (required)
│   │   ├── templates/        # Jinja2 HTML templates
│   │   │   ├── index.html    # Main search page
│   │   │   ├── stats.html    # Statistics dashboard
│   │   │   ├── tools.html    # Tools page
│   │   │   ├── settings.html # Settings page
│   │   │   ├── story.html    # Your Story page
│   │   │   ├── inspect.html  # Metadata inspector
│   │   │   └── _nav.html     # Shared navbar (include)
│   │   └── static/           # CSS, JS, images
│   │       ├── css/          # Stylesheets
│   │       ├── dist/         # TypeScript build output
│   │       └── favicon.svg   # Favicon
│   ├── custom/               # Custom UI (gitignored, auto-detected)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # Additional UI (any name)
│       ├── manifest.json
│       └── ...
├── routes/                   # Server-side API routes
│   ├── pages.py              # Page routing definitions
│   └── ...                   # Various API endpoints
└── docs/api/                 # API documentation
```

### UI Resolution Order

The server determines which UI to use at startup, following this priority:

| Priority | Condition | Behavior |
|----------|-----------|----------|
| 1 | `config.json` contains `"ui": "my-theme"` | Uses the specified `ui/my-theme/` |
| 2 | `ui/custom/` has a valid `manifest.json` | Auto-detects and uses `ui/custom/` |
| 3 | Neither of the above | Falls back to `ui/default/` |

### manifest.json

Every custom UI requires a `manifest.json`:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Identifier for the UI (recommended to match the directory name) |
| `version` | Yes | Semantic version |
| `description` | No | Description of the UI |
| `author` | No | Author name |
| `api_version` | No | Supported API version (`"1"`) |
| `type` | No | `"full"` (default) or `"theme"` |

### Static File Serving

The `static/` directory inside a custom UI maps to the Flask `/static/` URL:

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

Reference from HTML:
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### UI Management API

You can manage UIs through the "UI" tab on the Settings page or via the API:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/ui/list` | List installed UIs |
| POST | `/api/ui/switch` | Switch active UI (requires restart) |
| POST | `/api/ui/install` | Install a UI from a URL (localhost only) |
| DELETE | `/api/ui/<name>/uninstall` | Uninstall a UI (localhost only) |

### MCP Tools

UIs can also be managed through MCP (Model Context Protocol):

- `list_uis()` -- List installed UIs
- `switch_ui(name)` -- Switch active UI
- `install_ui(url)` -- Install a UI from a URL
- `uninstall_ui(name)` -- Uninstall a UI
