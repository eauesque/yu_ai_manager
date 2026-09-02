# Empezar con YU AI Manager en 5 minutos

## Qué es YU AI Manager

YU AI Manager es una aplicación WebUI que permite gestionar de forma centralizada los metadatos de imágenes generadas por IA (Stable Diffusion / NovelAI / ComfyUI, etc.). Extrae automáticamente los prompts e información del modelo incrustados en las imágenes y agiliza la búsqueda por etiquetas, la visualización y la organización.

---

## Requisitos del sistema

| Elemento | Requisito |
|------|------|
| Python | 3.11 o superior |
| Node.js | 18 o superior (para el build del frontend) |
| SO | Windows 10/11, macOS, Linux |
| Navegador | Chrome / Firefox / Edge (se recomienda la última versión) |

---

## Pasos de instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. Crear el entorno virtual de Python

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3. Instalar las dependencias de Python

```bash
uv pip install -r requirements.txt
```

> Si `uv` no está instalado, instálelo antes con `pip install uv`.

### 4. Compilar el frontend

```bash
pnpm install
pnpm run build
```

> Si `pnpm` no está instalado, instálelo antes con `npm install -g pnpm`.

Con esto la instalación ha terminado.

---

## Primer arranque

### 1. Arrancar el servidor

```bash
# Si no está activado el venv, actívelo antes
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. Acceder desde el navegador

Tras el arranque, abra la siguiente URL en el navegador:

```
http://localhost:5000
```

*(Captura de pantalla de la pantalla principal)*

---

## Primeras acciones

### Paso 1: Registrar una carpeta de imágenes para escaneo

Registre la carpeta donde están guardadas las imágenes generadas por IA para que se lean sus metadatos.

1. Abra **Settings** desde el menú hamburguesa en la parte superior derecha
2. Seleccione la pestaña **Scan**
3. Añada la ruta de la carpeta a escanear
4. Tras añadir la carpeta, el escaneo comienza automáticamente

*(Captura de pantalla de la pantalla de registro de carpeta de escaneo)*

Durante el escaneo aparece una barra de progreso en la parte superior. Con muchas imágenes puede tardar varios minutos, pero se puede buscar y ver durante el escaneo.

### Paso 2: Ver las imágenes en la cuadrícula de miniaturas

Al terminar el escaneo, la página principal muestra la cuadrícula de miniaturas.

*(Captura de pantalla de la cuadrícula de miniaturas)*

- **Scroll**: el scroll virtual permite mostrar grandes cantidades de imágenes de forma fluida
- **Ordenar**: cambie por fecha, por valoración, etc., desde el menú de orden en la parte superior
- **Clic derecho**: desde el menú contextual puede añadir a favoritos o a una colección

### Paso 3: Filtrar imágenes con búsqueda por etiquetas

Si escribe etiquetas separadas por comas en la barra de búsqueda, solo se muestran las imágenes coincidentes.

```
1girl, blue_eyes, school_uniform
```

*(Captura de pantalla de la pantalla de búsqueda por etiquetas)*

- **Autocompletado**: se muestran sugerencias de etiquetas mientras escribe
- **Filtro**: puede filtrar por rango de fechas, formato de archivo, valoración por estrellas, etc.
- **Búsqueda dentro del prompt**: también puede buscar en el texto completo del prompt

### Paso 4: Consultar la información de la imagen en el modal de detalles

Al hacer clic en una miniatura se abre el modal de detalles.

*(Captura de pantalla del modal de detalles)*

- **Pestaña Info**: consulte prompt, prompt negativo, nombre del modelo, parámetros de generación, etc.
- **Pestaña AI Analysis**: muestra el resultado del etiquetado automático por WD-Tagger (si está configurado)
- **Valoración por estrellas**: asigne una valoración de 1 a 5 estrellas a la imagen
- **Favoritos**: añada a favoritos con el icono de corazón
- **Edición de etiquetas**: puede añadir o eliminar etiquetas de usuario
- **Control por teclado**: use las flechas izquierda/derecha para moverse entre imágenes

---

## Resumen de operaciones frecuentes

| Qué quiere hacer | Acción |
|-------------|------|
| Buscar imágenes | Escribir etiquetas en la barra de búsqueda |
| Ver detalles de una imagen | Hacer clic en la miniatura |
| Añadir a favoritos | Icono de corazón en el modal de detalles, o menú con clic derecho |
| Poner valoración por estrellas | Icono de estrella en el modal de detalles |
| Añadir imagen a una colección | Menú con clic derecho > Añadir a colección |
| Seleccionar varias imágenes | Ctrl+clic (o Shift+clic para selección por rango) |
| Escanear una carpeta nueva | Settings > pestaña Scan |

---

## Siguientes pasos

Una vez familiarizado con lo básico, pruebe también las siguientes funciones.

### Settings (configuración)

En la página Settings puede personalizar la apariencia, configurar la zona horaria, la publicación en LAN, etc.
Para más detalles consulte la [guía de Settings](settings.md).

### Bridge (integración con herramientas de generación)

Puede enviar y recibir prompts integrándose con SD WebUI / ComfyUI / la API de NovelAI.
Para más detalles consulte la [guía de Bridge](bridges.md).

### Extensions (extensiones)

Están disponibles muchas extensiones como WD-Tagger (etiquetado automático), biblioteca de prompts, visor de logs de chat, etc. Se gestionan desde Settings > pestaña Extensions.

### Búsqueda semántica

Configurando un modelo CLIP puede buscar imágenes en lenguaje natural, por ejemplo "una chica mirando el atardecer en la playa".
Para más detalles consulte la [guía de búsqueda](search.md).

### Servidor MCP

Puede operar YU AI Manager desde agentes de IA como Claude Desktop. Se conecta mediante transporte stdio.

---

## Solución de problemas

Si surge algún problema consulte la [guía de solución de problemas](troubleshooting.md).

Problemas frecuentes:

- **El comando `uv` no se encuentra**: instálelo con `pip install uv`
- **El comando `pnpm` no se encuentra**: instálelo con `npm install -g pnpm`
- **El puerto 5000 está ocupado**: especifique otro puerto con `python web_ui.py --port 5100`
- **No se muestran las imágenes**: verifique que la ruta de la carpeta escaneada es correcta y que los archivos realmente existen
