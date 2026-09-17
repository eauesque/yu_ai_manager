# Guía de la UI de perfiles de WD-Tagger

Este documento explica cómo usar la **UI de gestión de perfiles** de WD-Tagger (añadida en v4.197.0+).

## 1. Resumen

- Un **perfil** agrupa ajustes de WD-Tagger como archivos del modelo, definición de tags, umbrales y preprocesado.
- Abrir: Página Tools → sección **WD-Tagger** → `Administrar perfiles...`.
- En el modal puedes alternar entre **Lista (List)** y **Formulario (Form)**.

## 2. Pantalla de lista (List)

### 2.1 Insignias (Builtin / User)

- `builtin`: perfiles integrados (solo lectura)
- `user`: perfiles de usuario (se pueden crear/editar/eliminar)
- `↻`: este perfil **reemplaza** a un perfil integrado con el mismo `id`

### 2.2 Filtro (All / User / Builtin)

Botones de filtro:

- `Todos`
- `Usuario`
- `Integrados`

### 2.3 Botones (acciones)

Acciones por fila:

- `Duplicar`: copia el perfil y abre el formulario (para modificar un perfil integrado)
- `Editar`: editar perfil de usuario (los integrados no se pueden editar)
- `Eliminar`: eliminar perfil de usuario (los integrados no se pueden eliminar)
- `Exportar`: descargar el perfil como `.json`
- `Probar (descarga en seco)`: comprobar sin descargar realmente que los archivos se pueden obtener desde HuggingFace

Arriba a la derecha:

- `+ Nuevo`: crear un perfil vacío
- `Importar`: crear un perfil desde JSON (subir / pegar)

## 3. Pantalla de formulario (Form)

El formulario está dividido en 5 secciones tipo acordeón.

### 3.1 Metadata

- `id`: identificador del perfil (no se puede cambiar después)
- `Nombre para mostrar`: nombre visible en la lista
- `profile_version`: versión del esquema (normalmente no hace falta tocarla)

### 3.2 Model & Files

- `model_id`: id del modelo en HuggingFace (ej.: `SmilingWolf/wd-swinv2-tagger-v3`)
- `adapter_family`, `backend`, `hf_subdir`: solo si es necesario
- `Archivos`:
  - `name`: nombre de archivo (ej.: `model.onnx`)
  - `Obligatorio`: el test lo trata como imprescindible
  - `size_hint_mb`: opcional
  - `+ Añadir archivo` / `Quitar`: añadir/quitar filas

### 3.3 Tag source

De dónde se cargan las definiciones de tags.

- `csv`: archivo(file), separador(delimiter), columna nombre(name_col), columna categoría(category_col), mapa(category_map)
- `json_list`: archivo(file), esquema(schema)
- `json_dict`: archivo(file), mapeo(mapping)
- `composite`: combinar fuentes(sources)

### 3.4 Threshold source

De dónde se cargan los umbrales.

- `global_per_category`: definir umbrales por categoría en la UI
- `per_tag`: archivo + reserva
  - archivo(file)
  - modo de reserva(fallback.mode): `global` / `category_default`
  - valor de reserva(fallback.value)

### 3.5 Preprocess & Categories

- Preprocesado(`preprocess_spec`): `input_size`, `dtype`, `layout`, `channel_order`, `resize_strategy` (`letterbox` / `longest_side_pad` / `stretch`), `scale`, `mean`, `std`
- Categorías:
  - `Categorías compatibles`
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. Importar / Exportar

### 4.1 Importar

`Importar` muestra dos pestañas:

- Subir JSON: subir un `.json`
- Pegar JSON: pegar JSON en el área de texto

Luego se abre el formulario. Revisa/ajusta y `Guardar`.

### 4.2 Exportar

En la lista, `Exportar` descarga el perfil como JSON.

## 5. Probar (descarga en seco)

- Verifica si los archivos listados en `files` se pueden obtener desde **HuggingFace**.
- En éxito puede aparecer `Descarga OK: {n} archivos ({total} MB)`.
- En error, se muestra el motivo (ver siguiente sección).

## 6. Errores comunes (breve)

- `id_conflict`: ya existe un perfil de usuario con el mismo `id`
- `id_immutable`: `id` no se puede cambiar (renombrar con Duplicar → Eliminar)
- `in_use`: no se puede eliminar porque el perfil está activo
- `validation_failed`: fallo de validación (`{detail}` contiene detalles)
- `profile_too_large`: el JSON importado supera 1MB
- `ssrf_blocked`: redirección fuera de HuggingFace bloqueada (protección SSRF)
- `hf_unavailable`: HuggingFace no disponible o respuesta inválida
- `timeout`: tiempo de espera agotado (60s)
- `required_missing`: falta un archivo obligatorio

## 7. Limitaciones (importante)

- Los perfiles integrados (`builtin`) no se pueden editar/eliminar. Usa `Duplicar`.
- `id` es inmutable. Para renombrar: `Duplicar` → `Eliminar` el anterior.
- Límite de importación: **1MB**.
- `Probar` solo permite hosts de HuggingFace (allowlist SSRF):
  - `huggingface.co`
  - `hf.co`
