# Hailo-10H エコシステム評価

**作成日**: 2026-03-19  
**対象**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)  
**HailoRT**: v5.2.0  
**DFC**: v5.2.0  
**目的**: 本プロジェクトでの Hailo-10H 開発経験を記録し、現実的な制約と今後の展望を整理する

---

## 総合評価

**ハードウェアは優秀。ソフトウェアエコシステムが決定的に不足。**

Hailo-10H は 40 TOPS の推論性能を持つ NPU であり、ハードウェアとしてのポテンシャルは十分にある。しかし、ソフトウェアツールチェーンが閉鎖的で未成熟なため、開発者が自由にモデルを持ち込んで動かすことが**実質的にできない**。

本プロジェクトでは CLIP セマンティック検索、YOLO 物体検出、LLM/VLM チャット、Whisper 音声認識、分散タガーサーバーと、Hailo-10H を多面的に活用する開発を行ってきたが、安定して動作しているものは**全て Hailo 公式の Model Zoo からダウンロードしたプリコンパイル済み HEF を使用**しており、自前で ONNX から HEF に変換できた例は**一度もない**。

---

## 本プロジェクトでの実装状況

### 動作している機能（全て公式 HEF ダウンロード）

| 機能 | 使用 API | HEF 入手元 |
|------|---------|-----------|
| CLIP 画像エンコーダ | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| YOLO 物体検出 | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| LLM チャット | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| VLM 画像+テキスト推論 | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Whisper 音声認識 | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### 動作できなかった機能（HEF 変換失敗）

| 機能 | 試みた内容 | 結果 |
|------|-----------|------|
| WD-Tagger (SwinV2) | ONNX → HEF 変換 | DFC が LayerNormalization を処理できず失敗 |
| WD-Tagger (ViT) | ONNX → HEF 変換 | 同上 |
| WD-Tagger (ConvNeXt) | ONNX → HEF 変換 | DFC が Transpose 操作を処理できず失敗 |

### 実装の特筆事項

本プロジェクトでは `hailo_platform` wheel の Python API を**直接叩いて**全機能を実装した。hailo-ollama や hailo-apps は使用していない。

特に以下は Hailo 社が公式に提供する前に自前で構築したもの：

- **VDevice 排他制御デバイスマネージャー** — CLIP/YOLO/LLM/VLM/S2T を単一 VDevice で自動切替。hailo-apps にはデバイス共有の仕組みがない
- **マルチバックエンドフォールバック** — Hailo → CoreML → ONNX Runtime を透過的に自動切替
- **uint8 脱量子化パイプライン** — `quant_info` の scale/zero_point から float32 を復元
- **LAN 分散推論アーキテクチャ** — 複数マシンのワークスティーリング並列タグ付け

これらの開発は **API ドキュメントがほぼ存在しない状態**で行われた。InferModel API の入出力仕様、バッファサイズ要件、量子化パラメータの取得方法は全てエラーメッセージとソースコード推測から解明した。

---

## Hailo Dataflow Compiler (DFC) の問題

### DFC とは

ONNX / TensorFlow モデルを Hailo-10H 用の HEF (Hailo Executable Format) に変換するためのコンパイラ。x86_64 Linux 上で動作し、以下のパイプラインでモデルを変換する：

```
model.onnx → HAR (float32) → 最適化 → 量子化 (INT8) → コンパイル → model.hef
```

### 現実

**DFC は Hailo が自社 Model Zoo 向けに事前検証したアーキテクチャしかまともに変換できない。**

本プロジェクトでの変換試行（2026-03-06、DFC v5.2.0）：

| モデル | サイズ | エラー | 到達段階 |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | 最適化前 |
| wd-vit-tagger-v3 | 362 MB | 同上 | 最適化前 |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | 最適化前 |

3モデル全てが**最適化段階に達する前に**パーサーレベルで失敗。500枚の校正用画像を準備したが使われることすらなかった。

### 根本原因

DFC の ONNX パーサーが以下の演算子を処理できない：

