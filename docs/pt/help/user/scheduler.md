# Agendador de Tarefas

## Visão geral

O agendador de tarefas é uma função que executa automaticamente tarefas periódicas, como manutenção do banco de dados e polling de serviços externos. Um scheduler em background baseado em APScheduler gerencia jobs com triggers cron / interval.

Pela página Scheduler (`/scheduler`) da WebUI, é possível listar, adicionar, remover, pausar e executar imediatamente jobs.

## Setup

O agendador vem ativado por padrão. Pode ser controlado por `scheduler.enabled` em `config.json`:

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

Os jobs descritos em `config.json` são registrados automaticamente na inicialização. Jobs adicionados pela WebUI valem apenas durante a sessão (são apagados ao reiniciar).

## Lista de jobs embutidos

### Manutenção do banco de dados

| ID do job | Descrição | Frequência recomendada |
|-----------|------|---------|
| `db_vacuum` | Executa VACUUM do SQLite e recupera áreas não utilizadas | 1x por semana |
| `db_integrity_check` | Verifica a integridade do banco com `PRAGMA integrity_check` | Diariamente |
| `db_backup` | Cria backup do banco (via builtin-backup extension) | Diariamente |

### Gestão de cache e índices

| ID do job | Descrição | Frequência recomendada |
|-----------|------|---------|
| `thumbnail_cleanup` | Remove arquivos de cache de miniaturas expirados | Diariamente |
| `prune_unused_tags` | Remove registros de tags órfãs não vinculadas a arquivos | Semanal a mensal |
| `refresh_monthly_stats` | Atualiza o cache pré-computado das estatísticas mensais | Diariamente |
| `rebuild_groups_index` | Reconstrói o cache de índice de grupos de pastas/arquivos compactados | Semanal |

### Integração com serviços externos

| ID do job | Descrição | Frequência recomendada |
|-----------|------|---------|
| `github_issue_poll` | Faz polling da API do GitHub e incorpora Issues novas na fila local | 5 min a 1 h |
| `bsky_notification_poll` | Faz polling da API do Bluesky e obtém notificações novas | 5 min a 1 h |

## Configuração de triggers

### Trigger cron

Executa em horários, dias da semana ou datas específicas. Forma de especificação similar ao cron Unix.

| Parâmetro | Exemplo | Descrição |
|-----------|--------|------|
| `hour` | `3`, `*/6`, `1,13` | Hora (0-23). `*` = toda hora |
| `minute` | `0`, `30`, `0,30` | Minuto (0-59). `*` = todo minuto |
| `day` | `1`, `15`, `1,15` | Dia (1-31). `*` = todo dia |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | Dia da semana. `*` = todo dia |

**Exemplo**: executar no dia 1 e 15 de cada mês, às 2h30 da manhã

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Trigger interval

Executa repetidamente em um intervalo fixo.

| Parâmetro | Exemplo | Descrição |
|-----------|--------|------|
| `hours` | `2` | Intervalo em horas |
| `minutes` | `30` | Intervalo em minutos |

**Exemplo**: executar a cada 30 minutos

```json
{ "trigger": "interval", "minutes": 30 }
```

## Como usar na WebUI

### Lista de jobs

Ao abrir a página Scheduler, é exibida a lista dos jobs registrados. É possível ver o estado de cada job (ativo/pausado), a configuração de trigger e o próximo horário de execução.

### Adicionando um job

1. Clique em **Adicionar job**
2. Informe o ID do job (nome único)
3. Selecione a função a executar no dropdown
4. Selecione o tipo de trigger (cron / interval)
5. Preencha os parâmetros de schedule (pode usar `*` como wildcard)
6. Clique em **Adicionar**

### Operações com jobs

- **Executar agora**: executa o job imediatamente, uma vez, fora da agenda
- **Pausar / Retomar**: interrompe/retoma temporariamente a execução periódica
- **Remover**: remove o job totalmente (jobs de config.json são restaurados na próxima inicialização)

### Histórico de execuções

Na parte inferior da página há o histórico recente de execuções (máximo 50 entradas). É possível verificar o status (sucesso/falha) e mensagens de resultado. Ao concluir um job, o histórico é atualizado em tempo real por SSE.

## Ferramentas MCP

É possível operar o agendador a partir de clientes MCP (Claude Desktop etc.):

| Ferramenta | Descrição |
|--------|------|
| `get_scheduler_status` | Obtém o estado de operação do agendador |
| `list_scheduled_jobs` | Obtém a lista de jobs registrados |
| `trigger_scheduled_job` | Executa um job imediatamente |
| `pause_scheduled_job` | Pausa um job |
| `resume_scheduled_job` | Retoma um job |
| `get_scheduler_history` | Obtém o histórico de execuções |

## Dicas

- **Jobs de polling externo** (`github_issue_poll`, `bsky_notification_poll`) são melhores com trigger interval. Fixar um horário via cron pode fazer o polling ficar com espaçamento grande demais
- **`db_vacuum`** adquire lock de escrita; recomenda-se configurar em horários noturnos de baixo acesso
- **`db_backup`** respeita as configurações de cooldown da extension builtin-backup. Mesmo configurando interval curto, é pulado durante o cooldown
- **O histórico de execuções fica em memória** (máximo 100 entradas). O histórico é limpo ao reiniciar o servidor
