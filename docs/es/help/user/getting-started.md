# Primeros pasos

YU AI Manager es una aplicación WebUI para gestionar los metadatos de imágenes generadas por IA.

## Instalación

### Requisitos del sistema

- Python 3.11 o superior
- Node.js 18 o superior (para compilar el frontend)

### Pasos de configuración

```bash
# Clonar el repositorio
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# Instalar uv (solo la primera vez)
pip install uv

# Crear entorno virtual Python e instalar paquetes dependientes
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# Compilar el frontend
pnpm install
pnpm run build

# Opcional: aceleración de búsqueda semántica (para bibliotecas de gran escala)
uv pip install faiss-cpu
```

## Método de inicio

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

Acceder a `http://localhost:5000` desde el navegador.

## Configuración inicial

1. **Registrar carpeta de escaneo**: Agregar la carpeta donde se guardan las imágenes de IA en la pestaña Settings > Scan
2. **Ejecutar escaneo**: Después de agregar la carpeta, el escaneo comienza automáticamente
3. **Ver imágenes**: Las imágenes se pueden buscar y ver en la página principal

## Exposición en LAN

Si quieres acceder desde otros dispositivos:

1. Activar "LAN Access" en la pestaña Settings > **Server**
2. Configurar la autenticación PIN (obligatorio al exponer en LAN)  
   Ingresar un número (4〜8 dígitos) en el campo "Código de autenticación PIN" de la **pestaña Settings > Server**
3. Reiniciar el servidor

Puedes acceder desde otros dispositivos en la LAN con `http://<IP del servidor>:5000`.
