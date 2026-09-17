# Guía de ajuste de rendimiento

Guía de ajuste para usar YU AI Manager cómodamente en entornos que gestionan más de 100 000 archivos.
Aunque muchas optimizaciones funcionan automáticamente con la configuración por defecto, se puede mejorar aún más ajustando según el entorno.

---

## 1. Hardware recomendado

| Elemento | Requisitos mínimos | Recomendado (más de 100 000 archivos) |
|------|---------|------------------------|
| CPU | 2 núcleos | 4 núcleos o más (la generación de miniaturas se paraleliza) |
| RAM | 4 GB | 8 GB o más |
| Almacenamiento | HDD | **Muy recomendado SSD** — afecta directamente a la velocidad de respuesta de la base de datos |
| Red | — | 1 Gbps o más cuando se usa a través de LAN |

**Especialmente importante**: Coloque siempre el archivo de base de datos (`data/tags.db`) en un SSD.
Los archivos de imagen en sí pueden estar en HDD sin problema, pero si la BD está en HDD, la búsqueda y navegación se vuelven notablemente lentas.

---

## 2. Optimización del escaneo inicial

### División de rutas de escaneo

Escanear muchos archivos a la vez lleva tiempo.
Recomendamos registrar varias rutas de escaneo en Settings > Scan Roots y escanear por etapas.

- Escanee primero las carpetas que más usa
- Añada el resto de carpetas a la cola de escaneo (se procesan automáticamente en orden)
- Aunque registre la misma carpeta de forma duplicada, se detecta y omite automáticamente

### Se puede navegar durante el escaneo

Durante el escaneo, la búsqueda y la visualización de miniaturas funcionan con normalidad.
Internamente se utiliza una conexión de base de datos de solo lectura, por lo que la escritura del escaneo no bloquea la navegación.

### Optimización automática tras el escaneo

Al finalizar el escaneo, las estadísticas de la base de datos se actualizan automáticamente (ANALYZE).
Esto optimiza los planes de ejecución de las consultas de búsqueda y acelera las búsquedas posteriores.
No se requiere ninguna operación especial.

---

## 3. Mejora de la velocidad de navegación

### Caché del Service Worker

El Service Worker del navegador cachea automáticamente los siguientes contenidos:

| Tipo | Límite de caché | Efecto |
|------|-------------|------|
| Miniatura | 5000 elementos | Visualización inmediata de la cuadrícula en segundos accesos |
| Vista previa (1200 px) | 200 elementos | Aceleración de la visualización modal |
| Imagen a tamaño original | 50 elementos | Re-visualización inmediata de imágenes vistas recientemente |

El Service Worker es gestionado automáticamente por el navegador, sin configuración especial.
Para limpiar la caché use las herramientas de desarrollador > Application > Storage del navegador.

### Activar el scroll virtual

Al mostrar miles de resultados, activar el scroll virtual mejora notablemente el rendimiento de renderizado.

**Cómo activarlo**: Settings > Appearance > "Virtual Scroll" en ON

El scroll virtual solo renderiza en el DOM las tarjetas visibles en pantalla, reduciendo considerablemente el uso de memoria y la carga de renderizado.
Se recomienda encarecidamente activarlo en librerías de decenas de miles de elementos.

### Miniaturas WebP

Las miniaturas se generan en formato WebP (30-40 % más pequeñas que JPEG).
Esto reduce el volumen de transferencia, resultando especialmente efectivo en accesos por LAN.
Se aplica automáticamente sin configuración.

---

## 4. Rendimiento de búsqueda

### Efecto de los índices

En la base de datos se crean automáticamente índices optimizados para los principales patrones de búsqueda.
El orden por fecha, el filtrado por etiquetas y la búsqueda de ruta operan con rapidez.

**Orientación**:
- Búsqueda sin filtro: respuesta en menos de 50 ms incluso a escala de 280 000 elementos
- Búsqueda con filtro de etiquetas: menos de 100 ms
- Búsqueda por ruta (FTS5): menos de 50 ms

### Búsqueda FTS5 vs búsqueda LIKE

Para la búsqueda de rutas se utiliza automáticamente el índice FTS5 (Full-Text Search).
Comparado con la búsqueda LIKE tradicional (`%keyword%`), es 20-100 veces más rápido.

Cuando FTS5 no está disponible (por ejemplo, al actualizar desde una BD antigua), se hace fallback automáticamente a LIKE.
Ejecutando el escaneo una vez se construye el índice FTS5.

**Nota sobre búsquedas en japonés**: Las búsquedas que incluyen kanji, hiragana o katakana pueden usar internamente el fallback LIKE.
Se debe a una limitación del tokenizador FTS5 de SQLite y es un comportamiento normal.

---

## 5. Optimización de la reproducción de vídeo

### Caché Faststart

Para acelerar la reproducción de archivos MP4/MOV, se aplica automáticamente el procesado faststart.
Los vídeos ya procesados con faststart empiezan a reproducirse en streaming de inmediato.

| Elemento | Valor |
|------|-----|
| Ubicación de la caché | `cache/faststart/` |
| Límite de capacidad | 4 GB (gestionado automáticamente mediante LRU) |
| Límite por archivo | 500 MB |
| Objetivo | MP4, MOV (WebM se omite por no ser necesario) |

**Mejora perceptible orientativa**:

