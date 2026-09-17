# HailoRT 5.3.0 CMA-Speicherleck — Bestätigte Diagnose und Betriebseinschränkungen

> **Korrekturhinweis**: Dieses Dokument ist ein Diagnoseprotokoll des CMA-Leaks, das auf der alten Messung beruht; die alten Schlussfolgerungen — dass CMA auch nach `release()` nicht zurückgewonnen wird, dass es während der Inferenz kontinuierlich mit ca. 14 MB/Minute leckt, und dass allein der Neustart des Pi selbst ein zuverlässiges Wiederherstellungsmittel ist — sind widerrufen. Die endgültige Beurteilung nach dem Retest mit HailoRT/driver 5.4.0 ist in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 korrigiert. Die alten Schlussfolgerungen dieses Dokuments dürfen nicht als aktuelle praktische Beurteilung herangezogen werden.

**Erstellt**: 2026-05-17 (entdeckt und dokumentiert in v4.214.11)
**Betroffener Bereich**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (über `hailo_platform.genai`-Pfad)
**Symptom**: Sobald ein LLM geladen wird, wird CMA nach dem Aufruf von `VDevice.release()` / `LLM.release()` kaum zurückgewonnen. Außerdem leckt CMA während der Inferenz kontinuierlich. Es gibt keine Wiederherstellungsmöglichkeit außer einem Neustart des Pi.
**Status**: Als strukturelle Einschränkung auf Treiberseite bestätigt. Umgehungslösungen werden untersucht.

---

## 1. Grundlage der bestätigten Diagnose

Mit dem in `v4.214.10` eingeführten CMA-Ereignis-Logger (`logs/hailo_cma.log`, `core/hailo_device_core/device_helpers.py::log_hailo_cma_event`) wurde am 2026-05-17 folgende Sequenz gemessen.

### 1-1. Beobachtungsprotokoll (raw)

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 Minuten Chat-Nutzung (ca. 5–10 Nachrichten Inferenz)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. Interpretation

| Phase | CmaFree-Differenz | Bedeutung |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB (≈ 0)** | VDevice-Erstellung selbst verbraucht kaum CMA |
| `acquire_pre` → `acquire_post` (Qwen3-1.7B-Instruct laden) | **−285 MB** | 1 LLM verbraucht 285 MB |
| `acquire_post` → `release_pre` (6 Minuten Inferenz) | **−84 MB / 6 min ≒ −14 MB/min** | **Kontinuierliches Leck auch während der Inferenz** |
| `release_pre` → `release_post` (LLM entladen) | **+1 MB** | **`release()` gibt faktisch kein CMA zurück** |

### 1-3. Vergleich mit früherer Hypothese

Dies ist ein Messergebnis, das die in `SQLCIPHER_MMAP_CORRUPTION.md` §7 vom 2026-05-16 und in alten Dokumenten enthaltene Anfangshypothese „Die VDevice-Haltestrategie (unser leeres `_maybe_reset_vdevice`) verstärkt das Leck" teilweise widerlegt. Da VDevice-Erstellung 0 MB / Release 0 MB beträgt, **würde eine Änderung der Haltestrategie (= `_maybe_reset_vdevice` bei jedem Aufruf zurücksetzen) keinen Effekt haben**.

---

## 2. Strukturelle Einschränkungen

Basierend auf den Messergebnissen weist HailoRT 5.3.0 (Community-Build, `hailo_platform.genai` API) drei gleichzeitig auftretende Probleme auf:

1. **`VDevice.release()` / GenAI-Modell `release()` gibt Host-CMA nicht zurück** (durch Messung bestätigt)
   - Innerhalb eines einzelnen Prozesses hält der PCIe-Treiber (`hailo1x_pci`) DMA-Bereiche weiterhin, und es findet kein `munmap`-äquivalenter Vorgang statt
2. **Kontinuierliches CMA-Leck während der Inferenz (ca. 14 MB/min)** (durch Messung bestätigt)
   - Heutige Beobachtung: 84 MB innerhalb von 6 Minuten Nutzung von Qwen3-1.7B-Instruct verloren
   - Ein separater Pfad unabhängig von Laden/Entladen. Erschöpfung tritt auch ohne Entladen auf
3. **Keine bestätigte Methode außer Pi-Neustart, um CMA zuverlässig zurückzugewinnen** (Messung + Community-Berichte)
   - Selbst ein Neustart des Serverprozesses (entspricht `systemctl restart yu-ai-manager`) ist unvollständig, da `hailo1x_pci` DMA bis zum PCIe-Power-Cycle hält. Vollständige Wiederherstellung erfordert `sudo reboot` des Pi (in diesem Repository gemessen)
   - In der Hailo-Community existieren mehrere unabhängige Berichte: <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> und <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (wird ausdrücklich dargelegt, dass `VDevice.release()` / Prozessbeendigung / Treiber-Reload nicht wiederherstellt, nur Host-Neustart)
   - Dies ist bereits in der Vorab-Ablehnungsfehlermeldung von `acquire_genai` für Benutzer dokumentiert (`core/hailo_device_core/device_manager_genai.py::acquire_genai`, "a full system reboot is required")

