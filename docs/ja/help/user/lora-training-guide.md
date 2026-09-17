# LoRA 学習ガイド

YU AI Manager + MCP + kohya_ss による自然言語 LoRA 学習完全ガイド

---

## はじめに

本書は、YU AI Manager の MCP サーバーと kohya_ss を連携させ、自然言語指示だけで LoRA を作成するフローを解説する実践ガイドである。

従来の LoRA 作成の工数の大半は「dataset 準備の手作業」にあった。画像の選定、タグの精査と除外、caption ファイルの整形、フォルダ構成の整理——これらを全部人間が担っていた。

YU AI Manager の MCP 連携によりこのフローが変わる。「○○の LoRA を作ってください。タグは△△を除外して」という指示だけで、素材収集からタグ付け、dataset 生成、kohya_ss 起動まで一貫して動く。

---

## 全体フロー

LoRA 作成の工程は以下の 5 段階で構成される。

| フェーズ | 作業内容 | 担当 |
|---------|---------|------|
| 1. 素材準備 | 学習用画像の収集・配置 | 人間 / AI エージェント |
| 2. タグ付け | WD-Tagger による自動タグ付け | MCP（自動） |
| 3. Dataset 生成 | プロジェクト作成・除外タグ設定・export | MCP（自動） |
| 4. 学習実行 | kohya_ss 呼び出しによる学習 | MCP（自動） |
| 5. 検証 | SD で LoRA を使い結果を確認 | 人間 |

人間が関与するのは「何を学習させるか」という意思決定と、最終的な結果確認のみである。

---

## 前提条件

### 必要なソフトウェア

- YU AI Manager — MCP サーバー機能を含む
- Claude Desktop または Claude Code — MCP クライアント
- kohya_ss — sd-scripts を含むもの
- Stable Diffusion WebUI（A1111 / ComfyUI / Forge）— 結果検証用

### GPU 要件

| GPU VRAM | 対応モデル | 必要な設定 |
|---------|----------|-----------|
| 8GB | SD 1.5 のみ実用的 | `--gradient_checkpointing` 必須 |
| 12GB | SDXL が動作（制限あり） | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL 快適 | デフォルト設定で動作 |
| 24GB+ | SDXL・FLUX 両対応 | ほぼ制限なし |

> **注記**: RTX 3060 12GB で SDXL の LoRA 学習は可能だが、gradient_checkpointing 必須のため 24,000 ステップに約 10 時間かかる。RTX 5060 Ti 16GB であれば 3〜5 時間程度に短縮できると推測される。

### kohya_ss のディレクトリ構成

kohya_ss はトップディレクトリと実際のスクリプトディレクトリが分離していることが多い。

```
O:\webui\kohya_ss\              ← kohya_path に設定するトップディレクトリ
O:\webui\kohya_ss\venv\         ← Python 仮想環境（自動検出される）
O:\webui\kohya_ss\sd-scripts\   ← 学習スクリプトが格納されるディレクトリ
```

> ⚠️ **注意**: YU AI Manager は `kohya_path` のトップディレクトリを指定すれば `sd-scripts` サブフォルダと venv を自動検出する。sd-scripts のパスを直接指定しないこと。

---

## YU AI Manager の設定

### Extension 設定

LoRA Dataset Manager の設定タブで以下を入力する。

| 設定項目 | 説明 | 例 |
|---------|------|---|
| `kohya_path` | kohya_ss トップディレクトリ | `O:\webui\kohya_ss` |
| `output_base_dir` | Dataset 出力先ベースディレクトリ | `C:\lora_datasets` |
| `checkpoint_dir` | ベースモデルのディレクトリ | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | デフォルトのモデル種別 | `sdxl` |

### WD-Tagger の設定

LoRA dataset 用途では VLM（llava 等）との組み合わせは推奨しない。VLM は自由記述のタグを大量生成し、caption の品質を下げる。

```
engine_type: "onnx"  ← ONNX 単体を使用
```

> ⚠️ **注意**: `engine_type` を `"both"` に設定すると VLM 由来の複合タグ（`wooden_bear_and_fish_sculpture` 等）が生成される。これらは kohya_ss の caption として機能せず、学習の妨げになる。

---

## MCP による LoRA 作成手順

### Step 1: 素材画像の準備

学習用画像を YU AI Manager の scan root に配置してスキャンする。

- YU AI Manager の Scan Root 設定で学習用フォルダを追加
- スキャン完了後、対象画像が DB に登録される
- 最低 20〜30 枚、推奨 50〜200 枚

