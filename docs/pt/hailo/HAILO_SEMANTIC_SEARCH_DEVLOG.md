# Hailo-10H Semantic Search — Log de Desenvolvimento

**Projeto**: YU AI Manager — Hailo-10H CLIP Semantic Image Search  
**Objetivo**: Realizar busca semântica de imagens por linguagem natural baseada em CLIP no Raspberry Pi 5 + AI HAT 2 (Hailo-10H)  
**Data de início**: 2026-03-01  
**Status**: Phases 1-8 completas, Phases 9-12 (integração com legendas VLM, S2T de vídeo, multi-turn LLM, API compatível com OpenAI) completas

---

## Por Que Este Projeto É Importante

O Hailo-10H (AI HAT 2) é um acelerador de IA de borda relativamente novo, lançado no final de 2025,
que se encaixa no slot M.2 do Raspberry Pi 5. Tem desempenho de inferência de 40 TOPS, mas
**há ainda muito pouco uso prático publicado em aplicações reais**.

Este projeto provavelmente será o primeiro software prático a realizar busca semântica
(busca de imagens por linguagem natural) em uma biblioteca de imagens em escala de 200.000
usando o Hailo-10H.

---

## Phase 1: Verificação de Viabilidade (2026-03-01)

### Informações do Ambiente

| Item | Valor |
|------|-----|
| Hardware | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| Driver HailoRT | 5.2.0 (hailort-pcie-driver) |
| Biblioteca HailoRT | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**compilado do fonte**) |

### Passo 1-1: Reconhecimento do Dispositivo — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

O dispositivo foi reconhecido sem problemas. Conexão PCIe e carregamento do driver normais.

### Passo 1-2: Download do HEF — OK

Foi possível baixar diretamente do bucket S3 do Hailo Model Zoo v5.2.0 (sem autenticação necessária).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

Padrão de URL:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Passo 1-3: Bindings Python — Requer Compilação do Fonte

#### Problema: Incompatibilidade de Versão de Pacote

O repositório do Raspberry Pi OS tem 2 sistemas de pacotes:

| Sistema de pacotes | Versão | Observação |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | deb oficial Hailo. Sem bindings Python |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Fornecido pelo time Raspberry Pi. Com Python |

**Problema**: Os 2 sistemas têm `Conflicts` configurados e não podem coexistir. `h10-hailort` (5.1.1) instala o driver 5.1.1, mas hailo-ollama requer 5.2.0.

#### Solução: Compilar wheel Python hailort 5.2.0 do fonte

**Não há wheel no PyPI**. A página de downloads da Hailo Developer Zone também
**não tem wheel para aarch64** (apenas x86_64).

Resolvido com compilação do fonte do repositório GitHub:

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# Dependências de build
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# Build (~2 minutos)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# Instalar
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**Pontos importantes**:
- `--plat-name linux_aarch64` é obrigatório. Sem isso, ocorre `ValueError: not enough values to unpack` ao fazer parse do nome do diretório `LIBHAILORT_PATH` (bug na linha 163 do setup.py)
- O deb `hailort` (biblioteca C) precisa ser instalado com antecedência
- `h10-hailort` e `hailort` têm `Conflicts` e não podem coexistir, portanto remover `h10-hailort` antes de instalar `hailort` 5.2.0

### Passo 1-4: Teste de Inferência — Sucesso (com mudanças na API)

#### Descoberta Importante: Hailo-10H Não Suporta API VStreams Legada

O código `InferVStreams` + `ConfigureParams.create_from_hef()` escrito na especificação
**não funciona no Hailo-10H**. `VDevice.configure()` retorna `HAILO_NOT_IMPLEMENTED (error 7)`.

Esta é uma **diferença de API fundamental entre Hailo-8/8L e Hailo-10H**,
fato importante não claramente documentado na documentação oficial.

#### API Correta: InferModel

