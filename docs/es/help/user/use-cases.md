# Casos de uso

Se recopilan las formas típicas de uso de YU AI Manager en formato "en este caso, úsalo así".

---

## 1. Organizar una gran cantidad de imágenes de IA

Cuando tiene miles de imágenes generadas por NovelAI o Stable Diffusion acumuladas en carpetas y es difícil revisarlas.

### Procedimiento

1. Registre las carpetas de escaneo en **Settings > Scan** (pueden ser varias)
2. Tras añadir la carpeta, el escaneo inicia automáticamente. También se pueden escanear archivos dentro de ZIP/7z
3. Al terminar el escaneo, filtre imágenes en la página principal mediante búsqueda por etiquetas (ej. `1girl, blue_eyes`) u orden
4. Seleccione las imágenes que le gustan y, con clic derecho > **Añadir a colección**, agrúpelas
5. Desde la barra lateral de colecciones puede navegar por grupos en cualquier momento

### Consejos

- Durante el escaneo se puede buscar y visualizar (la conexión de solo lectura de BD no entra en conflicto)
- Activando la extensión Auto Scan Watcher se detectan automáticamente las adiciones nuevas a la carpeta
- Incluso con un millón de archivos, la paginación por keyset permite navegar rápido

---

## 2. Buscar imágenes generadas con un prompt concreto

Cuando piensa "aquel prompt de la composición, ¿cuál era?".

### Procedimiento

1. Cambie el objetivo de la barra de búsqueda a **in_prompt**
2. Escriba la palabra clave que recuerde (ej. `cherry blossom`) y busque
3. Usar expresiones regulares permite filtrado más flexible (ej. `masterpiece.*cherry`)

### Consejos

- Si FTS (búsqueda de texto completo) está activado, la búsqueda es rápida incluso con muchos prompts
- Combinar con filtros de rango de fechas o formato de archivo es efectivo
- Con el orden `random` puede redescubrir imágenes olvidadas

---

## 3. Encontrar imágenes con composición similar

Cuando quiere buscar "otras imágenes con un ambiente parecido a esta".

### Procedimiento A: Búsqueda por similitud pHash (composición, colorido)

1. Abra el modal de detalles de la imagen
2. Haga clic en el botón **Buscar imágenes similares**
3. En el panel lateral se muestran las imágenes de composición próxima mediante pHash (hash perceptual)

### Procedimiento B: Búsqueda semántica CLIP (significado, concepto)

1. Haga clic en el botón **Búsqueda semántica** a la derecha de la barra de búsqueda
2. Escriba una descripción en lenguaje natural (ej. "chica de pie junto al mar", "ciudad al atardecer")
3. CLIP entiende el significado de la imagen y las muestra por similitud

### Consejos

- La búsqueda semántica requiere configurar previamente un modelo CLIP (ONNX o Hailo-10H)
- En bibliotecas grandes (más de 100 000), instalar `faiss-cpu` mejora drásticamente la velocidad
- pHash busca coincidencia de composición y CLIP similitud semántica. Probar ambas amplía los hallazgos

---

## 4. Gestionar las imágenes favoritas

Cuando quiere poder revisar al instante solo sus obras maestras dentro de una gran colección.

### Procedimiento

1. Registre como favorito con el **botón de corazón** en la tarjeta o en el modal de detalles
2. Configure la **valoración por estrellas** (1 a 5) en el modal para evaluar la calidad
3. Deje notas libres en **Anotaciones** (ej. "Candidato a retoma", "Publicado en SNS")
4. Filtre con "Solo favoritos" o "4 estrellas o más", etc.

### Consejos

- El orden por valoración (`rating_desc`) le permite ver juntas las imágenes mejor valoradas
- También puede operar favoritos y valoración desde el menú contextual (clic derecho)

---

## 5. Enviar el prompt de una imagen a otra herramienta

Cuando quiere reutilizar el prompt de una imagen antigua para regenerar o crear variaciones en otra herramienta.

