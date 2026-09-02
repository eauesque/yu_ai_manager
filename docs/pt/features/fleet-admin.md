# Gerenciamento de Frota (Fleet Admin)

O recurso Fleet Admin do LAN Cowork permite gerenciar vários nós yu-ai-manager na rede a partir de um ponto central.

## Visão Geral

- **Coleta de Informações de Máquina**: Agregue CPU / RAM / GPU / Disco / Versão / Tempo de atividade de cada nó para o centro
- **Visualização de Log Remoto**: Transmita ao vivo logs de qualquer peer na interface central via SSE
- **Distribuição de Atualização de Versão**: Instrua pares especificados a executar `git pull --ff-only` + graceful restart a partir do centro

## Pré-requisitos

- A extensão LAN Cowork está habilitada (`extensions["builtin-lan-cowork"].enabled = true`)
- O pareamento entre pares foi concluído
- Clone como repositório git (se usar recurso de atualização)
- `psutil>=5.9` está instalado no ambiente virtual Python

## Configuração

### Configuração do Nó Chefe

Adicione o seguinte a `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id do pareamento concluído>"
        ],
        "allow_log_stream_from": [
          "<peer_id do pareamento concluído>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### Configuração de Nó Geral

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id do chefe>"
        ],
        "allow_log_stream_from": [
          "<peer_id do chefe>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Acessar Interface de Gerenciamento de Frota

Acesse `/ext/lan_cowork/fleet/ui` no navegador do nó chefe.

Esta URL retorna 404 em nós não-chefe.

## Funcionalidade de Abas

### Aba de Visão Geral

- Exibição de cartões de todos os nós (com barras de uso de CPU / RAM / GPU / Disco)
- Exibição de estado: Online / Offline / Falha na obtenção de informações
- Badge `[CHIEF]` no nó chefe
- Atualização automática a cada 30 segundos + botão de atualização manual
- Banner de aviso quando múltiplos chefes são detectados

### Aba de Logs

- Exibição ao vivo de logs de qualquer peer via SSE (estilo tail -f)
- Filtro de nível (DEBUG / INFO / WARNING / ERROR)
- Caixa de pesquisa (filtro do lado do cliente)
- Alternância de rolagem automática ON/OFF
- Pausar / Retomar

### Aba de Atualização

- Tabela de comparação de versão / git commit / branch
- Botão "Pull & Restart" para nó individual
- Atualização em lote de múltiplos nós (dispatch)
- Exibição de progresso (precheck → fetching → pulling → restarting → online)
- O próprio chefe é excluído da atualização em lote (apenas botão individual)

## Segurança

### Estrutura de Autorização em Duas Camadas

1. **Pareamento (Verificação de Identidade)**: Identifique "quem" com token Bearer
2. **Allowlist (Permissões)**: Permita explicitamente por operação

Pareado ≠ todas as permissões.

### Exemplo de Configuração de Allowlist

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- Tanto formato de string quanto `{peer_id: ...}` são suportados
- O peer_id do próprio nó é adicionado automaticamente (não é necessário configurar)

## Rebaixamento Automático de Chefe

Se vários nós com `chief = true` forem iniciados na mesma rede, o nó que começar depois será rebaixado automaticamente (após observação por `chief_observation_sec` segundos).

Para retornar ao status de chefe após rebaixamento, é necessário reiniciar após alterar a configuração (não há promoção automática).

## Restrições de Atualização git

- Apenas `git pull --ff-only` é usado (merge/rebase não é usado)
- Se fast-forward não for possível, falha imediatamente (`failed`) (árvore de trabalho não é alterada)
- Atualização é rejeitada se árvore de trabalho estiver dirty

## Solução de Problemas

| Sintoma | Causa | Solução |
|---------|-------|---------|
| `/fleet/ui` retorna 404 | `chief = true` não configurado | Verifique config.json e reinicie |
| `/fleet/info` retorna 500 | psutil não instalado | `uv pip install psutil>=5.9` |
| Erro `git_not_available` | git não está disponível ou PATH incorreto | Verifique instalação do git |
| Timeout `postcheck_online` após atualização | Reinicialização levou mais de 3 minutos | Aumente `postcheck_timeout_sec` |
| Banner de múltiplos chefes não desaparece | Processo chefe antigo está remanescente | Reinicie o chefe antigo |

## Referência de API

### Comum a Todos os Nós

| Endpoint | Descrição |
|----------|-----------|
| `GET /ext/lan_cowork/fleet/info` | Informações da máquina (autenticação Bearer obrigatória) |
| `GET /ext/lan_cowork/fleet/logs/stream` | Log do nó próprio SSE (autorização allowlist) |
| `POST /ext/lan_cowork/fleet/update` | git pull + reiniciar (autorização allowlist) |
| `GET /ext/lan_cowork/fleet/update/status` | Consultar status do job de update |

### Apenas Nó Chefe

| Endpoint | Descrição |
|----------|-----------|
| `GET /ext/lan_cowork/fleet/peers` | Informações agregadas de todos os pares |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | Retransmissão SSE de log de peer especificado |
| `POST /ext/lan_cowork/fleet/update/dispatch` | Atualização em lote para múltiplos pares |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | Consultar progresso de dispatch |
| `GET /ext/lan_cowork/fleet/ui` | Interface de Gerenciamento de Frota |