Para Hailo-10H, usar `VDevice.create_infer_model()`:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs são propriedades (não callable)
    inp_info = infer_model.inputs[0]   # NÃO inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Entrada: imagem uint8
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # Saída: alocar buffer uint8 explicitamente
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### Pontos de Dificuldade e Soluções

| Problema | Erro | Solução |
|------|--------|------|
| `infer_model.inputs()` dá TypeError | `'list' object is not callable` | É propriedade, use `inputs[0]` (sem parênteses) |
| Buffer de saída não configurado | `not configured as view` | Configurar explicitamente com `bindings.output().set_buffer(buf)` |
| Buffer de saída alocado como float32 | `buffer size 2048 != expected 512` | Alocar em **uint8** (512 bytes). float32 fica 2048 bytes |
| Erro ao encerrar VDevice | `Lost communication with server` | Problema na ordem de limpeza do VDevice. **Sem impacto nos resultados de inferência** |

### Desempenho de Inferência

| Item | Valor |
|------|-----|
| Modelo | CLIP ViT-B/16 Image Encoder |
| Entrada | (224, 224, 3) uint8 |
| Saída | (1, 1, 512) uint8 (quantizado) |
| Tempo de inferência | **~20 ms** |
| Throughput teórico | **~50 images/sec** |

Construção de índice para 200.000 imagens: apenas a inferência levaria cerca de 67 minutos. Com pré-processamento, esperado completar em poucas horas.

### Julgamento da Phase 1

| Critério | Resultado |
|------|------|
| Saída de vetor de 512 dimensões | **OK** (quantizado em uint8, desquantização necessária) |
| Velocidade de inferência | **Excelente** (20ms/imagem) |
| Compatibilidade de API | Usando InferModel API (API VStreams da especificação não funciona) |
| Julgamento | **Avançar para Phase 2** |

### Itens de Transferência para Próxima Fase

1. **Desquantização**: Saída uint8 precisa ser convertida para float32. HEF deve conter parâmetros de quantização (scale/zero_point). `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer` pode ser utilizável.
2. **Encoder de texto**: HEF existe mas não testado. Verificar se funciona com a mesma InferModel API. Pode ser mais seguro implementar com CPU (sentence-transformers) conforme diretrizes da especificação.
3. **Coexistência com hailo-ollama**: VDevice usa o dispositivo de forma exclusiva. hailo-ollama precisa ser parado durante a construção do índice.
4. **Limpeza do VDevice**: Mensagem de erro ao encerrar é inofensiva, mas cuidado com vazamento de recursos em processos servidor de longa duração.

---

## Phase 2: Extensão do Schema do Banco de Dados (2026-03-01)

### Conteúdo da Implementação

Tabela `file_vectors` adicionada como Migration 25.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**Decisões de design**:
- `vector` armazena BLOB float32 após desquantização. Armazenar em uint8 causa degradação de precisão
- `file_id` é PRIMARY KEY (1 vetor por arquivo). Necessária mudança para UNIQUE(file_id, model) para suporte futuro a múltiplos modelos
- `ON DELETE CASCADE` exclui automaticamente ao excluir de files

**Teste**: Aplicação de migration em DB em memória → confirmação de existência de tabela/índice → OK

---

## Phase 3: Núcleo de Inferência Hailo (2026-03-01)

### Conteúdo da Implementação

Criado pacote `core/hailo_clip_core/` *(atualmente em `extensions/builtin_hailo_semantic_search/core_impl/`)*:

| Arquivo | Responsabilidade |
|---------|------|
| `hailo_inference.py` | Singleton HailoClipEncoder. Wrapper da API InferModel |
| `image_preprocess.py` | Redimensionar para 224x224 com cv2 + converter BGR→RGB |
| `dequantize.py` | Desquantização uint8→float32 + normalização L2 + extração quant_params |
| `text_encoder.py` | Encoder de texto CLIP em CPU (`openai/clip-vit-base-patch16`) |

