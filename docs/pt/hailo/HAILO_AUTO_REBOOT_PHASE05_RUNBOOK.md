# Hailo Auto-Reboot Phase 0.5 — Manual de operações para este ambiente

**Criado**: 2026-05-17 (v4.215.1)
**Ambiente alvo**: — Pi 5 a executar este repositório
**Propósito**: Um manual autónomo que permite iniciar, verificar e concluir a observação da Fase 0.5, mesmo que a sessão de chat original seja perdida.
**Especificação de projeto**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**Guia geral do operador**: `docs/pt/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (este documento é a variante específica do ambiente)

---

## 0. Pré-requisitos e trabalhos já concluídos

- A implementação da observação da Fase 0.5 foi integrada e enviada para main na v4.215.1 (commit `80af4fb73` + merge `69be148c6`)
- `config.json` (raiz do repositório) já contém o bloco `hailo.auto_reboot`, **adicionado em 2026-05-17**
  - Definições recomendadas: `mode = "lazy"` + `dry_run = true`
  - Cópia de segurança: `config.json.bak.<timestamp>`
- **Nenhum reinício real será acionado** (`dry_run = true` + o design da Fase 0.5 apenas regista eventos `would_fire`)

Verificar config.json:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → Deve aparecer {"mode":"lazy","dry_run":true,...}
```

---

## 1. Procedimento de primeiro arranque e ativação

### 1.1 Reinício do servidor

É necessário reiniciar para aplicar a alteração de configuração. **Reinicie utilizando o mesmo método de arranque atualmente em uso.**

Comando de arranque típico (a ajustar ao ambiente real):

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

Se estiver a correr como serviço systemd, reiniciar a unidade correspondente com `sudo systemctl restart <unit>`.

### 1.2 Verificação nos primeiros 30 segundos após o arranque (3 pontos)

#### A. O evento `boot_baseline` está registado?

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

Esperado: uma linha contendo `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`.

**Resolução de problemas caso não esteja presente**:

- `logs/hailo_auto_reboot.log` não existe → o ciclo judge não está em execução (possivelmente não iniciado em modo `["full"]` ou a variável de ambiente `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` está definida)
- O ficheiro existe mas está vazio → falha na resolução de caminho em `core/hailo_device_core/auto_reboot_logger.py`; verificar permissões do diretório `logs/`
- `cma_free_mb: null` → falha na leitura de `/proc/meminfo` (comportamento esperado em hardware que não seja Pi, inofensivo)

#### B. O opt-in está ativo através da resposta `/api/system/cma`?

Se tiver sessão iniciada com PIN no navegador, não é necessária nenhuma chave API. Utilizar curl ou executar na consola DevTools do navegador (com sessão PIN ativa):

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

Esperado:

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

Se `enabled: false` ou `mode: "off"` → verificar se `hailo.auto_reboot.mode` em config.json é `"lazy"` e se o servidor reiniciou completamente.

#### C. Não há erros de arranque em `error.log`?

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

Sem saída significa OK. Se houver erros, consultar «8. Armadilhas conhecidas» no final deste documento.

---

## 2. Operações diárias durante o período de observação

### 2.1 Utilização normal

**Ação principal**:

- **Utilizar o chat LLM como habitualmente** através de `/ext/hailo-genai/chat` ou `/tools` (p. ex., Qwen3-1.7B)
- Usar VLM / S2T conforme necessário
- Sessões longas (30+ minutos contínuos) e múltiplas trocas de modelo também valem a pena ser tentadas intencionalmente para alargar os dados de observação

Não são necessários testes especiais. **Quanto mais se usa normalmente, mais dados a Fase 0.5 recolhe** — esse é o objetivo do design.

### 2.2 Revisão semanal (uma vez por semana, ~5 minutos)

