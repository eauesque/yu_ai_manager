# Guia de Implantação e Operação

Este documento resume os procedimentos para operar o YU AI Manager em produção.

## 1. Visão geral

Existem basicamente três padrões de operação.

| Padrão | Uso | Configuração |
|---------|------|------|
| Execução direta | Uso pessoal / desenvolvimento | Iniciar com Python + venv |
| Docker | Operação em servidor | Quart + Nginx via docker-compose |
| Proxy reverso | Publicação externa | Atrás de um servidor Web existente |

Em todos os casos, os dados são armazenados em `data/tags.db` (SQLite). Não é necessário um servidor de DB externo.

---

## 2. Execução direta (desenvolvimento / uso pessoal)

### Setup

```bash
# Clonar o repositório
git clone <repository-url> && cd yu_ai_manager

# Criar o ambiente virtual Python
python -m venv venv

# Ativar o ambiente virtual
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Instalar dependências
uv pip install -r requirements.txt

# Build do front-end
pnpm install && pnpm run build

# Iniciar
python web_ui.py --db data/tags.db
```

Abra `http://localhost:5000` no navegador.

### Configuração de argumentos via launch-args.txt

Copiando `launch-args.txt.example` para `launch-args.txt` e editando-o, é possível fixar os argumentos de inicialização. Argumentos da CLI têm prioridade.

```txt
# Mudar porta
--port 5100
# Publicar na LAN (bind em 0.0.0.0)
--lan
# Autenticação por PIN
--pin 1234
```

### Como serviço systemd (Linux)

```ini
# /etc/systemd/system/yu-ai-manager.service
[Unit]
Description=YU AI Manager
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/opt/yu_ai_manager
ExecStart=/opt/yu_ai_manager/venv/bin/python web_ui.py --db data/tags.db --lan
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yu-ai-manager
```

### Como serviço no Windows

O mais simples é registrar `start.bat` no Task Scheduler. Configure para "Executar no logon".

---

## 3. Implantação com Docker

### Início rápido

```bash
# Preparar o arquivo de configuração
cp config.json.example config.json
# Editar config.json (pin, scan_roots etc.)

mkdir -p data

# Build e start
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Acesse em `http://localhost` (via Nginx).

### Estrutura de docker-compose.prod.yml

- **app**: Aplicação Quart (porta 5000, apenas interna)
- **nginx**: Proxy reverso (expõe a porta 80)

### Montagens de volume

| Host | Container | Uso |
|-------|---------|------|
| `data/` | `/app/data/` | Persistência do arquivo DB |
| `config.json` | `/app/config.json` | Arquivo de configuração (somente leitura) |
| `static/` | `/app/static/` | Arquivos estáticos servidos diretamente pelo Nginx |

Para pastas de imagens, monte adicionalmente os caminhos definidos em `scan_roots` de `config.json`.

```yaml
# Adicionar em docker-compose.prod.yml
volumes:
  - /path/to/images:/images:ro
```

### Variáveis de ambiente

Copie `deploy/.env.example` para `deploy/.env` e edite.

| Variável | Padrão | Descrição |
|------|----------|------|
| `NGINX_PORT` | `80` | Porta pública do Nginx |
| `UPSTREAM_HOST` | `app` | Nome do container do Quart (não alterar) |
| `UPSTREAM_PORT` | `5000` | Porta do Quart (não alterar) |

### Uso com Podman

Em vez do Docker, também funciona com Podman. Instale `podman compose` ou `podman-compose` e use os mesmos comandos. Para detalhes, consulte `docs/ja/installation/podman.md`.

---

## 4. Configuração de proxy reverso

### Pontos da configuração do Nginx

`deploy/nginx.conf.template` contém uma configuração prática. Os pontos principais são:

- **Arquivos estáticos**: `/static/` é servido diretamente pelo Nginx (contorna o Quart)
- **SSE**: em `/api/events/`, desabilite o buffering com `proxy_buffering off`
- **Limite de upload**: `client_max_body_size 100m` (alinhado com o lado Quart)
- **Gzip**: comprima JSON, CSS e JS