**Decisões de design**:
- Pré-processamento de imagem passado para o Hailo como uint8 (normalização ocorre internamente no HEF)
- Encoder de texto usa `CLIPModel` de `transformers` (não `sentence-transformers`). Motivo: `openai/clip-vit-base-patch16` é o mesmo modelo que o CLIP ViT-B/16 do Hailo HEF, então o espaço vetorial coincide
- Parâmetros de desquantização obtidos de `infer_model.outputs[0].quant_infos[0]`, com fallback para scale=1.0, zero_point=0.0 em caso de falha

**Dependências**: `opencv-python-headless`, `numpy` (obrigatório), `transformers`, `torch` (para busca de texto)

---

## Phase 4: Indexador + Extension (2026-03-01)

### Conteúdo da Implementação

| Arquivo | Responsabilidade |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(atualmente em `extensions/builtin_clip_search/core_impl/`)* | Construção de índice em lote em thread background |
| `core/hailo_clip_core/event_handler.py` *(atualmente em `extensions/builtin_clip_search/core_impl/`)* | Indexação automática no evento scan.complete |
| `extensions/builtin_hailo_semantic_search/extension.json` | Manifesto da Extension |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint 5 API |

**Endpoints de API**:
- `GET /ext/hailo-semantic/api/status` — estado do dispositivo e do índice
- `POST /ext/hailo-semantic/api/index/start` — iniciar construção de índice
- `GET /ext/hailo-semantic/api/index/status` — progresso
- `POST /ext/hailo-semantic/api/index/stop` — interromper
- `GET /ext/hailo-semantic/api/search` — busca semântica
- `POST /ext/hailo-semantic/api/index/clear` — limpar índice

**Eventos**: `semantic_index.start/progress/complete` adicionados ao event_bus

---

## Phase 5: Motor de Busca Semântica (2026-03-01)

### Conteúdo da Implementação

`core/hailo_clip_core/search.py` *(atualmente em `extensions/builtin_clip_search/core_impl/search.py`)* — busca por similaridade cosseno com cache em memória

**Algoritmo**:
1. Carregar todos os vetores do banco de dados de uma vez → cache em memória
2. Pré-normalização L2 dos vetores
3. Texto da consulta → encoder de texto CLIP → vetor de 512 dimensões
4. Cálculo em lote de similaridade cosseno por produto interno (dot product)
5. Ordenar acima do threshold → retornar resultados

**Estimativa de memória**: 200K × 512 × 4 bytes = ~400 MB (dentro da faixa tolerável para Pi5 8GB RAM)

**Formato de resposta**:
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6: Integração de UI (2026-03-01)

### Página de Pesquisa

- Adicionado toggle de busca semântica (ícone de cérebro, estilo `regex-pill`) ao lado da barra de pesquisa
- Exibido apenas quando Hailo está disponível e o índice foi construído
- Quando toggle está ON: intercepta envio do formulário de pesquisa → API de busca semântica → exibe resultados no grid existente
- Placeholder substituído por exemplos de texto em inglês

### Página de Ferramentas

- Adicionada seção de busca semântica na aba Search & Analysis
- Exibição do estado do dispositivo e status do índice
- Slider de batch size + checkbox de indexação automática
- Botões Build Index / Stop / Clear + barra de progresso (polling de 2 segundos)

---

## Notas Técnicas

### Principais Diferenças entre Hailo-10H e Hailo-8/8L (Perspectiva do Desenvolvedor)

| Item | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| API VStreams | Suportada | **Não suportada** (NOT_IMPLEMENTED) |
| API InferModel | Suportada | Suportada |
| ConfigureParams | create_from_hef(hef, interface) | Desnecessário (create_infer_model é alternativo) |
| Formato de saída | float32 ou uint8 selecionável | uint8 fixo (desquantização necessária) |
| Pacote Python | Wheel no PyPI disponível | **Não disponível** (compilação do fonte necessária) |
| Pacote APT | `hailort` unificado | `h10-hailort` separado (apenas 5.1.1) |

### Armazenamento de Wheel Compilado

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