```bash
cd /home/pi/GitHub/yu_ai_manager

# Contagem de cada tipo de evento
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# Timestamps e CmaFree para eventos would_fire
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# Motivo de drain_entered (cma ou rejects)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**Pontos de verificação**:

- `would_fire` ocorre 1 ou mais vezes → a introdução da Fase 1 tem valor (verificar se os timestamps registados coincidem com os reinícios manuais efetuados)
- `prewarn_entered` dispara frequentemente mas nunca progride para `drain_entered` → `prewarn_threshold_mb` (80 MB) pode ser demasiado baixo; recalibrar
- O motivo de `drain_entered` é sempre `rejects` → o DRAIN é impulsionado por rejeições; são necessárias medidas diferentes do ajuste de limiar

---

## 3. Fim da observação e critérios de decisão para a Fase 1

### 3.1 Período de observação necessário

**Mínimo 7 dias / Recomendado 14 dias**. O período deve cobrir pelo menos os seguintes padrões:

- Chat LLM normal
- Chat LLM longo (30+ minutos numa única sessão)
- Troca de modelos VLM / S2T
- Pelo menos uma rejeição prévia de `acquire_genai` (CmaFree insuficiente)
- Primeiro carregamento após reinício do Pi

### 3.2 Critérios numéricos para introdução da Fase 1

Agregação:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

Tabela de decisão:

| Resultado da observação | Decisão Fase 1 |
|---|---|
| `would_fire` ≥ 1 | **GO** (a automatização do reinício tem valor) |
| `would_fire` = 0, `drain_entered` ≥ 1 | Reajustar limiares e considerar a Fase 1 (DRAIN é atingido mas `would_fire` não — `fire_grace_seconds` pode ser reduzido) |
| Apenas `prewarn_entered`, `drain_entered` = 0 | O limiar atual nunca atinge o estado «crítico» → a Fase 1 pode não ser necessária dependendo dos padrões de uso |
| Todos os eventos a 0 (apenas `boot_baseline`) | O uso não esgota a CMA → Fase 1 não necessária |

### 3.3 Tarefas pós-observação

1. Guardar os resultados agregados em `docs/pt/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (novo ficheiro)
2. Em caso de introdução da Fase 1: avançar para a Fase 1 na especificação rev3 §5.2 (banner DRAIN na interface + i18n); reconfirmar os limiares de §3.1 com base nos dados de observação
3. Se a Fase 1 não for necessária: definir `mode = "off"` em config.json e arquivar o registo de observação

---

## 4. Procedimento de desativação (emergência / paragem da observação)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# Reiniciar o servidor
```

Mesmo com `mode = "off"`, os eventos JSONL continuam a ser registados (a saída WARN para `error.log` é suprimida). Para desativar completamente, utilizar a variável de ambiente:

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. Referência de ficheiros de registo (ficheiros relacionados)

| Ficheiro | Função |
|---|---|
| `logs/hailo_auto_reboot.log` | **Registo principal desta funcionalidade**. Formato JSONL; rotação a 10 MB × 30 cópias de segurança |
| `logs/hailo_cma.log` | Registador de eventos CMA existente (desde v4.214.10). Regista eventos de ciclo de vida de VDevice/modelo como `acquire_genai` |
| `logs/error.log` | Registo de erros global da aplicação. Quando `mode != "off"`, também gera resumos WARN para `drain_entered` / `would_fire` |

---

## 6. Localizações do código relacionado (para investigações futuras)

| Funcionalidade | Ficheiro |
|---|---|
| Máquina de estados + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| Ponto de entrada do ciclo em segundo plano | `core/web/startup_background_hailo_judge.py` |
| Registo de tarefas em segundo plano | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Valores predefinidos de configuração | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| Hook acquire_genai | `core/hailo_device_core/device_manager_genai.py` |
| Extensão `/api/system/cma` | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| Testes unitários | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. Histórico de revisão (referência)

Esta implementação passou pelo processo de revisão completo do AGENTS (ver a mensagem do commit v4.215.1). Os ficheiros de relatório individuais foram escritos em `.claude/agent-outputs/`, que está em `.gitignore` e não é gerido pelo git. Podem ser regenerados se necessário.

---

## 8. Armadilhas conhecidas

| Sintoma | Causa e remédio |
|---|---|
| Nada aparece em `logs/hailo_auto_reboot.log` | Servidor não reiniciado / `mode = "off"` ainda definido / não iniciado em modo `["full"]` / variável de ambiente `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` definida |
| `cma_free_mb: null` persiste | A correr em hardware que não é Pi (p. ex., WSL2) ou falha na leitura de `/proc/meminfo`; verificar no hardware Pi real |
| `hailo_runtime_version: null` | O pacote `hailo_platform` não está instalado neste ambiente; num Pi 5 real, o valor é preenchido se o HailoRT 5.3.0 estiver instalado |
| `would_fire` nunca aparece | A carga de uso é demasiado leve ou os limiares são demasiado permissivos; tentar chats longos contínuos / trocas de modelo e rever |
| O modo `eager` está configurado mas não funciona | Na Fase 0.5, `eager` reverte intencionalmente para `off` (com um registo de aviso); previsto para implementação na Fase 1+ |

---

## 9. Reversão de emergência

No caso improvável de a implementação da Fase 0.5 ter um problema (baixa probabilidade uma vez que não são acionados reinícios reais):

```bash
cd /home/pi/GitHub/yu_ai_manager
# Reverter de v4.215.1 para v4.214.13 (apenas especificação, antes da implementação)
git revert -m 1 69be148c6
git push
```

Ou **desativação completa apenas via configuração** (recomendado):

```bash
# Adicionar ao ambiente de arranque e reiniciar o servidor
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. Manutenção deste documento

- Quando a observação estiver concluída, **acrescentar o resumo de §3.3 ao final deste documento** (necessário para a decisão da Fase 1 em futuras sessões de chat)
- Após a introdução da Fase 1, renomear este documento para `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` e criar um novo manual para a Fase 1
- Este documento reside em `/home/pi/GitHub/yu_ai_manager/docs/pt/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` (gerido pelo git)
