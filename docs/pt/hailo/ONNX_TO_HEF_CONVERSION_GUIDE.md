# Guia de Conversão ONNX → HEF

**Objetivo**: Converter modelos ONNX como WD-Tagger para o formato HEF Hailo e possibilitar inferência na NPU Hailo-10H  
**Ambiente de execução**: x86_64 Linux (servidor de IA) — Hailo Dataflow Compiler suporta apenas x86  
**Ambiente de inferência**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## Conhecimento Preliminar

### Por Que a Conversão É Necessária

| Item | ONNX Runtime (atual) | Hailo HEF (objetivo) |
|------|---------------------|-------------------|
| Destino de execução | CPU | NPU Hailo-10H (40 TOPS) |
| Quantização | float32 | INT8 (uint8) |
| Velocidade de inferência | ~500ms/image (Pi5 CPU) | ~20ms/image (estimativa, baseada em resultados CLIP) |
| Memória | ~200MB (carregamento do modelo) | ~dezenas de MB (HEF) |

### Visão Geral do Pipeline de Conversão

```
model.onnx (float32)
  |
  | [1] Parser Hailo Model Zoo (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] Otimização (fusão de camadas, layout de memória)
  v
model_optimized.har
  |
  | [3] Quantização (float32 → INT8, usando imagens de calibração)
  v
model_quantized.har
  |
  | [4] Compilação (conversão para instruções HW)
  v
model.hef (Hailo Executable Format)
```

---

## 1. Configuração do Ambiente do Servidor de IA

### 1-1. Instalação do Hailo Dataflow Compiler

