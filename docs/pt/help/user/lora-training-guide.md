# Guia de Treinamento LoRA

Guia completo de treinamento LoRA em linguagem natural com YU AI Manager + MCP + kohya_ss

---

## Introdução

Este documento é um guia prático que explica o fluxo para criar LoRA somente com instruções em linguagem natural, integrando o servidor MCP do YU AI Manager com o kohya_ss.

A maior parte do esforço do processo tradicional de criação de LoRA estava em "preparação manual do dataset": selecionar imagens, refinar e excluir tags, ajustar arquivos de caption, organizar a estrutura de pastas — tudo isso era feito por humanos.

Com a integração MCP do YU AI Manager, esse fluxo muda. A instrução "por favor, crie um LoRA de ○○, excluindo as tags △△" é suficiente para rodar tudo de forma integrada: coleta de material, tagueamento, geração do dataset e execução do kohya_ss.

---

## Fluxo geral

O processo de criação de LoRA é composto de 5 etapas.

| Fase | Tarefa | Responsável |
|---------|---------|------|
| 1. Preparação de material | Coleta e alocação de imagens de treinamento | Humano / Agente de IA |
| 2. Tagueamento | Tagueamento automático com WD-Tagger | MCP (automático) |
| 3. Geração do Dataset | Criação do projeto, definição de tags excluídas, export | MCP (automático) |
| 4. Execução do treinamento | Invocação do kohya_ss para treinar | MCP (automático) |
| 5. Validação | Usar o LoRA no SD e checar o resultado | Humano |

A intervenção humana ocorre apenas nas decisões de "o que treinar" e na conferência do resultado final.

---

## Pré-requisitos

### Softwares necessários

- YU AI Manager — inclui o servidor MCP
- Claude Desktop ou Claude Code — cliente MCP
- kohya_ss — contendo o sd-scripts
- Stable Diffusion WebUI (A1111 / ComfyUI / Forge) — para validação de resultados

### Requisitos de GPU

| VRAM da GPU | Modelos suportados | Configuração necessária |
|---------|----------|-----------|
| 8GB | Apenas SD 1.5 é prático | `--gradient_checkpointing` obrigatório |
| 12GB | SDXL funciona (com limitações) | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL confortável | Funciona com configuração padrão |
| 24GB+ | Suporta tanto SDXL quanto FLUX | Praticamente sem restrições |

> **Observação**: É possível treinar LoRA SDXL em uma RTX 3060 12GB, mas como o gradient_checkpointing é obrigatório, 24.000 passos levam cerca de 10 horas. Em uma RTX 5060 Ti 16GB estima-se redução para 3 a 5 horas.

### Estrutura de diretórios do kohya_ss

No kohya_ss, é comum que o diretório raiz e o diretório dos scripts estejam separados.

```
O:\webui\kohya_ss\              ← diretório raiz a ser definido em kohya_path
O:\webui\kohya_ss\venv\         ← ambiente virtual Python (detectado automaticamente)
O:\webui\kohya_ss\sd-scripts\   ← diretório que contém os scripts de treinamento
```

> ⚠️ **Atenção**: o YU AI Manager detecta automaticamente a subpasta `sd-scripts` e o venv se você especificar o diretório raiz em `kohya_path`. Não aponte diretamente para o sd-scripts.

---

## Configuração do YU AI Manager

### Configuração da Extension

Na aba de configurações do LoRA Dataset Manager, preencha:

| Item | Descrição | Exemplo |
|---------|------|---|
| `kohya_path` | Diretório raiz do kohya_ss | `O:\webui\kohya_ss` |
| `output_base_dir` | Diretório base de saída do Dataset | `C:\lora_datasets` |
| `checkpoint_dir` | Diretório dos modelos base | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | Tipo padrão de modelo | `sdxl` |

### Configuração do WD-Tagger

Para uso em LoRA dataset, não é recomendada a combinação com VLM (llava etc.). O VLM gera muitas tags em formato livre, reduzindo a qualidade do caption.

```
engine_type: "onnx"  ← usar somente ONNX
```

> ⚠️ **Atenção**: se `engine_type` for definido como `"both"`, são geradas tags compostas vindas do VLM (como `wooden_bear_and_fish_sculpture`). Elas não funcionam como caption no kohya_ss e prejudicam o treinamento.

---

## Procedimento de criação de LoRA via MCP

### Passo 1: preparar as imagens de material

Coloque as imagens de treinamento no scan root do YU AI Manager e execute o scan.