### 2-1. „Gibt das Beenden eines Kindprozesses CMA zurück?": **Durch Messung widerlegt** (2026-05-17 Phase 0 PoC)

Die frühere Version (rev1) kam theoretisch zu dem Schluss, dass „der Linux-Kernel DMA-Seiten beim `mm_struct`-Teardown zurückfordert, sodass das Beenden eines Kindprozesses CMA vollständig zurückgewinnt", aber **die Messung mit Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`) bestätigte zweimal unabhängig, dass das Beenden eines Kindprozesses CMA kaum zurückgewinnt**.

**Messergebnisse (2. Durchgang, strenge Version)**:

| Messpunkt | CmaFree | Δ |
|---|---:|---:|
| Ausgangslinie (vor PoC-Start) | 503 MB | — |
| Nach VDevice-Erstellung | 372 MB | **-131 MB** (VDevice-Konstruktion verbraucht CMA bei Cold-Spawn-Kindprozess) |
| Nach LLM-Laden | 372 MB | 0 MB (LLM ist im VDevice-DMA-Pool enthalten, kein neuer Verbrauch) |
| Nach SIGTERM + Join | 378 MB | +6 MB |
| **Nach 30 Sekunden Wartezeit** | **380 MB** | **Nur +8 MB insgesamt zurückgewonnen** |

Gegen einen erwarteten Rückgewinn von ≥250 MB betrug der tatsächliche Messwert nur +8 MB (+1 MB beim ersten zufälligen Messdurchgang). Dies liegt auf dem Niveau von System-Jitter — **es fand keine signifikante CMA-Rückgewinnung statt**.

**Bestätigte Diagnose**:

- Der `hailo1x_pci`-Treiber verwaltet den DMA-Pool im **internen globalen Treiberzustand** und nicht im `mm_struct` des Benutzerprozesses (geschätzt)
- Keine Rückgewinnung durch `process exit`, `kill` oder `module unload` (konsistent mit Community-Berichten)
- **Die einzige bestätigte Wiederherstellungsmethode ist `sudo reboot` des Pi (= PCIe-Power-Cycle)** ← dies ist die in §2 Zeile 3 genannte gemessene Tatsache

