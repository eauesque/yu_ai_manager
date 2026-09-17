# Extensions

O YU AI Manager permite adicionar funcionalidades pelo sistema de Extensions.
Atualmente acompanham 43 Extensions embutidas, distribuídas em 6 categorias.

## Lista de Extensions embutidas

### Extração de metadados (metadata)

| Extension | Descrição |
|-----------|------|
| builtin-a1111 | Extração de metadados PNG/WebP/WebM do Automatic1111 / SD WebUI |
| builtin-novelai-v3 | Extração de metadados até NovelAI V3 |
| builtin-novelai-v4 | Extração de metadados NovelAI V4 (suporte a Character Prompts, Vibe Transfer) |
| builtin-comfyui | Análise do workflow JSON do ComfyUI |
| builtin-annotations | Salvar, buscar e operações em lote de anotações de arquivos |
| builtin-ratings | Sistema de avaliação por estrelas (1 a 5 estrelas) |
| builtin-tag-dictionary | Busca, importação e divisão do dicionário de tags do Danbooru |

### Integração com Bridge (bridge)

| Extension | Descrição |
|-----------|------|
| builtin-sd-webui-bridge | Integração com SD WebUI / Forge (geração de imagens, gerenciamento de modelos) |
| builtin-nai-bridge | Integração com a API do NovelAI (geração de imagens) |
| builtin-comfyui-bridge | Integração com ComfyUI (execução de workflow) |

### Prompt (prompt)

| Extension | Descrição |
|-----------|------|
| builtin-prompt-library | Biblioteca de prompts e organização |
| builtin-prompt-syntax | Realce de sintaxe de prompts e detecção de erros (suporta NAI/SD/DP) |
| builtin-prompt-simulator | Simulador de Dynamic Prompts, cálculo de pesos e conversão |
| builtin-sd-nai-convert | Conversão bidirecional entre prompts SD ↔ NovelAI |

### IA (ai)

