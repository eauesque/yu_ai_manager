# Avaliação do Ecossistema Hailo-10H

**Data de criação**: 2026-03-19  
**Alvo**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)  
**HailoRT**: v5.2.0  
**DFC**: v5.2.0  
**Objetivo**: Registrar a experiência de desenvolvimento com o Hailo-10H neste projeto e organizar restrições realistas e perspectivas futuras

---

## Avaliação Geral

**O hardware é excelente. O ecossistema de software é decisivamente inadequado.**

O Hailo-10H é uma NPU com desempenho de inferência de 40 TOPS, com potencial suficiente como hardware. No entanto, como a toolchain de software é fechada e imatura, os desenvolvedores **praticamente não conseguem** trazer livremente seus próprios modelos e executá-los.

Neste projeto, desenvolvemos implementações de pesquisa semântica CLIP, detecção de objetos YOLO, chat LLM/VLM, reconhecimento de voz Whisper e servidor tagger distribuído — usando o Hailo-10H de forma abrangente. No entanto, tudo que funciona de forma estável **usa HEFs pré-compilados baixados do Model Zoo oficial da Hailo**, e **nunca conseguimos converter** um modelo personalizado de ONNX para HEF.

---

## Status de Implementação Neste Projeto

### Funcionalidades Funcionando (todas usando download de HEF oficial)

| Funcionalidade | API Usada | Origem do HEF |
|------|---------|-----------|
| Encoder de imagens CLIP | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Detecção de objetos YOLO | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Chat LLM | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| Inferência VLM imagem+texto | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Reconhecimento de voz Whisper | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### Funcionalidades que Não Funcionaram (falha na conversão HEF)

| Funcionalidade | O que foi tentado | Resultado |
|------|-----------|------|
| WD-Tagger (SwinV2) | Conversão ONNX → HEF | DFC não conseguiu processar LayerNormalization |
| WD-Tagger (ViT) | Conversão ONNX → HEF | Idem |
| WD-Tagger (ConvNeXt) | Conversão ONNX → HEF | DFC não conseguiu processar operação Transpose |

### Destaques de Implementação

Neste projeto, todas as funcionalidades foram implementadas **chamando diretamente** a API Python do wheel `hailo_platform`. Não foram usados hailo-ollama nem hailo-apps.

Em particular, os seguintes foram construídos antes de serem fornecidos oficialmente pela Hailo:

- **Gerenciador de dispositivos com controle exclusivo VDevice** — alternância automática de CLIP/YOLO/LLM/VLM/S2T em um único VDevice. O hailo-apps não tem mecanismo de compartilhamento de dispositivo
- **Fallback multi-backend** — alternância automática transparente Hailo → CoreML → ONNX Runtime
- **Pipeline de desquantização uint8** — restauração de float32 a partir de scale/zero_point de `quant_info`
- **Arquitetura de inferência distribuída LAN** — tagging paralelo work-stealing em múltiplas máquinas

Esses desenvolvimentos foram feitos em um **estado onde a documentação da API praticamente não existia**. As especificações de entrada/saída da API InferModel, os requisitos de tamanho de buffer e os métodos para obter parâmetros de quantização foram todos descobertos a partir de mensagens de erro e suposições sobre o código-fonte.

---

## Problemas com o Hailo Dataflow Compiler (DFC)

### O que é o DFC

O compilador que converte modelos ONNX / TensorFlow para o formato HEF (Hailo Executable Format) para Hailo-10H. Executa em x86_64 Linux com o seguinte pipeline:

```
model.onnx → HAR (float32) → Otimização → Quantização (INT8) → Compilação → model.hef
```

### A Realidade

**O DFC só consegue converter adequadamente arquiteturas que a Hailo pré-validou para seu próprio Model Zoo.**

Tentativas de conversão neste projeto (2026-03-06, DFC v5.2.0):