Detaillierter Bericht: `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

Aufgrund dieser Ergebnisse wird `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` als **REJECTED** markiert, und der Abschwächungsansatz durch Subprocess-Isolation wird aufgegeben. Der automatische Neustart-Ansatz aus §4 (D) wird als Alternative übernommen.

---

## 3. Betriebliche Auswirkungen

### 3-1. „1 Modell pro Pi-Neustart" ist faktisch das Limit

- Mit Pi 5 (CMA-Limit 512 MB, gemäß Pi-Spezifikation nicht erhöhbar) + Qwen3 LLM (285 MB):
    - CmaFree unmittelbar nach Neustart ≒ 480 MB
    - Nach Laden von 1 LLM → CmaFree ≒ 190 MB
    - Nach einigen Dutzend Minuten Inferenz → CmaFree ≒ 50 MB oder weniger
    - **Das Laden eines zweiten Modells ist dauerhaft unmöglich** (benötigt 250+ MB, aber Restmenge unzureichend, und Release gibt nichts zurück)

### 3-2. Gleichzeitige Nutzung von LLM + VLM / LLM + S2T nicht möglich

- Anwendungsfälle, bei denen zwischen VLM (llava-basiert, ~300 MB), S2T (whisper-small, ~175 MB) und LLM gewechselt wird, sind aufgrund der obigen Einschränkungen unmöglich, es sei denn, die Prozedur **Laden → Neustart → Laden** wird eingehalten.
- **Multi-Modell-UX wie „Bild während der Konversation anhängen und zu einem anderen Modell wechseln" oder „Konversationsaudio transkribieren" ist mit HailoRT 5.3.0 konzeptionell nicht realisierbar**.

### 3-3. Lange kontinuierliche Inferenz-Sitzungen sind schwierig

- Das Leck von 14 MB/min bedeutet, dass selbst bei 200 MB CmaFree nach 14 Minuten die Hälfte und nach 30 Minuten nahezu alles erschöpft ist.
- Chat-Sitzungen von mehr als 30 Minuten können ohne zwischengeschalteten Pi-Neustart nicht stabilisiert werden.

---

## 4. Mögliche Gegenmaßnahmen

Mit Priorität und Aufwand aufgelistet:

| Option | Wirkung | Aufwand | Nebeneffekte / Risiken |
|---|---|---|---|
| ~~(A) Hailo-Operationen in Subprocess isolieren, periodisch beenden, damit Kernel CMA zurückerhält~~ | ❌ **REJECTED** (durch Phase 0 PoC widerlegt, 2-mal reproduziert). Rückgewinnung nach Kill nur +8 MB insgesamt — Hypothese widerlegt | — | Nicht übernommen |
| **(B) `_CMA_ESTIMATES_MB` auf gemessene Werte + Puffer aktualisieren** | Verbessert Genauigkeit der Vorab-Ablehnung (reduziert falsch-positive Ladeversuche) | ✅ Sofort anwendbar, 1 Zeile | Fälle, die mit 250-MB-Annahme gerade noch funktionierten, werden abgelehnt, aber diese scheiterten ohnehin |
| **(C) UI-Banner bei `CmaFree < 80 MB` / WARN in error.log bei `< 30 MB`** | Benutzer können die Situation verstehen, Pi-Neustart wird empfohlen | Mittel | Risiko von Warnmüdigkeit / übermäßigen Benachrichtigungen |
| **(D) SIGTERM an Supervisor senden wenn `CmaFree < 30 MB` erkannt** | Automatische Wiederherstellung (da Pi-Gesamtneustart erforderlich, über `systemctl reboot`) | Mittel | Supervisor-Berechtigungen erforderlich / Sitzungsunterbrechung während anderer Arbeiten |
| **(E) Auf HailoRT-Fix warten + Einschränkungen klar dokumentieren** | Kosten 0 | 0 | Abhängig vom Hailo-Release-Zyklus (Monate+) |
| **(F) Fix-Anfrage an Hailos Issue-Tracker / Forum senden** | Möglicherweise frühere Behebung | Klein | Reaktionsgeschwindigkeit hängt von Supportvertrag und Community-Status ab |

Kurzfristige Richtlinie (in v4.214.11 umgesetzt): **(B) anwenden + dieses Dokument (Ausgangspunkt für E und F)**.
Mittelfristige Richtlinie (separate Spec): Reihenfolge **(C) UI-Warnung → (A) Subprocess-Isolation** prüfen.
Langfristig: HailoRT-Releases überwachen und dieses Dokument bei Behebung aktualisieren, um die Einschränkungen aufzuheben.

---

## 5. Verwandte Dokumente / Code

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — Vorab-CmaFree-Prüfung + benutzerseitige Fehlermeldung legt diese Einschränkung explizit dar
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — CMA-Bedarfsschätzungen pro Modell (qwen in v4.214.11 von 250 → 300 erhöht)
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — Messinstrumentierung eingeführt in v4.214.10. Messdaten in diesem Dokument stammen von hier
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — Design, das VDevice für die Prozesslebensdauer hält (leere Funktion). Diese Messung bestätigt, dass eine Änderung zum Zurücksetzen keinen Beitrag zur CMA-Rückgewinnung leisten würde
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Operator-Leitfaden für Phase 0.5 Beobachtungsphase. Verfahren zum Sammeln nur von `would_fire`-Protokollen mit `mode=lazy` + `dry_run=true`
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — CMA-Gesamtlimit des Pi5 und Basisverbrauch der einzelnen Treiber (camera / KMS / Hailo / HEVC)
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — Hintergrund der Migration zu HailoRT 5.3.0 und bekannte Unterschiede

---

## 6. Reproduktionsschritte (für Hailo-Issue-Berichte)

Minimale Reproduktionsschritte für externe Bug-Berichte:

```bash
# 1. Ausgangslinie unmittelbar nach Pi-Neustart prüfen
grep CmaFree /proc/meminfo
# CmaFree: ~480000 kB

# 2. Server starten + 1. LLM laden (z.B. 1 Nachricht über GenAI in /tools senden)
# 1 Anfrage an /api/llm/generate oder /api/chat/send

# 3. CmaFree prüfen
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. Modell entladen
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. CmaFree prüfen
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (nicht zurückgegeben ← Bug)

# 6. Versuch, dasselbe / ein anderes Modell erneut zu laden → abgelehnt wegen unzureichendem CMA
```

Erwartetes Verhalten: In Schritt 5 sollte CmaFree auf einen Wert nahe der Ausgangslinie aus Schritt 1 zurückkehren (>400 MB).
Tatsächliches Verhalten: Nur etwa +1 MB zurückgegeben, Nachladen ist unmöglich.
