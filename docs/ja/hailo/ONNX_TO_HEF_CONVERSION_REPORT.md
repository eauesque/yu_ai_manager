# ONNX to HEF 変換 報告書

**実施日**: 2026-03-06
**目的**: WD-Tagger ONNX モデルを Hailo HEF 形式に変換し、Raspberry Pi 5 + AI HAT 2 (Hailo-10H) で推論可能にする
**結果**: 失敗 (全モデルバリアントで変換不可)

---

## 環境

| 項目 | 詳細 |
|------|------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (uv でインストール) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## 試行したモデル

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **ソース**: `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **入力**: `[batch, 448, 448, 3]` float32
- **出力**: `[batch, 10861]` float32
- **結果**: 失敗
- **エラー**: `IndexError: list index out of range` in `_convert_axes_to_nhwc`
- **原因**: LayerNormalization の軸変換が DFC v5.2.0 で未対応

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **ソース**: `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **入力**: `[batch, 448, 448, 3]` float32
- **出力**: `[batch, 10861]` float32
- **結果**: 失敗
- **エラー**: 同上 (`IndexError` in `_convert_axes_to_nhwc`)
- **原因**: ViT も LayerNormalization を使用しており、同じ箇所で失敗

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **ソース**: `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **入力**: `[batch, 448, 448, 3]` float32
- **出力**: `[batch, 10861]` float32
- **結果**: 失敗
- **エラー**: `UnsupportedShuffleLayerError` (多数の Transpose ノード) + `UnsupportedModelError` (Mul の shape 不一致)
- **原因**: ConvNeXt の channels-last 設計に伴う Transpose 操作が DFC 未対応

---

## 失敗の根本原因

DFC v5.2.0 の ONNX パーサーが、以下の操作を正しく処理できない:

1. **LayerNormalization**: 3次元以上のテンソルに対する LayerNorm の NHWC 軸変換でインデックスエラーが発生
2. **Transpose (Shuffle)**: ConvNeXt の channels-last/first 変換に使われる Transpose パターンが未対応

WD-Tagger の全バリアント (SwinV2, ViT, ConvNeXt) はいずれも LayerNormalization を多用する現代的なアーキテクチャであり、DFC v5.2.0 では変換不可能。

---

## キャリブレーションデータ

- ComfyUI / Stable Diffusion forge の出力画像からランダムに500枚を選定
- WD-Tagger と同一の前処理 (RGBA→RGB白背景合成、アスペクト比保持リサイズ、白パディング、BGR変換) を適用
- `calibration_data.npy` として保存済みだったが、変換ステップに到達せず未使用

---

## 今後の可能性

- **DFC の将来バージョン**: Hailo が LayerNormalization / Transpose のサポートを改善した場合、再挑戦の価値あり
- **モデル改造**: LayerNorm を BatchNorm に置換した改造モデルの作成 (工数大、精度劣化リスクあり)
- **現状維持**: ONNX Runtime (CPU) での推論を継続
