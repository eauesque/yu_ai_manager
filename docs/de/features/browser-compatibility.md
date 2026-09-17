# Browser-Kompatibilitätsbericht

**Umfragedatum:** 2026-02-23

## Unterstützte Browser (empfohlen)

| Browser  | Mindestversion | Vollständige Feature-Version |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

IE11 und ältere Versionen werden nicht unterstützt.

---

## API-Kompatibilität

| Feature | Chrome | Firefox | Safari | Edge | Notizen |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | Alle Browser werden unterstützt |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | Alle Browser werden unterstützt |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | Wird für unendliches Scrollen verwendet |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | Wird in der gesamten Codebasis verwendet |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | Wird für Dock-Karten verwendet |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Wird nicht auf Safari 15 und älter unterstützt |
| `inset` CSS-Kurzform | 102+ | 106+ | **16+** | 102+ | Wird nicht auf Safari 15 und älter unterstützt |
| `backdrop-filter` | 76+ | **Nicht unterstützt** | 9+ | 79+ | Wird auf Firefox nicht unterstützt |
| `-webkit-backdrop-filter` | ✓ | **Nicht unterstützt** | 9+ | ✓ | Keine Alternative für Firefox |

---

## Bekannte Probleme

### 🔴 Firefox — `backdrop-filter` wird nicht unterstützt

- **Betroffene Dateien:** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **Symptom:** Der Panel-Unschärfe-Effekt (Glassmorphismus) wird nicht gerendert, wodurch der Hintergrund transparent bleibt
- **Schweregrad:** Verschlechterung der visuellen Qualität (Funktionalität ist nicht beeinträchtigt)
- **Plan:** Unberücksichtigt (ein opaker Hintergrund-Fallback für Firefox könnte in Zukunft hinzugefügt werden)

### 🟡 Safari 15 und älter — `scrollbar-gutter`, `inset` werden nicht unterstützt

- **Betroffene Dateien:** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **Symptom:** Scrollleisten-Bereichsflimmern und geringfügige Positions-Berechnungsoffsets
- **Schweregrad:** Gering (Layout bleibt funktionsfähig)

---

## Vorhandene Kompatibilitätsmaßnahmen (Best Practices)

- Sowohl `-webkit-backdrop-filter` als auch das Standard-`backdrop-filter` werden deklariert
- Firefox-Scrollleisten verwenden `scrollbar-width` / `scrollbar-color`
- WebKit-Scrollleisten verwenden `-webkit-scrollbar`
- Destruktive APIs (`crypto.randomUUID`, `structuredClone`, `.at()` usw.) werden nicht verwendet

---

## Zukünftige Kandidaten

| Element | Priorität | Beschreibung |
|------|----------|-------------|
| Firefox backdrop-filter-Fallback | P3 | Wechsel zu einem semi-transparenten Hintergrund ohne Unschärfe |
| `@supports` bedingte Abfrage | P3 | CSS-Feature-Erkennung |