> **注記**: 画像の品質が学習結果の最大の決定要因。解像度は 512px 以上、対象物がはっきり映っているものを選ぶ。

### Step 2: WD-Tagger でタグ付け

MCP から一括タグ付けを実行する。

```python
# 対象ファイルの ID リストを取得して一括タグ付け
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

既存タグがある場合はまず削除してから再実行する。

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Step 3: プロジェクト作成

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # kohya_ss のフォルダ名に使用
    base_model="sdxl",
    repeat=20
)
```

### Step 4: ファイルとタグの設定

プロジェクトにファイル ID をセットし、タグ集計を確認する。

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

タグ集計を見て除外するタグを決定する。

#### 除外タグの設計思想

LoRA に「何を学習させるか」の核心がここにある。

**残すタグ**: 学習させたい概念固有の特徴（造形・スタイル・固有要素）

**除外するタグ**: モデルが既知の汎用タグ（`no_humans`, `realistic`, `animal`, `solo`, background 系など）

例：木彫りクマの LoRA の場合

- 残す: `bear`, `fish`, `statue`, `sculpture`, `standing`, `full_body`, `open_mouth`
- 除外: `no_humans`, `animal_focus`, `animal`, `realistic`, `simple_background`, `solo`, `indoors`, `shadow`...

> ⚠️ **注意**: 概念の切り出しに失敗すると学習が分散する。`bear` や `wood` を残したい場合、WD-Tagger の ONNX はこれらを確実に付与しないことがある。この場合は caption のプレビューで実際の出力を確認すること。

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Step 5: caption のプレビュー確認

```python
preview_lora_caption(project_id=N, file_id=任意のファイルID)
```

出力例:

```
"fish, full_body, open_mouth, standing"
```

VLM ノイズがなく、シンプルなタグ列になっていることを確認する。空の caption が多い場合は除外タグの見直しが必要。

### Model Scope

各 project は `model_scope` 設定を持ち、caption / preview / export に使用する WD-Tagger model を制御します。

- `active` (新規 project デフォルト): アクティブ WD model のタグのみ使用。アクティブ未設定時は全 model fallback。
- `all` (既存 project デフォルト): 全 model のタグ混在。
- `<model_id>` (例: `wd-eva02-large-tagger-v3`): 明示指定 model のタグのみ。

複数 model でタグ付けされた file は通常 `active` で十分です。比較や検証目的で明示指定を使う場合は Tools ページの WD-Tagger profile dropdown と同じ model_id を指定します。

### Step 6: Dataset Export

```python
export_lora_dataset(project_id=N)
```

出力フォルダ構成:

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Step 7: 学習実行

