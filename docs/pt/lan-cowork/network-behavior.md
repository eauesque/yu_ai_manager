# Comportamento de rede do LAN Cowork (o que acontece na LAN)

> Destinado a: Rust standalone (`yu-server`) v4.538.0 e versões posteriores. Para configuração híbrida com back-end Python,
> consulte "Diferenças em relação à versão Python" no final.

Esta página resume **"o que sua máquina começará a fazer na rede quando você abilitar LAN Cowork"**
em uma única página. Leia-a antes de alterar as configurações.

---

## Pontos-chave

- **Por padrão, não faz nada.** Rust standalone não inicia listening ou broadcast na LAN, a menos que
  explicitamente habilitado pelas configurações descritas abaixo.
- Quando habilitado, **sua máquina fica detectável por outros nós na mesma LAN**. Este é o comportamento esperado.
- **A presença ou ausência de PIN não interrompe o broadcast de descoberta.** Para detalhes, consulte
  "Relação com PIN (ponto facilmente confundido)".

---

## O que começa quando habilitado

| Operação | Detalhes |
|---|---|
| **Listening UDP** | Faz bind em `0.0.0.0:19850` (todas as interfaces) |
| **Broadcast periódico** | A cada 10 segundos, envia um HELLO assinado para `255.255.255.255:19850`. O conteúdo inclui ID do nó, chave pública, porta da API, nome do host, etc. |
| **Registro de outros nós** | Verifica a assinatura dos HELLOs recebidos e registra nós remotos em sua lista de peers (TOFU) |
| **Aceitação de HTTP inbound** | Os endpoints de peer listados na tabela abaixo começam a responder |
| **Entrega local** | Eventos de peer recebidos são entregues ao SSE (`/api/events/stream`) assinado por telas logadas |
| **Limpeza de expirados** | A cada 60 segundos, limpa requests de pairing expirados e PINs em texto plano da memória |

### Endpoints aceitos no inbound

| Endpoint | Autenticação |
|---|---|
| `GET /ext/lan_cowork/api/peer/discover` | **Sessão não obrigatória** (consulta lista de peers) |
| `GET /ext/lan_cowork/api/peer/status` | **Sessão não obrigatória** (descritor do nó próprio) |
| `POST /ext/lan_cowork/api/peer/register` | **Sessão não obrigatória** (auto-registro de peer; o servidor valida o destino) |
| `POST /ext/lan_cowork/api/peer/pair/request` / `pair/verify` | **Sessão não obrigatória** (início de pairing; um peer sem pairing não pode ter sessão) |
| `POST /ext/lan_cowork/api/peer/token/renew` | Assinatura + nonce (Bearer não obrigatório) |
| `POST /ext/lan_cowork/api/peer/event` / `heartbeat` | Assinatura + token Bearer |

"Sessão não obrigatória" significa **sem requisição de sessão de login**, não "sem autenticação".
Como um peer sem pairing não pode ter sessão, apenas estes 5 endpoints ficam abertos como exceção.
Todos os outros endpoints exigem login como antes.

---

## Como habilitar e desabilitar

Alterne pelo **setor `extensions`** em `config.json`.

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

- **Quando a chave está ausente, é "desabilitado"** (Rust standalone).
- **Reinicialização é obrigatória** para que a alteração tenha efeito.
- Para alterações temporárias, você pode usar opções de inicialização. A prioridade é
  **linha de comando > `config.json` > variável de ambiente > padrão**.

| Método | Habilitar | Desabilitar |
|---|---|---|
| Linha de comando | `--native-daemon` | `--no-native-daemon` |
| Variável de ambiente | `YU_LAN_COWORK_NATIVE_DAEMON=1` | `YU_LAN_COWORK_NATIVE_DAEMON=0` |

> A variável de ambiente interpreta apenas `1` / `true` / `yes` como "habilitado". `on` ou `Y` são **tratados como desabilitados**.

