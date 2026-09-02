# Danbooru Auto-Tagging — Especificação de Implementação

**Status**: Implementado (Phase 1-5: v2.77.0)
**Alvo**: YU AI Manager
**Propósito**: Atribuir automaticamente tags do Danbooru a imagens de IA usando uma abordagem de duas camadas: WD-Tagger ONNX (CPU) + VLM (API compatível com OpenAI)
**Implementação**: `extensions/builtin_wd_tagger/core_impl/` (12 arquivos), `routes/wd_tagger.py` (11 APIs)

---

## Status de Implementação

| Fase | Status | Localização |
|---|---|---|
| Fase 1: WD-Tagger ONNX | **Completa** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Fase 2: VLM Engine (compatível com OpenAI) | **Completa** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Fase 3: Tag Post-processing | **Completa** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Fase 4: Batch API | **Completa** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Fase 5: UI | **Completa** | Tools page + detail modal WD tag badges + XMP viewer |

### Visão Geral da Implementação das Fases 2/3 (v2.77.0-v2.77.1)

- **VLM Engine** (`engine_vlm.py`): Fallback automático entre API compatível com OpenAI e API nativa do Ollama
- **Composite Engine** (`engine_composite.py`): Pipeline de duas camadas ONNX + VLM (Modo B)
- **Tag Post-processing** (`tag_postprocess.py`): Normalização (minúsculas, underscore, remoção de caracteres inválidos, deduplicação) + filtro NSFW (~30 tags)
- **Engine Factory**: Roteamento por `engine_type` ("onnx" / "vlm" / "both")
- **UI**: Seleção de tipo de engine, configurações de URL/modelo/timeout do VLM, teste de conexão, filtro NSFW
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: `wd_tagger_vlm_test`, `wd_tagger_vlm_models` tools
- **Testado**: Tagging de imagem real confirmado com Ollama qwen2.5vl:7b, 23 testes unitários passando

---

## Prior Art

### DeepDanbooru (KichangKim)
- **Abordagem**: Modelo de classificação de imagem (TensorFlow) para previsão direta de tags
- **Pontos Fortes**: Rápido, especializado em tags, ONNX-conversível
- **Pontos Fracos**: Conjunto de tags fixo, não pode se adaptar a novas tags
- **Referência**: Já integrado no A1111

### WD-Tagger (SmilingWolf) — Adotado na Fase 1
- **Abordagem**: Sucessor do DeepDanbooru. Quatro arquiteturas: SwinV2/ViT/ConvNeXt/EVA02
- **Pontos Fortes**: Precisão maior que DeepDanbooru, classificação de categoria incluída (general/character/copyright/rating)
- **ONNX**: Modelos ONNX oficiais + `selected_tags.csv` distribuídos no HuggingFace
- **Entrada**: 448x448 RGB (proporção preservada + preenchimento branco)

### DanTagGen / DTG (KohakuBlueleaf)
- **Abordagem**: LLM baseado em LLaMA (400M) para geração e conclusão de tags
- **Pontos Fortes**: Conclusão de tags ciente de contexto
- **Pontos Fracos**: Lento devido à inferência de LLM
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### Justificativa do Design
O sistema suporta **tanto** WD-Tagger ONNX (rápido, confiável) quanto Qwen2-VL via hailo-ollama (flexível, ciente de contexto), para que os usuários possam escolher a ferramenta certa para o trabalho.

---

## Arquitetura

```
[Image Input]
    |
[Engine Selection]  (engine_factory.py)
    |-- WD-Tagger ONNX (rápido, conjunto de tags fixo ~10,000 tags)  [Fase 1: implementado]
    |       | Scores de confiança + lista de tags categorizada
    |-- Qwen2-VL via hailo-ollama (lento, flexível, ciente de contexto)   [Fase 2]
    |       | Array JSON -> parse de tags
    |-- Duas camadas: ONNX -> complemento de Qwen2-VL                    [Fase 2 option]
    |       | Alimentar tags ONNX em prompt, deixar LLM gerar tags adicionais
    |
[Post-processing: normalização de tags, filtragem NSFW]  [Fase 3]
    |
[DB: salvar em tabela file_wd_tags]  (store.py)
[XMP: embutir em arquivo (opcional)]  (xmp_write.py)
```

---

## Fase 1: WD-Tagger ONNX Engine — Implementado

**Modelo**: SmilingWolf/wd-swinv2-tagger-v3 (recomendado), ViT v3, ConvNeXt v3, EVA02-Large v3

**Arquivos de implementação** (`extensions/builtin_wd_tagger/core_impl/`):
| Arquivo | Linhas | Papel |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | Parse de selected_tags.csv, mapeamento de categoria |
| `model_download.py` | ~120 | Download HTTP do HuggingFace |
| `engine_onnx.py` | ~150 | Inferência ONNX (448x448, BGR, filtragem de threshold) |
| `engine_factory.py` | ~50 | Cache de engine + criação |
| `store.py` | ~130 | CRUD de DB (tabela file_wd_tags) |
| `xmp_xml.py` | ~60 | Construção de pacote XMP |
| `xmp_read.py` | ~90 | Leitura de XMP |
| `xmp_write.py` | ~160 | Escrita de XMP em PNG/JPEG/WebP |
| `config_ops.py` | ~70 | Leitura/escrita de config.json |
| `single_ops.py` | ~80 | Pipeline de tagging de imagem única |
| `batch_ops.py` | ~120 | Processamento em lote (integração JobManager) |