- `LayerNormalization`（多次元テンソルでの軸変換）
- `Transpose`（channels-last/first 変換パターン）

これらは Transformer 系アーキテクチャ（SwinV2, ViT, ConvNeXt 等）の基本構成要素であり、2022年以降の主流モデルの大半が使用している。

### DFC の実質的な対応範囲

| アーキテクチャ | DFC 対応 | 根拠 |
|---------------|---------|------|
| ResNet, MobileNet 等 CNN 系 | ✓ 対応 | Model Zoo に多数存在 |
| YOLO v5/v8/v11 | ✓ 対応 | Model Zoo に HEF あり |
| CLIP ViT (Hailo 版) | ✓ 対応 | Model Zoo に HEF あり（Hailo 社が変換） |
| SwinTransformer V2 | ✗ 非対応 | LayerNorm 変換失敗 |
| Vision Transformer (汎用) | ✗ 非対応 | LayerNorm 変換失敗 |
| ConvNeXt | ✗ 非対応 | Transpose 変換失敗 |

> **注記**: CLIP ViT が Model Zoo にあるのは Hailo 社内で特別な対応（手動のグラフ変換やカスタムパーサー）をしている可能性が高い。同じ ViT でも一般ユーザーが DFC で変換すると失敗する。

---

## HEF フォーマットの問題

- **バイナリ仕様が非公開** — Hailo はフォーマットのドキュメントを公開していない
- **DFC 以外に生成手段がない** — サードパーティツールで HEF を作ることが不可能
- **リバースエンジニアリングも非現実的** — NPU の命令セットとデータフローアーキテクチャの知識が必要

つまり、DFC が変換できないモデルは**どうやっても Hailo-10H で動かせない**。代替手段は存在しない。

---

## 開発ツールチェーンの評価

### hailo_platform (Python SDK)

| 項目 | 評価 |
|------|------|
| InferModel API | 動作するが、ドキュメントが極めて不足 |
| GenAI API (LLM/VLM/S2T) | 比較的使いやすい。ただし undocumented な挙動多数 |
| Python wheel 配布 | PyPI になし。aarch64 wheel はソースからビルドが必要 |
| エラーメッセージ | 最低限。バッファサイズ不一致の原因特定が困難 |
| VDevice 管理 | 排他アクセスのみ。マルチモデル同時利用不可 |

### 開発中に解明した undocumented な挙動

1. **InferModel API が正解** — 旧 VStreams API（`InferVStreams`、`ConfigureParams.create_from_hef`）は Hailo-10H で `HAILO_NOT_IMPLEMENTED` を返す
2. **出力は uint8 量子化** — float32 でバッファを確保すると `buffer size mismatch`。uint8 で確保して後から脱量子化する必要がある
3. **`input()`/`output()` はプロパティ** — メソッドではない（他の Hailo API と一貫性がない）
4. **`quant_info` の取得** — `infer_model.output().quant_info` で scale/zero_point を取得できるが、これを説明するドキュメントは存在しない
5. **hailo-ollama との排他** — VDevice 使用中は hailo-ollama を停止する必要がある。エラーメッセージからは原因が分かりにくい

---

## 競合製品との比較

### Ryzen AI (XDNA) NPU

| 項目 | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| 性能 | 40 TOPS | 16〜50 TOPS（世代による） |
| モデル持ち込み | DFC で変換必須、大抵失敗 | **ONNX Runtime が直接対応** |
| 開発者体験 | 独自ツールチェーン、ドキュメント不足 | `pip install onnxruntime-directml` で完了 |
| エコシステム | 閉鎖的、Model Zoo 依存 | ONNX / DirectML / Microsoft 共同 |
| 普及台数 | Pi + AI HAT、USB ドングル（予定） | **数百万台のノート PC に内蔵済み** |

Ryzen AI での統合は以下だけで完結する：

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

Hailo-10H では同じことが不可能。ONNX Runtime Execution Provider が存在しない。

### NVIDIA CUDA

