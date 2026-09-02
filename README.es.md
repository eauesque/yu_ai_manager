# YU AI Manager

Interfaz web de gestión de metadatos para imágenes generadas con IA.

## Descripción general

Herramienta WebUI para extraer, buscar y gestionar metadatos incrustados en imágenes generadas con IA (prompts, modelos, semillas, etc.).

**Esto es lo que puedes hacer:**

- Escanear carpetas o archivos ZIP completos para registrar automáticamente imágenes
- Búsqueda y filtrado transversales por prompts, etiquetas, nombres de modelos, valores de semilla
- Enviar instantáneamente imágenes favoritas a SD / ComfyUI / NovelAI para regenerarlas
- Etiquetado automático con WD-Tagger, análisis de contenido con Ollama/OpenAI
- Acceder desde otros dispositivos en la LAN (teléfono inteligente, etc.) mediante código QR

**Fuentes compatibles**: Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

## Entorno de funcionamiento

- Windows / Linux / macOS

> **No se requiere instalación manual.** `start.sh` / `start.bat` inicia automáticamente todas las herramientas necesarias en el proyecto (sin permisos de administrador ni escritura en el sistema).

## Configuración e inicio

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

Configuración automática en el primer inicio:

| Herramienta | Método de obtención |
| --- | --- |
| `uv` | Descarga automática a `./bin/uv` |
| Python 3.11+ | Instalación automática por `uv` |
| Node.js 22 LTS | Opcional — confirmación de descarga a `./bin/node/` (aproximadamente 30 MB) |
| pnpm | Se activa automáticamente mediante `corepack` una vez que Node.js está instalado |
| ffmpeg | Opcional — Windows/macOS: confirmación de descarga a `./bin/ffmpeg/` (aproximadamente 80 MB), Linux: se proporciona orientación sobre comandos `apt`/`dnf`/`pacman` de la distribución |

Establecer `YU_AUTO_INSTALL=1` omite los mensajes incluso en entornos no interactivos (como CI) para una instalación completamente automática. ffmpeg es solo para funcionalidades extendidas como análisis de video, S2T y OCR, no es necesario para iniciar la aplicación principal.

A partir de la segunda ejecución, solo se reinstala y se reconstruye si se actualizan las dependencias o el código fuente de TypeScript.

Puedes establecer la configuración permanente escribiendo `--db`, `--port`, `--lan`, `--pin`, etc. en `launch-args.txt`.

## Características principales

### Escaneo y registro
- Extracción automática de metadatos de PNG / WebP / JPEG
- Escaneo transparente de archivos ZIP / 7z sin descompresión
- Adición de archivos mediante arrastrar y soltar

### Búsqueda y visualización
- Búsqueda de texto completo por prompts, etiquetas, nombres de modelos, valores de semilla
- Búsqueda de expresiones regulares, filtros de condiciones múltiples
- Búsqueda de imágenes similares por pHash, búsqueda semántica por CLIP

### Organización y gestión
- Favoritos, clasificación de estrellas (1-5), notas (anotaciones)
- Colecciones (agrupación)
- Panel de estadísticas, informes mensuales, sistema de trofeos

### Integración con herramientas de generación (Bridge)
- Envío instantáneo de prompts a SD WebUI / Forge / ComfyUI / NovelAI
- También compatible con envío mediante portapapeles

### Asistencia con IA
- Etiquetado automático con WD-Tagger
- Análisis de contenido de imágenes usando Ollama / OpenAI
- Conversión de voz a texto (S2T)

### Red y uso compartido
- Modo compartido en LAN (acceso desde teléfono inteligente mediante código QR)
- Servidor MCP (operación desde agentes de IA)
- Gestión de Fleet (gestión centralizada de múltiples instancias)

### Personalización
- Sistema de UI personalizada y extensiones
- Compatibilidad de temas (claro / oscuro)
- Aplicación de escritorio Tauri (sin necesidad de navegador para iniciar)

## Soporte multilingüe

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## Documentación

- [Inicio rápido](docs/ja/help/user/quickstart.md)
- [Casos de uso](docs/ja/help/user/use-cases.md)
- [Referencia de API](docs/ja/api/README.md)
- [Ajuste de rendimiento](docs/ja/help/user/performance-tuning.md)
- [Implementación](docs/ja/help/user/deployment.md)
- [Desarrollo de extensiones](docs/ja/plugin-development/getting-started.md)
- [UI personalizada](docs/ja/custom-ui/README.md)
- [Referencia de herramientas MCP](docs/ja/api/MCP_TOOLS_REFERENCE.md)
- [Lista completa de documentación](docs/ja/README.md)

## Desarrollo y personalización

Consulte [DEVELOPMENT.ja.md](DEVELOPMENT.ja.md) ([English](DEVELOPMENT.en.md))

## Preguntar a una IA si tiene problemas

### Si no inicia

Abra este proyecto en un agente de IA como Claude Code Desktop y dígale:

> `start.bat` (o `start.sh`) se congela cuando lo inicio. Por favor, investiga.

> **Nota**: En Claude Code Desktop, debe especificar la carpeta del proyecto antes de comenzar la conversación.

### Problemas después del inicio, configuración y uso

**Paso 1 — Obtenga el contexto**

Abra la página de ayuda (`/help`) y presione el botón **"Copiar contexto de IA"**.
Usa la sesión del navegador autenticada para hacer fetch en `GET /api/ai-context` y copiar el JSON al portapapeles (funciona incluso en entornos LAN http://).

> **Nota (si tienes una clave de API)**: Si tienes una clave de API con alcance de administrador, puedes llamar directamente a `GET /api/ai-context` con el encabezado `Authorization: Bearer <key>`.

**Paso 2 — Pasar a la IA**

Pegue el JSON copiado en el chat de IA y escriba su pregunta:

> 〔JSON pegado〕
> Considerando esto, por favor resuelve 〔descripción del problema〕.

`/api/ai-context` incluye la versión actual, funciones habilitadas, consejos de configuración, lista de API y reglas CSRF, asegurando que la IA tenga toda la información necesaria para ayudarte de manera precisa.

## Preguntas frecuentes

[docs/ja/FAQ.md](docs/ja/FAQ.md) ([English](docs/en/FAQ.md))

## Reportar errores

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## Licencia

MIT License — [LICENSE](LICENSE) / [Interpretación literal](docs/ja/LICENSE.md) ([English](docs/en/LICENSE.md))