Pode ser copiado e instalado para deployment em outros ambientes Pi5
(porém necessita de libhailort.so.5.2.0 e hailort-pcie-driver 5.2.0).

---

## Log de Correção de Bugs Após Implementação das Phases 2-6 (2026-03-01)

### 1. Problema de Compatibilidade `get_text_features` do Encoder de Texto

**Problema**: `CLIPModel.get_text_features(**inputs)` nas novas versões do transformers começou a retornar um objeto `BaseModelOutputWithPooling` em vez de `torch.Tensor`. Portanto, a chamada `.squeeze()` causava `AttributeError`, e a busca semântica retornava erro `Search failed`.

**Sintoma**: `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**Causa**: O valor de retorno de `_model.get_text_features()` depende da versão do transformers. Novas versões retornam o objeto completo de saída do modelo, e é necessário extrair `.pooler_output`, etc. manualmente.

**Correção**: Alterado em `text_encoder.py` para processar em 2 etapas explícitas `text_model()` → `text_projection()`:

```python
# Antes (quebrado)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# Depois (corrigido)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**Desempenho**:
- Primeira consulta (incluindo carregamento do modelo): ~6 segundos
- Segunda consulta em diante: ~100-170ms (apenas inferência CPU)
- Busca vetorial: <1ms (51 itens, cache em memória)

### 2. Loop Infinito de Retry na Construção do Índice

**Problema**: Arquivos com falha de decodificação (arquivos não-imagem, corrompidos, etc.) não eram rastreados como `failed_ids`, e `get_unindexed_file_ids()` retornava os mesmos arquivos com falha a cada vez, fazendo a contagem de erros ultrapassar 3 milhões.

**Correção**: Adicionado `failed_ids: set` ao `indexer.py`. Registrar file_ids com falha e excluí-los do próximo lote.

### 3. Falha na Leitura de Imagens em Arquivos de Arquivamento

**Problema**: `cv2.imread('test.7z!image.png')` não entende caminhos de membros de arquivamento.

**Correção**: Usar `is_archive_member()` em `image_preprocess.py` para detectar caminhos de arquivamento, e alternar para o padrão `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()`.

### 4. Atualização de Progresso SSE em Tempo Real

**Problema**: Polling de 2 segundos tornava o progresso intermitente, experiência ruim.

**Correção**: Alternado para conexão SSE `EventSource`. Atualização em tempo real com evento `semantic_index.progress`.
Desconectar SSE quando aba fica oculta via `visibilitychange`, e reconectar ao retornar.

---

## Phase 7: Detecção de Objetos YOLO (2026-03-02)

### Visão Geral

Após a busca semântica CLIP, implementação de detecção de objetos YOLO no mesmo Hailo-10H.
Detecção de objetos COCO de 80 classes em imagens e vídeos, salvando resultados na tabela `file_annotations`.

### Design de Arquitetura

#### Problema de Compartilhamento VDevice

O Hailo-10H só pode usar 1 VDevice de um único processo, e InferModel também é exclusivo.
CLIP e YOLO não podem rodar simultaneamente.

**Solução**: Criação do novo `core/hailo_device_core/device_manager.py`.
- `acquire_device(owner, hef_path)` — liberar automaticamente se outro owner estiver segurando, então alternar
- Reutilizar se mesmo owner + mesmo HEF (evitar re-inicialização)
- Thread-safe com `threading.Lock`
- Refatorar `hailo_inference.py` do CLIP para delegar ao device_manager

#### Tratamento de Tensores de Saída YOLO

Enquanto CLIP tem apenas 1 tensor de saída, YOLO tem múltiplos tensores de saída (correspondendo aos heads de cada stride).
`device_manager` coleta e retorna parâmetros de quantização para todas as saídas.

#### Pipeline de Pós-processamento