### Procedimiento

1. Abra el modal de detalles de la imagen y revise la información del prompt
2. Haga clic en los botones **Enviar a SD WebUI** / **Enviar a ComfyUI** / **Enviar a NAI**
3. Se abre la página Bridge con el prompt rellenado automáticamente
4. Edite el prompt si es necesario y ejecútelo en la herramienta de generación

### Consejos

- Entre SD y NAI se convierte automáticamente la sintaxis de pesos `()` y `{}`
- Con el botón **QP** de la barra de herramientas de Bridge puede insertar presets de calidad con un clic
- También se puede enviar desde Prompt Converter o Prompt Simulator a cada Bridge

---

## 6. Visualizar imágenes dentro de archivos ZIP/7z

Cuando un conjunto de imágenes descargado viene en ZIP y quiere ver el contenido sin descomprimir.

### Procedimiento

1. Registre en Settings > Scan la carpeta que contiene los archivos ZIP/7z
2. Active **Escaneo dentro de ZIP/7z** en las opciones de escaneo
3. Tras el escaneo, las imágenes dentro de archivos también se pueden buscar y visualizar como las normales
4. En el modal de detalles se muestra el nombre del archivo y la ruta dentro del archivo

### Consejos

- Los vídeos dentro del archivo se expanden a una caché temporal (LRU 2 GB), por lo que la reproducción repetida es fluida
- Se admiten archivos ZIP anidados (ZIP-in-ZIP)
- Con la función de descarga por lotes se pueden reagrupar las imágenes de un archivo en un ZIP nuevo

---

## 7. Compartir imágenes con el equipo o la familia

Cuando quiere permitir ver las imágenes desde otros dispositivos (móvil, tableta, etc.) en la misma Wi-Fi.

### Procedimiento

1. Active "LAN Access" en la pestaña **Settings > Server**
2. Configure el **código PIN** (obligatorio al publicar en LAN)
3. Reinicie el servidor
4. Acceda desde otros dispositivos de la LAN a `http://<IP_del_servidor>:5000`
5. Introduzca el PIN e inicie sesión

### Consejos

- Emitiendo un **token de LAN Share** (ruta `/s/`), puede compartir un enlace de acceso como invitado sin PIN
- En la pantalla del servidor se muestra un código QR, que se puede leer con la cámara del móvil para acceder
- También se admite la autenticación Trusted Proxy mediante proxy inverso

---

## 8. Etiquetado automático

Cuando el etiquetado manual es tedioso y quiere que la IA analice las imágenes y asigne etiquetas automáticamente.

### Procedimiento A: WD-Tagger (rápido, especializado en etiquetas)

1. Descargue el modelo ONNX de WD-Tagger en **Settings**
2. Haga clic en **Ejecutar WD-Tagger** desde la página Tools o el modal de detalles
3. Se asignan automáticamente etiquetas estilo Danbooru

### Procedimiento B: AI Analysis (lenguaje natural, alta precisión)

1. En **Settings > AI Analysis** añada un servidor Ollama o compatible con OpenAI
2. Ejecute el análisis desde la pestaña **AI Analysis** del modal de detalles
3. Se genera una descripción de la imagen en lenguaje natural

### Consejos

- WD-Tagger también admite modo combinado con un motor VLM (compatible con API OpenAI)
- Se aplican automáticamente post-procesados como filtro NSFW y normalización de etiquetas
- Se admite la escritura de etiquetas en metadatos XMP, facilitando la integración con otras herramientas

---

## 9. Ver estadísticas e informes

Cuando quiere conocer la tendencia y el crecimiento de su biblioteca de imágenes.

### Procedimiento

1. Abra la página **Stats** desde la navegación y consulte las estadísticas globales
2. Consulte el informe mensual detallado en la página **Monthly Report**
   - Número mensual de archivos, comparación con el mes anterior, TOP 20 etiquetas, etiquetas nuevas, distribución por origen, conteo diario
