# Material de Desenvolvimento Hailo-10H AI Hat+

Registros de implementação de inferência de IA usando Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H).

Publicando conhecimentos obtidos no desenvolvimento real em áreas onde a documentação oficial é insuficiente.

## Lista de Documentos

| Arquivo | Conteúdo |
|---------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | Notas de migração HailoRT 5.2.0 → 5.3.0. Diferenças de API, renomeação do nó de dispositivo (`/dev/h1x-0`), compatibilidade HEF, script de smoke test |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | Padrão de implementação do gerenciador VDevice compartilhado para fazer coexistir múltiplos modelos (YOLO/CLIP/LLM/VLM/Whisper) no mesmo processo |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Limitações de alocação CMA do Pi 5 (comportamento sob `numa=fake=8`). Por que `cma=1G` falha silenciosamente, `cma-512` (`dtoverlay=cma,cma-512` em `config.txt`) como limite verificado e valor recomendado, requisitos de memória do Hailo GenAI, comportamento de não devolução de CMA pelo `VDevice.release()` |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Log de desenvolvimento da pesquisa semântica CLIP. Registros de implementação por fase, problemas encontrados e soluções |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Métodos de controle do dispositivo Hailo, gerenciamento VDevice, controle exclusivo, troca de modelos |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | Guia de conversão ONNX → HEF. Dataflow Compiler, quantização, resolução de problemas |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | Relatório de verificação de conversão (DFC v5.2.0). Análise detalhada das falhas nos 3 modelos WD-Tagger |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | Acompanhamento DFC v5.3.0. Reverificação dos mesmos 3 modelos WD-Tagger (ainda falhando), além de melhorias confirmadas no v5.3.0 (novo `_create_layer_normalization_layer`, fluxo de nova tentativa onnxsim, recomendação de end-node) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | Log de desenvolvimento CLIP ONNX multi-backend. Fallback para ambientes sem hardware Hailo |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **Restrição estrutural e medição real do vazamento de CMA**. `VDevice.release()` não recupera; vazamento contínuo durante a inferência (cerca de 14 MB/min); e **não é recuperado nem por kill do processo filho, nem por saída do processo, nem por descarregamento do módulo** (medido de forma independente 2 vezes no PoC da Phase 0, com apenas +8 MB após SIGTERM + 30s de espera). O único meio confiável de recuperação é reiniciar o próprio Pi **(conclusão antiga. Corrigida por reteste no HailoRT / driver 5.4.0 em [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **Correção e reverificação do julgamento de vazamento de CMA acima**. Comparação A/B entre o vanilla oficial e a versão corrigida com `FOLL_LONGTERM` no HailoRT / driver 5.4.0, corrigindo o julgamento antigo, que era incorreto por considerar apenas a quantidade absoluta de recuperação de `CmaFree` após o carregamento inicial do HEF. Inclui a diferença de código-fonte v5.3.0 → v5.4.0, as armadilhas do procedimento de compilação própria e dados de medição real |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | Guia operacional da linha de reboot automático adotada com base no acima. Fase de observação (`would_fire` é apenas registrado, sem reiniciar), limiares de decisão, motivo do `mode = "off"` padrão |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | Runbook da mesma fase para este ambiente. Procedimentos de início, verificação e encerramento da observação |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | Log de implementação que resolveu o problema do Quart event loop travar por causa do GIL durante o cold_load (~71 segundos), isolando a inferência de chat LLM em subprocess |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Avaliação do ecossistema Hailo-10H (2026-03-19, na época do HailoRT/DFC v5.2.0) |

## Problemas Conhecidos Importantes

### Ambiente / Raspberry Pi 5

- **O limite de CMA no Pi 5 (8 GB) é 512 MB, configurado em `config.txt`**: O kernel padrão aplica `numa=fake=8`, dividindo a RAM em 8 nós NUMA × 1 GB. A CMA precisa caber dentro de um único limite de nó, e `cma-1024` e `cma-768` falham silenciosamente (`CmaTotal=0` sem kernel panic). **`cma-512` é o limite verificado e o valor recomendado** (revalidado via overlay em 2026-05-16, `CmaTotal: 524288 kB`). Devido a uma regressão de firmware em 2026-05, usar `dtoverlay=cma,cma-512` em `/boot/firmware/config.txt`, e não `cma=` na cmdline. Ver detalhes em [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)
- **Sempre verificar CMA após reinicialização**: Confirmar com `grep CmaTotal /proc/meminfo`. Se 0, a configuração foi ignorada
- **`VDevice.release()` não devolve a CMA**: A CMA é mantida durante toda a sessão do OS. Tratar o VDevice como um singleton de escopo de sessão. **Não é recuperada nem com o reinício do processo** — verificou-se de forma independente, 2 vezes, no PoC da Phase 0, que não é recuperada nem por kill do processo filho, nem por saída do processo, nem por descarregamento do módulo (apenas +8 MB após SIGTERM + 30 segundos de espera, com valor esperado ≥250 MB). O único meio confiável de recuperação é `sudo reboot` (power-cycle do PCIe) do próprio Pi. Detalhes e a solução adotada em [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md). **Correção**: este item baseia-se na medição antiga. O reteste A/B no HailoRT / driver 5.4.0 não reproduziu um vazamento de CMA de relevância prática, e foi corrigido em [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8
- **`numa=fake=8` afeta instalação do Node.js**: Memória por nó NUMA (1 GB) é detectada erroneamente como RAM total, e instaladores npm/node abortam. Reportado upstream: [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Wheel Python requer compilação do fonte**: Sem wheel em PyPI ou na Hailo Developer Zone para aarch64
- **Exclusividade com hailo-ollama**: VDevice em uso requer parar o hailo-ollama
- **Vazamento de VDevice ao sair do processo**: Verificar com `lsof /dev/hailo*` e usar `kill PID` para tratar

### VDevice / API

- **Usar InferModel API**: `VDevice.create_infer_model()` é o correto. API VStreams legada (`InferVStreams`, `ConfigureParams.create_from_hef`) retorna `HAILO_NOT_IMPLEMENTED` no Hailo-10H
- **InferModel suporta apenas modelos simples**: HEF YOLO de 1 entrada funciona, mas HEF Whisper de 2 entradas e 4 saídas retorna `HAILO_INVALID_ARGUMENT` em `configure()`. Usar GenAI SDK para modelos complexos
- **VDevice mapeia para 1 dispositivo físico**: Criar 2 instâncias de `VDevice()` simultaneamente resulta em `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **Liberar completamente VDevice ao trocar modelos**: Apenas definir referência Python como `None` é insuficiente. Liberar o dispositivo físico explicitamente com `VDevice.release()` antes de criar novo VDevice
- **`set_format_type(FormatType.FLOAT32)` não suportado no hailort 5.2.0**: Atributo `format_type` não existe. Fazer quantização/desquantização manual em uint8 ou usar GenAI SDK
- **Saída é quantizada em uint8**: Alocar buffer de saída em float32 resulta em `buffer size mismatch`. Alocar em uint8 e converter para float32 com parâmetros de desquantização (scale, zero_point)

### GenAI (LLM / VLM / Speech2Text)

- **No HailoRT 5.3.0, `temperature=0.0` é rejeitado**: `LLM.generate()` lança `HAILO_INVALID_ARGUMENT` com `temperature=0`. Clampar antes de chamar: `temperature = max(temperature, 0.01)`. Afeta quando clientes compatíveis com OpenAI enviam `temperature=0` por padrão
- **Possível carregar 2 GenAI simultaneamente**: LLM + Whisper-tiny podem ser carregados simultaneamente no mesmo VDevice (confirmado no HailoRT 5.3.0). Margem CMA ao carregar ambos: aproximadamente 10 MB de 256 MB. Whisper-base ou maior pode transbordar a memória
- **Orçamento CMA LLM + Whisper-tiny**: Total de cerca de 246 MB (valor medido). Consulte [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) para números de CMA de todos os modelos

### Whisper (Reconhecimento de Voz)

- **Usar GenAI SDK**: `hailo_platform.genai.Speech2Text` fornece o pipeline completo. Executa encoder+decoder completamente na NPU
- **HEF é apenas o decoder**: `Whisper-Base.hef` tem 2 entradas (encoder_features + token_embeddings) e 4 saídas (vocab dividido em 4). Não funciona com InferModel API
- **Entrada do GenAI SDK**: Dados de áudio PCM normalizados little-endian float32 (`<f4`), [-1,1]
- **Fallback ONNX**: Quando GenAI SDK não está disponível, executar encoder+decoder em CPU com modelo ONNX do HuggingFace

### YOLO (Detecção de Objetos)

- **Funciona com InferModel API**: HEF de 1 entrada não tem problema
- **Fallback ONNX**: Quando Hailo não está disponível, baixar automaticamente `yolo11n.onnx`. Saída `(1,84,8400)` é compatível com yolov8n
- **Cooldown após falha de inicialização**: Não tentar novamente por 60 segundos após falha na inicialização do engine

### Inferência Distribuída

- **Health check obrigatório**: Confirmar disponibilidade de nós remotos com `filter_available()` antes de iniciar distribuição
- **Em caso de falha remota**: Fallback de itens restantes para processamento local. Auto-detecção no próximo lote quando recuperar
- **Distribuição de carga de trabalho**: Grande diferença de velocidade entre GPU vs NPU, e divisão igual não é eficiente. Distribuição dinâmica baseada em medição de throughput é tarefa futura