| 項目 | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| モデル持ち込み | DFC 経由、Model Zoo 外は大抵失敗 | ONNX / PyTorch / TensorFlow → そのまま動く |
| ツールチェーン | 未成熟・半閉鎖 | 成熟・公開・大量のドキュメント |
| 開発者コミュニティ | 極小 | 世界最大 |
| 価格帯 | 安い（$70 程度） | 高い（$200〜$2000+） |

Hailo の唯一の優位性は**価格と消費電力**。

---

## hailo-apps (2025-10) との関係

### hailo-apps の概要

Hailo 社が 2025年10月にリリースした公式アプリケーション集。20以上のサンプルアプリを含む：

- GenAI: voice_assistant、vlm_chat、agent_tools_example、whisper
- Pipeline: 物体検出、ポーズ推定、顔認識、CLIP 分類、OCR
- Standalone: Python/C++ の HailoRT 学習用デモ

### 本プロジェクトとの比較

| 項目 | hailo-apps | 本プロジェクト |
|------|-----------|-------------|
| VLM 対応 | vlm_chat アプリ | `hailo_platform.genai.VLM` 直接実装 |
| CLIP | clip アプリ | セマンティック検索システムとして統合 |
| LLM | simple_llm_chat | GenAI Extension として統合 |
| Whisper | simple_whisper_chat | Speech-to-Text Extension として統合 |
| デバイス管理 | なし（単一アプリ前提） | **排他制御デバイスマネージャー（CLIP/YOLO/LLM/VLM/S2T 自動切替）** |
| バックエンドフォールバック | なし | **Hailo → CoreML → ONNX 自動切替** |
| 分散推論 | なし | **LAN 分散ワークスティーリング** |
| 統合度 | 個別デモアプリ | 単一の統合 WebUI アプリケーション |

本プロジェクトは hailo-apps が公開される前に、同等以上の機能を `hailo_platform` wheel の低レベル API から自前実装していた。

---

## 今後の展望

### 短期（現実的）

- **ONNX Runtime + LAN 分散が唯一の実用解** — 分散タガーサーバーの ONNX バックエンドで運用
- Hailo-10H は公式 HEF がある用途（YOLO、CLIP、LLM、Whisper）に限定して使用
- カスタムモデルの NPU 実行は諦める

### 中期（希望的）

- ASUS 等から Hailo-10H 搭載 USB ドングルが発売 → ユーザー増加
- ユーザー増加に伴い Hailo 社にツール改善圧力がかかる可能性
- DFC の将来バージョンで Transformer 系サポートが追加される可能性

### 長期（構造的課題）

- Hailo が ONNX Runtime EP を提供しない限り、Ryzen AI (XDNA) に開発者エコシステムで負ける
- USB ドングルでハードが普及しても、ソフトの自由度がなければ「速い YOLO が動くキー」止まり
- 40 TOPS のポテンシャルが Model Zoo の数十モデルでしか使えない状態が続く

---

## まとめ

Hailo-10H は 40 TOPS という優れたハードウェア性能を持つが、ソフトウェアエコシステムの閉鎖性と未成熟さにより、開発者が自由にモデルを持ち込んで活用することが**実質的に不可能**な状態にある。

本プロジェクトでは undocumented な API を手探りで解明しながら Hailo 社の公式アプリケーション集（hailo-apps）以上の統合ソフトウェアを構築した。しかし、それでもカスタムモデル（WD-Tagger）の NPU 実行は DFC の制約により実現できなかった。

**「ツールが足らなすぎて開発が実質できない」** — これが数ヶ月にわたる Hailo-10H 開発を経ての正直な結論である。

---

## 関連ドキュメント

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — CLIP セマンティック検索の開発ログ（Phase 1〜12+）
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — DFC 変換ガイド（参考資料）
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — WD-Tagger 変換失敗レポート
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — CLIP ONNX フォールバック開発ログ
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — VDevice デバイス管理設計
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — 分散タガーサーバードキュメント
