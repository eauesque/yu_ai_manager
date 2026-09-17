# Integração de Bridge

A funcionalidade Bridge permite enviar prompts diretamente do YU AI Manager para várias ferramentas de geração de imagens de IA.

## Bridges Suportadas

### SD WebUI Bridge
Integra-se com Stable Diffusion WebUI (Automatic1111 / Forge).
- Enviar/receber prompts
- Transferir parâmetros de geração

### NAI Bridge
Integra-se com NovelAI.
- Conversão automática de sintaxe de prompt (SD ↔ NAI)
- Inserção automática de tags de qualidade

#### Vibe Transfer (poção NovelAI) e cache de encode-vibe

Os modelos NAI V4+ requerem pré-codificação das imagens de referência via `/ai/encode-vibe`
(**2 Anlas por chamada**) antes de serem usadas em solicitações de geração.

Para evitar o desperdício de Anlas ao gerar repetidamente com a mesma imagem, os resultados
de codificação são armazenados em cache local em:

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **Chave**: SHA256 da imagem bruta + nome do modelo + informação extraída (passos de 0,01)
- **Tamanho máximo**: 500 MB por padrão. Alterável em Settings > NAI Bridge > "Vibe encode cache (MB)" (0 = desativado)
- **Remoção LRU**: arquivos mais antigos são removidos em um thread em segundo plano quando o limite é excedido

### ComfyUI Bridge
Integra-se com ComfyUI.
- Inserção de prompt em workflow
- Personalização de formato de saída

## Geração em Lote

Todas as três Bridges suportam geração em lote no caminho de geração principal (semântica compatível com A1111).

### Batch count / Batch size

- **Batch count** — Número de execuções de geração sequenciais (eixo temporal). O cliente chama a API uma vez por iteração.
- **Batch size** — Número de imagens geradas em paralelo por chamada de API (eixo VRAM). Não exibido no NAI Bridge.
- Total de imagens = Batch count × Batch size

Com seed fixo, o seed é incrementado como `base + i` a cada iteração do loop (mesmo comportamento que A1111). Com `-1` (aleatório), um novo seed aleatório é usado a cada vez.

### Botões de parada

| Bridge | Execução única (count=1) | Loop (count>1) |
|---|---|---|
| NAI | Sem botão de parada | Apenas «Parar após o atual» |
| SD WebUI | «Parar» (API cancel do servidor) | «Parar após o atual» + «Parar» |
| ComfyUI | «Parar» (API cancel do servidor) | «Parar após o atual» + «Parar» |

- **Parar (imediato)** — Interrompe a chamada de API em andamento e para o loop. No SD WebUI / ComfyUI, a API cancel do servidor também é chamada.
- **Parar após o atual** — Deixa a imagem atual terminar de ser gerada e pula a próxima iteração.

O NAI Bridge não exibe botão de parada para geração de imagem única porque a API NAI consome Anlas (créditos) no momento em que aceita o fetch. Cortar a conexão HTTP não para a geração no servidor nem reembolsa o custo — um botão de parada só causaria confusão.

### Nota sobre VRAM

Aumentar o Batch size incrementa o consumo de VRAM da GPU do servidor proporcionalmente ao número de imagens. Com SDXL e Batch size 4 ou mais podem ocorrer erros OOM; comece com 1 e aumente gradualmente.

## Presets de Qualidade

Clique no botão "QP" na barra de ferramentas de cada Bridge para inserir tags de melhoria de qualidade com um clique.

Presets integrados:
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

Você também pode criar presets personalizados.

## Presets de Resolução

Acima das entradas Width/Height do SD WebUI Bridge e ComfyUI Bridge, há um dropdown "Resolution Preset" e botão ⇄ Swap. Insira resoluções típicas com um clique.

- **SD 1.5** — 5 tipos baseados em 512 para modelos SD1.5
- **SDXL Trained** — 9 tipos de bucket oficial de treinamento SDXL (prioridade de qualidade)
- **SDXL Cheat Sheet** — 12 tipos que aproximam proporções cinematográficas/fotográficas em múltiplos de 8 (prioridade de composição, fonte [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet))

Quando `Custom` é selecionado, os valores W/H existentes são mantidos. Se você editar W/H manualmente após aplicar um preset, muda automaticamente para `Custom`. O botão ⇄ troca Width e Height.

As resoluções da Cheat Sheet ficam fora do bucket oficial, portanto alguns modelos podem ter leve distorção de composição.

> No ComfyUI Bridge, aplicável apenas no modo Simple. Não afeta valores de nós no modo Raw JSON Workflow.

## Transferência Entre Bridges

Você pode transferir prompts diretamente entre bridges. A sintaxe é convertida automaticamente entre SD ↔ NAI.

