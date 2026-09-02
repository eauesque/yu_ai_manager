# WD-Tagger Profil-UI – Bedienungsanleitung

Dieses Dokument beschreibt die WD-Tagger **Profilverwaltung** (neu ab v4.197.0+).

## 1. Übersicht

- Ein **Profil** bündelt WD-Tagger-Einstellungen wie Modelldateien, Tag-Definitionen, Schwellwerte und Vorverarbeitung.
- Öffnen: Tools-Seite → Abschnitt **WD-Tagger** → `Profile verwalten...`.
- Im Modal wechselt man zwischen **Liste (List)** und **Formular (Form)**.

## 2. Listenansicht (List)

### 2.1 Badges (Builtin / User)

- `builtin`: integrierte Profile (schreibgeschützt)
- `user`: Benutzerprofile (erstellen/bearbeiten/löschen möglich)
- `↻`: dieses Profil **überschreibt ein integriertes** Profil mit derselben `id`

### 2.2 Filter (All / User / Builtin)

Oben filtern:

- `Alle`
- `Benutzer`
- `Integriert`

### 2.3 Buttons (Aktionen)

Aktionen pro Zeile:

- `Duplizieren`: Profil kopieren und im Formular öffnen (um integrierte Profile anzupassen)
- `Bearbeiten`: Benutzerprofil bearbeiten (integrierte Profile sind nicht editierbar)
- `Löschen`: Benutzerprofil löschen (integrierte Profile sind nicht löschbar)
- `Exportieren`: Profil als `.json` herunterladen
- `Test (Trockenlauf-Download)`: **ohne echten Download** prüfen, ob Dateien von HuggingFace abrufbar sind

Oben rechts:

- `+ Neu`: leeres Profil anlegen
- `Importieren`: Profil aus JSON erstellen (Upload / Paste)

## 3. Formularansicht (Form)

Das Formular besteht aus 5 Accordion-Sektionen.

### 3.1 Metadata

- `id`: Profilkennung (kann später nicht geändert werden)
- `Anzeigename`: Name in der Liste
- `profile_version`: Schema-Version (meist unverändert lassen)

### 3.2 Model & Files

- `model_id`: HuggingFace Model-ID (z. B. `SmilingWolf/wd-swinv2-tagger-v3`)
- `adapter_family`, `backend`, `hf_subdir`: nur bei Bedarf
- `Dateien`:
  - `name`: Dateiname (z. B. `model.onnx`)
  - `Erforderlich`: bei Test als Pflichtdatei behandeln
  - `size_hint_mb`: optionaler Größenhinweis
  - `+ Datei hinzufügen` / `Entfernen`: Zeilen hinzufügen/entfernen

### 3.3 Tag source

Quelle für Tag-Definitionen.

- `csv`: Datei(file), Trennzeichen(delimiter), Namensspalte(name_col), Kategoriespalte(category_col), Kategoriezuordnung(category_map)
- `json_list`: Datei(file), Schema(schema)
- `json_dict`: Datei(file), Zuordnung(mapping)
- `composite`: Quellen(sources) kombinieren

### 3.4 Threshold source

Quelle für Schwellwerte.

- `global_per_category`: Schwellwerte pro Kategorie direkt im UI setzen
- `per_tag`: Datei + Fallback
  - Datei(file)
  - Fallback-Modus(fallback.mode): `global` / `category_default`
  - Fallback-Wert(fallback.value)

### 3.5 Preprocess & Categories

- Vorverarbeitung(`preprocess_spec`): `input_size`, `dtype`, `layout`, `channel_order`, `resize_strategy` (`letterbox` / `longest_side_pad` / `stretch`), `scale`, `mean`, `std`
- Kategorien:
  - `Unterstützte Kategorien`
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. Import / Export

### 4.1 Importieren

`Importieren` öffnet zwei Tabs:

- JSON hochladen: `.json` Datei hochladen
- JSON einfügen: JSON in das Textfeld einfügen

Danach öffnet sich das Formular. Prüfen/anpassen und `Speichern`.

### 4.2 Exportieren

In der Liste `Exportieren`, um das Profil als JSON herunterzuladen.

## 5. Test (Trockenlauf-Download)

- Prüft, ob die in `files` gelisteten Dateien von **HuggingFace** abrufbar sind.
- Erfolg kann als Banner wie `Download OK: {n} Dateien ({total} MB)` erscheinen.
- Bei Fehler zeigt ein Banner die Ursache (nächster Abschnitt).

## 6. Häufige Fehler (kurz)

- `id_conflict`: Benutzerprofil mit derselben `id` existiert bereits
- `id_immutable`: `id` ist unveränderlich (Umbenennen: Duplizieren → Löschen)
- `in_use`: Profil ist aktuell aktiv und kann nicht gelöscht werden
- `validation_failed`: Schema-Validierung fehlgeschlagen (`{detail}` enthält Details)
- `profile_too_large`: Importiertes JSON überschreitet 1MB
- `ssrf_blocked`: Weiterleitung außerhalb von HuggingFace blockiert (SSRF-Schutz)
- `hf_unavailable`: HuggingFace nicht erreichbar/ungültige Antwort
- `timeout`: Zeitüberschreitung (60s)
- `required_missing`: Pflichtdatei fehlt

## 7. Einschränkungen (wichtig)

- Integrierte (`builtin`) Profile sind nicht editier-/löschbar. Verwende `Duplizieren`.
- `id` kann nicht geändert werden. Umbenennen: `Duplizieren` → altes Profil `Löschen`.
- Import-Limit: **1MB**.
- `Test` erlaubt nur HuggingFace-Hosts (SSRF-Allowlist):
  - `huggingface.co`
  - `hf.co`