O pós-processamento YOLO segue estas etapas:
1. Desquantização uint8 → float32 (usando scale/zero_point por output)
2. Decodificação de grid cell → coordenadas em pixel (sigmoid + offset de grid + stride)
3. Filtragem por confiança
4. NMS por classe (pure numpy)
5. Coordenadas letterbox → coordenadas normalizadas (0-1) da imagem original

#### Suporte a Vídeo

Extração de frames com ffmpeg → detecção de cada frame independentemente → agregação por classe.
Manter máxima confiança por classe + número de frames de ocorrência.

### Estrutura de Novos Módulos

| Módulo | Papel |
|---|---|
| `core/hailo_device_core/device_manager.py` | Gerenciamento do ciclo de vida do VDevice compartilhado |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | Singleton YOLODetector |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, decodificação de box, desquantização |
| `core/hailo_yolo_core/yolo_labels.py` | Rótulos de 80 classes COCO |
| `core/hailo_yolo_core/yolo_preprocess.py` | Redimensionamento letterbox 640x640 |
| `core/hailo_yolo_core/yolo_video.py` | Extração de frames de vídeo + agregação |
| `core/hailo_yolo_core/yolo_indexer.py` | Detecção em lote em background |
| `core/hailo_yolo_core/model_download.py` | Download do HEF |
| `core/hailo_yolo_core/event_handler.py` | Handler scan.complete |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

---

## Phase 8: Integração GenAI (LLM / VLM / Speech2Text) (2026-03-02)

### Objetivo

Integrar o módulo `hailo_platform.genai` (LLM, VLM, Speech2Text) do Hailo-10H ao device_manager,
tornando geração de texto, compreensão de imagens e transcrição de voz disponíveis a partir da WebUI.

### Extensão do device_manager

- **Problema**: device_manager existente suportava apenas InferModel API (CLIP/YOLO). Classes GenAI recebem VDevice diretamente, não InferModel
- **Solução**: Distinguir modo com variável `_mode` (`"infer"` | `"genai"`). Adicionar `acquire_genai(owner, model_path, genai_factory)` e instanciar LLM/VLM/S2T com padrão factory
- **Diferença no processo de release**:
  - InferModel: `del configured` → `del infer_model` → `del vdevice`
  - GenAI: `instance.release()` → `vdevice.release()` (método release explícito)

### Descobertas na API GenAI

- **Formato de mensagem**: Estrutura role/content compatível com OpenAI. Conteúdo é array no formato `{"type": "text", "text": "..."}`
- **Entrada de imagem VLM**: Array numpy uint8 RGB 336x336. Passar como lista `frames=[image]`. Colocar placeholder `{"type": "image"}` no prompt
- **Entrada S2T**: little-endian float32 (`<f4`), mono, 16kHz. Normalização int16→float32 obrigatória
- **Segmentos S2T**: `generate_all_segments()` retorna lista de objetos `SegmentInfo`. Atributos `.text`, `.start`, `.end`
- **Gerenciamento de contexto**: LLM/VLM gerenciam janela de contexto com `get_context_usage_size()`, `max_context_capacity()`, `clear_context()`
- **Streaming**: `generate()` retorna iterador, yield por token

### URLs de Download HEF de Modelos

