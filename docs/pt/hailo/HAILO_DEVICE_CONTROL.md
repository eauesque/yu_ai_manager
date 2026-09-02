# Controle de Dispositivo Hailo-10H

## Visão Geral

A NPU Hailo-10H pode **executar vários modelos simultaneamente**.
O scheduler ROUND_ROBIN embutido divide automaticamente o acesso de hardware entre os modelos por time-slicing.

O yu_ai_manager mantém um único VDevice compartilhado, permitindo que CLIP, YOLO, LLM, VLM e Speech2Text sejam carregados e inferidos simultaneamente. O compartilhamento com processos externos (hailo-ollama) também é suportado via `group_id`.

## Arquitetura

```
┌─────────────────────────────────────────────┐
│              Shared VDevice                  │
│         (group_id = YU_SHARED)               │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │  CLIP   │ │  YOLO   │ │  LLM (GenAI)  │  │
│  │InferMdl │ │InferMdl │ │  VLM / S2T    │  │
│  └─────────┘ └─────────┘ └───────────────┘  │
│                                              │
│     HailoRT ROUND_ROBIN Scheduler            │
└─────────────────────────────────────────────┘
```

- API InferModel (CLIP, YOLO) e API GenAI (LLM, VLM, S2T) coexistem no mesmo VDevice
- Todos os modelos precisam ser criados na **mesma instância VDevice** (não funciona com instâncias separadas)

## Comparação dos Dois Modos

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (compatível com OpenAI) |
|---|---|---|
| Gerenciamento de dispositivo | device_manager do yu | Servidor C++ externo |
| Coexistência com pesquisa CLIP | Sim (operação simultânea) | Sim (group_id compartilhado, v5.3.0+) |
| Velocidade de inferência | Igual | Igual |
| Overhead | ~15ms | ~200-400ms (base64+HTTP) |
| Múltiplos clientes | Não | Possível |
| Thread Flask | Bloqueia durante inferência | Apenas aguarda HTTP |

## Compartilhamento VDevice (group_id)

### Compartilhamento Intra-Processo

`device_manager.py` gerencia automaticamente. Todos os modelos compartilham o mesmo VDevice.

O group_id pode ser alterado via variável de ambiente:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

Padrão: `YU_SHARED`

### Coexistência com hailo-ollama (v5.3.0+)

O hailo-ollama v5.3.0 ou posterior suporta a variável de ambiente `HAILO_OLLAMA_VDEVICE_GROUP_ID`.
Configurar o mesmo group_id que o yu_ai_manager permite que ambos os processos compartilhem o dispositivo:

```bash
# Lado yu_ai_manager
export HAILO_VDEVICE_GROUP_ID=SHARED

# Lado hailo-ollama
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**Nota**: No yu_ai_manager, group_id funciona com HailoRT 5.2.0 ou posterior.
O hailo-ollama não aceita group_id com versões anteriores ao v5.3.0.

## API do device_manager

### Obtenção de Modelos

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- Mesmo owner + mesmo HEF → reutiliza sessão existente
- Mesmo owner + HEF diferente → libera modelo antigo e cria novo
- Owner diferente → **coexistência** (modelo antigo não é liberado)

### Liberação de Modelos

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # Libera apenas CLIP, outros continuam
shutdown_all()            # Libera todos os modelos + VDevice (ao sair do processo)
```

### Verificação de Status

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## Resolução de Problemas

### Erro ao Criar VDevice

**Sintoma**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` ou `Failed to create VDevice`

**Causa**: Outro processo está ocupando o dispositivo com um group_id diferente

**Solução**:
1. Verificar se hailo-ollama está em execução:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. Alinhar o group_id ou parar o processo:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### Dispositivo Não É Liberado

**Solução**:
1. Reiniciar o processo do yu
2. Verificar processos zumbi:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Resetar o driver Hailo:
   ```bash
   sudo systemctl restart hailort.service
   ```

## Guia de Seleção de API

| Estrutura do Modelo | API Recomendada | Motivo |
|---|---|---|
| Simples (1 entrada, YOLO, etc.) | `InferModel` | Funciona com `create_infer_model()` + `configure()` |
| Complexo (2+ entradas, Whisper, etc.) | `GenAI SDK` | InferModel retorna `INVALID_ARGUMENT` |
| Encoder CLIP | `InferModel` | Sem problemas com 1 entrada/1 saída |
| LLM (qwen2.5, etc.) | `GenAI SDK` | Requer decodificação autorregressiva |

## Histórico

- **v4.61.0**: Migração para modo VDevice compartilhado. Abolido acquire/release exclusivo, suportando operação simultânea de CLIP + YOLO + LLM.
- **v4.60.1**: Todos os consumidores unificados via device_manager (modo exclusivo).
- **Antes do v4.60.0**: Cada consumidor chamava VDevice() individualmente, causando erros de conflito frequentes.
