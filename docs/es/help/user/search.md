# Búsqueda

## Búsqueda básica

Introduzca etiquetas separadas por comas en la barra de búsqueda.

```
1girl, blue_eyes, school_uniform
```

## Filtros de búsqueda

| Filtro | Descripción |
|---------|------|
| Rango de fechas | Filtrar entre fecha de inicio y fecha de fin |
| Formato de archivo | PNG / WebP / JPG / GIF |
| Valoración | Filtrar por 1 a 5 estrellas |
| Favoritos | Mostrar solo los marcados como favorito |
| Colección | Mostrar solo dentro de una colección específica |

## Búsqueda dentro del prompt

Usando el campo "in_prompt" se puede realizar una búsqueda de texto completo dentro del prompt de la imagen.
Si FTS (Full-Text Search) está activado, la búsqueda es rápida.

## Orden

| Orden | Descripción |
|--------|------|
| date | Fecha de registro (más recientes primero) |
| date_old | Fecha de registro (más antiguos primero) |
| folder | Por carpeta |
| path | Por ruta |
| random | Aleatorio |
| rating_desc | Valoración (descendente) |
| rating_asc | Valoración (ascendente) |

## Búsqueda semántica

Si se ha configurado un modelo Hailo-10H o ONNX CLIP, puede buscar imágenes en lenguaje natural.
Use el botón de búsqueda semántica a la derecha de la barra de búsqueda.

### Aceleración con FAISS (recomendado)

Por defecto la búsqueda semántica utiliza búsqueda por fuerza bruta con NumPy, pero
**instalar FAISS la acelera considerablemente**.

| Tamaño de la biblioteca | NumPy (por defecto) | FAISS (recomendado) |
|-------------|-------------------|-------------|
| Menos de 10 000 | Decenas de ms | Unos pocos ms |
| 100 000 | 1-3 s | Decenas de ms |
| Más de 1 000 000 | Más de 10 s | Menos de 100 ms |

FAISS selecciona automáticamente el índice óptimo según el tamaño objetivo:
- **Menos de 50 000**: IndexFlatIP (búsqueda exhaustiva exacta, suficientemente rápida)
- **50 000 o más**: IndexIVFFlat (búsqueda aproximada del vecino más cercano, rápida incluso a gran escala)

#### Instalación

```bash
# Activar venv antes de instalar
source venv/bin/activate

# x86_64 (Intel/AMD) — instalable directamente con pip
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — si no entra por pip
# Opción 1: vía conda
conda install -c conda-forge faiss-cpu

# Opción 2: compilación desde el código fuente
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

Tras la instalación, basta con reiniciar el servidor: se detecta automáticamente.
Si FAISS está activo, se muestra lo siguiente en el log de arranque:

```
FAISS x.x.x detected — using accelerated vector search
```

Aunque FAISS no esté instalado, sigue funcionando como siempre con NumPy.
