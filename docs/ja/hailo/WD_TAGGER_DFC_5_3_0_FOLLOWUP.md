# DFC 変換続報: WD-Tagger モデルを DFC v5.3.0 で再検証

**日付**: 2026-04-06
**DFC バージョン**: 5.3.0
**前回レポート**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**環境**: WSL2 (Ubuntu 24.04)、x86_64

---

## 背景

2026 年 3 月に、WD-Tagger の 3 バリアント (SwinV2、ViT、ConvNeXt)
が Hailo Dataflow Compiler v5.2.0 のパーサ段階で全て失敗し、量子化
ステップに到達しないことを報告した。元レポートは
[`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md)
に保存してある。

DFC v5.3.0 がリリースされたので、同じ 3 モデルを再検証した結果を
ここに記録する。

---

## 結果サマリ

| モデル | サイズ | DFC 5.2.0 エラー | DFC 5.3.0 エラー | 変化 |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `_convert_axes_to_nhwc` で `IndexError` | 同一 | **なし** |
| `wd-vit-tagger-v3` | 362 MB | 同上 | 同一 (onnxsim 再試行後も) | 再試行フロー追加のみ |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | 同一 + `UnsupportedModelError` 追加 | **エラーが増えた** |

**3 モデル全てが依然としてパーサ段階で失敗する**。500 枚分用意した
calibration 画像を使う量子化ステップは、v5.2.0 のときと同じく到達
できないままである。

---

## DFC v5.3.0 で変わった点

失敗自体は継続しているが、v5.2.0 と比較すると以下の改善が見られる:

### 1. `_create_layer_normalization_layer` メソッドが新規追加

このメソッドは v5.2.0 には存在しなかった。DFC v5.3.0 では
`LayerNormalization` 演算子を専用コードパスで明示的にハンドリング
しようとしている。これは確実に開発努力が進んでいる証拠である。

ただし**内部実装は未完成**で、メソッドが呼ばれた後の
`_convert_axes_to_nhwc` 呼び出しが、v5.2.0 と同じテンソル形状で
`IndexError: list index out of range` を発生させる。

### 2. onnxsim 簡略化 + 再試行フローの追加

ViT と ConvNeXt について、DFC v5.3.0 は入力 ONNX を `onnxsim` で
自動的に簡略化してパースを再試行するようになった。簡略化された
モデルは入力ファイルの隣に `model.sim.onnx` として保存される。
冗長な ONNX グラフを持つモデルにとっては有用なセーフティネットである。

ただし今回のモデルでは、根本原因が `_convert_axes_to_nhwc` 側に
あるため、再試行も**全く同じ箇所で失敗する**。

### 3. End ノード推薦機能

ConvNeXt について、DFC v5.3.0 はパーサが諦めた際に具体的な end
ノードを推薦し、それをピン留めして再試行するようユーザに促すように
なった。UX としては気の利いた改善である。

ただし推薦された end ノードでの再試行も同様に失敗する。やはり根本
原因が LayerNormalization / Transpose のハンドリング側にあるためで、
end ノード選択の問題ではない。

---

## 根本原因 (3 月から変わらず)

DFC ONNX パーサは、`LayerNormalization` 演算子の入力テンソルが期待
されている NCHW フォーマットに従っていない場合の axis 変換に依然
として失敗する。コールチェーンは:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

ConvNeXt については、加えて複数の `Transpose` ノード (`token_5` 〜
`token_34`) で発生する `UnsupportedShuffleLayerError` が、この
アーキテクチャが使う channels-last パターンに対する Transpose
ハンドリングの不完全性を示している。

要するに **新しいコードパスは存在するが、元々失敗していたケースは
まだハンドリングできていない**。

---

## 要望 (3 月から変わらず)

3 月のポストで挙げた 2 つの要望はそのまま継続:

### 1. `_convert_axes_to_nhwc` を多次元 `LayerNormalization` 対応に修正

メソッドが呼ばれるところまでは到達できるようになった (改善)。だが
axis マッピングロジック自体が非 NCHW 入力テンソルで失敗する。
SwinV2、ViT、ConvNeXt といった近年の Transformer 系アーキテクチャは
全てこれが正しく動くことに依存している。

### 2. Hailo-10H 用 ONNX Runtime Execution Provider

これがあれば DFC による完全変換は任意となり、本クラスの問題を構造的
に解決できる。多くのコミュニティユーザは、たとえ完全量子化された
HEF より低スループットでも、未修正の ONNX モデルを Hailo-10H 上で
直接実行できることを歓迎するだろう。

---

## 「ONNX Runtime Hailo Pipeline」コンポーネントについて

DFC v5.3.0 のリリースノートに「ONNX Runtime Hailo Pipeline」という
コンポーネントが言及されている。このコンポーネントによって、DFC で
パースできないモデルも含めて WD-Tagger 推論を Hailo-10H 上で
**フル DFC 変換なしに**実行できるなら (つまり ORT の execution
provider として、対応可能なサブグラフだけを NPU にデリゲートする
仕組みなら)、その正しい使い方について公式ガイダンスをいただけると
非常にありがたい。

具体的には:

- このコンポーネントは、DFC が現状パースできないモデルに対する
  前進パスとして意図されているのか?
- 部分的な HEF (パース可能なサブグラフを HEF にコンパイルし、残り
  を CPU で ORT 経由で実行) が必要なのか?
- Transformer 系の ONNX モデルに対してこれを使うサンプルコードや
  チュートリアルは存在するか?

---

## 再現手順

これらの結果を再現するための手順:

```bash
# 1. クリーンな Python venv に DFC v5.3.0 をセットアップ
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. 3 種類の WD-Tagger ONNX モデルをダウンロード
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. 各モデルでパースを試行
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

各実行のフルエラーログは要望があれば提供可能。

---

## テスト環境

| 項目 | 詳細 |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| モデル | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| Calibration data | 500 枚の ComfyUI / SD 出力 (量子化に到達せず未使用) |

---

## まとめ

DFC v5.3.0 で見られる開発努力 (`_create_layer_normalization_layer`、
onnxsim 再試行フロー、end ノード推薦) は本当に励まされる。コミュニ
ティが期待していた前進そのものである。残るギャップは
`_convert_axes_to_nhwc` の中身の実装で、到達できるようにはなったが
今回のモデルにはまだ正しく動作していない、という状況である。

DFC の各リリースで再検証を続け、状況が変わったらまた続報を出す
予定。Hailo の中の人がこれを読んでフルエラーログ・ONNX モデルの
SHA-256 ハッシュ・最小再現コードが必要であれば喜んで提供する。
