# Integración GitHub

## Resumen

GitHub Integration es una extensión que permite gestionar de forma centralizada repositorios, issues, pull requests, discussions y releases de GitHub desde YU AI Manager. Soporta múltiples cuentas de GitHub y almacena los tokens de forma cifrada y segura. El panel de control permite verificar rápidamente las notificaciones y las estadísticas del repositorio, y también cuenta con una función de clasificación de issues con IA.

## Configuración

### Obtener un Personal Access Token (PAT) de GitHub

1. Iniciar sesión en GitHub y abrir **Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. Hacer clic en **Generate new token (classic)**
3. Ingresar el nombre del token y establecer la fecha de caducidad
4. Marcar **`repo`** en los alcances (necesario para acceso completo al repositorio)
5. Hacer clic en **Generate token** y copiar el token mostrado

> **Nota**: El token solo se muestra en esta pantalla. Asegúrate de copiarlo antes de cerrarla.

### Agregar una cuenta

1. Hacer clic en la tarjeta **GitHub** en el lanzador de extensiones, o acceder directamente a `/ext/github`
2. Abrir la pestaña **Settings**
3. Hacer clic en **Agregar cuenta**
4. Ingresar la siguiente información:
   - **Etiqueta**: Nombre visible de la cuenta (p.ej., "Personal", "Trabajo")
   - **Token**: El PAT obtenido anteriormente
   - **Repositorios**: Ingresar los repositorios a monitorear en formato `owner/repo` (se pueden agregar múltiples)
5. Después de guardar, seleccionar la cuenta desde el menú desplegable

## Funciones

### Panel de control

Al seleccionar una cuenta, el panel de control se carga automáticamente.

- **Notificaciones**: Lista de notificaciones de GitHub no leídas
- **Estadísticas del repositorio**: Número de estrellas, forks y issues abiertos en formato de tarjeta
- **Tarjetas de resumen**: Resumen del estado de los repositorios monitoreados de un vistazo

### Issues

- Filtrado por repositorio y estado (open/closed)
- Visualización de detalles del issue (cuerpo, comentarios, etiquetas)
- Creación de nuevos issues
- **Función de clasificación**: Clasificación automática de issues con IA
  - `valid_bug` — Informe de bug válido
  - `needs_info` — Se necesita información adicional
  - `skip` — No requiere acción
- **Cola de issues**: Sondeo automático de nuevos issues de GitHub y encolamiento local. Se notifica a los pendientes cuando se conecta un cliente MCP (Claude Desktop).

### Pull Requests

- Lista de PRs y filtrado
- Visualización de estadísticas de diferencias (líneas agregadas, eliminadas y archivos modificados)
- Verificación del contenido de cambios por archivo en la vista detallada

### Discussions

- Obtención de la lista de discusiones a través de la API GraphQL
- Visualización de insignias de categoría y de respuesta

### Releases

- Lista de los últimos releases de los repositorios monitoreados
- Verificación de las notas de release

### Settings

- Agregar, editar, eliminar y habilitar/deshabilitar cuentas
- Visualización del límite de tasa restante de la API
- Configuración del filtro de idioma y el intervalo de programación
- Configuración del intervalo de sondeo de la cola de issues, cierre automático de issues inválidos y notificaciones de conexión MCP
- Edición de prompts de clasificación para issues, PRs y discussions ([ver ejemplos](/help/github-triage-examples))

### Cola de issues

La cola de issues sondea periódicamente GitHub y almacena los nuevos issues localmente.

- **Sondeo**: Ejecución automática por el programador (intervalo configurable, predeterminado 60 minutos)
- **Notificación**: Al conectarse al MCP, se notifica en conjunto al cliente los issues no procesados a Claude Desktop
- **Clasificación**: Posibilidad de clasificar cada issue de la cola como válido o inválido
- **Cierre automático**: Cierre automático en GitHub de los issues clasificados como inválidos con comentario de plantilla
- **Sondeo manual**: Hacer clic en "Poll Now" en Settings para obtener instantáneamente

### Prompts de clasificación

Las instrucciones de IA para la clasificación de issues, PRs y discussions se pueden personalizar.

- Hay prompts editables individualmente para cada tipo (Issue, PR, Discussion)
- Se proporcionan prompts predeterminados que se pueden restaurar en cualquier momento con "Restaurar predeterminado"
- Para plantillas en varios idiomas y estilos, ver [ejemplos de prompts de clasificación](/help/github-triage-examples)
- Los prompts se guardan en config.json (sin cifrado porque no contienen información confidencial)

## Integración MCP

GitHub Integration tiene 12 herramientas MCP disponibles para operar directamente desde Claude Code.

- Obtener lista y detalles de issues
- Obtener lista y detalles de PRs
- Obtener notificaciones
- Obtener y actualizar prompts de clasificación
- Gestión de la cola de issues (lista de pendientes, clasificación, rechazo, sondeo)

Usando las herramientas MCP puedes consultar la información de GitHub sin salir del IDE mientras editas código.

## Consejos

- **Múltiples cuentas**: Es más fácil gestionar si separas las cuentas por uso, como personal y trabajo
- **Permisos del token**: El alcance `repo` es suficiente para todas las funciones básicas. Para acceder a repositorios privados de organizaciones, se requiere autorización SSO adicional en la organización
- **Uso de la clasificación**: En repositorios con muchos issues, la función de clasificación automatiza la priorización de manera eficiente
- **Límite de tasa**: La API de GitHub tiene un límite de solicitudes por hora. Se puede verificar el saldo restante en la pestaña Settings
- **Seguridad del token**: Los tokens se almacenan cifrados en el lado del servidor. No se almacenan en texto plano
- **Actualización del panel de control**: Al cambiar de cuenta, los datos se vuelven a obtener automáticamente
