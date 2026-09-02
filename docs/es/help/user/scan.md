# Escaneo

## Registro de carpetas de escaneo

Añada carpetas a escanear en Settings > pestaña Scan.

- Se pueden reordenar mediante arrastrar y soltar
- Active o desactive con la casilla de verificación
- Se pueden registrar varias carpetas

## Ejecución del escaneo

- El escaneo inicia automáticamente tras añadir una carpeta
- Un escaneo manual se ejecuta desde la página Tools o con el `trigger_scan` de MCP
- El progreso del escaneo se notifica en tiempo real mediante SSE

## Escaneo automático (Watcher)

Al activar la extensión Auto Scan Watcher, los cambios de archivos en las carpetas registradas se detectan automáticamente y se escanean.

## Sistema de archivos remoto

Al escanear rutas remotas como WSL / NAS / SMB, ajuste los tiempos de espera en Settings > pestaña Remote FS.

## Escaneo en librerías a gran escala

Puntos a tener en cuenta al escanear cientos de miles o más de un millón de archivos:

- **La búsqueda de imágenes es posible durante el escaneo**: el API de búsqueda usa una conexión de BD de solo lectura, por lo que no le afecta el bloqueo de escritura durante el escaneo
- **Gestión automática de WAL**: durante el escaneo se ejecuta automáticamente un checkpoint de WAL cada 2000 archivos para evitar que el archivo WAL crezca demasiado
- **Evento scan.db_busy**: se envían eventos SSE al inicio y al final del escaneo, para que el frontend pueda mostrar el estado ocupado

## Proceso worker de escaneo

Desde la v3.27.0, el escaneo se ejecuta en un proceso independiente del de web_ui.py.
Gracias a esto, **aunque reinicie web_ui, el escaneo no se interrumpe**.

### Cómo funciona

- Al iniciar un escaneo desde la WebUI, se lanza un proceso worker en segundo plano
- El worker escribe archivos de progreso (JSON) y un archivo PID en `/tmp/yu-scan/`
- La WebUI hace polling de ese archivo de progreso y lo retransmite al frontend por SSE
- Al reiniciar la WebUI, se detecta automáticamente el worker en ejecución y se reconecta la visualización del progreso

### Uso desde la CLI

El worker también puede operarse directamente desde la CLI. Se puede usar incluso con la WebUI apagada.

```bash
# Verificar estado
python -m core.scan.scan_worker status

# Detener el escaneo en curso (graceful shutdown — guarda la posición de interrupción en la BD)
python -m core.scan.scan_worker stop

# Iniciar directamente un escaneo desde la CLI
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# Opciones
#   --recursive / --no-recursive  Incluir subdirectorios (por defecto: recursive)
#   --scan-zips                   Escanea también imágenes dentro de ZIP/7z
#   --force                       Re-escanea también archivos existentes
#   --resume                      Reanuda un escaneo interrumpido
#   --config config.json          Especifica un archivo de configuración
```

### Mecanismos de seguridad

- **Monitorización del proceso padre**: el worker lanzado desde la WebUI monitoriza cada 60 s que la WebUI esté viva. Si la WebUI termina de forma anómala, el worker guarda automáticamente el punto de interrupción y se detiene
- **Soporte SIGTERM**: al enviar SIGTERM con `stop` o `kill`, el worker termina el proceso actual, hace commit a la BD y guarda la posición de interrupción antes de salir
- **Prevención de duplicados**: nunca se lanzan varios workers simultáneamente

### Solución de problemas

Si el worker no responde:

```bash
# Verificar el PID
cat /tmp/yu-scan/worker.pid

# Forzar la terminación del proceso
kill -9 $(cat /tmp/yu-scan/worker.pid)

# Limpiar archivos residuales
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## Errores de escaneo

Si se producen errores durante el escaneo, puede consultarlos con `get_scan_errors` de MCP.
