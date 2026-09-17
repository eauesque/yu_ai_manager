# ONNX → HEF 変換手順書

**目的**: WD-Tagger 等の ONNX モデルを Hailo HEF 形式に変換し、Hailo-10H NPU で推論可能にする
**実行環境**: x86_64 Linux (AI サーバー) — Hailo Dataflow Compiler は x86 のみ対応
**推論環境**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)

---

## 前提知識

### なぜ変換が必要か

| 項目 | ONNX Runtime (現状) | Hailo HEF (目標) |
|------|---------------------|-------------------|
| 実行先 | CPU | Hailo-10H NPU (40 TOPS) |
| 量子化 | float32 | INT8 (uint8) |
| 推論速度 | ~500ms/image (Pi5 CPU) | ~20ms/image (推定、CLIP 実績ベース) |
| メモリ | ~200MB (モデルロード) | ~数十MB (HEF) |

### 変換パイプライン概要

```
model.onnx (float32)
  |
  | [1] Hailo Model Zoo パーサー (ONNX → HAR)
  v
model.har (Hailo Archive, float32)
  |
  | [2] 最適化 (レイヤー融合, メモリ配置)
  v
model_optimized.har
  |
  | [3] 量子化 (float32 → INT8, キャリブレーション画像使用)
  v
model_quantized.har
  |
  | [4] コンパイル (HW 命令に変換)
  v
model.hef (Hailo Executable Format)
```

---

## 1. AI サーバー環境構築

### 1-1. Hailo Dataflow Compiler インストール

