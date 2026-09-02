# Hub de Documentação

Use este arquivo como o "ponto de entrada de documentação (hub oficial)".

**Última atualização**: 2026-05-13

## Importante

- README do Projeto: [`../../README.pt.md`](../../README.pt.md)
- Changelog: [`../../CHANGELOG.pt.md`](../../CHANGELOG.pt.md)
- Master TODO (fonte única de verdade): [`../../TODO.md`](../../TODO.md)

## Diretrizes de Desenvolvimento

As diretrizes de desenvolvimento estão localizadas como arquivos individuais em `development/development_docs/`.

- **[Regras de TODO](TODO_RULES.md)** — Regras de redação de TODO (P0/P1/P2/P3 + categoria obrigatória)

### Documentos Principais (`development/development_docs/`)

| Documento | Conteúdo |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | Considere divisão em 300 linhas, divisão obrigatória em 500 linhas |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | Diretório feature-unit, 100-250 linhas é ideal |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | Modelo de três camadas de defesa (validação estática/parse/tempo de execução) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | `api_error()` unificado, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | Lista completa de pontos de entrada de todos os módulos |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | Estratégias de prevenção para 6 pontos críticos |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Design de botões Tier A/B/C |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Padrão híbrido Explorer/Library |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | Regras de posicionamento de documentação |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | Teste de fuzzing/burn-in de API e UI |

### Outra Documentação de Desenvolvimento

| Documento | Conteúdo |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | Princípios de design do desenvolvimento orientado por IA |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | Convenção de operações em lote |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Ciclo de vida dos hooks de Extensão |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | Lista de widgets de UI reutilizáveis |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | Especificação de sintaxe de prompt SD/NAI |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | Codificação de nome de arquivo de arquivo |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Tabela de compatibilidade de formatos de imagem da Vision API |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | Resultados de ciclo QA e questões pendentes |

### Registros de Desenvolvimento e Especificações

| Documento | Conteúdo |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Registro de desenvolvimento de CLIP Hailo-10H |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | Registro de desenvolvimento de CLIP ONNX multi-backend |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Controle de dispositivo Hailo |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | Especificação aprimorada do registro de chat |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Integração de aplicativo desktop Tauri |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Especificação de extensão Freeze & Pull-back |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | Plano de metadados de vídeo v2 (Rascunho) |

## Caminhos de Importação

Todos os imports usam caminhos de módulo reais diretos. O mecanismo de aliases foi removido.

**Exemplos de caminho principal:**
- `core.services_core.db_api` — Acesso DB (antigo `core.db`)
- `core.configuration.api` — Gerenciamento de configuração (antigo `core.config`)
- `core.extensions_core.runtime` — Tempo de execução de extensão (antigo `core.extensions`)
- Novos recursos adicionados diretamente ao diretório `core/<feature>_core/`

## Solução de Problemas e Operações

- Playbook de depuração: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Erros comuns (legado): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- Armadilhas de codificação CJK / 2 bytes: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- Erro de análise de colchetes com escape: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Recursos

| Documento | Status | Conteúdo |
|---|---|---|
| [Guia de Integração MCP](features/mcp-integration-guide.md) | Atual | Operar yu_ai_manager a partir de LLM |
| [NovelAI V4](features/novelai-v4.md) | Atual | Formato de prompt NovelAI V4 e suporte a negativo por personagem |
| [Busca Semântica Hailo](features/hailo-semantic-search.md) | Implementado → Migração ONNX | Instruções de implementação Hailo-10H CLIP |
| [Geração Automática de Tags Danbooru](features/danbooru-tag-gen-spec.md) | Implementado (v2.77.0) | WD-Tagger + abordagem de duas camadas VLM |
| [Gerenciamento de Texto e Registro de Chat](features/text-chatlog-management-spec.md) | Atual | Importação de Chatlog e busca FTS |
| [Protocolo QR v1](features/qr-protocol-v1.md) | Atual | Código QR para compartilhamento de LAN |
| [Benchmark de Busca com Expressão Regular](features/regex-search-benchmark.md) | Atual | Desempenho de Regex |
| [Compatibilidade de Navegador](features/browser-compatibility.md) | Atual | Lista de navegadores suportados |

## Referência de API

- [Visão Geral da API (Autenticação, CSRF, Limite de Taxa)](api/README.md)
- [API de Busca](api/search.md)
- [API de Arquivos](api/files.md)
- [API de Varredura](api/scan.md)
- [Eventos SSE](api/events.md)
- [Variáveis CSS de Tema](api/theming.md)

## Desenvolvimento de UI Personalizada / Plugin

- [Guia de UI Personalizada](custom-ui/README.md) — Desenvolvimento de UI personalizada (quickstart, design, templates, advanced)
- [Guia de Desenvolvimento de Plugin](plugin-development/getting-started.md) — Introdução ao desenvolvimento de Extensão
- [Referência de Manifesto](plugin-development/manifest-reference.md) — Especificação extension.json

## Instalação

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Documentação Histórica

O seguinte são notas de implementação passadas / registros de hotfix (localizados em `archive/docs_history/`).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — Instruções de depuração da era v2.5.4
- `DARK_MODE_TAGS_IMPROVEMENT.md` — Proposta de melhoria de tags em modo escuro (implementada)
- `EXTENSION_DRAFT.md` — Rascunho inicial do sistema de Extensão (sucessor em plugin-development/)