Baixar da Hailo Developer Zone (https://hailo.ai/developer-zone/).
Requer registro de conta.

```bash
# Python 3.10 ou 3.11 recomendado (3.12+ pode não ser suportado)
python3 --version

# Criar venv
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Instalar Hailo Dataflow Compiler (DFC)
# Especificar o .whl baixado da Developer Zone
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# Pacotes de dependência
uv pip install numpy pillow onnx onnxruntime
```

**Verificação**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (Opcional mas Recomendado)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

O Model Zoo contém configurações de conversão (YAML) para muitos modelos, que servem como referência.

---

## 2. Preparação do Modelo Alvo

### 2-1. Modelo WD-Tagger

Modelos atualmente em uso:
- **Repositório**: `SmilingWolf/wd-swinv2-tagger-v3`, etc. no HuggingFace
- **Arquivo**: `model.onnx` (~110MB, float32)
- **Entrada**: `(1, 448, 448, 3)` float32, BGR, sem normalização [0, 255]
- **Saída**: `(1, num_tags)` float32, probabilidades pós-sigmoid

```bash
# Baixar do HuggingFace
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# Obter model.onnx e selected_tags.csv
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. Verificar Entrada/Saída do Modelo ONNX

```python
import onnx

model = onnx.load("model.onnx")

print("=== Entrada ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== Saída ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

Anote o shape e o nome de entrada/saída. Necessários na conversão.

---

## 3. Preparação das Imagens de Calibração

A quantização INT8 requer um conjunto representativo de imagens (dados de calibração).
Usados para determinar os parâmetros de quantização (scale/zero_point).

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### Requisitos

- **Quantidade**: Aproximadamente 100~1000 (mais é mais estável, mas mais lento)
- **Conteúdo**: Amostras representativas das imagens que serão inferidas (variações de imagens geradas por IA)
- **Formato**: JPEG/PNG
- **Tamanho**: Qualquer (redimensionado pelo script de pré-processamento)

```bash
# Exemplo: copiar aleatoriamente 500 imagens da biblioteca yu_ai_manager
# (transferir via scp do Pi para o servidor de IA)
scp pi@raspberrypi:/path/to/images/*.png ~/hailo_convert/calibration_images/
```

### Script de Pré-processamento de Calibração

É necessário aplicar o mesmo processamento do WD-Tagger:

```python
# calibration_preprocess.py
"""Pre-processar imagens de calibração no formato WD-Tagger."""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Mesmo pré-processamento que engine_onnx.py do yu_ai_manager."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # Composição em fundo branco (suporte a transparência)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Redimensionar preservando proporção
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Padding branco para quadrado
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """Retornar imagens de calibração como tensor em lote."""
    images = []
    for p in sorted(Path(image_dir).glob("*")):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            images.append(preprocess(str(p)))
        except Exception as e:
            print(f"  skip {p.name}: {e}")
        if len(images) >= max_images:
            break

    print(f"Loaded {len(images)} calibration images")
    return np.stack(images, axis=0)  # (N, 448, 448, 3)


if __name__ == "__main__":
    dataset = load_calibration_set("calibration_images")
    np.save("calibration_data.npy", dataset)
    print(f"Saved: calibration_data.npy {dataset.shape}")
```

---

## 4. Executando a Conversão HEF

### 4-1. Script de Conversão

```python
# convert_wd_tagger.py
"""Script de conversão WD-Tagger ONNX → Hailo HEF."""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== Configuração ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Para Hailo-10H
# ==========================

# --- Passo 1: Parse ONNX → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

# start_node / end_node especifica os nomes dos nós de entrada/saída do modelo
# (especificar os nomes confirmados no Passo 2-2)
hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # especificar se necessário
)
print(f"  Parsed: {len(npz)} layers")

# --- Passo 2: Otimização do modelo ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Passo 3: Quantização INT8 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Passo 4: Compilação → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# Salvar HAR (arquivo intermediário) também (para depuração)
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. Execução

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# Pré-processamento das imagens de calibração
python calibration_preprocess.py

# Conversão HEF
python convert_wd_tagger.py
```

**Estimativa de tempo**: Varia com o tamanho do modelo e número de imagens de calibração, mas algumas dezenas de minutos a várias horas.

### 4-3. Erros Comuns e Soluções

| Erro | Causa | Solução |
|--------|------|------|
| `UnsupportedOp: <op_name>` | Operador ONNX não suportado pelo DFC | Verificar lista de operadores suportados da Hailo. Para ops não suportados, modificar o modelo ou remover com `onnx-simplifier` |
| `Shape mismatch` | Shape de entrada é dinâmico | Especificar shape fixo explicitamente com `net_input_shapes` |
| `Quantization error` / degradação de precisão | Dados de calibração inadequados | Aumentar número de imagens, usar imagens operacionais reais |
| `Memory allocation failed` | Modelo muito grande para a memória da NPU | Fixar batch size=1 ou considerar modelo mais leve |
| `hailo_sdk_client not found` | DFC não instalado | Verificar Passo 1-1 |

### 4-4. (Recomendado) Pré-processamento com onnx-simplifier

Simplificar o modelo ONNX antes da conversão aumenta a taxa de sucesso:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. Verificação Após Conversão (no Servidor de IA)

### 5-1. Verificação de Precisão com Emulador Hailo

Permite verificar a precisão do modelo convertido para HEF sem hardware real:

```python
# verify_hef.py
"""Comparar saída HEF com ONNX para verificar degradação de precisão."""
import numpy as np
import onnxruntime as ort

# Inferência ONNX (float32, valor de referência)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # extrair 1 imagem
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# Inferência do emulador HEF
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# Comparação
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# Taxa de correspondência de tags (correspondência na limiar 0.35)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**Critérios de julgamento**:
- Similaridade cosseno > 0.95: Bom
- Taxa de correspondência de tags > 90%: Nível prático
- Taxa de correspondência de tags < 80%: Revisão dos dados de calibração necessária

---

## 6. Transferência para Pi e Teste no Hardware Real

### 6-1. Transferência do Arquivo HEF

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. Teste de Inferência no Hardware Real

```python
# test_wd_tagger_hef.py (executar no Pi5)
"""Teste de inferência no hardware real do WD-Tagger convertido para HEF."""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """Mesmo pré-processamento que engine_onnx.py (mas com saída uint8)."""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    img = img.resize((int(old_w * scale), int(old_h * scale)), Image.LANCZOS)
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - img.width) // 2, (INPUT_SIZE - img.height) // 2))
    arr = np.array(padded, dtype=np.uint8)
    arr = arr[:, :, ::-1]  # RGB -> BGR
    return arr

# Imagem de teste
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Entrada
    bindings.input().set_buffer(test_img)

    # Buffer de saída (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # Inferência
    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")
    print(f"Output range: [{output_buf.min()}, {output_buf.max()}]")

    # Desquantização
    try:
        qi = out_info.quant_infos[0]
        scale = qi.qp_scale
        zp = qi.qp_zp
    except Exception:
        scale, zp = 1.0 / 255.0, 0.0

    probs = (output_buf.astype(np.float32) - zp) * scale
    print(f"Dequantized range: [{probs.min():.4f}, {probs.max():.4f}]")
```

---

## 7. Problemas Conhecidos

### Possibilidade de Conversão da Arquitetura SwinV2

O WD-Tagger v3 é baseado em **Swin Transformer V2**. Os seguintes ops podem não ser suportados pelo DFC:

- **Window Attention** (shifted window)
- Operação **Roll**
- **Relative Position Bias**

Alternativas se SwinV2 não puder ser convertido:
1. **wd-vit-tagger-v3** (baseado em Vision Transformer) — ViT é da mesma família que CLIP com histórico de conversão Hailo
2. **wd-convnext-tagger-v3** (baseado em ConvNeXt) — baseado em CNN, mais fácil de converter
3. **wd-eva02-large-tagger-v3** (baseado em EVA-02) — modelo grande (300MB+), cuidado com memória da NPU

### Diferença de Pré-processamento

- **Versão ONNX**: Entrada float32 (faixa 0-255, sem normalização)
- **Versão HEF**: Entrada uint8 (normalização incorporada no HEF)

Ao converter para HEF, o pré-processamento pode ser incorporado no HEF.
Confirmar o tratamento do pré-processamento ao chamar `translate_onnx_model()` no DFC.

### Parâmetros de Desquantização

A saída é quantizada em uint8. Para restaurar corretamente as probabilidades de tags (0.0-1.0),
é obrigatório usar os parâmetros de quantização (scale/zero_point) do HEF.
Consultar o resultado de CLIP (`extensions/builtin_hailo_semantic_search/core_impl/dequantize.py`) como referência.

---

## 8. Template de Instrução para Claude

Exemplo de prompt ao solicitar ao Claude trabalho de conversão em servidor de IA:

```
Por favor, converta o modelo ONNX WD-Tagger para Hailo HEF seguindo os passos abaixo.

1. Ativar ~/hailo_env
2. Baixar model.onnx para ~/hailo_convert/wd_tagger/
3. Criar dados de calibração com imagens de amostra preparadas em calibration_images/
4. Executar convert_wd_tagger.py para converter para HEF
5. Executar verify_hef.py para comparar precisão com ONNX
6. Reportar os resultados

Se a conversão falhar:
- Reportar a mensagem de erro
- Tentar onnx-simplifier
- Se SwinV2 não for suportado, tentar novamente com wd-vit-tagger-v3

Modelo alvo: SmilingWolf/wd-swinv2-tagger-v3
HW alvo: hailo10h
```

---

## Links de Referência

- [Documentação Hailo Dataflow Compiler](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [Modelos WD-Tagger (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
