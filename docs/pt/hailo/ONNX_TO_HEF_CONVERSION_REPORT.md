# Relatório de Conversão ONNX para HEF

**Data de Realização**: 2026-03-06  
**Objetivo**: Converter modelos ONNX WD-Tagger para o formato HEF Hailo e tornar possível a inferência no Raspberry Pi 5 + AI HAT 2 (Hailo-10H)  
**Resultado**: Falha (impossível converter em todas as variantes do modelo)

---

## Ambiente

| Item | Detalhes |
|------|------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (instalado via uv) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## Modelos Tentados

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **Fonte**: `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **Entrada**: `[batch, 448, 448, 3]` float32
- **Saída**: `[batch, 10861]` float32
- **Resultado**: Falha
- **Erro**: `IndexError: list index out of range` em `_convert_axes_to_nhwc`
- **Causa**: Conversão de eixo de LayerNormalization não suportada no DFC v5.2.0

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **Fonte**: `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **Entrada**: `[batch, 448, 448, 3]` float32
- **Saída**: `[batch, 10861]` float32
- **Resultado**: Falha
- **Erro**: Idem (`IndexError` em `_convert_axes_to_nhwc`)
- **Causa**: ViT também usa LayerNormalization, falhando no mesmo ponto

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **Fonte**: `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **Entrada**: `[batch, 448, 448, 3]` float32
- **Saída**: `[batch, 10861]` float32
- **Resultado**: Falha
- **Erro**: `UnsupportedShuffleLayerError` (múltiplos nós Transpose) + `UnsupportedModelError` (incompatibilidade de shape no Mul)
- **Causa**: Operações Transpose devido ao design channels-last do ConvNeXt não são suportadas pelo DFC

---

## Causa Raiz da Falha

O parser ONNX do DFC v5.2.0 não consegue processar corretamente as seguintes operações:

1. **LayerNormalization**: Erro de índice na conversão de eixo NHWC do LayerNorm em tensores de 3 ou mais dimensões
2. **Transpose (Shuffle)**: Padrões Transpose usados para conversões channels-last/first do ConvNeXt não são suportados

Todas as variantes do WD-Tagger (SwinV2, ViT, ConvNeXt) são arquiteturas modernas que usam LayerNormalization extensivamente e não podem ser convertidas no DFC v5.2.0.

---

## Dados de Calibração

- 500 imagens selecionadas aleatoriamente de saídas de ComfyUI / Stable Diffusion forge
- Aplicado o mesmo pré-processamento que o WD-Tagger (composição RGBA→RGB em fundo branco, redimensionamento com preservação de proporção, padding branco, conversão BGR)
- Salvo como `calibration_data.npy`, mas não utilizado pois a conversão não alcançou a fase de quantização

---

## Possibilidades Futuras

- **Versões futuras do DFC**: Se a Hailo melhorar o suporte a LayerNormalization / Transpose, vale a pena tentar novamente
- **Modificação do modelo**: Criação de modelo modificado substituindo LayerNorm por BatchNorm (grande esforço, risco de degradação de precisão)
- **Manter o estado atual**: Continuar usando inferência com ONNX Runtime (CPU)