| Modelo | Tamanho | Erro | Fase Alcançada |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` em `_convert_axes_to_nhwc` | Antes da otimização |
| wd-vit-tagger-v3 | 362 MB | Idem | Antes da otimização |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | Antes da otimização |

Todos os 3 modelos falharam **no nível do parser, antes de atingir a fase de otimização**. 500 imagens de calibração foram preparadas, mas nunca foram usadas.

### Causa Raiz

O parser ONNX do DFC não consegue processar os seguintes operadores:

- `LayerNormalization` (conversão de eixo em tensores multidimensionais)
- `Transpose` (padrões de conversão channels-last/first)

Esses são componentes básicos de arquiteturas baseadas em Transformer (SwinV2, ViT, ConvNeXt, etc.), usados na grande maioria dos modelos principais desde 2022.

### Escopo de Cobertura Efetiva do DFC

| Arquitetura | Suporte DFC | Base |
|---------------|---------|------|
| CNNs como ResNet, MobileNet | ✓ Suportado | Muitos no Model Zoo |
| YOLO v5/v8/v11 | ✓ Suportado | HEF no Model Zoo |
| CLIP ViT (versão Hailo) | ✓ Suportado | HEF no Model Zoo (convertido pela Hailo) |
| SwinTransformer V2 | ✗ Não suportado | Falha na conversão LayerNorm |
| Vision Transformer (genérico) | ✗ Não suportado | Falha na conversão LayerNorm |
| ConvNeXt | ✗ Não suportado | Falha na conversão Transpose |

> **Nota**: O fato do CLIP ViT estar no Model Zoo provavelmente indica que a Hailo realizou tratamento especial (transformações manuais de grafo ou parser personalizado) internamente. Mesmo o mesmo ViT falhará quando os usuários comuns tentarem convertê-lo com DFC.

---

## Problemas com o Formato HEF

- **Especificações binárias não públicas** — A Hailo não publica documentação do formato
- **Sem outros meios de geração além do DFC** — Impossível criar HEF com ferramentas de terceiros
- **Engenharia reversa também impraticável** — Requer conhecimento da arquitetura de conjunto de instruções e fluxo de dados da NPU

Em outras palavras, modelos que o DFC não consegue converter **simplesmente não podem ser executados no Hailo-10H**. Não existe alternativa.

---

## Avaliação da Toolchain de Desenvolvimento

### hailo_platform (Python SDK)

| Item | Avaliação |
|------|------|
| API InferModel | Funciona, mas documentação é extremamente insuficiente |
| API GenAI (LLM/VLM/S2T) | Relativamente fácil de usar. No entanto, muitos comportamentos não documentados |
| Distribuição de wheel Python | Não no PyPI. Wheel aarch64 precisa ser compilado do fonte |
| Mensagens de erro | Mínimas. Difícil identificar causa de incompatibilidades de tamanho de buffer |
| Gerenciamento de VDevice | Apenas acesso exclusivo. Multi-modelos simultâneos não são possíveis |

### Comportamentos Não Documentados Descobertos Durante o Desenvolvimento

1. **InferModel API é a correta** — A API VStreams legada (`InferVStreams`, `ConfigureParams.create_from_hef`) retorna `HAILO_NOT_IMPLEMENTED` no Hailo-10H
2. **Saída é quantizada em uint8** — Alocar buffer em float32 resulta em `buffer size mismatch`. Precisa alocar em uint8 e desquantizar depois
3. **`input()`/`output()` são propriedades** — Não são métodos (inconsistente com outras APIs Hailo)
4. **Obtenção de `quant_info`** — `infer_model.output().quant_info` pode ser obtido com scale/zero_point, mas não existe documentação explicando isso
5. **Exclusividade com hailo-ollama** — VDevice em uso requer parar o hailo-ollama. A causa não é clara a partir das mensagens de erro

---

## Comparação com Produtos Concorrentes

### Ryzen AI (XDNA) NPU

| Item | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| Performance | 40 TOPS | 16~50 TOPS (varia por geração) |
| Trazer modelo personalizado | Conversão obrigatória via DFC, geralmente falha | **ONNX Runtime suporta diretamente** |
| Experiência do desenvolvedor | Toolchain proprietária, documentação insuficiente | `pip install onnxruntime-directml` e pronto |
| Ecossistema | Fechado, dependente do Model Zoo | ONNX / DirectML / co-desenvolvimento Microsoft |
| Número de unidades | Pi + AI HAT, dongle USB (planejado) | **Embutido em milhões de notebooks** |

A integração com Ryzen AI é concluída com:

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

O mesmo não é possível com o Hailo-10H. Não existe Execution Provider ONNX Runtime.

### NVIDIA CUDA

| Item | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| Trazer modelo personalizado | Via DFC, geralmente falha fora do Model Zoo | ONNX / PyTorch / TensorFlow → funciona diretamente |
| Toolchain | Imatura, semi-fechada | Madura, aberta, documentação abundante |
| Comunidade de desenvolvedores | Muito pequena | Maior do mundo |
| Faixa de preço | Barato (~$70) | Caro ($200~$2000+) |

A única vantagem do Hailo é **preço e consumo de energia**.

---

## Relação com hailo-apps (2025-10)

### Visão Geral do hailo-apps

Coleção oficial de aplicativos lançada pela Hailo em outubro de 2025. Inclui mais de 20 aplicativos de exemplo:

- GenAI: voice_assistant, vlm_chat, agent_tools_example, whisper
- Pipeline: detecção de objetos, estimativa de pose, reconhecimento facial, classificação CLIP, OCR
- Standalone: demos de aprendizado HailoRT Python/C++

### Comparação com Este Projeto

| Item | hailo-apps | Este Projeto |
|------|-----------|-------------|
| Suporte VLM | app vlm_chat | Implementação direta `hailo_platform.genai.VLM` |
| CLIP | app clip | Integrado como sistema de pesquisa semântica |
| LLM | simple_llm_chat | Integrado como Extension GenAI |
| Whisper | simple_whisper_chat | Integrado como Extension Speech-to-Text |
| Gerenciamento de dispositivo | Nenhum (assume app único) | **Gerenciador de dispositivo com controle exclusivo (alternância automática CLIP/YOLO/LLM/VLM/S2T)** |
| Fallback de backend | Nenhum | **Alternância automática Hailo → CoreML → ONNX** |
| Inferência distribuída | Nenhum | **Work-stealing distribuído LAN** |
| Nível de integração | Apps de demo individuais | Aplicativo WebUI único integrado |

Este projeto implementou software com funcionalidade igual ou superior ao hailo-apps (lançado depois) a partir de APIs de baixo nível do wheel `hailo_platform` antes de sua publicação.

---

## Perspectivas Futuras

### Curto Prazo (Realista)

- **ONNX Runtime + LAN distribuído é a única solução prática** — Operação com backend ONNX do servidor tagger distribuído
- Uso do Hailo-10H limitado a propósitos com HEF oficial disponível (YOLO, CLIP, LLM, Whisper)
- Desistir da execução NPU de modelos personalizados

### Médio Prazo (Esperançoso)

- Dongle USB com Hailo-10H lançado pela ASUS, etc. → Aumento de usuários
- Com o aumento de usuários, possível pressão sobre a Hailo para melhorar as ferramentas
- Possibilidade de suporte a Transformers ser adicionado em versões futuras do DFC

### Longo Prazo (Desafios Estruturais)

- A menos que a Hailo forneça um EP ONNX Runtime, vai perder para o Ryzen AI (XDNA) em ecossistema de desenvolvedores
- Mesmo que o hardware se popularize com dongle USB, "apenas YOLO rápido" sem liberdade de software
- 40 TOPS de potencial continuando a ser usável apenas para as dezenas de modelos do Model Zoo

---

## Resumo

O Hailo-10H tem excelente performance de hardware de 40 TOPS, mas devido ao fechamento e imaturidade do ecossistema de software, está em um estado onde os desenvolvedores **praticamente não conseguem** trazer livremente seus próprios modelos e utilizá-los.

Neste projeto, construímos software de integração igual ou superior à coleção de aplicativos oficial da Hailo (hailo-apps) explorando APIs não documentadas. No entanto, mesmo assim, a execução NPU do modelo personalizado (WD-Tagger) não pôde ser realizada devido às restrições do DFC.

**"Faltam ferramentas demais para que o desenvolvimento seja praticamente possível"** — esta é a conclusão honesta após meses de desenvolvimento com o Hailo-10H.

---

## Documentos Relacionados

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — Log de desenvolvimento da pesquisa semântica CLIP (Phase 1~12+)
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — Guia de conversão DFC (material de referência)
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — Relatório de falha de conversão WD-Tagger
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — Log de desenvolvimento do fallback ONNX CLIP
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — Design de gerenciamento de dispositivo VDevice
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — Documentação do servidor tagger distribuído
