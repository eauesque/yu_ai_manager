# LoRA-Trainings-Leitfaden

YU AI Manager + MCP + kohya_ss Vollständiger LoRA-Trainings-Leitfaden per natürlicher Sprache

---

## Einführung

Dieser Leitfaden erklärt den Workflow zur LoRA-Erstellung durch Verknüpfung des MCP-Servers von YU AI Manager mit kohya_ss — alles durch natürliche Sprachanweisungen gesteuert.

Der Großteil des bisherigen LoRA-Erstellungsaufwands lag in der "manuellen Dataset-Vorbereitung". Bildauswahl, Tag-Prüfung und -Ausschluss, Caption-Datei-Formatierung, Ordnerstruktur-Organisation — all das wurde manuell durchgeführt.

Durch MCP-Integration in YU AI Manager ändert sich dieser Workflow. Mit der Anweisung "Erstelle eine LoRA für XXX. Schließe Tags YYY aus" läuft alles von der Materialsammlung über Tagging und Dataset-Generierung bis zum kohya_ss-Start automatisch durch.

---

## Gesamtworkflow

Der LoRA-Erstellungsprozess besteht aus 5 Phasen:

| Phase | Inhalt | Verantwortlich |
|---------|---------|------|
| 1. Material-Vorbereitung | Trainingsbilder sammeln und platzieren | Mensch / KI-Agent |
| 2. Tagging | Automatisches Tagging mit WD-Tagger | MCP (automatisch) |
| 3. Dataset-Generierung | Projekt erstellen, Ausschluss-Tags setzen, exportieren | MCP (automatisch) |
| 4. Training ausführen | Training durch kohya_ss-Aufruf | MCP (automatisch) |
| 5. Verifizierung | Ergebnisse mit SD prüfen | Mensch |

Menschen sind nur an der Entscheidung "was gelernt werden soll" und der abschließenden Ergebnisverifizierung beteiligt.

---

## Voraussetzungen

### Erforderliche Software

- YU AI Manager — inklusive MCP-Server-Funktion
- Claude Desktop oder Claude Code — MCP-Client
- kohya_ss — mit sd-scripts
- Stable Diffusion WebUI (A1111 / ComfyUI / Forge) — für Ergebnisverifizierung

### GPU-Anforderungen

| GPU VRAM | Unterstützte Modelle | Erforderliche Einstellungen |
|---------|----------|-----------|
| 8GB | Nur SD 1.5 praktikabel | `--gradient_checkpointing` erforderlich |
| 12GB | SDXL läuft (mit Einschränkungen) | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL komfortabel | Standardeinstellungen funktionieren |
| 24GB+ | SDXL und FLUX | Fast keine Einschränkungen |

### kohya_ss Verzeichnisstruktur

```
O:\webui\kohya_ss\              ← Für kohya_path gesetztes Hauptverzeichnis
O:\webui\kohya_ss\venv\         ← Python-Virtualumgebung (automatisch erkannt)
O:\webui\kohya_ss\sd-scripts\   ← Trainings-Skripte
```

> ⚠️ **Hinweis**: YU AI Manager erkennt `sd-scripts`-Unterordner und venv automatisch bei Angabe des `kohya_path`-Hauptverzeichnisses. sd-scripts-Pfad nicht direkt angeben.

---

## YU AI Manager konfigurieren

### Extension-Einstellungen

Im Einstellungs-Tab des LoRA Dataset Managers eingeben:

| Einstellung | Beschreibung | Beispiel |
|---------|------|---|
| `kohya_path` | kohya_ss Hauptverzeichnis | `O:\webui\kohya_ss` |
| `output_base_dir` | Dataset-Ausgabe-Basisverzeichnis | `C:\lora_datasets` |
| `checkpoint_dir` | Basis-Modell-Verzeichnis | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | Standard-Modelltyp | `sdxl` |

### WD-Tagger-Konfiguration

Für LoRA-Dataset-Zwecke wird die Kombination mit VLM (llava usw.) nicht empfohlen. VLMs generieren viele Freitext-Tags und verschlechtern die Caption-Qualität.

```
engine_type: "onnx"  ← ONNX allein verwenden
```

> ⚠️ **Hinweis**: Bei `engine_type: "both"` werden VLM-abgeleitete komplexe Tags (wie `wooden_bear_and_fish_sculpture`) generiert. Diese funktionieren nicht als kohya_ss-Captions.

---

## LoRA-Erstellungsschritte per MCP

### Schritt 1: Material-Bilder vorbereiten

Trainingsbilder in Scan Root von YU AI Manager platzieren und scannen.

- Scan Root in YU AI Manager hinzufügen
- Nach Scan-Abschluss in DB registriert
- Mindestens 20–30, empfohlen 50–200 Bilder

### Schritt 2: Tagging mit WD-Tagger

Massen-Tagging per MCP ausführen:

```python
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

Bei vorhandenen Tags zuerst löschen:

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Schritt 3: Projekt erstellen

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # Für kohya_ss Ordnername verwendet
    base_model="sdxl",
    repeat=20
)
```