- Adicione a pasta de treinamento nas configurações de Scan Root
- Após o scan, as imagens alvo são registradas no DB
- Mínimo 20 a 30 imagens, recomendado 50 a 200

> **Observação**: a qualidade das imagens é o maior fator determinante do resultado do treinamento. Escolha imagens com resolução mínima de 512px e com o objeto claramente visível.

### Passo 2: tagueamento com WD-Tagger

Execute o tagueamento em lote a partir do MCP.

```python
# Obter a lista de IDs dos arquivos alvo e taguear em lote
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

Se já houver tags, exclua-as primeiro e reexecute.

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Passo 3: criar o projeto

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # usado como nome de pasta no kohya_ss
    base_model="sdxl",
    repeat=20
)
```

### Passo 4: configurar arquivos e tags

Atribua os IDs de arquivo ao projeto e confira a agregação de tags.

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

A partir da agregação de tags, decida quais excluir.

#### Filosofia de design das tags de exclusão

Aqui está o cerne de "o que se quer ensinar ao LoRA".

**Tags a manter**: características específicas do conceito que se quer ensinar (forma, estilo, elementos únicos)

**Tags a excluir**: tags genéricas já conhecidas pelo modelo (`no_humans`, `realistic`, `animal`, `solo`, relacionadas a background etc.)

Exemplo: para um LoRA de urso entalhado em madeira

- Manter: `bear`, `fish`, `statue`, `sculpture`, `standing`, `full_body`, `open_mouth`
- Excluir: `no_humans`, `animal_focus`, `animal`, `realistic`, `simple_background`, `solo`, `indoors`, `shadow`...

> ⚠️ **Atenção**: falhar em recortar o conceito dispersa o aprendizado. Se quiser manter `bear` ou `wood`, o ONNX do WD-Tagger pode não atribuí-los de forma confiável. Nesse caso, confirme a saída real com o preview de caption.

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Passo 5: confirmar preview do caption

```python
preview_lora_caption(project_id=N, file_id=ID_de_arquivo_qualquer)
```

Exemplo de saída:

```
"fish, full_body, open_mouth, standing"
```

Confirme que não há ruído de VLM e que é uma sequência simples de tags. Se muitos captions saírem vazios, é preciso revisar as tags excluídas.

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Passo 6: exportar Dataset

```python
export_lora_dataset(project_id=N)
```

Estrutura da pasta de saída:

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Passo 7: executar treinamento