3. Consulte los trofeos de logros en la sección **Trophies**

### Consejos

- Los trofeos se desbloquean por etapas en 6 categorías (milestone / streak / diversity / source / hidden) y 4 tiers (bronze a platinum)
- Configurar correctamente la zona horaria (Settings > Appearance) asegura que las estadísticas diarias sean precisas

---

## 10. Integración con agentes de IA vía MCP

Cuando quiere operar su biblioteca de imágenes desde Claude Desktop u otras herramientas de IA compatibles con MCP.

### Procedimiento

1. Registre el servidor MCP de YU AI Manager en la configuración del cliente MCP (Claude Desktop, etc.)
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. Pida a la IA con lenguaje natural: "busca imágenes", "añádelo a favoritos", etc.
3. Están disponibles más de 60 herramientas como `search_images`, `add_favorite`, `trigger_scan`

### Consejos

- Desde la extensión de cliente MCP también puede conectarse a servidores MCP externos (stdio / SSE / Streamable HTTP)
- Si configura autenticación con API Key, puede llamar directamente a la REST API desde herramientas externas sin la cabecera CSRF
- Con la extensión Hailo GenAI puede integrarse también a través del endpoint compatible con el SDK de OpenAI

---

## 11. Usar Hailo-10H como servidor compatible con OpenAI

Cuando tiene equipo con NPU Hailo-10H y quiere usarlo como servidor de IA local compatible con el SDK de OpenAI. Puede usar tal cual el LLM / VLM / reconocimiento de voz / embedding CLIP de Hailo desde herramientas externas como Open WebUI, Continue.dev, scripts propios, etc.

### Endpoints soportados

| Endpoint | Función | API de OpenAI equivalente |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | Lista de modelos descargados | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | Generación de texto / comprensión de imagen (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | Transcripción de audio | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | Texto → vector (CLIP) | Embeddings |

### Procedimiento

1. Verifique que la extensión Hailo GenAI está activada en la página **Extensions > GenAI**
2. Descargue los modelos que quiera usar (LLM: `qwen2.5-1.5b-chat` etc., VLM: `llava-v1.6-vicuna-7b` etc.)
3. En la configuración de conexión de la herramienta externa establezca la **Base URL** en:
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   (Ajuste el puerto a la configuración de arranque de YU AI Manager)
4. No se requiere API Key (por ser acceso local). Si la herramienta exige API Key, introduzca un valor ficticio (por ejemplo `dummy`)

### Ejemplo de conexión con herramientas externas

#### Open WebUI

Añada en Settings > Connections > OpenAI API:
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev (asistente de IA de VS Code)

Añada a `~/.continue/config.json`:
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

#### Python (SDK de OpenAI)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# Generación de texto
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# Comprensión de imagen (VLM) — adjuntar imagen en base64
import base64
with open("image.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

res = client.chat.completions.create(
    model="llava-v1.6-vicuna-7b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
)

# Transcripción de audio
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# Embedding de texto (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### Parámetros soportados

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input` (cadena o array de cadenas)
- **Alias de modelo**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### Notas

- **Exclusividad del dispositivo**: Hailo-10H solo puede cargar simultáneamente 1 modelo GenAI (LLM o VLM o S2T). El cambio de modo se realiza en la página GenAI
- **Limitación de URL de imagen**: Por seguridad, se bloquea la especificación de imagen mediante URL `http://`. Use el formato `data:image/...;base64,...` o el formato `file_id:` de YU AI Manager
- **Embedding CLIP**: Solo admite texto → vector. Para imagen → vector use el endpoint `/api/semantic/`
- **Formato de audio**: Formatos distintos de WAV (MP3, M4A, OGG, etc.) requieren ffmpeg
- **Campo `usage`**: El conteo de tokens siempre se devuelve 0 (limitación de la NPU Hailo)
