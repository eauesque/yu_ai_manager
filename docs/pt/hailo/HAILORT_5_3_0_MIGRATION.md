# Notas de Migração HailoRT 5.2.0 → 5.3.0

Conhecimentos adquiridos da atualização do HailoRT 5.2.0 para 5.3.0 no Raspberry Pi 5 + AI HAT 2 (Hailo-10H). Baseado em testes de implementação de ponta a ponta e análise direta de diff do git nas tags `v5.2.0` / `v5.3.0` oficiais.

**Público-alvo**: Desenvolvedores que executam inferência na NPU Hailo-10H usando Python (`pyhailort`).

---

## TL;DR

- **Praticamente zero mudanças incompatíveis em aplicativos Python típicos de inferência**.
  Os números de destaque (688 arquivos alterados, +12.035 / −8.987 linhas) são grandes, mas as superfícies de `VDevice`, `InferModel` e GenAI (`LLM` / `VLM` / `Speech2Text`) são completamente retrocompatíveis.
- A maior parte das alterações é a **remoção de APIs de câmera/ISP/gerenciamento de firmware Hailo-8** e refatoração interna. Não afeta a inferência NPU pura.
- **Arquivos `.hef` da era v5.2.0 carregam sem alterações no runtime 5.3.0.** Verificado com 5 modelos (YOLOv8n, CLIP ViT-B/16, Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base).
- O driver Linux mudou de `hailo_pci` para `hailo1x_pci`, e o nó de dispositivo de `/dev/hailort0` para **`/dev/h1x-0`**. O `pyhailort` resolve o novo nó internamente, portanto o código Python usando `VDevice()` não requer alterações. **Apenas o passthrough de dispositivo Docker precisa ser atualizado.**
- `Speech2Text.SegmentInfo` expõe atributos `text` / `start_sec` / `end_sec` (mesmo que v5.2.0). `start` ou `start_time` não são expostos e código defensivo usando esses nomes retornará silenciosamente 0.0.

---

## 1. Escopo das Alterações

Diff direto das tags `v5.2.0` e `v5.3.0` do repositório oficial HailoRT no GitHub:

| Escopo | Arquivos | Adições | Remoções |
|---|---:|---:|---:|
| Total | 688 | +12.035 | −8.987 |
| Headers C++ públicos (`include/hailo/`) | 27 | +205 | **−383** |
| Bindings Python (`bindings/python/`) | 35 | +306 | **−413** |
| Somente `pyhailort.py` | 1 | +98 | **−158** |

**As remoções superam as adições.** Esta é uma release de "simplificação".
A maior parte do que foi removido não é relacionada a inferência NPU.

---

## 2. APIs Removidas — Apenas câmera/ISP/firmware Hailo-8

`hailort/libhailort/include/hailo/device.hpp` perdeu 169 linhas, e `platform.h` perdeu 75 linhas. Tudo removido foi controle de dispositivo de baixo nível:

- `firmware_update()` / `second_stage_update()` (reescrita de firmware)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` / `write_user_config()` / `erase_user_config()`

Todas essas são APIs para **módulos de câmera AI Hailo-8** (placas no estilo SoC onde o chip Hailo controla diretamente o ISP e o sensor de imagem). Não são chamadas no fluxo típico `VDevice` → `InferModel` → `generate` com NPU Hailo-10H puro.

**Impacto**: Zero para aplicativos de inferência NPU pura. Apenas aplicativos que realmente controlam módulos de câmera Hailo-8 precisam auditar o uso.

---

## 3. Mudanças de Assinatura Python

| API | v5.2.0 | v5.3.0 | Compatibilidade |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | Padrão `10000` | Padrão `600000` | ✅ Apenas padrão, chamadas existentes sem alteração |
| `Speech2Text.generate_all_text(timeout_ms=)` | Mesmo | Mesmo | ✅ Igual |
| `LLM.read_all(timeout_ms=10000)` | Com padrão | Padrão **removido** (obrigatório) | ⚠️ `read_all()` sem argumento → `TypeError` |
| `DeviceArchitecture.__init__` | 9 argumentos posicionais | +`chip_serial_number` (10) | ⚠️ Construção direta quebra |

**A correção de `read_all()` é uma alteração de 1 linha**:

```python
# Antes (estilo v5.2.0, padrão de 10 segundos)
text = generator.read_all()

# Depois (v5.3.0 requer timeout explícito)
text = generator.read_all(timeout_ms=600000)  # 10 minutos
```

`DeviceArchitecture` raramente é construído diretamente em código de usuário, portanto sua mudança de assinatura tem pouco impacto.

---

## 4. Renomeações de Headers C++ (Transparentes via Python)

Incompatíveis para aplicativos que usam HailoRT diretamente em C++:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10s) → **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10min), renomeado e estendido
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** adicionado, também 10 minutos
- 4 sobrecargas de `generate_from_embeddings()` adicionadas ao `vlm.hpp`

Essas renomeações não se propagam via bindings Python.

---

## 5. Correção de Coordenadas de Bounding Box NMS (Mudança de Comportamento)

Correção de lógica na pós-processamento NMS do `pyhailort.py`:

```python
# v5.2.0
y_min = numpy.ceil(bbox[0] * image_height)
x_min = numpy.ceil(bbox[1] * image_width)
bbox_width = numpy.ceil((bbox[3] - bbox[1]) * image_width)

