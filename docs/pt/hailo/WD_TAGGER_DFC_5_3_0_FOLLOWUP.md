# Acompanhamento DFC: Reverificação de Modelos WD-Tagger com DFC v5.3.0

**Data**: 2026-04-06  
**Versão DFC**: 5.3.0  
**Relatório Anterior**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)  
**Ambiente**: WSL2 (Ubuntu 24.04), x86_64

---

## Contexto

Em março de 2026, reportamos que as 3 variantes do WD-Tagger (SwinV2, ViT, ConvNeXt)
falharam todas no nível do parser do Hailo Dataflow Compiler v5.2.0, sem atingir a etapa de quantização. O relatório original está salvo em
[`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md).

Com o lançamento do DFC v5.3.0, reverificamos os mesmos 3 modelos e registramos os resultados aqui.

---

## Resumo dos Resultados

| Modelo | Tamanho | Erro DFC 5.2.0 | Erro DFC 5.3.0 | Mudança |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `IndexError` em `_convert_axes_to_nhwc` | Idêntico | **Nenhuma** |
| `wd-vit-tagger-v3` | 362 MB | Idem | Idêntico (mesmo após nova tentativa com onnxsim) | Apenas fluxo de nova tentativa adicionado |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | Idem + `UnsupportedModelError` adicionado | **Erros aumentaram** |

**Todos os 3 modelos ainda falham no nível do parser.** As 500 imagens de calibração preparadas para quantização permanecem inutilizadas, assim como no v5.2.0.

---

## O que Mudou no DFC v5.3.0

Embora as falhas persistam, as seguintes melhorias são observadas em comparação ao v5.2.0:

### 1. Método `_create_layer_normalization_layer` Recém-Adicionado

Este método não existia no v5.2.0. No DFC v5.3.0, ele tenta explicitamente tratar o operador `LayerNormalization` em um caminho de código dedicado. Isso é claramente evidência de progresso de desenvolvimento.

No entanto, **a implementação interna está incompleta**, e a chamada `_convert_axes_to_nhwc` após o método é invocado causa `IndexError: list index out of range` com as mesmas formas de tensor que antes do v5.2.0.

### 2. Adição de Fluxo de Simplificação + Nova Tentativa com onnxsim

Para ViT e ConvNeXt, o DFC v5.3.0 agora simplifica automaticamente o ONNX de entrada com `onnxsim` e tenta novamente o parse. O modelo simplificado é salvo como `model.sim.onnx` próximo ao arquivo de entrada. Isso é uma rede de segurança útil para modelos com grafos ONNX redundantes.

No entanto, para os modelos desta vez, como a causa raiz está no lado de `_convert_axes_to_nhwc`, a nova tentativa **falha exatamente no mesmo ponto**.

### 3. Funcionalidade de Recomendação de Nó End

Para ConvNeXt, o DFC v5.3.0 agora recomenda nós end específicos quando o parser desiste, e solicita ao usuário que fixe e tente novamente. Isso é uma melhoria UX agradável.

No entanto, a nova tentativa com o nó end recomendado também falha da mesma forma. A causa raiz está no tratamento de LayerNormalization / Transpose, não na seleção do nó end.

---

## Causa Raiz (Inalterada desde março)

O parser ONNX do DFC ainda falha na conversão de eixo quando o tensor de entrada do operador `LayerNormalization` não segue o formato NCHW esperado. A cadeia de chamadas é:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

Para ConvNeXt, além disso, `UnsupportedShuffleLayerError` em múltiplos nós `Transpose` (`token_5` até `token_34`) indica incompletude no tratamento de Transpose para o padrão channels-last usado por esta arquitetura.

Em resumo, **novos caminhos de código existem, mas o caso que falhava antes ainda não está sendo tratado**.

---

## Solicitações (Inalteradas desde março)

As 2 solicitações levantadas no post de março continuam:

### 1. Corrigir `_convert_axes_to_nhwc` para LayerNormalization Multidimensional

O método agora pode ser alcançado (melhoria). No entanto, a própria lógica de mapeamento de eixo ainda falha em tensores de entrada não-NCHW.
Arquiteturas Transformer recentes como SwinV2, ViT e ConvNeXt dependem de que isso funcione corretamente.

### 2. ONNX Runtime Execution Provider para Hailo-10H

Se disponível, a conversão completa via DFC se torna opcional, resolvendo estruturalmente este tipo de problema. Muitos usuários da comunidade dariam as boas-vindas à capacidade de executar diretamente modelos ONNX não modificados no Hailo-10H, mesmo com throughput menor que um HEF completamente quantizado.

---

## Sobre o Componente "ONNX Runtime Hailo Pipeline"

As notas de lançamento do DFC v5.3.0 mencionam um componente chamado "ONNX Runtime Hailo Pipeline". Se este componente permitisse executar inferência WD-Tagger no Hailo-10H **sem conversão DFC completa** (ou seja, delegar apenas subgrafos compatíveis com NPU como um execution provider ORT), orientação oficial sobre seu uso correto seria muito apreciada.

Especificamente:

- Este componente se destina como caminho avante para modelos que o DFC não consegue atualmente parsear?
- É necessário um HEF parcial (compilar subgrafos parseáveis para HEF, executar o restante via ORT em CPU)?
- Existem exemplos de código ou tutoriais para usar isso com modelos ONNX baseados em Transformer?

---

## Passos de Reprodução

Passos para reproduzir esses resultados:

```bash
# 1. Configurar DFC v5.3.0 em venv Python limpo
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. Baixar 3 variantes de WD-Tagger ONNX
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. Tentar parse de cada modelo
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

Logs de erro completos de cada execução podem ser fornecidos mediante solicitação.

---

## Ambiente de Teste

| Item | Detalhes |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| Modelos | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| Dados de calibração | 500 imagens de saída ComfyUI / SD (não utilizadas pois quantização não foi alcançada) |

---

## Resumo

Os esforços de desenvolvimento visíveis no DFC v5.3.0 (`_create_layer_normalization_layer`, fluxo de nova tentativa onnxsim, recomendação de nó end) são genuinamente encorajadores. Eles representam exatamente o progresso que a comunidade esperava. A lacuna restante está na implementação dentro de `_convert_axes_to_nhwc`, que agora pode ser alcançada mas ainda não funciona corretamente para os modelos desta vez.

Continuaremos reverificando a cada release do DFC e publicaremos um acompanhamento quando a situação mudar. Se alguém da Hailo estiver lendo isso e precisar de logs de erro completos, hashes SHA-256 dos modelos ONNX ou código mínimo de reprodução, teremos prazer em fornecer.
