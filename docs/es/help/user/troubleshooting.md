# Solución de problemas

## Problemas frecuentes

### El servidor no arranca

- Verifique que el entorno virtual de Python está activado: `source venv/bin/activate`
- Verifique que las dependencias están instaladas: `uv pip install -r requirements.txt`
- Verifique que el puerto no está en uso: `ss -tlnp | grep 5000`

### No se muestran las imágenes

- La API de miniaturas necesita que exista el archivo de imagen
- Verifique que la ruta de la tabla `files` coincide con la ruta real del archivo
- Verifique que la ruta de la raíz de escaneo es correcta

### No se puede acceder desde la LAN

- Verifique que "LAN Access" está ON en Settings > Server
- Verifique que la autenticación por PIN está configurada (obligatoria al publicar en LAN)
- Verifique que el firewall tiene abierto el puerto correspondiente
- Verifique que la dirección IP del servidor es correcta

### Error de conexión MCP

- Verifique que `YU_BASE_URL` es correcta
- Verifique que el servidor está arrancado
- Verifique que la API key es válida
- Si es vía LAN, verifique que el endpoint HTTP/SSE (`/mcp`) está disponible

### El escaneo es lento

- Desactivar `compute_hash` lo acelera
- Para rutas remotas, ajuste el timeout de Remote FS
- Con muchos archivos, el primer escaneo lleva tiempo

### La generación de miniaturas es lenta

- Durante el escaneo la E/S de disco está saturada, por lo que la generación de miniaturas se ralentiza. Al finalizar el escaneo se ejecuta automáticamente un preheat
- **pyvips (opcional)**: si hay muchas imágenes JPEG grandes, el shrink-on-load de libvips lo acelera
  - Linux: `sudo apt install libvips-dev && uv pip install pyvips`
  - macOS: `brew install vips && uv pip install pyvips`
  - Windows: descargue la DLL desde la [página de releases de libvips](https://github.com/libvips/libvips/releases), añádala al PATH y ejecute `uv pip install pyvips`
  - Si está instalado, se detecta automáticamente. Sin él funciona con Pillow
- **Pillow-SIMD (opcional)**: acelera el redimensionado 2-4 veces con ARM NEON / x86 AVX2
  - `uv pip install pillow-simd` (drop-in replacement que sustituye a Pillow)
  - Build optimizado para ARM NEON: `CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - En entornos sin wheels se requieren herramientas de compilación (gcc, etc.)

## Depuración

- Consulte los logs del servidor en Settings > pestaña Logs
- Modo de depuración MCP: con `YU_DEBUG_MODE=1` se habilitan herramientas adicionales
- Comprobación de integridad de BD: `python db_health.py`