### Schritt 4: Dateien und Tags konfigurieren

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

Tag-Aggregation prüfen und Ausschluss-Tags bestimmen.

#### Design-Philosophie für Ausschluss-Tags

**Behalten**: Konzept-spezifische Merkmale (Form, Stil, einzigartige Elemente)

**Ausschließen**: Allgemeine Tags, die das Modell bereits kennt (z.B. `no_humans`, `realistic`, `animal`, `solo`, Hintergrundtags)

Beispiel für geschnitzten Bären-LoRA:
- Behalten: `bear`, `fish`, `statue`, `sculpture`, `standing`, `full_body`, `open_mouth`
- Ausschließen: `no_humans`, `animal_focus`, `animal`, `realistic`, `simple_background`, `solo`...

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Schritt 5: Caption-Vorschau prüfen

```python
preview_lora_caption(project_id=N, file_id=beliebige_Datei_ID)
```

Beispielausgabe:
```
"fish, full_body, open_mouth, standing"
```

Sicherstellen, dass einfache Tag-Reihe ohne VLM-Rauschen.

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Schritt 6: Dataset-Export

```python
export_lora_dataset(project_id=N)
```

Ausgabe-Ordnerstruktur:

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← Caption
    image002.jpeg
    image002.txt
```

### Schritt 7: Training ausführen

Zuerst dry run zur Befehlsprüfung:

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="vollständiger_Pfad\checkpoint.safetensors"
)
```

Bei OK Training starten:

```python
start_lora_training(
    project_id=N,
    checkpoint="vollständiger_Pfad\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

Fortschritt prüfen:

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## Standard-Trainings-Parameter

| Parameter | Standardwert | Beschreibung |
|-----------|------------|------|
| `network_dim` | 32 | LoRA-Rang. Größer = mehr Ausdrucksstärke, aber auch größere Datei |
| `network_alpha` | 16 | Normalerweise halb so groß wie dim |
| `learning_rate` | 1e-4 | Lernrate |
| `max_train_epochs` | 10 | Epochen-Anzahl |
| `save_every_n_epochs` | 2 | Zwischenspeicherungsintervall |
| `mixed_precision` | fp16 | Präzision |
| `resolution` | 1024,1024 (SDXL) | Trainingsauflösung |

---

## GPU-spezifische empfohlene Einstellungen

| GPU VRAM | Empfohlene extra_args |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | (Standard) |
| 24GB+ | (Standard, batch_size kann erhöht werden) |

---

## Empfohlene Schritt-Anzahl und Epochen

**Gesamt-Trainingsschritte = Bildanzahl × Wiederholungen × Epochen**

| Konzeptkomplexität | Empfohlene Schrittanzahl | Beispiel (50 Bilder) |
|------------|-------------|--------------|
| Einfaches Objekt / Stil | 1.000–3.000 | repeat=10, epoch=5 |
| Charakter / Skulptur | 3.000–8.000 | repeat=20, epoch=5 |
| Komplexer Stil / Person | 5.000–15.000 | repeat=20, epoch=10 |

---

## Fehlerbehebung

### ModuleNotFoundError: No module named 'torch'

**Ursache**: Versuche kohya_ss-Skripte in YU AI Manager's venv auszuführen.

**Lösung**: `kohya_path` auf Hauptverzeichnis (Elternordner von sd-scripts) setzen.

---

### torch.OutOfMemoryError: CUDA out of memory

**Ursache**: VRAM unzureichend.

**Lösung**: Zu `extra_args` hinzufügen:
```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### VLM-Rauschen in Tags

**Ursache**: `engine_type` ist `"both"`.

**Lösung**: WD-Tagger-Einstellung auf `engine_type="onnx"` ändern und Tags neu erstellen:

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

## Generations-Prompts

### Basis-Prompt-Aufbau

```
{concept_token}, {Merkmals-Tags}, <lora:{lora_name}:{strength}>
```

Beispiel für geschnitzter Bären-LoRA:

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

### LoRA-Stärke anpassen

| Stärke | Eigenschaften |
|-----|------|
| 0,5–0,6 | Basis-Modell-Einfluss stark |
| 0,7–0,8 | Empfohlener Bereich. Balance zwischen LoRA und Basis-Modell |
| 0,9–1,0 | LoRA-Einfluss stark. Form kommt raus, aber Farbe tendiert zu weiß/creme |

---

## Zusammenfassung

Durch den YU AI Manager + MCP + kohya_ss-Workflow kann der LoRA-Erstellungsaufwand erheblich reduziert werden.

- Von Material-Bildern bis zum vollständigen Training über alle Epochen mit nur MCP-Anweisungen
- Gesamter Workflow per natürlicher Sprache gesteuert

Die verbleibende Herausforderung ist nur die Automatisierung der Material-Sammlung — durch Kombination mit Claude in Chrome usw. ist vollständige Automatisierung in Sicht.