### SSL/TLS (Let's Encrypt)

O Nginx da configuração Docker usa apenas HTTP. Se precisar de HTTPS, há duas formas.

**Método 1: proxy frontal (recomendado)**

Coloque Cloudflare, Caddy, Traefik etc. à frente e faça a terminação HTTPS.

```
cliente --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**Método 2: adicionar SSL diretamente no Nginx**

Em `nginx.conf.template`, adicione `listen 443 ssl;` e os caminhos dos certificados, e obtenha o certificado Let's Encrypt com certbot.

### Configuração de Trusted Proxy

Ao usar via proxy reverso, especifique os IPs confiáveis em `config.json`.

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

Isso faz com que os cabeçalhos `X-Forwarded-For` / `X-Forwarded-Proto` sejam processados corretamente. Há suporte à notação CIDR.

---

## 5. Configuração de autenticação

Há 4 tipos de autenticação disponíveis. Combine-os conforme a necessidade.

### Autenticação por PIN (para acesso por navegador)

```json
{ "pin": "your-secret-pin" }
```

Ao publicar na LAN (`--lan` ou bind em `0.0.0.0`), a configuração do PIN é obrigatória. Se você fizer bind em `0.0.0.0` sem PIN, a inicialização é rejeitada.

### Autenticação por API Key (acesso programático)

Emita uma API Key na tela de Settings e passe-a no cabeçalho da requisição.

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

Na autenticação por API Key, o cabeçalho CSRF (`X-Requested-With`) não é necessário.

### Autenticação via Trusted Proxy

Disponível em configurações em que o proxy reverso adiciona o cabeçalho `X-Remote-User`. A configuração de `trusted_proxy_ips` é obrigatória.

### Modo de compartilhamento em LAN

Na rota `/s/`, é possível emitir links de compartilhamento para convidados. Pula o PIN e autentica individualmente por token.

---

## 6. Backup e recuperação

Os arquivos que devem ser backupeados periodicamente são estes 3:

| Arquivo | Conteúdo |
|---------|------|
| `data/tags.db` | DB SQLite contendo todos os metadados, tags e configurações |
| `config.json` | Configurações da aplicação |
| `data/secret.key`, `data/secret.salt` | Chaves de criptografia (usadas para criptografar configurações) |

### Procedimento de backup

```bash
# Cópia do DB (seguro mesmo em operação)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# Configurações e chaves de criptografia
cp config.json data/secret.key data/secret.salt backup/
```

### Procedimento de recuperação

Basta colocar os arquivos de backup no local original e reiniciar o servidor. A migração do DB é aplicada automaticamente na inicialização.

Se perder as chaves de criptografia (`secret.key`, `secret.salt`), não será mais possível decifrar os valores criptografados nas configurações (credenciais de API etc.). Faça backup sem falta.

---

## 7. Procedimento de upgrade

```bash
# 1. Parar o servidor
# 2. Atualizar o código
git pull

# 3. Atualizar dependências
source venv/bin/activate  # ou .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. Rebuild do front-end
pnpm install && pnpm run build

# 5. Iniciar o servidor
python web_ui.py --db data/tags.db
```

A migração do schema do DB é executada automaticamente na inicialização. Nenhuma ação manual é necessária.

No caso do Docker, basta fazer o rebuild.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. Monitoramento e log

### Streaming de log

Na aba Settings > Logs, é possível ver os logs em tempo real. Fica disponível via SSE (`/api/logs/stream`) no navegador.

Os logs passados podem ser obtidos em `/api/logs/recent`.

### Health check

No endpoint `/api/server-info` é possível verificar o estado de operação.

```bash
curl http://localhost:5000/api/server-info
```

Retorna informações como versão, versão do schema do DB, fuso horário etc. Use esse endpoint como health check em ferramentas de monitoramento.

### Diagnóstico via MCP

A partir de um cliente MCP (Claude Desktop etc.), chame a ferramenta `debug_health_check` para executar, de uma só vez, a verificação de integridade do DB, a verificação do comportamento da busca e a validação de contagens.
