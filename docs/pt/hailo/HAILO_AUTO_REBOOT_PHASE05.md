# Guia de operações Hailo Auto-Reboot Phase 0.5

**Criado**: 2026-05-17 (v4.215.0)
**Alvo**: Operações de observação de CMA leak no Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0
**Status**: Fase de observação. Nenhuma reinicialização real é realizada; apenas os eventos `would_fire` são registados.

---

## 1. Propósito da Phase 0.5

A Phase 0.5 é a fase de observação do design de reinicialização automática contra CMA leaks no HailoRT 5.3.0 + `hailo1x_pci`.

Nesta fase, a máquina de estados calcula os seguintes estados:

| Estado | Condição |
|---|---|
| `idle` | Estado normal |
| `prewarn` | `CmaFree < 80 MB` persiste por 180 segundos |
| `draining` | `CmaFree < 30 MB` persiste por 60 segundos, ou o pré-rejeição de `acquire_genai` ocorre 3 vezes consecutivas |
| `would_fire` | 120 segundos decorridos desde `draining` |

Importante: Na Phase 0.5, mesmo que `would_fire` seja atingido, o Pi NÃO é reinicializado. O evento é apenas registado como JSON Lines em `logs/hailo_auto_reboot.log`.

---

## 2. Por que o valor padrão é `mode = "off"`

O valor padrão de `hailo.auto_reboot.mode` é `"off"`. Como a reinicialização automática pode interromper o trabalho do operador, a observação só é iniciada em ambientes onde o operador optou explicitamente por participar (opt-in).

A configuração recomendada para a Phase 0.5 é a seguinte:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` é um pré-requisito para a Phase 0.5. O caminho de reinicialização real é tratado na Phase 4 e posteriores.

### 2.1 Procedimento de opt-in

A configuração de inicialização prioriza o ficheiro especificado via `--config` ou `TAGDB_CONFIG`. Se não especificado, lê `config.json` no diretório raiz do repositório, depois `tagdb_config.json`.

Exemplo:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

Adicione as seguintes configurações ao `<repo>/config.json` ou ao ficheiro JSON especificado via `--config` / `TAGDB_CONFIG` durante a operação:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

Reinicie o servidor para aplicar a configuração. Mantenha os argumentos que está a utilizar de acordo com o seu método de inicialização.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

Se operar com systemd, reinicie a unidade correspondente:

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 Procedimento de desativação

Defina `hailo.auto_reboot.mode` como `"off"` na mesma configuração e reinicie o servidor.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

Com `mode = "off"`, os eventos de observação JSON Lines são preservados, mas nenhum resumo WARN é emitido para `error.log`.

---

## 3. Como ler os registos

Os registos de observação são escritos no seguinte ficheiro:

```text
logs/hailo_auto_reboot.log
```

O formato é JSON Lines. Os principais eventos são os seguintes:

| Evento | Significado |
|---|---|
| `boot_baseline` | Ponto de início de observação no arranque |
| `prewarn_entered` | Condição PREWARN satisfeita |
| `drain_entered` | Condição DRAIN satisfeita |
| `would_fire` | Ponto que se tornaria um gatilho de reinicialização na Phase 1+ |
| `drain_cleared` | CMA recuperado e DRAIN eliminado |

Exemplo:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

Exemplos de comandos de verificação:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

Se `would_fire` ocorrer com frequência, indica que com os limiares atuais é muito provável que seja necessária uma reinicialização do Pi durante a operação real. Pelo contrário, se apenas `prewarn_entered` aparecer sem progredir para `drain_entered`, os limiares ou os tempos de tolerância podem ser reajustados antes da Phase 1.

---

## 4. Procedimento de verificação da API

Verifique `/api/system/cma` com a chave de API de administrador.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

Examine `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state` e `cma.auto_reboot.consecutive_rejects` na resposta.

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. Período de observação

O objetivo é de 1 a 2 semanas. Garanta que o período cubra pelo menos os seguintes padrões:

- Utilização normal de chat com LLM
- Utilização prolongada de chat
- Operações que causem falhas de carregamento do modelo Hailo GenAI ou pré-rejeições
- Primeiro carregamento após reinicialização do Pi

A observação considera-se completa quando os dados de frequência de `prewarn_entered` / `drain_entered` / `would_fire` ao longo de 1 a 2 semanas puderem ser agregados. Após a observação, reveja o número de ocorrências de `would_fire`, o motivo de `drain_entered` (`cma` / `rejects`) e a taxa de diminuição de `CmaFree` para finalizar os limiares antes de implementar a Phase 1.

Exemplo de agregação:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. Documentos relacionados

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
