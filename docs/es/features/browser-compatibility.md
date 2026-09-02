# Informe de Compatibilidad de Navegadores

**Fecha de encuesta:** 2026-02-23

## Navegadores Compatibles (Recomendado)

| Navegador  | Versión Mínima | Versión de Características Completas |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

IE11 y versiones anteriores no se admiten.

---

## Compatibilidad de API

| Característica | Chrome | Firefox | Safari | Edge | Notas |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | Todos los navegadores admitidos |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | Todos los navegadores admitidos |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | Se utiliza para desplazamiento infinito |
| Encadenamiento opcional `?.` | 80+ | 74+ | 13.1+ | 80+ | Se utiliza extensamente en toda la base de código |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | Se utiliza para tarjetas de muelle |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | No compatible en Safari 15 y anteriores |
| `inset` atajo CSS | 102+ | 106+ | **16+** | 102+ | No compatible en Safari 15 y anteriores |
| `backdrop-filter` | 76+ | **No compatible** | 9+ | 79+ | No compatible en Firefox |
| `-webkit-backdrop-filter` | ✓ | **No compatible** | 9+ | ✓ | Sin alternativa para Firefox |

---

## Problemas Conocidos

### 🔴 Firefox — `backdrop-filter` No Compatible

- **Archivos afectados:** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **Síntoma:** El efecto de desenfoque del panel (glassmorphism) no se renderiza, dejando el fondo transparente
- **Severidad:** Degradación de calidad visual (la funcionalidad no se ve afectada)
- **Plan:** Sin resolver (un fondo opaco alternativo para Firefox se puede añadir en el futuro)

### 🟡 Safari 15 y Anteriores — `scrollbar-gutter`, `inset` No Compatible

- **Archivos afectados:** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **Síntoma:** Inestabilidad de región de barra de desplazamiento y desplazamientos menores de cálculo de posición
- **Severidad:** Menor (el diseño sigue siendo funcional)

---

## Medidas de Compatibilidad Existentes (Buenas Prácticas)

- Tanto `-webkit-backdrop-filter` como el `backdrop-filter` estándar se declaran
- Las barras de desplazamiento de Firefox utilizan `scrollbar-width` / `scrollbar-color`
- Las barras de desplazamiento de WebKit utilizan `-webkit-scrollbar`
- Las APIs destructivas (`crypto.randomUUID`, `structuredClone`, `.at()`, etc.) no se utilizan

---

## Candidatos Futuros

| Elemento | Prioridad | Descripción |
|------|----------|-------------|
| Alternativa de backdrop-filter para Firefox | P3 | Cambiar a un fondo semi-transparente sin desenfoque |
| Consulta condicional `@supports` | P3 | Detección de características CSS |
