# Índice da Documentação de Desenvolvimento

Lista de documentos internos de design, materiais técnicos e logs de desenvolvimento.
Todos os arquivos estão armazenados em `docs/development/development_docs/`.

Também é possível lê-los diretamente com a ferramenta `source_read` do MCP.

---

## Design e Arquitetura

| Documento | Conteúdo |
|-------------|------|
| DESIGN_PHILOSOPHY | Filosofia de design — diretrizes e critérios de decisão de todo o projeto |
| MODULE_ORGANIZATION_GUIDELINES | Diretrizes de organização de módulos |
| CODE_SIZE_GUIDELINES | Diretrizes de tamanho de código (critérios de divisão de arquivos) |
| ENTRYPOINT_MAP | Lista de entry points |
| DOCUMENT_LIFECYCLE | Política do ciclo de vida dos documentos |
| UI_STATE_SPEC | Especificação de estado da UI (híbrido Explorer/Library) |
| NOTIFICATION_PROGRESS_DESIGN | Diretrizes de design de notificações e exibição de progresso |

## API e Processamento em Lote

| Documento | Conteúdo |
|-------------|------|
| API_RESPONSE_GUIDELINES | Diretrizes de formato de resposta da API |
| BATCH_API_STANDARD | Especificação padrão de API em lote |
| ERROR_HANDLING | Política de tratamento de erros |

## Sistema de Extensions

| Documento | Conteúdo |
|-------------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | Especificação do modelo de segurança com separação de poderes |
| EXTENSION_SANDBOX_SPEC | Especificação de Sandbox & Permission |
| EXTENSION_HOOKS_SPEC | Especificação de Extension Hooks |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Especificação do Freeze & Pull-back Generator |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Especificação de migração Core → Extension |

## Integração com IA e Agentes

| Documento | Conteúdo |
|-------------|------|
| AGENT_INTEGRATION_DESIGN | Guia de design de integração de AI Agent |
| AGENT_SAFETY_GATEWAY_SPEC | Especificação do AI Agent Safety Gateway |
| AI_ANALYSIS_LANGUAGE | Especificação de idioma de resposta para análise por IA |
| MCP_DEBUG_TOOLS | Especificação das ferramentas de depuração MCP |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Armadilhas e contramedidas da integração Ollama/VLM |
| OPENAI_COMPAT_API_DEVLOG | Log de desenvolvimento da API compatível com OpenAI |
| VLM_ROUTING_OCR_SPEC | Especificação de design de VLM Model Routing & OCR |
| VISION_API_IMAGE_FORMATS | Tabela de suporte a formatos de imagem da Vision API |
| ai-driven-development-principles | Princípios de design do desenvolvimento orientado por IA |

## Banco de Dados e Desempenho

| Documento | Conteúdo |
|-------------|------|
| SQLITE_READONLY_SEPARATION | Padrão de separação leitura/escrita em SQLite |
| LARGE_SCALE_QUERY_OPTIMIZATION | Otimização de queries de DB em larga escala (280K arquivos) |

## Front-end e UI

| Documento | Conteúdo |
|-------------|------|
| UI_AUDIT_GUIDE | Guia integral de auditoria de UI |
| UI_BUTTON_PRIORITY_GUIDELINES | Diretrizes de priorização de botões (estilo controlador GC) |
| REUSABLE_UI_WIDGETS | Guia de integração de widgets de UI reutilizáveis |
| VIRTUAL_SCROLL_PITFALLS | Scroll virtual: notas e coleção de bugs conhecidos |
| IMAGE_DISPLAY_OPTIMIZATION | Material técnico de otimização de exibição de imagens |
| MODAL_LOADING_OPTIMIZATION | Material técnico de aceleração de carregamento da modal de detalhes |
| MODAL_MEDIA_LIFECYCLE | Gerenciamento do ciclo de vida de mídia em modais |
| CONTAINER_VIEW_PERFORMANCE | Otimização de desempenho da container view |
| BROWSER_CONNECTION_SATURATION | Perda de resultados de busca por saturação de conexões do navegador |

## Processamento de Vídeo

| Documento | Conteúdo |
|-------------|------|
| VIDEO_STREAMING_ARCHITECTURE | Arquitetura de streaming de vídeo |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | Registro completo da otimização de desempenho de vídeo |
| VIDEO_METADATA_V2_PLAN | Plano de Video Metadata v2 (rascunho) |

## Processamento de Arquivos e Arquivos Compactados

| Documento | Conteúdo |
|-------------|------|
| NESTED_ZIP_HANDLING | Design e armadilhas do tratamento de ZIP aninhado |
| ZIP_SCAN_PERFORMANCE | Otimização de desempenho de scan de ZIP/7z |
| ENCODING_FALLBACK | Fallback de encoding de nomes em arquivos compactados |
| SD_NAI_PROMPT_SYNTAX_SPEC | Especificação de sintaxe de prompts SD / NAI |

## Multiplataforma e Infraestrutura

| Documento | Conteúdo |
|-------------|------|
| CROSS_PLATFORM_ISSUES | Guia de diferenças entre plataformas |
| DRAG_TO_SHARE_CROSS_PLATFORM | Suporte multiplataforma a drag & drop |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | Correção de bloqueio do event loop de asyncio |
| MODULE_SAFETY | Design de carregamento seguro de módulos |
| DOCKER_SETUP | Guia de configuração do ambiente Docker |
| TAURI_DESKTOP_APP | Guia de desenvolvimento do app desktop Tauri |

## Transição e Migração

| Documento | Conteúdo |
|-------------|------|
| QUART_MIGRATION_DEVLOG | Material técnico da migração Flask → Quart (ASGI) |
| CHATLOG_ENHANCED_SPEC | Especificação aprimorada de chat log |

## Teste e Garantia de Qualidade

| Documento | Conteúdo |
|-------------|------|
| FUZZ_BURN_IN_TEST | Guia de testes Fuzz / Burn-in |
| QA_HANDOFF | Documento de handoff de investigação de qualidade |
| yu-ai-manager-qa-agent-prompt | System prompt do agente de QA |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | Pontos de acidente frequentes e guia de velocidade da camada comum |
| BUG_VIDEO_AI_ANALYZED_FILTER | Registro de bug: filtro de vídeo + analisado por IA |

## Release e Tradução

| Documento | Conteúdo |
|-------------|------|
| RELEASE_PROCEDURE | Procedimento de release |
| TRANSLATION_STYLE_GUIDE | Guia de estilo de tradução japonês-inglês |