Hailo Developer Zone (https://hailo.ai/developer-zone/) からダウンロード。
アカウント登録が必要。

```bash
# Python 3.10 or 3.11 推奨 (3.12+ は未サポートの可能性あり)
python3 --version

# venv 作成
python3 -m venv ~/hailo_env
source ~/hailo_env/bin/activate

# Hailo Dataflow Compiler (DFC) インストール
# Developer Zone からダウンロードした .whl を指定
uv pip install hailo_dataflow_compiler-3.29.0-py3-none-linux_x86_64.whl

# 依存パッケージ
uv pip install numpy pillow onnx onnxruntime
```

**確認**:
```bash
python -c "from hailo_sdk_client import ClientRunner; print('DFC OK')"
```

### 1-2. Hailo Model Zoo (任意だが推奨)

```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git ~/hailo_model_zoo
uv pip install -e ~/hailo_model_zoo
```

Model Zoo には多くのモデルの変換設定 (YAML) が含まれており、参考になる。

---

## 2. 対象モデルの準備

### 2-1. WD-Tagger モデル

現在使用中のモデル:
- **リポジトリ**: HuggingFace の `SmilingWolf/wd-swinv2-tagger-v3` 等
- **ファイル**: `model.onnx` (~110MB, float32)
- **入力**: `(1, 448, 448, 3)` float32, BGR, [0, 255] 正規化なし
- **出力**: `(1, num_tags)` float32, シグモイド済み確率

```bash
# HuggingFace からダウンロード
mkdir -p ~/hailo_convert/wd_tagger
cd ~/hailo_convert/wd_tagger

# model.onnx と selected_tags.csv を取得
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx
wget https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv
```

### 2-2. ONNX モデルの入出力を確認

```python
import onnx

model = onnx.load("model.onnx")

print("=== 入力 ===")
for inp in model.graph.input:
    shape = [d.dim_value for d in inp.type.tensor_type.shape.dim]
    print(f"  {inp.name}: {shape}")

print("=== 出力 ===")
for out in model.graph.output:
    shape = [d.dim_value for d in out.type.tensor_type.shape.dim]
    print(f"  {out.name}: {shape}")
```

入出力の shape と名前をメモしておく。変換時に必要。

---

## 3. キャリブレーション画像の準備

INT8 量子化には代表的な画像セット (キャリブレーションデータ) が必要。
量子化パラメータ (scale/zero_point) を決定するために使う。

```bash
mkdir -p ~/hailo_convert/calibration_images
```

### 要件

- **枚数**: 100〜1000 枚程度 (多いほど精度が安定するが、時間もかかる)
- **内容**: 実際に推論する画像の代表サンプル (AI 生成画像のバリエーション)
- **形式**: JPEG/PNG
- **サイズ**: 任意 (前処理スクリプトでリサイズされる)

```bash
# yu_ai_manager のライブラリからランダムに 500 枚コピーする例
# (Pi から AI サーバーに scp 等で転送)
scp pi@raspberrypi:/path/to/images/*.png ~/hailo_convert/calibration_images/
```

### キャリブレーション前処理スクリプト

WD-Tagger の前処理と同じ処理を適用する必要がある:

```python
# calibration_preprocess.py
"""キャリブレーション画像を WD-Tagger 形式に前処理する。"""
import numpy as np
from PIL import Image
from pathlib import Path

INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """yu_ai_manager の engine_onnx.py と同一の前処理。"""
    with Image.open(image_path) as raw:
        img = raw.convert("RGBA")

    # 白背景に合成 (透過対応)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # アスペクト比を保持してリサイズ
    old_w, old_h = img.size
    scale = INPUT_SIZE / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 白パディングで正方形に
    padded = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (255, 255, 255))
    padded.paste(img, ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2))

    # HWC, float32, RGB -> BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    return arr  # (448, 448, 3)


def load_calibration_set(image_dir: str, max_images: int = 500) -> np.ndarray:
    """キャリブレーション画像をバッチテンソルとして返す。"""
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

## 4. HEF 変換の実行

### 4-1. 変換スクリプト

```python
# convert_wd_tagger.py
"""WD-Tagger ONNX → Hailo HEF 変換スクリプト。"""
from hailo_sdk_client import ClientRunner
import numpy as np

# ========== 設定 ==========
ONNX_PATH = "model.onnx"
MODEL_NAME = "wd_swinv2_tagger_v3"
CALIBRATION_NPY = "calibration_data.npy"
HW_ARCH = "hailo10h"  # Hailo-10H 用
# ==========================

# --- Step 1: ONNX パース → HAR ---
print("[1/4] Parsing ONNX model...")
runner = ClientRunner(hw_arch=HW_ARCH)

# start_node / end_node はモデルの入出力ノード名
# (Step 2-2 で確認した名前を指定)
hn, npz = runner.translate_onnx_model(
    ONNX_PATH,
    MODEL_NAME,
    # net_input_shapes={"input": [1, 448, 448, 3]},  # 必要に応じて指定
)
print(f"  Parsed: {len(npz)} layers")

# --- Step 2: モデル最適化 ---
print("[2/4] Optimizing model...")
runner.optimize(npz)

# --- Step 3: INT8 量子化 ---
print("[3/4] Quantizing (INT8)...")
calib_data = np.load(CALIBRATION_NPY)
print(f"  Calibration set: {calib_data.shape}")

runner.quantize(calib_data)

# --- Step 4: コンパイル → HEF ---
print("[4/4] Compiling to HEF...")
hef = runner.compile()

hef_path = f"{MODEL_NAME}.hef"
with open(hef_path, "wb") as f:
    f.write(hef)
print(f"Done: {hef_path} ({len(hef) / 1024 / 1024:.1f} MB)")

# HAR (中間ファイル) も保存 (デバッグ用)
har_path = f"{MODEL_NAME}.har"
runner.save_har(har_path)
print(f"HAR saved: {har_path}")
```

### 4-2. 実行

```bash
source ~/hailo_env/bin/activate
cd ~/hailo_convert/wd_tagger

# キャリブレーション画像の前処理
python calibration_preprocess.py

# HEF 変換
python convert_wd_tagger.py
```

**所要時間の目安**: モデルサイズとキャリブレーション枚数次第だが、数十分〜数時間。

### 4-3. よくあるエラーと対処

| エラー | 原因 | 対処 |
|--------|------|------|
| `UnsupportedOp: <op_name>` | ONNX オペレータが DFC 未対応 | Hailo の対応オペレータ一覧を確認。未対応 op はモデル修正か `onnx-simplifier` で除去 |
| `Shape mismatch` | 入力 shape が動的 | `net_input_shapes` で固定 shape を明示指定 |
| `Quantization error` / 精度劣化 | キャリブレーションデータが不適切 | 画像枚数を増やす、実際の運用画像を使う |
| `Memory allocation failed` | モデルが大きすぎて NPU メモリに収まらない | バッチサイズ=1 に固定、または軽量モデルを検討 |
| `hailo_sdk_client not found` | DFC 未インストール | Step 1-1 を確認 |

### 4-4. (推奨) onnx-simplifier で前処理

変換前に ONNX モデルを単純化しておくと成功率が上がる:

```bash
uv pip install onnx-simplifier
python -m onnxsim model.onnx model_simplified.onnx
```

---

## 5. 変換後の検証 (AI サーバー上)

### 5-1. Hailo Emulator で精度検証

HEF に変換したモデルの精度を、実機なしで検証できる:

```python
# verify_hef.py
"""HEF の出力を ONNX の出力と比較して精度劣化を確認する。"""
import numpy as np
import onnxruntime as ort

# ONNX 推論 (float32, 基準値)
sess = ort.InferenceSession("model.onnx")
test_image = np.load("calibration_data.npy")[0:1]  # 1枚取り出し
input_name = sess.get_inputs()[0].name
onnx_output = sess.run(None, {input_name: test_image})[0][0]

# HEF エミュレータ推論
from hailo_sdk_client import ClientRunner

runner = ClientRunner(har="wd_swinv2_tagger_v3.har")
hef_output = runner.infer(test_image)[0]

# 比較
diff = np.abs(onnx_output - hef_output)
print(f"Max diff:  {diff.max():.6f}")
print(f"Mean diff: {diff.mean():.6f}")
print(f"Cosine similarity: {np.dot(onnx_output, hef_output) / (np.linalg.norm(onnx_output) * np.linalg.norm(hef_output)):.6f}")

# タグ一致率 (閾値 0.35 での一致)
threshold = 0.35
onnx_tags = set(np.where(onnx_output > threshold)[0])
hef_tags = set(np.where(hef_output > threshold)[0])
overlap = len(onnx_tags & hef_tags)
print(f"Tag match: {overlap}/{len(onnx_tags)} ({overlap/max(len(onnx_tags),1)*100:.1f}%)")
```

**判定基準**:
- コサイン類似度 > 0.95: 良好
- タグ一致率 > 90%: 実用レベル
- タグ一致率 < 80%: キャリブレーションデータの見直しが必要

---

## 6. Pi への転送と実機テスト

### 6-1. HEF ファイルの転送

```bash
scp ~/hailo_convert/wd_tagger/wd_swinv2_tagger_v3.hef pi@raspberrypi:~/hailo_models/
```

### 6-2. 実機推論テスト

```python
# test_wd_tagger_hef.py (Pi5 上で実行)
"""HEF 変換した WD-Tagger の実機推論テスト。"""
import numpy as np
from hailo_platform import VDevice
from PIL import Image
import time

HEF_PATH = "~/.hailo_models/wd_swinv2_tagger_v3.hef"
INPUT_SIZE = 448

def preprocess(image_path: str) -> np.ndarray:
    """engine_onnx.py と同一の前処理 (ただし uint8 で出力)。"""
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

# テスト画像
test_img = preprocess("/path/to/test/image.png")

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(HEF_PATH)
    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 入力
    bindings.input().set_buffer(test_img)

    # 出力バッファ (uint8)
    out_info = infer_model.outputs[0]
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    # 推論
    t0 = time.perf_counter()
    configured.run([bindings], timeout=10000)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"Inference: {elapsed:.1f} ms")
    print(f"Output shape: {output_buf.shape}")
    print(f"Output range: [{output_buf.min()}, {output_buf.max()}]")

    # 脱量子化
    try:
        qi = out_info.quant_infos[0]
        scale = qi.qp_scale
        zp = qi.qp_zp
    except Exception:
        scale, zp = 1.0 / 255.0, 0.0

    probs = (output_buf.astype(np.float32) - zp) * scale
    print(f"Dequantized range: [{probs.min():.4f}, {probs.max():.4f}]")
