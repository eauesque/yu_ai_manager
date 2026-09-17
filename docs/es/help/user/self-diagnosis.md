# Autodiagnóstico y reporte de problemas

Si YU AI Manager no funciona o se comporta de forma extraña, siga estos pasos para recopilar pistas sobre la causa y reportarla a los desarrolladores. No requiere conocimiento de comandos ni Git.

## 1. Presione primero "Reportar un problema"

1. Abra la aplicación en el navegador y seleccione **Diagnostics** desde el menú en la esquina superior derecha.
2. Presione el botón **"Reportar un problema"**.
3. Después de esperar un momento, se creará una carpeta `repair/2026XXXX-HHMMSS/`. Contiene el siguiente conjunto de reporte automático:
   - Información del entorno, registros recientes y configuración (información personal y tokens están enmascarados)
   - Plantillas de indicaciones para reparación con IA

Presione **"Abrir carpeta"** para abrirla en el Explorador. Con **"Convertir a ZIP"** puede agruparla en un solo zip.

> Acerca del enmascaramiento: Nombres de usuario, correos electrónicos, cadenas similares a claves API, direcciones IP, etc., se reemplazan automáticamente con `<REDACTED>`. Como no es perfecto, revise el contenido una vez antes de compartirlo.

## 2. Comparta el reporte

Adjunte el archivo ZIP al desarrollador, soporte o Discord. El botón **"Copiar mensaje para Discord"** le proporciona un texto breve listo para pegar.

## 3. Soluciones temporales que puede intentar por su cuenta

### 3-A. Verificación de entorno (doctor)

Presione el botón **"Diagnóstico del entorno"** en la pantalla de diagnóstico para mostrar el estado de Python, GPU, DB, etc. en markdown. Pruebe secuencialmente los `fix_hint` (sugerencias de corrección) listados en los elementos de color rojo (ERROR) o amarillo (WARN).

### 3-B. Reiniciar en Safe Mode

Si la aplicación no se inicia normalmente, se bloquea o la carga nunca se detiene, puede iniciar en **Safe Mode**.

- Windows: Doble clic en `start.bat --safe-mode` (o agregue ` --safe-mode` al final del acceso directo)
- macOS / Linux: Desde la terminal, `./start.sh --safe-mode`

Durante Safe Mode puede:

- Verificar la configuración
- "Reportar un problema" y "Diagnóstico del entorno"
- Aplicar **paquetes de actualización seguros (update.zip)** proporcionados por el desarrollador (solo reemplazo de archivos - scripts de reparación automática deshabilitados)

Safe Mode continuará hasta el próximo inicio normal. Un reinicio normal lo devuelve al modo normal.

### 3-C. Aplicar paquete de actualización (update.zip)

Si recibe `update.zip` del desarrollador:

1. Pantalla de diagnóstico → Sección **"Aplicar actualización"**
2. Seleccione el archivo y confirme que **Verify** se pone verde
3. Presione **Aplicar** en el diálogo de confirmación
4. Siga las instrucciones mostradas para reiniciar

> No aplique nunca un zip que muestre validación en rojo. Podría ser alterado o un paquete para otra aplicación.

Si algo sale mal, puede usar **"Deshacer la última actualización (Rollback)"** para volver al estado anterior.

## 4. Qué no debe hacer

- Publicar registros sin enmascarar en redes sociales o foros públicos
- Aplicar `update.zip` de origen desconocido
- Editar manualmente la carpeta `data/` o `tags.db`

## Si aún tiene problemas

Si eso no lo resuelve, reporté el ZIP junto con "qué acción realizó y qué sucedió". El lado de IA cargará `prompt_for_codex.md` / `prompt_for_claude.md` y proporcionará una propuesta de parche de corrección.
