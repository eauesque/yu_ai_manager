# Autenticação PIN entre peers e pareamento por token

**Versão de implementação**: 4.92.0
**Arquivos relacionados**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## Visão geral

Antes da v4.92, na comunicação entre peers na LAN, o peer era identificado apenas pelo cabeçalho `X-Peer-Id`.
Como qualquer um na LAN pode forjar esse cabeçalho, a segurança era insuficiente.

A partir da v4.92, migramos para o esquema de **pareamento por token baseado em aprovação por PIN**.

- Na primeira conexão, envia-se uma "solicitação de pareamento"
- O administrador do outro lado aprova na tela de gestão e emite um PIN de 6 dígitos
- Ao inserir o PIN, um token Bearer (válido por 30 dias) é emitido
- A partir daí, a comunicação é autenticada com `Authorization: Bearer <token>`

O método antigo baseado em cabeçalho `X-Peer-Id` pode manter compatibilidade por configuração, mas operações DELETE sempre exigem a nova autenticação.

---

## Fluxo de pareamento

```
[Peer A de origem]                        [Peer B de destino]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                              admin confirma/aprova em /lan-cowork/peers
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (PIN de 6 dígitos, validade 5 min) |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (token Bearer, válido por 30 dias) |
       |                                      |
       |--- a partir daqui Authorization: Bearer <token>
```

### Detalhes de cada passo

| Passo | Endpoint | Descrição |
|----------|---------------|------|
| 1. Enviar pedido | `POST /api/lan/pair/request` | Envia peer ID, display name e chave pública |
| 2. Aguardar aprovação | — | Admin confere em `/lan-cowork/peers` |
| 3. Emitir PIN | — | Ao clicar em "aprovar", gera PIN de 6 dígitos (válido por 5 min) |
| 4. Verificar PIN | `POST /api/lan/pair/verify` | Envia o PIN e recebe um token Bearer |
| 5. Comunicação autenticada | — | Envia o cabeçalho `Authorization: Bearer <token>` |

---

## Tela de gerenciamento (`/lan-cowork/peers`)

### Pedidos aguardando aprovação

Quando chega uma nova solicitação de pareamento, ela aparece na aba "Aguardando aprovação" da tela de gerenciamento.

- **Aprovar**: gera um PIN e notifica, via SSE, o peer que fez o pedido
- **Rejeitar**: remove o pedido. Ao peer de origem é retornado 403

### Lista de peers conectados

Exibe a lista de peers já pareados e a validade de cada token.

| Coluna | Conteúdo |
|----|------|
| Nome de exibição | Nome do peer |
| Endereço IP | Último IP de origem confirmado |
| Validade | Validade do token Bearer (30 dias) |
| Última conexão | Horário do último heartbeat |
| Ações | Botão de invalidar token |

### Invalidação de token

Ao clicar em "Invalidar", o token Bearer do peer alvo é imediatamente invalidado.
Na próxima comunicação retorna-se 401, e o peer tenta reparar automaticamente.

---

## Itens de configuração

As configurações podem ser alteradas na seção `lan_cowork` de `config.json`, ou na aba "LAN Cowork" da tela de configurações.

### `ip_check_mode`

Especifica o método de verificação do endereço IP de origem.

| Valor | Comportamento |
|----|------|
| `strict` | Permite apenas correspondência exata com o IP no momento da emissão do token (padrão) |
| `cidr` | Permite se estiver dentro do intervalo CIDR definido em `allowed_cidr` |
| `rfc1918` | Permite todos os IPs privados (192.168.x.x / 10.x.x.x / 172.16-31.x.x) |

### `allow_legacy_auth`

Se mantém compatibilidade com a autenticação antiga por cabeçalho `X-Peer-Id`.

- `true`: permite alguns acessos somente com `X-Peer-Id` (padrão: `true`)
- `false`: rejeita qualquer conexão sem token Bearer

> **Atenção**: operações com método `DELETE` (parar scan, exclusão forçada etc.) exigem token Bearer independentemente de `allow_legacy_auth`.

### `protect_heartbeat`

Se o endpoint de heartbeat (`/api/lan/heartbeat`) também exige autenticação.

- `true`: heartbeat também exige token Bearer
- `false`: heartbeat passa sem autenticação (padrão: `false`)

Como heartbeats são enviados frequentemente, `false` evita atrasos na detecção de token expirado.

### `protect_events`

Se a stream de eventos SSE (`/api/events/`) também exige autenticação.

- `true`: conexão SSE exige token Bearer
- `false`: SSE passa sem autenticação (padrão: `false`)

---

## Notas de segurança

### Hashing do token

O token Bearer emitido **não é salvo em texto plano** no banco.
Ele é armazenado depois de passar por scrypt (N=16384, r=8, p=1).
Mesmo que o DB vaze, o token original não pode ser reconstruído.

### Mascaramento em logs

- O cabeçalho `Authorization: Bearer <token>` é automaticamente substituído por `Bearer [REDACTED]` quando escrito em log
- Os códigos PIN também não aparecem nos logs

### Rate limit

Para prevenir DoS e força bruta, os seguintes limites são aplicados.

| Endpoint | Limite |
|---------------|------|
| `POST /api/lan/pair/request` | 10 por minuto por IP |
| `POST /api/lan/pair/verify` | 30 por minuto por IP |

O PIN expira automaticamente em 5 minutos e só pode ser verificado uma vez por pedido.

---

## Troubleshooting

### O pedido de pareamento não chega

- Verifique se a URL do peer alvo está configurada corretamente
- Verifique se o firewall não está bloqueando a porta
- Confira nos logs do peer alvo o recebimento de `pair/request`

### O PIN expirou

O PIN tem validade de 5 minutos. Caso expire, clique em "Aprovar" novamente na tela de gerenciamento para gerar um novo.

### O token deixou de funcionar de repente

Possíveis causas:

1. Admin invalidou o token na tela de gerenciamento
2. A validade de 30 dias expirou
3. Com `ip_check_mode: strict`, o IP mudou

Faça novo pareamento.

### Depois de colocar `allow_legacy_auth` em `false` perdi a conexão

Se peers existentes continuarem na autenticação antiga, todos retornarão 401.
Conclua o repareamento em cada peer antes de mudar `allow_legacy_auth: false`.
