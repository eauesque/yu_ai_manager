# API de Atualização do Sistema

API para verificar novas versões no GitHub e aplicar atualizações de aplicação. Detecta automaticamente o tipo de instalação (git / tauri / docker / portable) e fornece o método de atualização apropriado.

## GET /api/system/update/check

Verifica se uma nova versão está disponível no repositório GitHub.

- **Taxa de limite**: Nenhuma (GET)
- **Auth**: Sessão PIN ou API Key

### Resposta

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `current` | string | Versão atual |
| `latest` | string | Versão mais recente no GitHub |
| `update_available` | bool | Se nova versão está disponível |
| `release_url` | string | URL da página GitHub Release |
| `release_notes` | string | Notas de release (Markdown) |
| `published_at` | string | Data de publicação da release (ISO 8601) |
| `install_type` | string | Tipo de instalação (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | Apenas Docker: comando para atualizar |
| `portable_download_url` | string \| null | Apenas Portable: URL de download |

## GET /api/system/update/status

Obtém o tipo de instalação atual e informações de versão.

- **Taxa de limite**: Nenhuma (GET)
- **Auth**: Sessão PIN ou API Key

### Resposta

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `version` | string | Versão atual |
| `install_type` | string | Tipo de instalação (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | Se uma atualização está em progresso |

## POST /api/system/update/apply

Aplica uma atualização disponível. Suportado apenas para instalações git clone e portable.

- **Taxa de limite**: DESTRUCTIVE
- **Auth**: Sessão PIN (localhost) ou token de reinicialização
- **CSRF**: `X-Requested-With: XMLHttpRequest` obrigatório

### Corpo da Solicitação

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `confirm` | string | Sim | String de confirmação. Deve ser `"update"` |

### Resposta

```json
{
  "ok": true,
  "message": "Update started"
}
```

### Eventos SSE

Durante a atualização, eventos `update.progress` são entregues via SSE.

### Erros

**Instalações Docker** (400):
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Instalações Tauri** (400):
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```