**DB**: `file_wd_tags` table (schema v14)
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**: `routes/wd_tagger.py` — 11 endpoints

---

## Fase 2: VLM Engine (API compatível com OpenAI) — Implementado (v2.77.0)

**Propósito**: Complementar WD-Tagger ONNX com descrições detalhadas e tags contextuais que ONNX não pode capturar
**Implementação**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (engine VLM genérico compatível com OpenAI)
**Nota**: A especificação original planejava um `engine_hailo.py` específico de Hailo, mas a implementação real usa um engine genérico `engine_vlm.py` que trata Ollama, hailo-ollama e outros servidores compatíveis com OpenAI uniformemente. Ele suporta fallback automático entre a API compatível com OpenAI (`/v1/chat/completions`) e a API nativa do Ollama (`/api/chat`).

### Configuração de Hardware

| Item | Especificação |
|---|---|
| **Device** | Raspberry Pi 5 + Hailo-10H AI accelerator |
| **Memória** | 8GB RAM |
| **Modelo VLM** | **Qwen2-VL-2B-Instruct** (único VLM no Hailo Model Zoo) |
| **Framework de Inferência** | hailo-ollama (API compatível com OpenAI) |
| **Endpoint** | `http://<pi-ip>:8000/v1/chat/completions` |

### Características do Modelo

- **Qwen2-VL-2B-Instruct**: Um modelo Vision-Language da família Qwen (2B parâmetros)
- Pertence à família Qwen, não à família llava. A precisão de compreensão de imagem é geralmente superior aos modelos baseados em llava
- Em 2B parâmetros, cabe confortavelmente no Hailo-10H 8GB RAM
- O Qwen2 somente texto (1.5B) foi confirmado a funcionar com hailo-ollama
- **Nota**: Em 2026-02, este é o único VLM disponível para Hailo-10H

### Design de Prompt

```python
SYSTEM_PROMPT = """Você é um assistente de tagging de imagens do Danbooru.
Analise a imagem e produza APENAS tags no estilo Danbooru como um array JSON.
Regras:
- Use underscores em vez de espaços (por exemplo, long_hair, blue_eyes)
- Saída APENAS do array JSON, nenhum outro texto
- Inclua tags para: contagem de personagens, gênero, cabelo, olhos, roupas, pose, fundo, estilo de arte
- NÃO inclua tags de copyright ou nome de personagem a menos que claramente identificáveis
- Máximo 40 tags
Saída de exemplo: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Marque esta imagem com tags do Danbooru."
```