# v5.3.0
y_min = int(max(numpy.floor(bbox[0] * image_height), 0))
x_min = int(max(numpy.floor(bbox[1] * image_width), 0))
x_max = int(min(numpy.ceil(bbox[3] * image_width), image_width))
bbox_width = x_max - x_min
```

Melhorias:

- Adicionado clipping de limite de imagem `max(0, …)` / `min(image_width, …)`
- `ceil` → `floor` (prevenção de overshoot)
- `bbox_width` recalculado de `x_max - x_min` clippado

**Diferença de comportamento**: Com o mesmo modelo e a mesma imagem, a saída NMS pode mudar em ±1 pixel perto dos limites.

---

## 6. Novas APIs (Adições)

- **`VDevice::create_session(uint16_t port)`** — API de sessão de inferência baseada em rede (novo recurso)
- **`VLM::generate_from_embeddings()`** — 4 sobrecargas. Aceita embeddings de imagem/vídeo pré-computados como entrada `MemoryView`. Permite calcular embeddings uma vez e reutilizá-los em múltiplas chamadas VLM, pulando a recodificação.
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — Filtragem em nível de classe para saída NMS (no chip)
- **`Device::query_performance_stats(sampling_period_ms)`** — Período de amostragem configurável
- **`Device::get_current_limit()`** — Consultar limite de corrente
- **`DeviceArchitecture.chip_serial_number`** — Ler número de série do chip

Todas são aditivas, portanto código existente não quebra. Adote conforme necessário.

---

## 7. Mudanças de Ambiente

### 7.1 Novo Driver PCI Linux

| Item | Antes | Depois |
|---|---|---|
| Módulo do kernel | `hailo_pci` | `hailo1x_pci` |
| Nó de dispositivo | `/dev/hailort0` (ou `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` resolve o novo nó de dispositivo internamente**, portanto código Python usando `VDevice()` continua funcionando sem alterações. Apenas código que abre diretamente `/dev/hailo*` ou `/dev/hailort0` precisa ser atualizado.

#### Passthrough Docker / Podman

Atualize as declarações de passthrough de dispositivo:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # era: /dev/hailort0:/dev/hailort0
```

Atualize também linhas `DeviceAllow=` de unidades systemd e regras udev.

### 7.2 Relaxamento das Restrições do numpy

- `setup.py` do v5.2.0: `numpy<2` (fixo)
- `setup.py` do v5.3.0: `numpy` (sem limite superior)

Aplicativos que antes estavam fixos no numpy 1.x podem atualizar para numpy 2.x junto com o bump do HailoRT.

### 7.3 Compatibilidade Binária HEF

**Arquivos `.hef` baixados para o bucket v5.2.0 carregam e executam sem alterações no runtime 5.3.0.**
Verificado com 5 modelos (Raspberry Pi 5 + AI HAT 2):

| Modelo | Arquivo | Resultado |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 image encoder | `clip_vit_b_16_image_encoder.hef` | ✅ saída de 512 dimensões |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` retorna texto válido |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` retorna texto válido |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` retorna `SegmentInfo` |

### 7.4 Bucket de URL de Download HEF

O Hailo Developer Zone (`dev-public.hailo.ai`) hospeda os buckets v5.2.0 e v5.3.0 em paralelo:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

Status do bucket v5.3.0 em 2026-04-06:

| Modelo | Bucket v5.3.0 |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Aplicativos que precisam de Llama-3.2-1B devem continuar buscando do bucket v5.2.0 por enquanto. HEFs v5.2.0 carregam corretamente no runtime 5.3.0.

---

## 8. Nomes de Atributos `Speech2Text.SegmentInfo`

Tanto no v5.2.0 quanto no v5.3.0, `Speech2Text.generate_all_segments()` retorna objetos `SegmentInfo` com esses atributos públicos:

```python
seg.text        # str
seg.start_sec   # float (segundos)
seg.end_sec     # float (segundos)
```

**`seg.start` ou `seg.start_time` não existem.** Documentação e código de exemplo mais antigos às vezes fazem referência a esses nomes, mas causarão `AttributeError` ou, mais perigosamente, retornarão silenciosamente 0.0 quando envolvidos em código defensivo como `getattr(seg, "start", 0.0)`.

Para verificar os nomes de atributos reais no runtime:

```python
from hailo_platform import VDevice
from hailo_platform.genai import Speech2Text, Speech2TextTask
import numpy as np

vd = VDevice()
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
if segments:
    print([a for a in dir(segments[0]) if not a.startswith("_")])
    # => ['end_sec', 'start_sec', 'text']