Primeiro, faça um dry_run e verifique o comando.

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="caminho_completo\checkpoint.safetensors"
)
```

Se estiver tudo bem, inicie o treinamento.

```python
start_lora_training(
    project_id=N,
    checkpoint="caminho_completo\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

Checagem de progresso:

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## Parâmetros padrão de treinamento

| Parâmetro | Valor padrão | Descrição |
|-----------|------------|------|
| `network_dim` | 32 | Rank do LoRA. Maior = mais expressividade, mas aumenta o tamanho do arquivo |
| `network_alpha` | 16 | Normalmente configurado como metade do dim |
| `learning_rate` | 1e-4 | Taxa de aprendizado |
| `max_train_epochs` | 10 | Número de epochs |
| `save_every_n_epochs` | 2 | Intervalo de salvamentos intermediários |
| `mixed_precision` | fp16 | Precisão. Em alguns casos bf16 economiza mais VRAM |
| `resolution` | 1024,1024 (SDXL) | Resolução de treinamento. SD1.5 é 512,512 |

> **Observação**: esses valores podem ser alterados na aba Settings ou via `set_extension_config`. Argumentos adicionais podem ser passados em `extra_args` de `start_lora_training`.

---

## Configurações recomendadas por GPU

| VRAM da GPU | extra_args recomendados |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | (funciona com o padrão) |
| 24GB+ | (funciona com o padrão, é possível aumentar o batch_size) |

> ⚠️ **Atenção**: usar gradient_checkpointing numa GPU de 12GB, com 24.000 passos em SDXL, leva cerca de 10 a 12 horas. A partir de 16GB esta restrição desaparece e o tempo é significativamente reduzido.

---

## Orientação de repeat e epoch

**Total de passos de treinamento = número de imagens × repeat × epochs**

| Complexidade do conceito | Passos recomendados | Exemplo (50 imagens) |
|------------|-------------|--------------|
| Objeto ou estilo simples | 1.000 a 3.000 | repeat=10, epoch=5 |
| Personagem ou objeto plástico | 3.000 a 8.000 | repeat=20, epoch=5 |
| Estilo complexo ou pessoa | 5.000 a 15.000 | repeat=20, epoch=10 |

> **Observação**: treinar com 120 imagens × 20 repeat × 10 epoch = 24.000 passos produz qualidade suficiente. Como 5 a 6 epochs podem dar resultado equivalente, recomenda-se tentar com epoch menor na próxima vez.

---

## Troubleshooting

### ModuleNotFoundError: No module named 'torch'

**Causa**: tentativa de rodar scripts do kohya_ss com o venv do YU AI Manager.

**Solução**: defina `kohya_path` como o diretório raiz (pai de sd-scripts). O YU AI Manager detecta automaticamente `kohya_path/venv/Scripts/python.exe`.

---

### AssertionError: resolution is required

**Causa**: `--resolution` não foi especificado.

**Solução**: na versão mais recente do YU AI Manager, é adicionado automaticamente (SDXL: 1024,1024; SD1.5: 512,512).

---

### AssertionError: network for Text Encoder cannot be trained with caching

**Causa**: `--cache_text_encoder_outputs` e `--network_train_unet_only` não estão pareados.

**Solução**: na versão mais recente do YU AI Manager, `--network_train_unet_only` é adicionado automaticamente ao usar SDXL.

---

### torch.OutOfMemoryError: CUDA out of memory

**Causa**: VRAM insuficiente.

**Solução**: adicione o seguinte em `extra_args`.

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### Ruído de tags do VLM

**Causa**: `engine_type` está como `"both"` e o VLM (llava etc.) está gerando tags em formato livre.

**Solução**: nas configurações do WD-Tagger, mude para `engine_type="onnx"`, apague todas as tags e retagueie.

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

### checkpoint must be inside checkpoint_dir (erro 403)

**Causa**: o path do checkpoint aponta para fora de `checkpoint_dir`.

**Solução**: confirme que `checkpoint_dir` nas configurações da Extension aponta para o diretório correto.

---

### output_base_dir not configured (erro 400)

**Causa**: `output_base_dir` não foi configurado ou salvo nas configurações da Extension.

**Solução**: salve novamente pela aba de configurações na UI, ou configure via MCP com `set_extension_config`.

---

## Prompts na geração

### Estrutura básica do prompt

```
{concept_token}, {tags de características}, <lora:{lora_name}:{strength}>
```

Exemplo de LoRA de urso entalhado em madeira:

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

Negative prompt:

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### Ajuste de força do LoRA

| Força | Característica |
|-----|------|
| 0.5 a 0.6 | Forte influência do modelo base. Cor e estilo puxam para o base |
| 0.7 a 0.8 | Faixa recomendada. Bom equilíbrio entre LoRA e modelo base |
| 0.9 a 1.0 | Forte influência do LoRA. A forma aparece, mas a cor tende a ficar branca/creme |

> **Observação**: se a cor estourar em branco, reduza a força ou inclua `brown wood, warm tone` no prompt para guiar a cor.

---

## Evoluções futuras

### Automação da coleta de material

Atualmente, as imagens de material ainda precisam ser preparadas manualmente. Usando agentes de navegador como o Claude in Chrome, é possível automatizar também a coleta com a instrução "por favor, colete imagens de ○○ da web e coloque na pasta".

Também é válido reutilizar como material as imagens geradas pelo próprio YU AI Manager. Forma-se um ciclo em que imagens criadas com SD/ComfyUI/NAI viram material de LoRA.

### Fluxo de produção em massa de LoRA

Com MCP + Claude Desktop, dá para alcançar a automação completa:

1. Coletar material na web (Claude in Chrome)
2. Scan e tagueamento no YU AI Manager (MCP)
3. Criar projeto, definir tags excluídas, exportar (MCP)
4. Iniciar treinamento no kohya_ss (MCP)
5. Dar a instrução antes de dormir → na manhã seguinte, LoRA pronto

### Escolha do modelo base

Modelos base da linha Illustrious, como waiSHUFFLENOOB, são otimizados para geração em estilo anime. Treinar materiais realistas (como um urso entalhado) tende a puxar as cores para branco/creme.

Se quiser textura mais realista, escolha modelos base da linha realisticPhoto. O LoRA precisa ser usado com o mesmo modelo base do treinamento.

---

## Conclusão

O fluxo YU AI Manager + MCP + kohya_ss reduz drasticamente o esforço para criar LoRAs.

- Do material até todos os epochs de treinamento, tudo conclui apenas com instruções MCP
- Todo o fluxo roda a partir de linguagem natural
- Nas imagens geradas, a forma do alvo de treinamento é expressa com clareza

O que falta é apenas automatizar a coleta de material; combinando com Claude in Chrome etc., a automação total está ao alcance.
