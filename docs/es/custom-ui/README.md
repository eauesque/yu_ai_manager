# Guía de Desarrollo de Interfaz Personalizada

Guía del sistema de interfaz personalizada que permite reemplazar completamente el frontend de YU AI Manager.

## Tabla de contenidos

- [Descripción general](#descripción-general)
- [Arquitectura](#arquitectura)
- [Primeros pasos](quickstart.md) — Procedimiento para crear una interfaz de configuración mínima
- [Guía de diseño](design-guide.md) — Diseño de CSS, temas, diseño responsivo, componentes
- [Guía de plantillas](templates.md) — Patrones Jinja2, i18n, estructura de páginas
- [Funciones avanzadas](advanced.md) — Actualizaciones en tiempo real con SSE, operaciones por lotes, seguridad
- [Referencia de API](api-reference.md) — Colección de enlaces a documentación de todas las API

## Descripción general

YU AI Manager tiene una API backend completamente separada, lo que permite reemplazar libremente el frontend. La interfaz personalizada se activa simplemente colocándola en el directorio `ui/<nombre>/`.

### Qué es posible con este sistema

- **Reemplazo completo de interfaz**: Cambiar a diseño personalizado todas las pantallas, incluyendo búsqueda, estadísticas, configuración, etc.
- **Personalización de temas**: Cambiar el esquema de colores solo sobreescribiendo variables CSS
- **Reemplazo parcial**: Personalizar solo las páginas necesarias y usar la interfaz predeterminada para el resto
- **Generación de interfaz con IA**: Pasar la documentación de API a Claude o ChatGPT para generar automáticamente la interfaz

### Arquitectura

```
yu_ai_manager/
├── ui/
│   ├── default/              # Interfaz de referencia (incorporada)
│   │   ├── manifest.json     # Metadatos de interfaz (obligatorio)
│   │   ├── templates/        # Plantillas HTML Jinja2
│   │   │   ├── index.html    # Página principal de búsqueda
│   │   │   ├── stats.html    # Panel de estadísticas
│   │   │   ├── tools.html    # Página de herramientas
│   │   │   ├── settings.html # Página de configuración
│   │   │   ├── story.html    # Página Your Story
│   │   │   ├── inspect.html  # Inspección de metadatos
│   │   │   └── _nav.html     # Barra de navegación común (include)
│   │   └── static/           # CSS, JS, imágenes
│   │       ├── css/          # Hojas de estilo
│   │       ├── dist/         # Salida de compilación de TypeScript
│   │       └── favicon.svg   # Favicon
│   ├── custom/               # Interfaz personalizada (gitignored, detección automática)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # Interfaz adicional (nombre libre)
│       ├── manifest.json
│       └── ...
├── routes/                   # Rutas API del lado del servidor
│   ├── pages.py              # Definición de enrutamiento de páginas
│   └── ...                   # Varios endpoints de API
└── docs/api/                 # Documentación de API
```

### Orden de resolución de interfaz

Al iniciar el servidor, se determina la interfaz a usar según el siguiente orden de prioridad:

| Prioridad | Condición | Comportamiento |
|-----------|-----------|---|
| 1 | `"ui": "my-theme"` configurado en `config.json` | Usar `ui/my-theme/` especificado |
| 2 | `manifest.json` válido existe en `ui/custom/` | Detectar y usar `ui/custom/` automáticamente |
| 3 | Ninguno de los anteriores | Usar `ui/default/` como fallback |

### manifest.json

Todos los interfaces personalizadas requieren `manifest.json`:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| Campo | Obligatorio | Descripción |
|-------|------------|------|
| `name` | Sí | Nombre de identificación de la interfaz (se recomienda que coincida con el nombre del directorio) |
| `version` | Sí | Versionado semántico |
| `description` | No | Descripción de la interfaz |
| `author` | No | Nombre del autor |
| `api_version` | No | Versión de API compatible (`"1"`) |
| `type` | No | `"full"` (predeterminado) o `"theme"` |

### Entrega de archivos estáticos

El directorio `static/` de la interfaz personalizada se asigna a la URL `/static/` de Flask:

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

Referencia desde HTML:
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### API de gestión de interfaz

La gestión de interfaces es posible desde la pestaña "Interfaz" de la página de configuración o mediante API:

| Método | Ruta | Descripción |
|--------|------|------|
| GET | `/api/ui/list` | Listar interfaces instaladas |
| POST | `/api/ui/switch` | Cambiar interfaz activa (requiere reinicio) |
| POST | `/api/ui/install` | Instalar interfaz desde URL (solo localhost) |
| DELETE | `/api/ui/<nombre>/uninstall` | Desinstalar interfaz (solo localhost) |

### Herramientas MCP

También es posible gestionar interfaces a través de MCP (Model Context Protocol):

- `list_uis()` — Listar interfaces instaladas
- `switch_ui(name)` — Cambiar interfaz activa
- `install_ui(url)` — Instalar interfaz desde URL
- `uninstall_ui(name)` — Desinstalar interfaz
