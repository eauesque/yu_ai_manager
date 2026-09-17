# Setup com Podman

O ambiente em containers do YU AI Manager suporta tanto Docker quanto Podman.
Os scripts de gerenciamento (`scripts/yu-docker.sh`, `tools/docker-build.sh`) detectam automaticamente o runtime instalado.

---

## Pré-requisitos

- Podman 4.0 ou superior
- Plugin `podman compose` (Podman 4.7+) ou `podman-compose` (pip)

### Instalação do Podman

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt install podman

# Fedora
sudo dnf install podman

# macOS (Homebrew)
brew install podman
podman machine init
podman machine start
```

### Instalação da ferramenta Compose

Para usar `docker-compose.yml` com Podman, é necessário um destes:

```bash
# Opção 1: podman-compose (pip, leve)
uv pip install podman-compose

# Opção 2: plugin podman compose (Podman 4.7+)
# Pode vir embutido no próprio podman. Verifique com:
podman compose version
```

---

## Uso básico

### Via scripts de gerenciamento (recomendado)

Como o script detecta automaticamente Docker / Podman, os comandos são os mesmos do Docker.

```bash
# Setup inicial
./scripts/yu-docker.sh init

# Build
./scripts/yu-docker.sh build

# Start
./scripts/yu-docker.sh up

# Logs
./scripts/yu-docker.sh logs

# Stop
./scripts/yu-docker.sh down
```

### Comandos diretos

```bash
# Build
podman build -t yu-ai-manager .

# Start (compose)
podman compose up yu-ai-manager -d

# Start (standalone)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Build da variante Hailo
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Diferenças em relação ao Docker e pontos de atenção

### Modo rootless

O Podman opera em rootless (sem privilégios de root) por padrão.
Na maior parte dos casos funciona sem alterações, mas atente para o seguinte.

| Item | Impacto | Solução |
|---|---|---|
| Porta abaixo de 1024 | Não pode fazer bind em rootless | Como usamos 5000, não há problema |
| Pass-through de dispositivo | Acesso a `/dev/hailort0` etc. requer permissão | `podman run --device` + permissão de grupo, ou `sudo podman` |
| Mapeamento de UID | O `appuser` no container tem UID diferente do host | Se surgirem problemas de permissão em volumes, corrija com `podman unshare chown` |

```bash
# Verificar mapeamento de UID
podman unshare cat /proc/self/uid_map

# Exemplo de correção de permissão de volumes
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Pass-through de dispositivo Hailo

```bash
# Em rootless, pode não conseguir acessar /dev/hailort0
# Opção 1: adicionar o usuário ao grupo hailort
sudo usermod -aG hailort $USER

# Opção 2: executar como rootful
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### Rede

A rede padrão do Podman é `podman`, equivalente à `bridge` do Docker.
A rede customizada do `docker-compose.debug.yml` (`debug-net`) também funciona normalmente.

```bash
# Conferir redes
podman network ls
```

### Volumes

Suporta volumes nomeados e bind mounts.
Os bind mounts de `docker-compose.yml` (`./data:/app/data`) funcionam como estão.

### Integração com systemd (operação em servidor Linux)

O Podman integra facilmente com systemd. Para configurar start automático:

```bash
# Após iniciar o container, gerar unit do systemd
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# Ativar
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# Também iniciar serviços de usuário na inicialização da máquina (linger)
loginctl enable-linger $USER
```

---

## Aliases compatíveis com a CLI Docker (opcional)

Se quiser usar documentação e scripts voltados a Docker tal como estão:

```bash
# Adicionar em ~/.bashrc ou ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose
```

Como os scripts de gerenciamento detectam automaticamente, esses aliases não são obrigatórios.

---

## Troubleshooting

### Aviso `WARN[0000] "/" is not a shared mount`

```bash
# Pode ocorrer em Podman rootless. É inofensivo, mas se quiser eliminar:
podman system migrate
```

### `podman compose` não encontrado

```bash
# Em versões anteriores a 4.7, o plugin não vem embutido
# Instale podman-compose via pip
uv pip install podman-compose
```

### Não consigo acessar localhost a partir do container

Em Podman rootless, use `host.containers.internal` (equivalente a `host.docker.internal` do Docker).

```bash
# Para acessar o serviço web a partir do container debug
# Use a rede de docker-compose.debug.yml (http://web:5000); não há problema
```

### Limpeza de imagens

```bash
# Remover imagens não usadas
podman image prune -a

# Remover todos os recursos
podman system prune -a
```

---

## Resumo do suporte

| Arquivo | Compatível com Podman | Observações |
|---|---|---|
| `Dockerfile` | OK | Spec OCI padrão |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | Atenção às permissões no pass-through de dispositivo |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | Detecção automática de runtime |
| `scripts/yu-docker.sh` | OK | Detecção automática de runtime |
| `.dockerignore` | OK | Podman também consulta o mesmo arquivo |
