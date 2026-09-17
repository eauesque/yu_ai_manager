# Guia de Instalação do ffmpeg

O Tag Database usa o ffmpeg para gerar miniaturas de arquivos de vídeo (WebM, MP4 etc.).

## Windows

### Opção 1: Scoop (recomendado)
```powershell
# Instalar o Scoop (se ainda não tiver)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Instalar o ffmpeg
scoop install ffmpeg
```

### Opção 2: Chocolatey
```powershell
# Instalar o Chocolatey (se ainda não tiver)
# Executar como administrador
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Instalar o ffmpeg
choco install ffmpeg
```

### Opção 3: Download manual
1. Baixe em: https://www.gyan.dev/ffmpeg/builds/
2. Extraia em `C:\ffmpeg`
3. Adicione ao PATH:
   - Abra "Variáveis de Ambiente"
   - Edite "Path"
   - Adicione `C:\ffmpeg\bin`
4. Reinicie o terminal

---

## macOS

### Homebrew (recomendado)
```bash
# Instalar o Homebrew (se ainda não tiver)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Instalar o ffmpeg
brew install ffmpeg
```

---

## Linux

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Fedora
```bash
sudo dnf install ffmpeg
```

### Arch
```bash
sudo pacman -S ffmpeg
```

---

## Confirmação da instalação

```bash
ffmpeg -version
```

Se as informações de versão aparecerem, a instalação foi bem-sucedida.

---

## Teste de miniaturas de vídeo

```bash
# Iniciar a WebUI
python web_ui.py --db tags.db

# Vá até um arquivo WebM
# As miniaturas são geradas automaticamente
```

---

## Troubleshooting

### Erro "ffmpeg not installed"

**Sintoma**: mensagem de erro exibida na miniatura do vídeo

**Soluções**:
1. Verifique se o ffmpeg está instalado: `ffmpeg -version`
2. Reinicie o terminal / PowerShell
3. Reinicie a WebUI
4. Confira as configurações do PATH

### Miniaturas não são geradas

**Sintoma**: na miniatura aparece "Failed to extract video frame"

**Causas possíveis**:
- Arquivo de vídeo corrompido
- Codec de vídeo não suportado
- Timeout do ffmpeg (ultrapassou 10 segundos)

**Depuração**:
```bash
# Testar manualmente
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# Checar logs
# Procure por mensagens "[ERROR] ffmpeg"
```

---

## Opcional: aceleração por GPU

Para processar vídeo mais rápido (para usuários avançados):

### Windows (NVIDIA)
```bash
# Baixe o build NVIDIA:
# https://www.gyan.dev/ffmpeg/builds/
# Escolha "ffmpeg-release-full.7z"
```

### macOS (VideoToolbox)
```bash
# Já incluído no build do Homebrew
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## Notas sobre desempenho

- Primeira geração de miniatura: cerca de 1 a 3 segundos
- Miniatura em cache: menos de 100ms
- Arquivos ZIP: processados após extração para diretório temporário
- Timeout: 10 segundos por vídeo

---

## Sem o ffmpeg

Se o ffmpeg não estiver disponível:
- As miniaturas dos vídeos exibem erro
- A busca de vídeos por metadados continua funcionando
- Para usar as funcionalidades completas, recomendamos instalar o ffmpeg