### Verificar se está habilitado

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/ext/lan_cowork/api/peer/status
```

| Resposta | Significado |
|---|---|
| `200` | Habilitado. Funcionalidade de peer está operacional |
| `405` | **Desabilitado** (funcionalidade não está compilada) |
| `503` | Habilitado mas não pronto (chave específica do nó não gerada, ou falha na inicialização interna) |

> **A listagem de extensões na tela não é confiável.** A listagem de extensões pode exibir LAN Cowork como "habilitado",
> mas isto se baseia nas informações incluídas no pacote, **e é diferente de se o daemon abaixo está realmente em execução**.
> Para decidir, use a resposta do endpoint acima ou a linha `native_daemon=...` no log de inicialização.

---

## Relação com PIN (ponto facilmente confundido)

**Não é preciso ter PIN configurado para que a LAN não consiga acessar nada — este entendimento não está correto.**

- **Correto**: Para usar `--lan` (listening em todas as interfaces), PIN é obrigatório; sem ele, a inicialização é abortada.
  O listening padrão é `127.0.0.1`, portanto **em inicialização normal, HTTP não é alcançável pela LAN**.
- **Aviso 1**: Se você especificar um IP da LAN diretamente em `--host`, o requisito obrigatório de PIN não é verificado.
  Além disso, sem PIN, até o próprio gate de login fica aberto, portanto **evite expor sua LAN sem PIN**.
- **Aviso 2**: **O broadcast UDP de descoberta independe de haver PIN configurado.** Se habilitado,
  mesmo um nó sem PIN anuncia sua existência na LAN a cada 10 segundos. O PIN limita apenas a exposição HTTP.

Portanto **PIN reduz exposição do lado HTTP, mas não interrompe o broadcast de descoberta.**

### Quando escuta apenas em loopback (v4.539.0 e posteriores)

Se o endereço de listening for somente loopback (o padrão `127.0.0.1`, que também se aplica à versão desktop),
**este nó não se anuncia na LAN**. Outros nós não poderiam se conectar mesmo que ele se anunciasse.
Após a inicialização, o aviso a seguir é registrado uma única vez (é WARN, não INFO, portanto aparece por padrão).

```
LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan
```

Para usá-lo na LAN, faça bind em um endereço LAN ou use `--lan` (`--lan` requer um PIN).

> Antes de v4.539.0, um listener apenas em loopback anunciava um IP da LAN. Os peers podiam descobri-lo,
> mas não se conectar; por isso esse comportamento foi alterado.

---

## O que você deve saber antes de habilitar

- **Desabilitar não remove automaticamente informações de peer registradas enquanto estava habilitado.**
  Além disso, **no primeiro boot após habilitar**, ocorre limpeza de registros antigos de peer
  (registros não alcançados há mais de 7 dias e registros não pareados há mais de 1 hora são deletados).
  Recomendamos fazer backup de `tags.db` antes de alternar.
- Eventos de peer recebidos são entregues ao SSE (`/api/events/stream`) assinado por telas logadas.
  **O conteúdo é entrada originária do nó remoto** (o ID do remetente é substituído pelo valor autenticado no lado do servidor).
- O que é registrado em log é **apenas contagem, tipo e ID do remetente**; o conteúdo do evento não é gravado.
- Para confirmar o status operacional, habilite INFO no nível de log
  (exemplo: `RUST_LOG=yu_server=info`). No padrão, nenhuma linha indicando recebimento de eventos de peer é produzida.

---

## Diferenças em relação à versão Python

| | Back-end Python híbrido | Rust standalone |
|---|---|---|
| Padrão | **Habilitado** (habilitado se a chave em `config.json` está ausente) | **Desabilitado** (requer habilitação explícita) |
| Implementação | Extensão Python cuida disso | `yu-server` cuida disso |

**Rust standalone é intencionalmente "desabilitado por padrão".** Isto é para evitar que apenas atualizar
mude o comportamento de sua máquina na rede. O comportamento da configuração híbrida não muda em relação à versão anterior.

> Documentação anterior indicava a configuração de habilitação como `{"lan_cowork": {"enabled": true}}` (no nível superior),
> mas **esta chave não é lida por nenhuma implementação.** A seção `extensions` acima é a localização correta.
