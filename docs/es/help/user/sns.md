# SNS Share y Bluesky Monitor

## Resumen

SNS Share es una extensión que permite compartir imágenes generadas por IA directamente desde YU AI Manager en Bluesky o X (Twitter). El texto de la publicación se genera automáticamente a partir de una plantilla personalizable y se expanden automáticamente las variables de metadatos de la imagen. Bluesky Monitor añade la monitorización de notificaciones, permitiendo triaje por IA y respuestas automáticas.

## Configuración

### Obtención del App Password de Bluesky

1. Inicie sesión en [bsky.app](https://bsky.app) y abra **Settings > App Passwords**
2. Haga clic en **Añadir App Password**
3. Introduzca un nombre (por ejemplo "YU AI Manager") y haga clic en **Crear App Password**
4. Copie la contraseña mostrada

> **Nota**: La App Password solo se muestra en esta pantalla. Cópiela antes de cerrar el diálogo. Nunca use la contraseña principal de Bluesky.

### Configuración en YU AI Manager

1. Abra **Settings** desde el menú de navegación
2. Cambie a la pestaña **SNS**
3. Introduzca la siguiente información:
   - **Handle de Bluesky**: el nombre del handle (ej. `yourname.bsky.social`)
   - **App Password**: la App Password obtenida arriba
   - **Plantilla de publicación**: la plantilla del texto de la publicación (véase [Variables de plantilla](#variables-de-plantilla))
4. Haga clic en **Guardar**

### Prueba de conexión

Tras guardar las credenciales, haga clic en **Probar conexión** para verificar la autenticación con Bluesky. Si tiene éxito, se muestran el handle y el nombre a mostrar.

## Funcionalidades

### Compartir en Bluesky

Puede compartir la imagen directamente en Bluesky desde la vista de detalles.

1. Abra el modal de detalles de la imagen
2. Haga clic en el botón **SNS**
3. Verifique y edite el texto generado
4. Haga clic en **Publicar en Bluesky**

- El texto de la publicación se genera a partir de la plantilla configurada expandiendo las variables de metadatos
- La imagen se comprime y redimensiona automáticamente para cumplir el límite de subida de 1 MB de Bluesky
- La publicación se limita a **300 grapheme** (el exceso se recorta automáticamente)
- Puede elegir si adjuntar la imagen o no

### Compartir en X (Twitter)

Comparte la información de la imagen en X usando Web Intent (abre la pantalla de publicación de X en el navegador).

1. Abra el modal de detalles de la imagen
2. Haga clic en el botón **SNS**
3. Haga clic en **Compartir en X**

Se abre la pantalla de publicación de X en una nueva pestaña, con el texto generado desde la plantilla rellenado automáticamente. Puede editar el texto antes de publicar. X no adjunta automáticamente la imagen, por lo que debe adjuntarla manualmente.

### Bluesky Monitor

Bluesky Monitor sondea las notificaciones de Bluesky, las pone en cola localmente y permite triaje y respuestas.

#### Tipos de notificación

- **Menciones**: le han mencionado en una publicación
- **Respuestas**: hay una respuesta a su publicación
- **Citas**: han citado su publicación
- **Follows**: alguien le ha seguido
- **Likes**: han dado like a su publicación
- **Reposts**: han reposteado su publicación

#### Sondeo

Las notificaciones se obtienen automáticamente a un intervalo configurable (por defecto: 30 min, mínimo: 5 min). También se puede disparar el sondeo de inmediato desde Settings o las herramientas MCP.

#### Sistema de cola

Cada notificación entra en la cola con estado **pending** (sin procesar). Después puede transitar a los siguientes estados:

- **notified** -- notificada al cliente MCP (Claude Desktop)
- **dismissed** -- descartada como no requiere acción

#### Triaje

Una clasificación por IA determina si cada notificación necesita acción:

- **valid** -- requiere acción (preguntas, reportes de bug, peticiones de colaboración, etc.)
- **invalid** -- se puede ignorar (elogios genéricos, spam, contenido de bot, etc.)

Existen prompts de triaje personalizables por tipo de notificación (menciones, respuestas, citas). Hay prompts por defecto disponibles que se pueden restaurar en cualquier momento.

#### Respuesta automática

Se pueden enviar respuestas automáticas basadas en plantilla a menciones, respuestas y citas clasificadas como valid:

- Active la respuesta automática en los ajustes del Monitor
- Personalice la plantilla de respuesta por tipo de notificación
- La respuesta se limita a 300 grapheme

#### Descarte automático

Follows, likes y reposts se pueden descartar automáticamente para reducir el ruido en la cola. Cada tipo puede alternarse individualmente en Settings.

#### Notificaciones al conectar MCP

Cuando el cliente MCP (Claude Desktop) se conecta, las notificaciones pendientes se reportan en bloque para que se puedan revisar durante la sesión de desarrollo.

### Settings

La configuración de SNS se realiza en la pestaña **SNS** de la página Settings:

- **Credenciales de Bluesky**: handle y App Password (la contraseña se guarda cifrada y se muestra enmascarada)
- **Plantilla de publicación**: texto de plantilla con variables marcadoras
- **Configuración de Monitor**:
  - Intervalo de sondeo (minutos)
  - Descarte automático de follows, likes y reposts
  - Activar/desactivar respuesta automática
  - Prompts de triaje para menciones, respuestas y citas
  - Plantillas de respuesta automática para menciones, respuestas y citas

## Integración MCP

SNS Share y Bluesky Monitor proporcionan 15 herramientas MCP:

**Compartir (6 herramientas)**:
- `share_to_bluesky` -- publica una imagen en Bluesky
- `get_x_share_url` -- obtiene la URL de X Web Intent
- `get_sns_preview` -- vista previa de la expansión de la plantilla
- `test_bluesky_connection` -- prueba de conexión API
- `get_sns_config` / `save_sns_config` -- obtiene / guarda la configuración de SNS

**Cola de notificaciones (5 herramientas)**:
- `bsky_get_pending_notifications` -- obtiene las notificaciones sin procesar
- `bsky_get_notification_queue` -- obtiene elementos de la cola con filtros
- `bsky_triage_notification` -- establece el resultado del triaje (valid/invalid)
- `bsky_send_auto_response` -- envía una respuesta a una notificación
- `bsky_poll_notifications` -- dispara el sondeo de inmediato

**Configuración del Monitor (4 herramientas)**:
- `bsky_get_monitor_config` / `bsky_save_monitor_config` -- obtiene / guarda la configuración del Monitor
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` -- obtiene / guarda prompts de triaje y plantillas de respuesta

## Variables de plantilla

Variables utilizables en la plantilla de publicación:

| Variable | Descripción |
|---|---|
| `{positive_short}` | Prompt positivo (primeros 100 caracteres) |
| `{positive}` | Prompt positivo completo |
| `{negative_short}` | Prompt negativo (primeros 50 caracteres) |
| `{model}` | Nombre del modelo |
| `{seed}` | Valor de la seed |
| `{steps}` | Número de pasos de sampling |
| `{cfg}` | Escala CFG |
| `{sampler}` | Nombre del sampler |
| `{size}` | Tamaño de la imagen |
| `{tags}` | Top 5 etiquetas |
| `{filename}` | Nombre de archivo |

Plantilla por defecto: `{positive_short}`

## Consejos

- **Seguridad de la App Password**: Use siempre una App Password, nunca la contraseña principal de Bluesky. La App Password se puede revocar en cualquier momento desde la configuración de bsky.app
- **Límites de tasa**: La API de Bluesky tiene límites de tasa. Evite publicaciones consecutivas. La subida de imágenes también cuenta
- **Conteo de grapheme**: Bluesky usa grapheme clusters (no caracteres) para el límite de 300. Los caracteres CJK cuentan como 1 grapheme
- **Compresión de imagen**: Las imágenes de más de 1 MB se redimensionan automáticamente. Si falla la preparación de la imagen, se publica solo texto
- **Intervalo de sondeo del Monitor**: Ajuste el intervalo según el volumen de notificaciones. Para cuentas con muchas notificaciones, conviene un intervalo corto
- **Descarte automático**: Activar el descarte automático de follows, likes y reposts permite centrarse en las notificaciones que sí requieren atención
- **Prompts de triaje**: Personalice los prompts de triaje según su estilo de comunicación y el tipo de interacciones que recibe