- Padrão: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- Nomes de modelos em CamelCase (ex: `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)

### Novos Arquivos

| Arquivo | Descrição |
|----------|------|
| `core/hailo_genai_core/__init__.py` | Init do pacote |
| `core/hailo_genai_core/genai_types.py` | Enum GenAIModelType + dataclass GenAIModelInfo |
| `core/hailo_genai_core/model_download.py` | Gerenciamento de download de HEF para 7 modelos |
| `core/hailo_genai_core/llm_inference.py` | Wrapper HailoLLM (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | Wrapper HailoVLM (singleton, pré-processamento de imagem) |
| `core/hailo_genai_core/s2t_inference.py` | Wrapper HailoS2T (singleton, suporte a segmentos) |
| `extensions/builtin_hailo_genai/extension.json` | Manifesto da Extension |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint 8 API (SSE streaming) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | UI da página de Ferramentas (4 painéis) |

---

## Phase 9: Integração Busca Semântica + Legendas VLM (2026-03-03)

### Objetivo

Gerar legendas em lote com VLM (Qwen2-VL) para imagens encontradas na busca CLIP,
salvando em `file_annotations`.

### Implementação

- **`core/hailo_clip_core/caption_runner.py`** *(atualmente em `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150 linhas): Executa geração de legendas VLM em lote em thread background. Segue o padrão `_state_lock` + `_stop_requested` + `_progress` do `indexer.py`. Eventos SSE `vlm_caption.start/progress/complete`
- **Extensão do Blueprint**: Adicionados 3 endpoints `/api/caption/start`, `/api/caption/status`, `/api/caption/stop` ao `hailo_semantic_search.py`
- **UI**: Adicionado painel "VLM Caption Generation" à seção Semantic Search da página de Ferramentas. Entrada de prompt, barra de progresso SSE, auto-vinculação de file_ids de resultados de busca

### Controle Exclusivo do VDevice

- Obter VLM com `acquire_genai("vlm", ...)`. Se o indexador CLIP estiver em execução, o device_manager libera automaticamente de acordo com o comportamento existente
- Após a conclusão das legendas, o VLM continua mantendo o dispositivo, portanto reiniciar o índice CLIP requer descarregar o modelo

### Convenção de Salvamento de Anotações

- `source="hailo:vlm"`, `key="caption"`, `value=<texto da legenda>`

---

## Phase 10: Transcrição de Voz de Vídeo — Pipeline S2T (2026-03-03)

### Objetivo

Extração de áudio de arquivo de vídeo com ffmpeg → transcrição com Whisper (S2T) → salvar em `file_annotations`.

### Implementação

