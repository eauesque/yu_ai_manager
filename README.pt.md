# YU AI Manager

Interface de gerenciamento de metadados para imagens geradas por IA.

## Visão geral

Ferramenta de interface web para extrair, pesquisar e gerenciar metadados incorporados em imagens geradas por IA (prompts, modelos, seeds, etc.).

**Aqui está o que você pode fazer:**

- Digitalizar pastas ou arquivos ZIP inteiros e registrar automaticamente imagens
- Pesquisar e filtrar por prompts, tags, nomes de modelos, valores de seed e muito mais
- Enviar imagens favoritas diretamente para SD / ComfyUI / NovelAI para regeneração
- Marcação automática com WD-Tagger, análise de conteúdo com Ollama/OpenAI
- Acessar de outros dispositivos (smartphones) na LAN usando código QR

**Fontes compatíveis**: Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

## Ambiente de execução

- Windows / Linux / macOS

> **Nenhuma instalação manual necessária.** `start.sh` / `start.bat` faz bootstrap automático de todas as ferramentas necessárias no projeto (sem gravação do sistema, sem privilégios de administrador).

## Configuração e inicialização

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

Configuração automática na primeira inicialização:

| Ferramenta | Método de aquisição |
| --- | --- |
| `uv` | Download automático para `./bin/uv` |
| Python 3.11+ | Instalação automática pelo `uv` |
| Node.js 22 LTS | Opcional — verifique download para `./bin/node/` (aproximadamente 30 MB) |
| pnpm | Ativado via `corepack` quando Node.js está instalado |
| ffmpeg | Opcional — Windows/macOS verificam download para `./bin/ffmpeg/` (aproximadamente 80 MB), Linux fornece instruções para `apt`/`dnf`/`pacman` do distro |

Configurando `YU_AUTO_INSTALL=1`, você pode pular prompts mesmo em ambientes não interativos (como CI). ffmpeg é apenas para recursos estendidos (análise de vídeo, S2T, OCR etc.), não é necessário para executar o aplicativo principal.

Subsequentes: reinstala e reconstrói apenas quando dependências ou fontes TypeScript são atualizados.

Você pode tornar as configurações permanentes escrevendo `--db`, `--port`, `--lan`, `--pin`, etc. em `launch-args.txt`.

## Principais recursos

### Varredura e registro
- Extração automática de metadados PNG / WebP / JPEG
- Varredura transparente de arquivos ZIP / 7z sem descompactação
- Adição de arquivos por arrastar e soltar

### Pesquisa e visualização
- Pesquisa de texto completo em prompts, tags, nomes de modelos, valores de seed
- Pesquisa de expressão regular, filtros de condição complexa
- Pesquisa de imagens similares por pHash, pesquisa semântica CLIP

### Organização e gerenciamento
- Favoritos, classificação por estrelas (1-5), anotações de notas
- Coleções (agrupamento)
- Painel de estatísticas, relatórios mensais, sistema de troféus

### Integração com ferramentas de geração (Bridge)
- Envio imediato de prompts para SD WebUI / Forge / ComfyUI / NovelAI
- Suporte para envio via clipboard

### Assistência com IA
- Marcação automática com WD-Tagger
- Análise de conteúdo de imagens usando Ollama / OpenAI
- Conversão de fala para texto (S2T)

### Rede e compartilhamento
- Modo de compartilhamento em LAN (acesso de smartphones via código QR)
- Servidor MCP (operável por agentes de IA)
- Gerenciamento de Fleet (gerenciamento centralizado de múltiplas instâncias)

### Personalização
- Sistema de UI customizada e extensão
- Suporte a temas (claro / escuro)
- Tauri desktop app (inicialização sem navegador)

## Suporte multilíngue

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## Documentação

- [Guia de inicialização rápida](docs/ja/help/user/quickstart.md)
- [Casos de uso](docs/ja/help/user/use-cases.md)
- [Referência da API](docs/ja/api/README.md)
- [Ajuste de desempenho](docs/ja/help/user/performance-tuning.md)
- [Implantação](docs/ja/help/user/deployment.md)
- [Desenvolvimento de extensão](docs/ja/plugin-development/getting-started.md)
- [UI Customizada](docs/ja/custom-ui/README.md)
- [Ferramentas MCP](docs/ja/api/MCP_TOOLS_REFERENCE.md)
- [Documentação completa](docs/ja/README.md)

## Desenvolvimento e personalização

Consulte [DEVELOPMENT.ja.md](DEVELOPMENT.ja.md) ([English](DEVELOPMENT.en.md))

## Quando tiver dúvidas, consulte a IA

### Se não iniciar

Abra a pasta do projeto como diretório de trabalho em um agente de IA como Claude Code Desktop e diga:

> `start.bat` (ou `start.sh`) para, mas não inicia. Investigue.

> **Nota**: No Claude Code Desktop, você precisa especificar a pasta do projeto antes de iniciar uma conversa.

### Problemas, configuração ou uso após inicialização

**Passo 1 — Obter contexto**

Abra a página de ajuda (`/help`) e pressione o botão **"Copiar contexto de IA"**.
Ele busca `GET /api/ai-context` usando a sessão de navegador conectada e copia o JSON para a área de transferência (funciona mesmo em ambientes LAN http://).

> **Nota (se você tiver uma chave de API)**: Se tiver uma chave de API com escopo admin, você pode chamar `GET /api/ai-context` diretamente com o header `Authorization: Bearer <key>`.

**Passo 2 — Passar para a IA**

Cole o JSON copiado em um chat com IA e escreva sua pergunta:

> [JSON colado]
> Com base nisso, resolva [descrição do problema].

`/api/ai-context` inclui a versão atual, recursos habilitados, dicas de configuração, lista de APIs e regras CSRF — tudo o que a IA precisa para ajudar com precisão.

## Perguntas frequentes

[docs/ja/FAQ.md](docs/ja/FAQ.md) ([English](docs/en/FAQ.md))

## Relatório de bugs

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## Licença

MIT License — [LICENSE](LICENSE) / [Tradução informal](docs/ja/LICENSE.md) ([English](docs/en/LICENSE.md))
