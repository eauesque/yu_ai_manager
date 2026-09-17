# Extensão de Pesquisa Semântica Hailo — Especificação de Implementação

**Status**: Implementado — A versão específica de Hailo foi superada por CLIP ONNX (v2.95.0)
**Alvo**: Extensão YU AI Manager
**Propósito**: Pesquisa de imagem semântica usando CLIP/SigLIP em Hailo-10H (AI HAT 2)
**Implementação**: `extensions/builtin_clip_search/core_impl/` (camada compartilhada) + `extensions/builtin_clip_onnx/core_impl/` (implementação ONNX)
**Nota**: Esta especificação descreve o design inicial apenas de Hailo. A implementação atual usa uma arquitetura ONNX multi-backend unificada

---

## Visão Geral

Esta Extensão adiciona a capacidade de pesquisar imagens usando texto em linguagem natural.
Exemplos: "céu azul e oceano", "garota sorrindo", "paisagem noturna da cidade" — tudo retorna imagens visualmente similares.

Deve funcionar **em paralelo** com a pesquisa existente de tags FTS5 e pesquisa de similaridade pHash.
A Extensão simplesmente se desativa em ambientes onde nenhum dispositivo Hailo está presente.

---

## Arquitetura

```
[Durante scan de imagem]
Arquivo de imagem -> CLIP Image Encoder (Hailo HEF) -> vetor de 512 dimensões -> Armazenamento em DB

[Durante pesquisa]
Entrada de texto -> CLIP Text Encoder (CPU / Hailo HEF) -> vetor de 512 dimensões
                 -> Pesquisa de similaridade cosseno -> lista de file_id -> Mesclar com resultados de pesquisa existentes
```

**Tanto CLIP quanto SigLIP são suportados**, alternáveis via configuração.
SigLIP oferece maior precisão, mas CLIP tem um histórico mais forte e mais recursos da comunidade.
A abordagem recomendada é começar com CLIP e adicionar SigLIP depois.

---

## Breakdown de Fase

### Fase 1: Verificação de Viabilidade (Faça Isso Primeiro)

Após se mover para o ambiente Pi5, tenha o Claude Code executar os seguintes passos **na ordem de cima para baixo**.
Pare em qualquer passo que falhar e resolva o problema antes de continuar.

#### Passo 1-1: Verificar HailoRT Runtime

```bash
# Verificar reconhecimento de dispositivo
hailortcli fw-control identify

# Verificar bindings de Python
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **Dispositivo não visível**: Verifique status do driver com `dmesg | grep hailo`. Verifique conexão PCIe do AI HAT 2
- **Falha de import**: Instale via `pip install hailort` ou do repositório APT do Hailo (`python3-hailort`)

#### Passo 1-2: Baixar Arquivos HEF de CLIP

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Image encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Text encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / Acesso negado**: Registro no Hailo Developer Zone (https://hailo.ai/developer-zone/) é necessário.
  Após registro, tente baixar via CLI do Model Zoo (`hailo_model_zoo`)
- **Verificação de tamanho**: Cada arquivo deve ter dezenas de MB até ~100 MB. Um arquivo anormalmente pequeno indica falha de download

#### Passo 1-3: Instalar Dependências Python

```bash
# Necessário para pré-processamento de imagem (usado na Fase 1)
pip install opencv-python-headless numpy

# Verificar
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Passo 1-4: Teste Minimalista de Inferência

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# Verificar informações de camada de entrada/saída do HEF (nomes de camada variam por modelo)
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Esperado: (224, 224, 3) etc.
    print(f"Input: name={input_name}, shape={input_shape}")

    # Teste de inferência com imagem dummy
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # Sucesso se um vetor de 512 dimensões for produzido
```

- **Erro de VDevice (`not enough free devices`)**: hailo-ollama pode estar em execução. Pare com `systemctl stop hailo-ollama` e tente novamente
- **Inferência bem-sucedida mas dimensões de saída não são 512-dim**: Verifique a versão HEF e variante de modelo

#### Passo 1-5: Critérios de Decisão

| Resultado | Próxima Ação |
|------|----------------|
| Saída de vetor de 512-dim | Proceda para Fase 2 e além |
| HEF carrega com sucesso mas dimensões de saída diferem | Tente uma variante de modelo diferente (clip_resnet_50 etc.) |
| Não pode baixar HEF | Registre no Developer Zone -> baixe via Model Zoo CLI |
| Não pode importar hailo_platform | Reinstale HailoRT. Caia de volta para CPU CLIP se não resolvido |
| Dispositivo não reconhecido | Problema de conexão/driver de hardware. Pause desenvolvimento desta Extensão |

Proceda com implementação completa se Fase 1 bem-sucedida. Considere CPU CLIP como alternativa se não.

---

### Fase 2: Extensão de Schema de DB

Adicione à migração de DB existente:

```sql
-- migration 14: semantic search vectors
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- array numpy float32 -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

