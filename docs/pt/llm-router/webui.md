# WebUI do LLM Router

Um dashboard de administrador acessível em `/llm-router`. Permite verificar o status dos backends registrados e habilitá-los/desabilitá-los.

---

## Layout da Página

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← Cartões de resumo
├─────────┴─────────┴────────┴─────────┤
│  Tabela Backends                     │
├───────────────────────────────────────┤
│  Tabela Routing Aliases              │
└───────────────────────────────────────┘
```

### Cartões de Resumo (4)

| Cartão | Conteúdo |
|---|---|
| **Backends** | Número total de backends registrados no catálogo |
| **Enabled** | Número de backends que não estão desabilitados |
| **Models** | Número total de modelos expostos por todos os backends |
| **Routing aliases** | Número de aliases definidos no arquivo de configuração |

Os valores dos cartões são renderizados automaticamente obtendo `/api/llm_router/status` no carregamento da página.

---

## Tabela Backends

Cada linha corresponde a um único backend físico (ex. uma instância Ollama).

### Descrições das Colunas

| Coluna | Descrição |
|---|---|
| **Alias** | Um nome curto único identificando o backend (ex. `ollama-mac`, `mdns-pi5-hailo`). Usado como chave para configuração de roteamento e resolução de alias |
| **Base URL** | A URL base do endpoint compatível com OpenAI do backend (ex. `http://192.168.1.10:11434`) |
| **Status** | Status de conectividade do backend. Veja detalhes abaixo |
| **SLO** | Status de carga de recursos do backend (`vision_idle` / `vision_active` / `unknown`). Usado para backends Hailo Vision |
| **Models** | Número de modelos recuperados na última sonda. Pode ser expansível para mostrar uma lista detalhada dependendo da implementação |
| **Last Seen** | Data e hora da última resposta bem-sucedida (ISO 8601). `null` se nenhuma resposta bem-sucedida foi recebida |
| **Actions** | Botões de ação por backend (veja abaixo) |

### Valores de Status

| Valor | Significado |
|---|---|
| `ready` | A última sonda foi bem-sucedida e a lista de modelos foi recuperada |
| `unreachable` | Ocorreu timeout de conexão ou erro |
| `unknown` | Nenhuma sonda foi executada ainda (ex. logo após inicialização) |
| `probing` | Uma sonda está em progresso (pode aparecer brevemente na UI durante um Refresh) |

> **Dica**: Backends `unreachable` são excluídos do roteamento mas permanecem no catálogo. Após recuperação de rede, execute Refresh All ou um Refresh individual para restaurá-los para `ready`.

### Valores SLO

| Valor | Significado |
|---|---|
| `vision_idle` | Tarefa Vision está inativa. Carga LLM é baixa |
| `vision_active` | Uma tarefa Vision está em execução. O roteador LLM pode priorizar outros backends |
| `unknown` | Informações SLO não estão disponíveis (backend não-Hailo, ou recuperação falhou) |

---

## Botão Refresh All

Clique em **Refresh All** no canto superior direito para forçar uma sonda em todos os backends, atualizando suas listas de modelos e status.

- O botão é desabilitado durante execução e a página é renderizada novamente na conclusão
- Comportamento interno: Chama `POST /api/llm_router/refresh` (sem corpo) para executar `discover_all` para todos os backends
- Refreshes individuais de backend podem estar disponíveis via um botão Refresh na coluna Actions (dependente da implementação)

---

## Desabilitação / Habilitação de Backends Individuais

### Passos

1. Veja a coluna **Actions** na tabela backends
2. Clique no botão **Disable** na linha do backend que você deseja desabilitar
3. O botão muda para **Enable** e a linha fica acinzentada
4. Para reabilitar, clique em **Enable**

### Comportamento e Persistência

- Mudanças são imediatamente refletidas no catálogo em memória
- Simultaneamente, uma escrita atômica é feita em `data/llm_router_state.json`

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- O estado desabilitado é preservado entre reinicializações da aplicação
- Se um backend descoberto via mDNS estava desabilitado antes da inicialização, o estado desabilitado é automaticamente aplicado após descoberta (mecanismo `_pending_disabled`)
- Se a escrita falhar, o estado em memória é revertido para evitar inconsistência com disco

### Comportamento de Backends Desabilitados

- Excluídos do roteamento em endpoints compatíveis com OpenAI como `/v1/chat/completions`
- Roteamento direto para um backend desabilitado retorna `503 Service Unavailable`
- Backends desabilitados ainda aparecem na tabela WebUI (para visibilidade de status e reabilitação)

---

## Tabela Routing Aliases

Exibe o mapeamento entre nomes de modelos lógicos e IDs de modelos físicos conforme definido no arquivo de configuração.

| Coluna | Descrição |
|---|---|
| **Alias** | O nome lógico que os clientes especificam no parâmetro `model` (ex. `default-llm`, `fast-chat`) |
| **Physical Model** | O ID de modelo físico que realmente processa a solicitação (formato: `backend-alias/model-name`, ex. `ollama-mac/qwen2.5:7b`) |

### Função dos Aliases

Aliases permitem trocar backends ou modelos sem alterar código do cliente.

- Clientes enviam solicitações usando um nome lógico como `"model": "default-llm"`
- O LLM Router resolve `default-llm → ollama-mac/qwen2.5:7b` e encaminha a solicitação
- Ao migrar um backend para outra máquina, basta alterar o alvo do alias

Aliases são definidos estaticamente no arquivo de configuração, e a WebUI os exibe em modo somente leitura. Mudanças requerem edição do arquivo de configuração e reinicialização da aplicação.

---

## Operações Comuns

### Quando um Backend é Inacessível

1. Verifique que o serviço backend (Ollama, etc.) está em execução
2. Execute **Refresh All** ou um Refresh individual
3. Se o problema persistir, verifique detalhes de erro na coluna `last_error` (ou resposta API)

### Desabilitação Permanente de um Backend Descoberto via mDNS

1. Clique em **Disable** na coluna Actions do backend alvo
2. O alias é salvo em `data/llm_router_state.json`, portanto permanece desabilitado mesmo após re-descoberta

### Parar Temporariamente a Carga em um Backend Específico

Use **Disable** para excluí-lo imediatamente do roteamento, depois **Enable** para restaurá-lo quando terminar. Nenhuma reinicialização é necessária.
