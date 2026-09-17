# Configurações

## Configurações de servidor

| Item | Descrição |
|------|------|
| Host | Endereço de bind (fixo em 127.0.0.1 com LAN OFF) |
| Port | Porta do servidor Web |
| LAN Access | Com ON, acessível por outros dispositivos da LAN |
| PIN Auth | Solicita PIN ao acessar |
| Boss Mode | Tela de login com PIN estilo jornal |

## Configurações de scan

Adicionar, remover, reordenar e ativar/desativar pastas registradas.

## Configurações de parsers

| Item | Descrição |
|------|------|
| Extract A1111 | Extrai metadados no formato Stable Diffusion WebUI |
| Extract ComfyUI | Extrai metadados de workflow do ComfyUI |
| Normalize tags | Unifica as tags em minúsculas |
| Compute hash | Calcula hash do arquivo (para detecção de duplicatas) |
| FTS | Ativa índice de busca full-text |

## API Keys

Gerencia API Keys para ferramentas externas (servidor MCP, scripts, agentes).
Usadas com autenticação Bearer.

## Aparência

Personalização de tema, cor de destaque, imagem de fundo, efeitos sonoros etc.

## Secret store criptografado

Valores sensíveis como PIN, senha do Bluesky e secrets de Webhook são protegidos por criptografia Fernet do pacote `cryptography`.

- **Formato criptografado**: string com prefixo `enc:`
- **Compatibilidade**: valores em texto plano existentes continuam funcionando (só novos salvamentos são criptografados)
- **Instalação**: `uv pip install cryptography` (função de criptografia fica desativada se não estiver instalado)

### Backends de chave

A chave de criptografia é obtida na seguinte ordem de prioridade:

1. **Passphrase** — definindo a variável de ambiente `YU_SECRET_PASSPHRASE`, a chave é derivada via PBKDF2-HMAC-SHA256 (600.000 iterações). O salt é salvo automaticamente em `data/secret.salt`
2. **Keychain do SO** — se o pacote `keyring` estiver instalado, armazena a chave em Windows Credential Manager / macOS Keychain / Linux Secret Service
3. **Arquivo** — `data/secret.key` (compatibilidade legada, gerado automaticamente na primeira vez)

```bash
# Exemplo de configuração de passphrase
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# Uso do keychain
uv pip install keyring
```

### Exportar/importar chave

Para migração entre máquinas ou backup, é possível exportar/importar a chave de criptografia em JSON protegido por senha.

- `POST /api/settings/secrets/export` — exporta protegido por senha (mínimo 8 caracteres)
- `POST /api/settings/secrets/import` — restaura a chave a partir dos dados exportados e da senha
- `POST /api/settings/secrets/migrate-keychain` — migra do arquivo para o keychain
- `GET /api/settings/secrets/status` — verifica o estado do backend

### Migração para o keychain

Para migrar uma chave salva em arquivo para o keychain, chame `/api/settings/secrets/migrate-keychain`. Após a migração, `data/secret.key` é removido automaticamente.

## Integração com 1Password CLI

Em ambientes com a CLI `op` instalada, é possível obter secrets dinamicamente do Vault do 1Password.

### Setup

1. Instale a [1Password CLI](https://developer.1password.com/docs/cli/)
2. Faça sign-in com `op signin`
3. Adicione o mapeamento `op_secrets` em `config.json`:

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. Configure pela Settings API ou por uma ferramenta MCP, especificando `op_uri`:

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### Comportamento

- Se a chave estiver registrada em `op_secrets`, o secret é obtido por `op read`
- O valor obtido fica em cache na memória por 5 minutos
- Em ambientes sem a CLI `op`, faz fallback para o store local criptografado
- É possível verificar o estado de autenticação no 1Password em `GET /api/settings/op-status`

## Ferramentas MCP de Settings

É possível gerenciar as configurações a partir de clientes MCP (Claude Desktop etc.).

| Ferramenta | Descrição |
|--------|------|
| `settings_get_schema` | Obtém o schema de todas as configurações (tipo, descrição, categoria) |
| `settings_get_all` | Obtém todos os valores de configuração (secrets são mascarados) |
| `settings_get` | Obtém um único valor |
| `settings_set` | Atualiza valor de configuração (secrets são criptografados automaticamente) |
| `secrets_status` | Obtém o estado do backend da chave de criptografia |
| `secrets_export` | Exporta a chave em JSON protegido por senha |
| `secrets_import` | Importa a chave a partir dos dados exportados |
