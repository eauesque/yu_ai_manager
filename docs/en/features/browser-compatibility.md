# Browser Compatibility Report

**Survey date:** 2026-02-23

## Supported Browsers (Recommended)

| Browser  | Minimum Version | Full Feature Version |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

IE11 and older versions are not supported.

---

## API Compatibility

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | All browsers supported |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | All browsers supported |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | Used for infinite scroll |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | Used extensively throughout codebase |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | Used for dock cards |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Not supported on Safari 15 and earlier |
| `inset` CSS shorthand | 102+ | 106+ | **16+** | 102+ | Not supported on Safari 15 and earlier |
| `backdrop-filter` | 76+ | **Not supported** | 9+ | 79+ | Not supported on Firefox |
| `-webkit-backdrop-filter` | ✓ | **Not supported** | 9+ | ✓ | No alternative for Firefox |

---

## Known Issues

### 🔴 Firefox — `backdrop-filter` Not Supported

- **Affected files:** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **Symptom:** The panel blur effect (glassmorphism) does not render, leaving the background transparent
- **Severity:** Visual quality degradation (functionality is unaffected)
- **Plan:** Unaddressed (an opaque background fallback for Firefox may be added in the future)

### 🟡 Safari 15 and Earlier — `scrollbar-gutter`, `inset` Not Supported

- **Affected files:** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **Symptom:** Scrollbar region jitter and minor position calculation offsets
- **Severity:** Minor (layout remains functional)

---

## Existing Compatibility Measures (Good Practices)

- Both `-webkit-backdrop-filter` and the standard `backdrop-filter` are declared
- Firefox scrollbars use `scrollbar-width` / `scrollbar-color`
- WebKit scrollbars use `-webkit-scrollbar`
- Destructive APIs (`crypto.randomUUID`, `structuredClone`, `.at()`, etc.) are not used

---

## Future Candidates

| Item | Priority | Description |
|------|----------|-------------|
| Firefox backdrop-filter fallback | P3 | Switch to a semi-transparent background without blur |
| `@supports` conditional query | P3 | CSS feature detection |
