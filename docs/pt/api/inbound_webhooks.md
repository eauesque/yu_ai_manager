# API de Webhook de Entrada

Um endpoint receptor para enviar eventos de serviços externos para o event_bus do yu_ai_manager.

## Endpoint de Recepção (Sem autenticação obrigatória — baseada em token)

`POST /api/webhooks/receive/{token}`

### Corpo da Requisição

| Campo | Tipo | Descrição |
|-------|------|-------------|
| event | string | event_type para disparar (padrão: `webhook.received`) |
| data | object | Dados do evento |

### Resposta

```json
{"ok": true, "event": "scan.start"}
```

### Erros

| Código | Descrição |
|------|-------------|
| 403 | Token inválido / incompatibilidade de HMAC / evento não em allowed_events |

## API de Gerenciamento (Requer sessão PIN)

### Criar

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

Resposta:

```json
{
  "id": "iwh_a1b2c3...",
  "token": "64char_hex...",
  "label": "n8n trigger",
  "allowed_events": ["scan.start"],
  "active": true,
  "created_at": 1712188800
}
```

### Listar

`GET /api/webhooks/inbound`

### Atualizar

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### Deletar

`DELETE /api/webhooks/inbound/{id}`

## Autenticação

- Aceito se o token na URL coincidir
- Se o header `X-Webhook-Signature` estiver presente, é realizada verificação adicional de HMAC-SHA256 (opcional)

## Segurança

- Token é hex de 64 caracteres (256 bit)
- `allowed_events` restringe quais eventos podem ser disparados
- Array vazio `allowed_events` = todos os eventos permitidos