Armazenamento: `numpy.ndarray.tobytes()` -> BLOB
Carregamento: `numpy.frombuffer(blob, dtype=numpy.float32)`

**Nota**: SQLite não tem ANN (Approximate Nearest Neighbor) index, então todos os 200,000 registros requerem cálculo de similaridade cosseno completo. Cálculo em lote com numpy deve manter isso dentro de limites aceitáveis em Pi5 (medição necessária). Considere extensão `sqlite-vec` se a contagem de registros crescer significativamente.

---

### Fase 3: Núcleo de Inferência Hailo

**Estrutura de arquivo**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Ponto de entrada da Extensão
├── core/
│   ├── hailo_clip.py     # Wrapper de inferência Hailo CLIP
│   ├── cpu_clip.py       # Fallback de CPU para ambientes não-Hailo (opcional)
│   └── vector_store.py   # CRUD de vetor de DB
├── routes/
│   └── semantic_search.py  # Endpoints de API
└── templates/
    └── _semantic_search_ui.html
```

**Responsabilidades de `hailo_clip.py`**:
- Carregamento de HEF e inicialização de VDevice (singleton, uma vez na inicialização)
- Imagem -> pré-processamento (redimensionamento 224x224, normalização) -> inferência HEF -> vetor de 512 dimensões
- Texto -> tokenização -> inferência HEF -> vetor de 512 dimensões
  * Use o HEF do text encoder se disponível para Hailo-10H; caso contrário use CPU (biblioteca transformers)

**Pré-processamento**:
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Fase 4: API de Construção de Index

**Endpoint**:
```
POST /api/extensions/hailo-semantic/index
```
- Processa imagens não-indexadas sequencialmente em uma thread de background
- Envia progresso via SSE como eventos `semantic_index.progress`
- Opcionalmente ganchos no evento existente `scan.complete` para execução automática

**Tamanho de lote**: 32 imagens por lote (equilibrando memória e velocidade)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Fase 5: API de Pesquisa Semântica

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**Fluxo de processamento**:
1. Converta texto `q` para um vetor
2. Carregue todos os vetores de `file_vectors` (numpy)
3. Compute similaridade cosseno em lote
4. Ordene resultados acima de `threshold` por similaridade decrescente
5. Retorne lista de `file_id` no formato `/api/search` existente

**Cálculo de similaridade cosseno**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**Alvo de desempenho**: Menos de 1 segundo para 200,000 registros (alcançável com cálculo em lote numpy, até em Pi5)

---

### Fase 6: Integração de UI

Adicione uma aba "Semantic Search" à UI de pesquisa existente.
Pode ser uma UI independente não integrada ao condition-builder existente (integração é para o futuro).

```html
<!-- Adicione botão de toggle próximo à barra de pesquisa -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 Semantic Search (Hailo)
</button>
```

- Oculte ou desabilite o botão quando nenhum dispositivo Hailo for detectado
- Reutilize a grade existente para resultados de pesquisa
- Mostre um prompt para construir o index quando nenhum index existir

---

## Configuração (adição config.json)

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## Fatos Verificados (em 2026-02-27)

As seguintes informações foram confirmadas através de pesquisa anterior. Use como referência durante execução de Fase 1.

### Disponibilidade de HEF de CLIP

Hailo Model Zoo v5.2.0 contém **tanto image quanto text encoder** HEFs para Hailo-10H em variantes CLIP/SigLIP:

| Modelo | Image Encoder HEF | Text Encoder HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | Disponível | Disponível |
| clip_vit_b_32 | Disponível | Disponível |
| clip_vit_l_14 | Disponível | Disponível |
| clip_resnet_50 | Disponível | Disponível |
| siglip_b_16 | Disponível | Disponível |
| siglip_l_16_256 | Disponível | Disponível |
| siglip2_b_32_256 | Disponível | Disponível |
| Variantes TinyCLIP | Disponível | Disponível |

Padrão de URL S3: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### Status do Text Encoder

- O aplicativo oficial `hailo-CLIP` executa **o text encoder em CPU (PyTorch)**
- HEFs de Text Encoder para Hailo-10H existem em Model Zoo, mas **nenhum aplicativo publicado os usa**
- Abordagem recomendada: **Implemente o text encoder em CPU (`sentence-transformers`)**. Ele é executado apenas uma vez por consulta de pesquisa, então velocidade não é uma preocupação
- O image encoder é onde aceleração Hailo fornece valor real (indexação em lote de 200K imagens)

### Coexistência com hailo-ollama

- Compartilhamento de dispositivo via `SHARED_VDEVICE_GROUP_ID` é oficialmente suportado
- No entanto, **o binário hailo-ollama não participa deste compartilhamento** (ocupa exclusivamente o dispositivo)
- Exemplo da comunidade: Um gerenciador de dispositivo customizado foi construído para executar 6 serviços simultaneamente
- **Abordagem prática**: Pare hailo-ollama durante construção de index e compartilhe tempo com o dispositivo
  - `systemctl stop hailo-ollama` -> Construir index -> `systemctl start hailo-ollama`

### Estimativas de Pesquisa de Vetor para 200,000 Registros

- 200K x 512 float32 = aproximadamente 400MB — cabe em Pi5 (8GB) RAM
- Similaridade cosseno em lote numpy deve completar em menos de 1 segundo no Cortex-A76 do Pi5

### Aceleração FAISS para Pesquisa de Vetor em Larga Escala (v3.26.0)

Suporte para FAISS (Facebook AI Similarity Search) foi adicionado em v3.26.0. O sistema auto-detecta `faiss-cpu` quando instalado e usa pesquisa aproximada de vizinho mais próximo em vez de brute force de NumPy.

| Escala | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (pesquisa exata de produto interno) é auto-selecionado
- **>= 50K**: IndexIVFFlat (clustering IVF) é auto-selecionado, nprobe = nlist/10
- Cai de volta para NumPy quando FAISS não está instalado (sem impacto)

**Instalação**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # Direct pip install funciona em x86_64
# Em aarch64 (RPi): conda install -c conda-forge faiss-cpu ou compilar do código-fonte
```