| Extension | Descrição |
|-----------|------|
| builtin-analysis | Análise de imagens por IA (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | Tagueamento automático com WD-Tagger (engines ONNX + VLM) |
| builtin-ocr | OCR via VLM — extração de texto, análise estruturada, tradução |
| builtin-clip-search | Engine de busca semântica de imagens com CLIP |
| builtin-clip-onnx | Backend do encoder CLIP em ONNX Runtime |
| builtin-clip-coreml | Encoder CLIP em Core ML (Apple Neural Engine) |
| builtin-hailo-semantic-search | Busca semântica Hailo-10H |
| builtin-hailo-yolo-detect | Detecção de objetos YOLO com Hailo-10H |
| builtin-hailo-genai | GenAI com Hailo-10H (LLM/VLM/S2T) |
| builtin-speech-to-text | Transcrição de fala (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-audio-analysis | Análise de áudio (Whisper local / OpenAI API) |
| builtin-video-analysis | Análise de vídeo por IA (múltiplos keyframes + Gemini) |
| builtin-inference | Detecção de providers do ONNX Runtime e aceleração por GPU |

### Biblioteca (library)

| Extension | Descrição |
|-----------|------|
| builtin-favorites-manager | Gerenciamento de favoritos e coleções |
| builtin-freeze-pullback | Geração de vídeo Freeze & Pull-back (efeito Ken Burns) |
| builtin-download | Download em lote em ZIP das imagens selecionadas |
| builtin-chatlog | Importador e visualizador de logs de chat (Claude / ChatGPT) |
| builtin-md-viewer | Visualizador de arquivos Markdown (busca full-text FTS5) |
| builtin-cross-search | Busca cruzada (MD, logs de chat, prompts, texto) |
| builtin-lan-share | Compartilhamento de coleções na LAN (autenticação por token com tempo limitado) |
| builtin-stats | Insights estatísticos (linha do tempo, marcos) |
| builtin-trophy | Sistema de troféus e conquistas |
| builtin-export | Hook de exportação (conversão de registros ao gerar CSV) |

### Sistema (system)

| Extension | Descrição |
|-----------|------|
| builtin-auto-scan-watcher | Detecção automática de mudanças de arquivos e atualização incremental |
| builtin-mcp-client | Gerenciamento de conexões com servidores MCP externos |
| builtin-backup | Backup, restauração e agendamento do DB |
| builtin-sns-share | Compartilhamento em redes sociais (Bluesky, X/Twitter) |
| builtin-webhook | Dispatcher de Webhooks (entrega HTTP orientada a eventos) |
| builtin-debug-check | CLI de diagnóstico de depuração |
| builtin-github-integration | Monitoramento de Issues, triagem e rastreamento de PR/Discussion/Release no GitHub |

## Gerenciamento de Extensions

Na aba Settings > Extensions, as seguintes operações estão disponíveis:

- **Ativar/desativar**: alternar instantaneamente pelo toggle switch
- **Nova instalação**: instalar especificando a URL de um repositório Git
- **Marketplace**: buscar Extensions públicas e instalar com um clique
- **Atualizar**: atualizar Extensions baseadas em Git para a versão mais recente
- **Desinstalar**: remover Extensions de terceiros

### Gerenciamento via API

```bash
# Lista de Extensions
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# Ativar/desativar
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Instalar a partir do Git
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension Sandbox

Extensions de terceiros são protegidas por sandbox.

### Níveis de confiança

| Nível | Alvo | Restrições |
|--------|------|------|
| L0 (TRUSTED) | `builtin-*` | Sem restrições |
| L2 (UNTRUSTED) | Outras | Restrições de DB/FS/rede |

### Quatro fases do sandbox

1. **Capability Token**: gerenciamento de permissões com token assinado em HMAC-SHA256. Validade de 24 horas
2. **SandboxedDB / SandboxedFS**: Extensions com apenas `db:read` só permitem SELECT. O acesso a arquivos é controlado por path
3. **SandboxedHTTPClient / ImportGuard**: prevenção de SSRF, monitoramento de import em runtime, detecção de adulteração por SHA-256
4. **Isolamento de processo (Linux)**: L2 Extensions executam em processos separados. IPC via JSON-RPC 2.0 em Unix socket

### Isolamento em nível de SO (opcional)

- **Linux**: geração automática de perfil AppArmor
- **macOS**: sandbox-exec (experimental)
- **Windows**: Restricted Token + Job Object

> **Dica**: Para detalhes sobre desenvolvimento de Extensions, consulte a seção "Desenvolvimento de Extensions".

## Estrutura de diretórios

```
extensions/builtin_<name>/
  extension.json            # manifest (nome, versão, permissões etc.)
  <name>_ext.py             # entry point (expõe get_blueprint())
  templates/<name>/          # templates Jinja2
  core_impl/                 # lógica de negócio (opcional)
```

### Campos obrigatórios de extension.json

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

As categorias são: `metadata`, `bridge`, `prompt`, `ai`, `library`, `system` (6 tipos).

## Extension Module API v2 (suporte a ES Module)

A partir da v4.29.0, é possível escrever Extensions usando o padrão de ES Module com `<script type="module">` e Import Maps.

### Como habilitar

Adicione `"script_type": "module"` em `extension.json`:

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entry": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library",
  "script_type": "module"
}
```

### Como usar

Altere o `<script>` do template para `<script type="module">` e importe de `yu-api`:

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Toast notification
showToast('Salvo');

// Subscribe to SSE events
sseSubscribe('scan.progress', (data) => {
  console.log('progresso:', data);
});

// i18n translation
const label = tr('my_ext.title', 'My Extension');

// API call (CSRF header is added automatically)
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### Lista de APIs públicas

| Função | Descrição |
|---|---|
| `showToast(message, isError?)` | Exibe uma notificação toast |
| `sseSubscribe(eventType, handler)` | Se inscreve em eventos SSE |
| `sseUnsubscribe(eventType, handler)` | Cancela a inscrição em eventos SSE |
| `tr(path, a?, b?)` | Resolve uma chave de tradução i18n |
| `apiFetch(path, opts?)` | Wrapper de fetch com CSRF |
| `apiUrl(path)` | Constrói URL de API |
| `escapeHtml(text)` | Escapa caracteres especiais de HTML |

### Definições de tipo TypeScript

Ao copiar `src/ts/extension-api/extension-api.d.ts` para o projeto da Extension, ativam-se o autocomplete e a verificação de tipos da IDE.

### Compatibilidade legada

Extensions com `"script_type": "classic"` (padrão) continuam podendo usar as funções globais como `window.showToast()`. Não é necessário reescrever Extensions existentes.

## Documentação de desenvolvimento

Você pode consultar o conhecimento de desenvolvimento sobre a criação de Extensions, decisões de design internas, pontos de atenção conhecidos e dicas de depuração no [MD Viewer](/ext/md-viewer/). O diretório `docs/development/development_docs/` já está registrado e também é compatível com a busca full-text FTS5.