まず dry_run でコマンドを確認する。

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="フルパス\checkpoint.safetensors"
)
```

問題なければ学習を起動する。

```python
start_lora_training(
    project_id=N,
    checkpoint="フルパス\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

進捗確認:

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## デフォルト学習パラメータ

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `network_dim` | 32 | LoRA のランク。大きいほど表現力が上がるがファイルサイズも増える |
| `network_alpha` | 16 | 通常は dim の半分に設定 |
| `learning_rate` | 1e-4 | 学習率 |
| `max_train_epochs` | 10 | エポック数 |
| `save_every_n_epochs` | 2 | 中間保存の間隔 |
| `mixed_precision` | fp16 | 精度。bf16 の方が VRAM を節約できる場合がある |
| `resolution` | 1024,1024 (SDXL) | 学習解像度。SD1.5 は 512,512 |

> **注記**: これらは Settings タブまたは `set_extension_config` で変更可能。任意引数は `start_lora_training` の `extra_args` で追加できる。

---

## GPU 別推奨設定

| GPU VRAM | 推奨 extra_args |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | （デフォルトで動作） |
| 24GB+ | （デフォルトで動作、batch_size を上げることも可） |

> ⚠️ **注意**: 12GB GPU で gradient_checkpointing を使用すると SDXL 24,000 ステップで約 10〜12 時間かかる。16GB 以上ではこの制約がなくなり大幅に高速化する。

---

## repeat 数と epoch 数の目安

**総学習ステップ数 = 画像枚数 × repeat 数 × epoch 数**

| 概念の複雑さ | 推奨ステップ数 | 例（50 枚の場合） |
|------------|-------------|--------------|
| シンプルなオブジェクト・スタイル | 1,000〜3,000 | repeat=10, epoch=5 |
| キャラクター・造形物 | 3,000〜8,000 | repeat=20, epoch=5 |
| 複雑なスタイル・人物 | 5,000〜15,000 | repeat=20, epoch=10 |

> **注記**: 120 枚×20 repeat×10 epoch=24,000 ステップで学習した場合、十分な品質が得られる。ただし 5〜6 epoch でも同等の結果が得られる可能性があるため、次回は短い epoch で試すことを推奨する。

---

## トラブルシューティング

### ModuleNotFoundError: No module named 'torch'

**原因**: YU AI Manager の venv で kohya_ss のスクリプトを実行しようとしている。

**対処**: `kohya_path` をトップディレクトリ（sd-scripts の親）に設定する。YU AI Manager は自動的に `kohya_path/venv/Scripts/python.exe` を検出する。

---

### AssertionError: resolution is required

**原因**: `--resolution` が指定されていない。

**対処**: YU AI Manager の最新版では自動的に付与される（SDXL: 1024,1024、SD1.5: 512,512）。

---

### AssertionError: network for Text Encoder cannot be trained with caching

**原因**: `--cache_text_encoder_outputs` と `--network_train_unet_only` が対になっていない。

**対処**: YU AI Manager の最新版では SDXL 時に自動的に `--network_train_unet_only` を付与する。

---

### torch.OutOfMemoryError: CUDA out of memory

**原因**: VRAM が不足している。

**対処**: `extra_args` に以下を追加する。

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### VLM ノイズタグの混入

**原因**: `engine_type` が `"both"` になっており、VLM（llava 等）が自由記述タグを生成している。

**対処**: WD-Tagger の設定で `engine_type="onnx"` に変更し、タグを全削除して再タグ付けする。

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

### checkpoint must be inside checkpoint_dir（403 エラー）

**原因**: checkpoint のパスが `checkpoint_dir` の外を指している。

**対処**: Extension 設定の `checkpoint_dir` が正しいディレクトリを指しているか確認する。

---

### output_base_dir not configured（400 エラー）

**原因**: Extension 設定の `output_base_dir` が未設定または保存されていない。

**対処**: UI の設定タブで保存し直すか、MCP から `set_extension_config` で設定する。

---

## 生成時のプロンプト

### 基本プロンプト構成

```
{concept_token}, {特徴タグ}, <lora:{lora_name}:{strength}>
```

木彫りクマ LoRA の例:

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

ネガティブプロンプト:

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### LoRA 強度の調整

| 強度 | 特性 |
|-----|------|
| 0.5〜0.6 | ベースモデルの影響が強い。色・スタイルはベースモデル寄り |
| 0.7〜0.8 | 推奨範囲。LoRA の特徴とベースモデルのバランスが良い |
| 0.9〜1.0 | LoRA の影響が強い。造形は出るが色が白/クリーム系に寄りやすい |

> **注記**: 色が白く飛ぶ場合は強度を下げるか、プロンプトに `brown wood, warm tone` を追加して色を誘導する。

---

## 今後の拡張

### 素材収集の自動化

現状、素材画像は人間が手動で準備する必要がある。Claude in Chrome 等のブラウザエージェントを使えば「○○の画像をウェブから集めてフォルダに入れてください」という指示で素材収集も自動化できる。

YU AI Manager の生成画像を素材として活用する方向も有効。SD/ComfyUI/NAI で生成した画像をそのまま LoRA 素材として再利用するサイクルが成立する。

### LoRA 量産フロー

MCP + Claude Desktop を使えば以下のような完全自動化が実現できる。

1. ウェブから素材を収集（Claude in Chrome）
2. YU AI Manager にスキャン・タグ付け（MCP）
3. プロジェクト作成・除外タグ設定・export（MCP）
4. kohya_ss 学習起動（MCP）
5. 就寝前に指示 → 翌朝 LoRA 完成

### ベースモデルの選択

waiSHUFFLENOOB 等の Illustrious 系ベースモデルはアニメ調の生成に最適化されている。実写素材（木彫りクマ等）を学習させると白/クリーム系の色味になりやすい。

実写に近い質感を求める場合は realisticPhoto 系ベースモデルを選択する。LoRA はベースモデルと同じモデルで使用する必要がある。

---

## まとめ

YU AI Manager + MCP + kohya_ss のフローにより、LoRA 作成の工数を大幅に削減できる。

- 素材画像から全エポックの学習が MCP 指示だけで完走する
- 自然言語指示でフロー全体が動作する
- 生成画像で学習対象の造形が明確に表現される

残る課題は素材収集の自動化のみであり、Claude in Chrome 等と組み合わせることで完全自動化が視野に入る。