- **`core/files_core/video_audio.py`** (~80 linhas): `extract_audio_wav()` para extração de áudio com ffmpeg (mono PCM s16le 16kHz). Cálculo dinâmico de timeout baseado na duração do vídeo (máximo 120 segundos). `check_ffmpeg()` reutilizado de `media_video.py`
- **Extensão do Blueprint**: 3 endpoints adicionados ao `hailo_genai_ext.py`:
  - `POST /api/s2t/transcribe-video`: Transcrição de um único vídeo (file_id, language)
  - `POST /api/s2t/batch-transcribe`: Transcrição em lote de múltiplos vídeos (file_ids, language), thread background + progresso SSE (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>`: Obter transcrição salva

### Convenção de Salvamento de Anotações

- `source="hailo:s2t"`, `key="transcript"`, `value=<texto completo>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### Pontos Importantes

- WAV temporário criado com `tempfile.NamedTemporaryFile`, sempre excluído no finally
- S2T e LLM/VLM são mutuamente exclusivos para o dispositivo (uso simultâneo impossível)

---

## Phase 11: Melhoria de UI de Conversa Multi-turn LLM (2026-03-03)

### Objetivo

Expansão de prompts únicos para suporte a histórico de conversa. Contexto contínuo, reset e UI estilo bolha.

### Implementação

- **Correção de API**: `api_llm_generate()` pode aceitar array `messages`. Compatibilidade retroativa: quando apenas `prompt` está presente, converter para mensagens system + user como antes. `generate_stream()` já suportava multi-turn (via `_normalise_prompt()`)
- **UI de Chat em Bolhas**: `hg-chat-container` + `hg-bubble` (usuário=direita/roxo, IA=esquerda/cinza). Classes CSS: `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **Gerenciamento de Histórico de Conversa**: Acumulação de `{role, content}` no array JS `_chatHistory = []`. Passar `messages: [systemMsg, ..._chatHistory]` ao enviar para API. Reset do array + limpar contexto HailoRT com `hgLlmClear()`
- **Streaming**: Inserir bolha de IA no DOM com antecedência, e adicionar tokens SSE progressivamente

### Correção de Bug: Erro de Role System em Conversa Multi-turn (2026-03-03)

Descoberto com depuração MCP + logs do hailort. O seguinte erro ocorria na chamada `generate()` a partir do 2º turno:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**Causa**: O template de UI enviava system role no início com `[systemMsg].concat(_chatHistory)` a cada vez. A API LLM do HailoRT não aceita role system quando o contexto existe (a partir do 2º turno).

**Correção**:
1. Adicionado método `_prepare_prompt()` ao `llm_inference.py`: Auto-excluir mensagem de role system quando `get_context_usage_size() > 0`
2. Template de UI (`_genai_ui.html`): Adicionar system apenas quando `_chatHistory.length <= 1` (apenas primeira mensagem do usuário)

**Nota técnica**: Como restrição do HailoRT, `LLM.generate()` processa role system apenas na primeira chamada. Isso é diferente da API OpenAI e requer atenção ao implementar conversas multi-turn.

---

## Teste Real WD-Tagger VLM × Hailo-10H (2026-03-03)

### Ambiente de Teste
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (versão compilada)
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### Descoberta Importante: hailo-ollama Não Suporta VLM

Explicitamente declarado na documentação oficial do hailo-ollama (USAGE.rst):
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

Também no campo API de Inferência para `Qwen2-VL-2B-Instruct` na tabela MODELS é apenas "C++, Python" sem incluir "Hailo-Ollama".

### Resultados do Teste Python SDK Hailo VLM Direto

VLM requer incluir `{"type": "image"}` no formato de mensagem:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **Carregamento do modelo**: 33 segundos (cold start inicial. Diferença com os 6.2 segundos publicados é dominado por I/O de disco)
- **Velocidade de inferência**: ~5.1 TPS (128 tokens / 20 segundos). Diferença com 6.73 TPS publicados inclui TTFT
- **Precisão de reconhecimento de imagem**: Entende corretamente o conteúdo da imagem
- **Qualidade de saída JSON**: Baixa. Modelo 2B tem precisão instável para JSON estruturado (vírgulas faltando, code fences markdown misturados)

---

## Phase 12: API Compatível com OpenAI + Correção de Bug de Troca de Dispositivo (2026-03-14)

### Objetivo

1. Fornecer API compatível com OpenAI para que ferramentas externas como OpenAI SDK / LiteLLM / Continue.dev / Open WebUI possam usar Hailo GenAI diretamente
2. Corrigir deficiências de suporte async do Quart
3. Suporte a endpoint SSE de ferramentas MCP

### Implementação: API Compatível com OpenAI (`hailo_openai_routes.py`)

Criado novo arquivo `extensions/builtin_hailo_genai/hailo_openai_routes.py`. Implementados 4 endpoints:

| Endpoint | Funcionalidade | Modelos Suportados |
|---|---|---|
| `GET /v1/models` | Lista de modelos disponíveis | Todos os modelos + CLIP |
| `POST /v1/chat/completions` | Chat de texto/imagem (suporte a stream) | LLM + VLM |
| `POST /v1/audio/transcriptions` | Transcrição de voz | Whisper |
| `POST /v1/embeddings` | Texto→vetor CLIP | CLIP ViT-B/16 |

#### Decisões de Design

- **Suporte a Vision**: Aceita formato OpenAI Vision API (`image_url` com `data:` base64) diretamente. Além disso, possível referenciar imagens da biblioteca YU diretamente com formato `file_id:123`
- **URLs HTTP não suportadas**: Para prevenir SSRF, `image_url` com `http://` / `https://` não é aceito
- **Aliases de modelos**: Aliases compatíveis com OpenAI definidos como `whisper-1` → `whisper-base`, `clip` → `clip-vit-b-16`
- **Áudio não-WAV**: Conversão automática com ffmpeg (16kHz mono PCM16)
- **Campo Usage**: Hailo SDK não retorna contagem de tokens, então fixado em `0`

#### Ferramenta MCP

- `hailo_genai_openai_info`: Ferramenta helper que retorna lista de endpoints e instruções de uso (gerado localmente sem chamar API)

### Correção: Gerador SSE async do Quart

Todos os arquivos de rotas tinham deficiências de suporte async nos geradores SSE:

| Arquivo | Problema | Correção |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` era função síncrona | Mudar para `async def`, executar `get_llm()` e `next(it)` com `asyncio.to_thread` |
| `hailo_vlm_routes.py` | Idem + referência ao DB era síncrona | Idem + encapsular com `run_db_sync` |
| `hailo_s2t_routes.py` | transcribe executava sincronamente + DB síncrono | `asyncio.to_thread` + encapsular com `run_db_sync` |
| `hailo_chat_routes.py` | Idem (LLM/VLM ambos) | Tornar todas as chamadas bloqueantes async |

No Quart (ASGI), passar gerador síncrono para resposta SSE funciona, mas processamento entre `yield`s bloqueia o event loop, e outras requisições não são processadas durante entrega de SSE.

### Bug Descoberto: Inconsistência de Singleton na Troca de Dispositivo

#### Sintoma

`'NoneType' object has no attribute 'get_context_usage_size'` ao chamar LLM após usar VLM. Também ocorria na direção inversa (LLM→VLM→LLM).

#### Análise da Causa

Como Hailo-10H só pode manter 1 VDevice, `device_manager.py` gerencia exclusivamente. Fluxo na troca de modelo:

1. `get_vlm()` do VLM → `acquire_genai("vlm", ...)` → `_release_internal()` libera o VDevice do LLM internamente
2. Uso do VLM concluído
3. `get_llm()` do LLM → `_instance` ainda existe + `model_name` também coincide → **reutiliza instância existente**
4. O VDevice por trás de `_instance._llm` já foi liberado → `get_context_usage_size()` chamado em `None` → crash

Raiz do problema: `_instance` do singleton persiste, mas os objetos nativos do SDK Hailo (`self._llm`) por trás dele foram liberados pelo `_release_internal()` do `device_manager`. O lado Python ainda está vivo pela contagem de referências, mas os recursos nativos do SDK Hailo foram liberados.

#### Correção

Adicionada verificação de `device_manager.get_current_owner()` na reutilização de singleton em `get_llm()` / `get_vlm()` / `get_s2t()`:

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # mantendo o dispositivo → OK reutilizar
            # dispositivo tomado por outro modelo → recriar
            _instance = None
        ...
```

A mesma correção aplicada a todos os 3 singletons LLM / VLM / S2T.

#### Verificação

Confirmada operação normal em 4 trocas consecutivas LLM → VLM → LLM → VLM.

### Outras Correções

- **Método MCP `post_sse`**: Adicionado método `post_sse()` ao `mcp_server/client.py` que consome stream SSE e retorna texto final como JSON. Ferramentas `hailo_llm_generate` e `hailo_vlm_generate` usam isso
- **Parâmetro MCP `yolo_search`**: Renomeado `labels` → `class_name` (para coincidir com nome de parâmetro no lado da API)
- **Circuit Breaker**: Adicionado `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`). Ferramentas de status como `hailo_genai_status` são permitidas no estado half_open
- **Async de Busca Semântica**: `get_encoder_info()` e `semantic_search()` encapsulados com `run_db_sync` (prevenção de bloqueio do event loop Quart)

### Notas Técnicas

- **Restrição de exclusividade VDevice é em nível de SDK**: Mesmo que você mantenha referência ao objeto em Python, quando os recursos do lado nativo do SDK Hailo são liberados, eles não podem mais ser usados. Ao usar padrão singleton, é necessário verificar separadamente a validade dos recursos nativos
- **Quart + Gerador Síncrono**: Passar gerador síncrono para resposta SSE do Quart funciona, mas o processamento entre `yield`s bloqueia o event loop. Processos pesados como inferência Hailo devem ser movidos para uma thread separada com `asyncio.to_thread`