| Tamaño del archivo | Sin faststart | Con faststart |
|--------------|---------------|---------------|
| 5-50 MB | 2-10 s de espera | Inicia en unos 200 ms |
| 50-200 MB | 10-60 s de espera | Inicia en unos 500 ms |
| 200-500 MB | Minutos de espera | Inicia en aproximadamente 1 s |

### Verificación de FFmpeg

El procesado faststart requiere FFmpeg. Si no está instalado, el vídeo se reproducirá tras descargar todo el archivo.

```bash
ffmpeg -version
```

Si FFmpeg no aparece en PATH, instálelo desde el [sitio oficial](https://ffmpeg.org/download.html).

---

## 6. Gestión del uso de memoria

### mmap de SQLite

En bases de datos grandes (más de 100 000 archivos), mmap (E/S mapeado en memoria) de SQLite se establece automáticamente a 1 GB.
Así las consultas de lectura se aceleran aprovechando la caché de páginas del sistema operativo.

**Entornos con 4 GB o menos de RAM**: mmap puede presionar la memoria.
En tal caso, monitoree la memoria libre del sistema y, si hay mucho swap, cierre otras aplicaciones.

### Gestión de pestañas del navegador

YU AI Manager se comunica en tiempo real con cada pestaña vía SSE (Server-Sent Events).

- Máximo 10 conexiones SSE simultáneas por IP
- Cerrar pestañas innecesarias libera recursos de conexión
- Abrir muchas pestañas también aumenta el uso de memoria del navegador

**Recomendación**: Mantenga como máximo 3-4 pestañas abiertas a la vez.

---

## 7. Solución de problemas — Lista de verificación cuando note "lentitud"

### Verificación básica

- [ ] **¿Usa SSD?**: Si `data/tags.db` está en HDD, todas las operaciones serán lentas
- [ ] **¿Tiene FFmpeg instalado?**: Esencial para acelerar la reproducción de vídeo
- [ ] **Número de pestañas del navegador**: Compruebe que no tiene 5 o más abiertas

### La navegación es lenta

- [ ] **Active el scroll virtual**: Settings > Appearance > Virtual Scroll
- [ ] **No borre la caché del navegador**: La caché del Service Worker está activa
- [ ] **Compruebe si está en escaneo**: Durante el escaneo funciona correctamente, pero la primera generación de miniaturas lleva tiempo

### La búsqueda es lenta

- [ ] **Complete el escaneo**: Al finalizar se ejecuta ANALYZE y se optimiza la búsqueda
- [ ] **Los resultados superan los 100 000**: Añada filtros para reducir resultados (etiquetas, fecha, ruta, etc.)

### La reproducción de vídeo es lenta

- [ ] **Verifique FFmpeg**: confirme con `ffmpeg -version`
- [ ] **Capacidad de caché faststart**: la carpeta `cache/faststart/` no debe superar 4 GB (es automático, pero puede revisarse)
- [ ] **Tamaño del archivo**: vídeos de más de 500 MB no entran en la caché faststart. Se sirven por Range, la primera vez será algo más lento

### El servidor en general va pesado

- [ ] **Número de conexiones simultáneas**: ¿Las conexiones SSE por IP superan 10?
- [ ] **Subiendo archivos**: ¿Está enviando archivos cercanos al límite de subida de 100 MB?
- [ ] **Pestaña Settings > Logs**: Verifique errores y advertencias en el log del servidor

---

## 8. Indicadores orientativos de rendimiento

Tiempos de respuesta orientativos en un entorno correctamente optimizado.

| Operación | Escala 280 000 archivos | Escala 100 000 archivos |
|------|-----------------|-----------------|
| Visualización de cuadrícula (primera vez) | 200-500 ms | 100-300 ms |
| Visualización de cuadrícula (con caché) | menos de 50 ms | menos de 50 ms |
| Búsqueda por etiquetas | menos de 100 ms | menos de 50 ms |
| Búsqueda por ruta (FTS5) | menos de 50 ms | menos de 30 ms |
| Miniatura (acierto de caché) | menos de 5 ms | menos de 5 ms |
| Inicio de reproducción de vídeo (faststart listo) | 200 ms | 200 ms |

Si se exceden notablemente estos valores, revise la lista de verificación anterior.

---

## Modo rápido (servidor Rust)

En entornos compatibles, el arranque cambia automáticamente al servidor Rust (`yu-server`).

En Ajustes -> «Servidor» -> «Modo rápido» se elige **cómo obtenerlo**:

- **Descargar el binario publicado** (predeterminado) -- nunca compila
- **Compilar en este equipo** -- nunca descarga
- **Descargar y, si falla, compilar**

Compilar necesita 8 GB libres de disco y usa mucha CPU y memoria. **En equipos con poca memoria (una Raspberry Pi, por ejemplo) puede agotar el swap y tumbar todo el sistema.** Todas las funciones siguen disponibles durante la compilación. Compilar en Windows requiere además las herramientas de compilación de Visual Studio (el enlazador).

El progreso aparece en la misma pantalla: tiempo transcurrido, la última línea de cargo, éxito o error, y si la compilación se detuvo a medias. El registro completo está en `bin/fast-mode-build.log`.

Cuando el modo rápido se rechaza por el estado de esta copia (un paquete web obsoleto, una extensión fuera de la lista incluida), descargar un binario no cambia la respuesta: no se descarga ni se compila. Ese motivo también se muestra allí.
