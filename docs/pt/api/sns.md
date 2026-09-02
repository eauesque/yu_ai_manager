# API de Compartilhamento SNS

APIs para compartilhamento SNS, postagem Bluesky e gerenciamento de fila de notificação.

Fornecido por `routes/sns_share.py`. Todos os endpoints requerem autenticação (sessão PIN ou API Key).

## Visualização e Intenção X

### GET /api/sns/preview

Expande um template de post com metadados de imagem e retorna uma visualização. Útil para visualizar o que será postado antes de compartilhar.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo de imagem alvo |
| `template` | string | Não | String de template customizado (usa padrão se omitido) |

### Resposta

```json
{
  "text": "New artwork: sunset landscape #aiart #stablediffusion",
  "graphemes": 52,
  "meta": {
    "title": "sunset landscape",
    "model": "sd_xl_base_1.0",
    "generator": "a1111"
  }
}
```

### Exemplo curl

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

Gera uma URL de Web Intent X (Twitter) para compartilhamento. Abre o diálogo de composição X com texto pré-preenchido.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo de imagem alvo |

### Resposta

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Postagem Bluesky

### POST /api/sns/bluesky/post

Posta texto (e opcionalmente uma imagem) no Bluesky.

### Solicitação

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo de imagem alvo |
| `text` | string | Não | Texto da post (usa expansão de template se omitido) |
| `attach_image` | boolean | Não | Anexa a imagem ao post (padrão: false) |

### Resposta

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### Resposta de Erro

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

Testa conexão Bluesky com credenciais configuradas.

### Resposta

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### Resposta de Erro

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## Configuração SNS

### GET /api/sns/config

Obtém configuração SNS. Senhas são mascaradas na resposta.

### Resposta

```json
{
  "bluesky": {
    "handle": "user.bsky.social",
    "app_password": "****...xxxx"
  },
  "post_template": "{title} #aiart #{generator}"
}
```

### POST /api/sns/config

Salva configuração SNS.

### Solicitação

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `bluesky_handle` | string | Não | Handle Bluesky (ex. `user.bsky.social`) |
| `bluesky_app_password` | string | Não | Senha de App Bluesky |
| `post_template` | string | Não | Template de post padrão com variáveis `{placeholder}` |

### Exemplo curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Fila de Notificação Bluesky

### GET /api/sns/bsky/queue

Lista itens de fila de notificação com filtros opcionais.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `status` | string | Filtro: `pending`, `notified`, `dismissed`, ou vazio para todos |
| `type` | string | Filtro de tipo de notificação (ex. `mention`, `reply`, `quote`, `like`, `repost`, `follow`) |
| `limit` | int | Máx resultados (padrão 50) |

### Resposta

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "type": "mention",
        "author_handle": "someone.bsky.social",
        "author_display_name": "Someone",
        "text": "@user.bsky.social great artwork!",
        "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": null
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/sns/bsky/queue/pending

Obtém notificações pendentes (não processadas) para notificação MCP.

### Resposta

```json
{
  "data": {
    "items": [...],
    "count": 3,
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### POST /api/sns/bsky/queue/<queue_id>/triage

Define resultado de triagem para um item de fila.

### Solicitação

```json
{ "result": "valid" }
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `result` | string | Sim | `valid` ou `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

Atualiza status do item de fila.

### Solicitação

```json
{ "status": "notified" }
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `status` | string | Sim | `pending`, `notified`, ou `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

Envia uma auto-resposta para uma notificação.

### Solicitação

```json
{ "text": "Thank you for your kind words!" }
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `text` | string | Sim | Texto de resposta a postar como uma reply |

### POST /api/sns/bsky/queue/poll

Dispara sondagem imediata para novas notificações Bluesky.

### Exemplo curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Configuração do Monitor Bluesky

### GET /api/sns/bsky/monitor/config

Obtém configurações do monitor de notificação Bluesky.

### Resposta

```json
{
  "data": {
    "poll_interval_minutes": 15,
    "auto_dismiss_follow": false,
    "auto_dismiss_like": true,
    "auto_dismiss_repost": true,
    "auto_respond_enabled": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/sns/bsky/monitor/config

Atualiza configurações do monitor de notificação Bluesky. Apenas campos fornecidos são atualizados.

### Solicitação

```json
{
  "poll_interval_minutes": 30,
  "auto_dismiss_follow": false,
  "auto_dismiss_like": true,
  "auto_dismiss_repost": true,
  "auto_respond_enabled": false,
  "notify_on_connect": true
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `poll_interval_minutes` | int | Não | Intervalo de sondagem em minutos |
| `auto_dismiss_follow` | boolean | Não | Auto-descarta notificações de follow |
| `auto_dismiss_like` | boolean | Não | Auto-descarta notificações de like |
| `auto_dismiss_repost` | boolean | Não | Auto-descarta notificações de repost |
| `auto_respond_enabled` | boolean | Não | Habilita auto-respostas |
| `notify_on_connect` | boolean | Não | Envia notificação na conexão do cliente MCP |

---

## Prompts de Triagem e Templates de Auto-Resposta

### GET /api/sns/bsky/monitor/triage-prompts

Obtém prompts de triagem editáveis, templates de auto-resposta e seus valores padrão.

### Resposta

```json
{
  "data": {
    "triage_prompts": {
      "mention": "Evaluate this mention for relevance...",
      "reply": "Evaluate this reply...",
      "quote": "Evaluate this quote post..."
    },
    "auto_responses": {
      "mention": "Thanks for the mention!",
      "reply": "Thank you for your reply!",
      "quote": "Thanks for sharing!"
    },
    "defaults": {
      "triage_prompts": {
        "mention": "Evaluate this mention for relevance...",
        "reply": "Evaluate this reply...",
        "quote": "Evaluate this quote post..."
      },
      "auto_responses": {
        "mention": "Thanks for the mention!",
        "reply": "Thank you for your reply!",
        "quote": "Thanks for sharing!"
      }
    }
  }
}
```

### PUT /api/sns/bsky/monitor/triage-prompts

Atualiza prompts de triagem e/ou templates de auto-resposta. Apenas campos fornecidos são atualizados.

### Solicitação

```json
{
  "triage_prompts": {
    "mention": "Custom mention triage prompt...",
    "reply": "Custom reply triage prompt...",
    "quote": "Custom quote triage prompt..."
  },
  "auto_responses": {
    "mention": "Custom mention auto-response...",
    "reply": "Custom reply auto-response...",
    "quote": "Custom quote auto-response..."
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `triage_prompts` | object | Não | Prompts de triagem indexados por tipo de notificação (`mention`, `reply`, `quote`) |
| `auto_responses` | object | Não | Templates de auto-resposta indexados por tipo de notificação |