### Design de Implementação (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100 linhas)

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct via hailo-ollama (API compatível com OpenAI)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # Inferência de tipo MIME
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Formato de resposta: lista ou {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs não retornam scores de confiança
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Verificar conectividade ao servidor hailo-ollama."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### Modos de Operação

**Modo A: Qwen2-VL Independente**
```
Imagem -> Qwen2-VL -> Array JSON de tags -> Normalização -> Salvar em DB
```
- O LLM analisa diretamente a imagem e gera tags
- Sem scores de confiança (uniformemente definidos em 0.5)
- Tagging flexível sem conjunto de tags fixo
- Velocidade: ~3-10 segundos por imagem (estimado em Hailo-10H)

**Modo B: WD-Tagger ONNX -> Complemento de Qwen2-VL (Duas camadas)**
```
Imagem -> WD-Tagger ONNX -> Tags de alta confiança (>=0.7)
                              |
                              v
    Qwen2-VL: "Essas tags descrevem a imagem. Sugira tags adicionais."
                              |
                              v
    Tags ONNX + tags de complemento LLM -> Merge -> Normalização -> Salvar em DB
```
- Combina tags ONNX confiáveis com compreensão contextual do LLM
- Incluir tags ONNX no prompt deve melhorar a precisão do LLM
- Velocidade: ONNX (~0.5s) + LLM (~3-10s) = ~4-11 segundos por imagem

**Prompt do Modo B**:
```python
补完_SYSTEM_PROMPT = """Você é um assistente de tagging de imagens do Danbooru.
A imagem já tem essas tags de classificação automatizada: {existing_tags}
Analise a imagem e sugira tags ADICIONAIS no estilo Danbooru não na lista acima.
Saída APENAS de um array JSON de novas tags. Use underscores em vez de espaços.
Concentre-se em: composição, clima, detalhes de fundo, itens de roupa específicos, estilo de arte.
Máximo 20 tags adicionais.
Exemplo: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### Adição a engine_factory.py

```python
# Adição a get_engine() em engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Duas camadas: complemento ONNX -> Hailo (opção Fase 2)
    ...
```

### Entradas config.json

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### Verificação Pré-implementação (Teste de Hardware Pi)

1. **Confirme que Qwen2-VL-2B-Instruct inicia em hailo-ollama**
   ```bash
   # No Pi
   hailo-ollama run qwen2-vl:2b
   ```

2. **Confirme que requisições de visão funcionam através da API compatível com OpenAI**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "O que há nesta imagem?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Confirme que saída JSON no formato Danbooru é estável**
   - Verifique se hailo-ollama suporta `response_format: json_object`
   - Um fallback de extração JSON baseado em regex de saída de texto é necessário se não suportado

4. **Meça velocidade de inferência real** — segundos por imagem (necessário para cálculo de tamanho de lote)

---

## Fase 3: Tag Post-processing — Implementado (v2.77.0)

**Implementação**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**Integração**: Automaticamente aplicado após inferência em `single_ops.py` / `batch_ops.py`

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Remover caracteres inválidos
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicar e ordenar
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # Lista de tags NSFW (gerenciada em arquivo separado)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Integração com Fase 1**:
- WD-Tagger ONNX já separa tags de rating usando categoria 9 (rating)
- O filtro NSFW usa tags de rating (`explicit`, `questionable`) mais uma lista NSFW adicional
- Implementação: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` (~80 linhas)

---

## Fase 4: Batch Processing API — Implementado

**API** (`routes/wd_tagger.py`):

| Método | Path | Propósito |
|---|---|---|
| POST | `/api/wd-tagger/batch` | Iniciar lote (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | Marcar uma única imagem |
| GET | `/api/wd-tagger/tags/<file_id>` | Recuperar tags |
| DELETE | `/api/wd-tagger/tags/<file_id>` | Deletar tags |
| GET | `/api/wd-tagger/stats` | Estatísticas |
| GET | `/api/wd-tagger/untagged` | Listar arquivos não marcados |
| GET/POST | `/api/wd-tagger/config` | CRUD de configurações |
| POST | `/api/wd-tagger/model/download` | Download de modelo |
| GET | `/api/wd-tagger/model/status` | Status do modelo |
| GET | `/api/wd-tagger/xmp/<file_id>` | Leitura de XMP |

**Fluxo de processamento** (`batch_ops.py`):
1. Processar arquivos em `file_ids` sequencialmente (padrão para arquivos sem marca com `meta_source=unknown` quando não especificado)
2. Executar inferência através do engine
3. UPSERT na tabela `file_wd_tags` (engine identificado pela coluna model)
4. Embutir XMP no arquivo (opcional)
5. Rastrear progresso e suportar cancelamento via JobManager

---

## Fase 5: UI — Implementado

**Página de ferramentas** (`templates/tools/content/primary/_wd_tagger.html`):
- Seleção de modelo (4 modelos), sliders de threshold (general/character)
- Toggle de escrita XMP, botão de download de modelo
- Botão de execução em lote + barra de progresso
- Exibição de estatísticas (contagem de tags, breakdown por categoria, contagem de não marcados)

**Modal de detalhe**:
- Badges WD (general=azul, character=verde, copyright=laranja, rating=vermelho)
- Botão do visualizador XMP (dc:subject + namespace wdtag + XML bruto)
- Clique em tag dispara pesquisa

---

## Estrutura de Arquivo (Atual)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # Inicialização de módulo
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # Parse de selected_tags.csv
├── model_download.py        # Download de modelo do HuggingFace
├── engine_onnx.py           # Inferência WD-Tagger ONNX [Fase 1]
├── engine_vlm.py            # VLM engine (compatível com OpenAI) [Fase 2: completo]
├── engine_composite.py      # Duas camadas ONNX + VLM [Fase 2: completo]
├── engine_factory.py        # Criação de engine + cache
├── store.py                 # CRUD de DB (file_wd_tags)
├── xmp_xml.py               # Construção de pacote XMP
├── xmp_read.py              # Leitura de XMP
├── xmp_write.py             # Escrita de XMP (PNG/JPEG/WebP)
├── config_ops.py            # Leitura/escrita de config.json
├── single_ops.py            # Pipeline de tagging de imagem única
├── batch_ops.py             # Processamento em lote (JobManager)
├── batch_processors.py      # Lógica interna de processamento em lote
└── tag_postprocess.py       # Normalização de tags, filtro NSFW [Fase 3: completo]

routes/wd_tagger.py          # API endpoints (11 total)

src/ts/tools-page/wd-tagger/
├── core.ts                  # CRUD de configurações, lote, download de modelo
└── render.ts                # Renderização DOM

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # Modal de detalhe WD tags + visualizador XMP
```

---

## Prioridade de Implementação (Atualizada)

```
Fase 1 (WD-Tagger ONNX)        -> Completa
Fase 4 (Batch API)              -> Completa
Fase 5 (UI)                     -> Completa
Fase 3 (Post-processing/NSFW)   -> Próximo (~80 linhas adicionais)
Fase 2 (Qwen2-VL hailo-ollama) -> Após teste de hardware Pi (~100 linhas adicionais + mudanças factory)
```

---

## Referências

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API specification: Referir ao código-fonte do fork modificado

---

*Criado: 2026-02-27 / Atualizado: 2026-02-27 (implementação da Fase 1 completa, Fase 2 revisada para base Qwen2-VL)*