```

---

## 9. Script de Smoke Test

Script mínimo para verificar que o ambiente realmente funciona após atualizar para 5.3.0:

```python
"""HailoRT 5.3.0 smoke test — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. Criar VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. Caminho InferModel (YOLOv8n ou qualquer HEF existente)
im = vd.create_infer_model("/path/to/yolov8n.hef")
conf = im.configure()
inp = im.inputs[0]
bindings = conf.create_bindings()
bindings.input().set_buffer(np.zeros(tuple(inp.shape), dtype=np.uint8))
for o in im.outputs:
    fmt = str(getattr(o.format, "type", "")).lower()
    dtype = np.float32 if "float" in fmt else np.uint8
    bindings.output(o.name).set_buffer(np.zeros(tuple(o.shape), dtype=dtype))
conf.run([bindings], timeout=10000)
print("2. InferModel (YOLO) OK")
del conf, im

vd.release()
del vd

# 3. Caminho GenAI LLM
from hailo_platform.genai import LLM
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
llm = LLM(vd, "/path/to/Qwen2.5-1.5B-Instruct.hef")
text = llm.generate_all(
    prompt=[{"role": "user", "content": "Say hi in one word."}],
    temperature=0.1, max_generated_tokens=16,
)
print(f"3. LLM OK: {text!r}")
llm.release(); vd.release()

# 4. Caminho Speech2Text
from hailo_platform.genai import Speech2Text, Speech2TextTask
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
print(f"4. Speech2Text OK: {len(segments)} segments")
if segments:
    seg = segments[0]
    print(f"   attrs: text={seg.text!r} start_sec={seg.start_sec} end_sec={seg.end_sec}")
s2t.release(); vd.release()

print("\nAll smoke tests passed.")
```

---

## 10. Checklist de Atualização

Pontos para auditar no código antes ou durante a atualização 5.2.0 → 5.3.0:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` — **sem alterações necessárias**
- [ ] Construtores `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` — **sem alterações necessárias**
- [ ] Argumentos nomeados de `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` / `.generate_all()` — **sem alterações necessárias**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=, timeout_ms=)` — **sem alterações necessárias** (quando `timeout_ms` é passado explicitamente)
- [ ] Verificar chamadas `LLM.read_all()` sem argumento `timeout_ms` → adicionar timeout explícito se encontrado
- [ ] Verificar construção direta de `DeviceArchitecture` → adicionar `chip_serial_number` se encontrado
- [ ] Fazer grep por aberturas diretas de `/dev/hailo*` ou `/dev/hailort0` → substituir por `/dev/h1x-0` (ou melhor, usar pyhailort)
- [ ] Atualizar seções `devices:` do Docker/Podman para `/dev/h1x-0`
- [ ] Atualizar linhas `DeviceAllow=` de unidades systemd e regras udev
- [ ] Fazer grep por acessos a atributos `SegmentInfo` usando `.start` ou `.start_time` → mudar para `.start_sec` / `.end_sec`
- [ ] Se numpy estava fixado em 1.x (por causa do `numpy<2` do v5.2.0), o pin pode ser removido agora
- [ ] Arquivos `.hef` existentes **não** precisam ser baixados novamente
- [ ] Se URLs de download HEF estão hardcoded com bucket `v5.2.0`, promover para `v5.3.0` (manter `v5.2.0` para Llama-3.2-1B)
- [ ] Se dependendo do pós-processamento NMS built-in do pyhailort, bounding boxes perto das bordas da imagem podem mudar em ±1 pixel

---

## 11. Comandos Usados na Investigação

Assumindo que o repositório oficial HailoRT está clonado:

```bash
cd ~/hailort

# Tamanho geral do diff
git diff --stat v5.2.0 v5.3.0 | tail

# Diff de headers C++ públicos
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Diff de bindings Python
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# Diff completo de pyhailort.py
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# Diff de API pública de header específico (apenas assinaturas de função)
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# APIs removidas de device.hpp
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

Os headers C++ contêm mais informações por linha para análise de API — os bindings Python são quase todos boilerplate pybind11, portanto diffs ingênuos de linhas são enganosos. Faça grep por símbolos públicos.

---

## 12. Conclusão

O headline "688 arquivos alterados" está longe do impacto real.
Em um aplicativo típico de inferência NPU Hailo-10H:

- **A API de inferência NPU principal (`VDevice` / `InferModel` / GenAI) é completamente retrocompatível**
- Todas as APIs removidas são superfícies de câmera/sensor/ISP/gerenciamento de firmware Hailo-8, sem relação com uso apenas NPU
- **Todos os arquivos `.hef` existentes carregam sem novo download**
- A única mudança obrigatória no nível de ambiente é atualizar o passthrough de dispositivo Docker para `/dev/h1x-0`

Principais melhorias de qualidade de vida após a atualização:

- Padrões de timeout drasticamente estendidos (10s → 10min), reduzindo timeouts falsos em geração de texto longo
- `FormatType.FLOAT32` disponível (o v5.2.0 exigia quantização/desquantização manual)
- Correção de bug de clipping de coordenadas NMS
- Caminho de atualização numpy 2.x desbloqueado
- `VLM.generate_from_embeddings()` permite reutilizar embeddings de imagem pré-computados em múltiplas chamadas VLM

Se você está mantendo um aplicativo Python Hailo-10H fixo no 5.2.0 e adiando a atualização, este documento deve confirmar que a migração é quase um no-op.