```

### 6-3. 精度比較 (ONNX vs HEF)

同じ画像を ONNX Runtime と Hailo HEF の両方で推論し、タグ出力を比較:

```bash
# Pi 上で実行
python test_wd_tagger_hef.py
python -c "
from extensions.builtin_wd_tagger.core_impl.engine_onnx import OnnxWdTaggerEngine
e = OnnxWdTaggerEngine(Path('cache/wd_tagger/...'))
r = e.tag_image('/path/to/test/image.png')
for t in r.tags[:20]: print(f'{t.tag}: {t.confidence}')
"
```

---

## 7. 既知の懸念事項

### SwinV2 アーキテクチャの変換可能性

WD-Tagger v3 は **Swin Transformer V2** ベース。以下の Op が DFC で未対応の可能性がある:

- **Window Attention** (shifted window)
- **Roll** 操作
- **相対位置バイアス**

SwinV2 が変換不可の場合の代替案:
1. **wd-vit-tagger-v3** (Vision Transformer ベース) — ViT は CLIP と同系統で Hailo 変換実績あり
2. **wd-convnext-tagger-v3** (ConvNeXt ベース) — CNN 系で変換しやすい
3. **wd-eva02-large-tagger-v3** (EVA-02 ベース) — モデルが大きい (300MB+) ため NPU メモリ要注意

### 前処理の差異

- **ONNX 版**: float32 入力 (0-255 範囲, 正規化なし)
- **HEF 版**: uint8 入力 (HEF 内部で正規化)

HEF に変換すると前処理が HEF に組み込まれる場合がある。
DFC の `translate_onnx_model()` 時に前処理の扱いを確認すること。

### 脱量子化パラメータ

出力は uint8 量子化される。タグ確率 (0.0-1.0) を正しく復元するには、
HEF の量子化パラメータ (scale/zero_point) を使った脱量子化が必須。
CLIP の実績 (`extensions/builtin_hailo_semantic_search/core_impl/dequantize.py`) を参考にすること。

---

## 8. Claude への指示テンプレート

AI サーバーで Claude に変換作業を依頼する際のプロンプト例:

```
以下の手順で WD-Tagger ONNX モデルを Hailo HEF に変換してください。

1. ~/hailo_env を有効化
2. model.onnx を ~/hailo_convert/wd_tagger/ にダウンロード
3. calibration_images/ に用意したサンプル画像でキャリブレーションデータを作成
4. convert_wd_tagger.py を実行して HEF に変換
5. verify_hef.py で ONNX との精度比較を実施
6. 結果をレポートしてください

変換が失敗した場合:
- エラーメッセージを報告
- onnx-simplifier を試す
- SwinV2 が未対応の場合は wd-vit-tagger-v3 で再試行

対象モデル: SmilingWolf/wd-swinv2-tagger-v3
ターゲット HW: hailo10h
```

---

## 参考リンク

- [Hailo Dataflow Compiler ドキュメント](https://hailo.ai/developer-zone/documentation/dataflow-compiler/)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [WD-Tagger モデル (HuggingFace)](https://huggingface.co/SmilingWolf)
- [ONNX Simplifier](https://github.com/daquexian/onnx-simplifier)