O log de inicialização mostra `FAISS x.x.x detected — using accelerated vector search` quando ativo.

### Notas sobre o Aplicativo hailo-CLIP

- `hailo-ai/hailo-CLIP` alvo **Hailo-8/8L**. Hailo-10H não é suportado
- É projetado para classificação zero-shot em tempo real, não pipelines de pesquisa de imagem
- Serve como material de referência mas não pode ser usado diretamente. Um pipeline customizado deve ser construído usando a API HailoRT

---

## Alternativa (Quando Hailo Não Está Disponível)

`sentence-transformers` com `clip-ViT-B-32` fornece suporte apenas em CPU para CLIP.
É mais lento mas permite a mesma Extensão rodar em ambientes sem Hailo.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

Definir `"device": "cpu"` na configuração da Extensão habilita modo CPU. Esta abordagem dual-arquitetura maximiza portabilidade.

---

## Prioridade de Implementação

```
Fase 1 (Verificação)   -> Necessária, faça isto primeiro
Fase 2 (DB)             -> Após sucesso de Fase 1
Fase 3 (Núcleo de Inferência) -> Após Fase 2
Fase 4 (Indexação)      -> Após Fase 3
Fase 5 (API de Pesquisa) -> Após Fase 4
Fase 6 (UI)             -> Após Fase 5, último
```

Alterne a abordagem inteira para CPU CLIP se Fase 1 falhar.

---

## Repositórios de Referência

- `hailo-ai/hailo-apps`: Amostras de classificação zero-shot CLIP
- `hailo-ai/hailort`: Referência de API pyHailoRT
- `hailo-ai/Hailo-Application-Code-Examples`: Amostras de inferência Python
- `hailo-ai/hailo_model_zoo`: Fonte de download HEF CLIP/SigLIP

---

*Criado: 2026-02-27*
*Adendo de pesquisa: 2026-02-27 — Detalhes de procedimento de Fase 1, confirmação de disponibilidade de HEF, análise de coexistência com hailo-ollama*
