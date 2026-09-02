# Hailo-10H セットアップ

Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) を YU AI Manager から利用するためのホスト側セットアップ手順です。ハードウェアと OS まわりは PyPI で完結しないため、いくつか手動の準備が必要になります。

> **対象**: Hailo-10H ハードウェアを搭載した Raspberry Pi 5 (8 GB 推奨) で、Hailo 系拡張 (GenAI チャット / Semantic Search / YOLO Detect / Tagger / Whisper) を有効にしたい場合のみ。Hailo HW が無い環境ではこのページの作業は一切不要です。

---

## 1. 前提条件

- Raspberry Pi 5 (8 GB を強く推奨。CMA 制約のため 4 GB では複数モデル同時ロードが厳しい)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (`pyproject.toml` の `requires-python` で `<3.14` に固定済み。`uv` が自動で 3.13 を選びます)

---

## 2. PCIe ドライバのインストール

Hailo-10H は専用カーネルモジュール `hailo1x_pci` を使います (旧 `hailo_pci` から HailoRT 5.3.0 で改名)。

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

再起動後に確認：

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

期待される結果：

- `hailo1x_pci` がロードされている
- `/dev/h1x-0` というデバイスノードが存在する (旧 `/dev/hailo0` ではない)
- `dmesg` に `Firmware loaded in NNNN ms` `Device created at /dev/h1x-0` の行がある

> **`/dev/hailo0` が無いように見えても問題ありません**。HailoRT 5.3.0 以降は `/dev/h1x-0` がデフォルトで、本アプリは両方を認識します (`core/llm_router/hailo_detect.py`)。

---

## 3. HailoRT (システム側) のインストール

`hailortcli` バイナリと `libhailort.so` 共有ライブラリ。`hailo-all` パッケージに含まれていますが、最新版が必要な場合は Hailo Developer Zone から `.deb` を取得して上書きインストールします。

確認：

```bash
hailortcli fw-control identify
```

期待される出力 (要点)：

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Python wheel (`hailort-*.whl`) の準備

ここが PyPI で配布されていない部分です。**aarch64 用の Hailo Python wheel は Hailo Developer Zone にも置かれていないため、自前でビルドします。**

### 4.1 ソースからビルド

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# 完了するとビルドツリー内に hailort-5.3.0-cp313-cp313-linux_aarch64.whl が生成される
```

(ビルド手順の詳細・依存パッケージは Hailo 公式 README を参照してください。)

### 4.2 wheel をホームディレクトリに配置

ビルドした wheel を **以下のどこか** にコピーすれば、本アプリの起動時に自動検出されます：

| 探索先 (優先度順) | 用途 |
|---|---|
| `$HAILORT_WHEEL` 環境変数 | 任意のフルパス指定 (最優先) |
| `$HOME/share/` | **推奨配置先** |
| `$HOME/hailort/` | ビルドツリーをそのまま置いている場合 |
| `$HOME/Downloads/` | DL 直後の暫定置き場 |
| `$HOME/` (直下) | 最後の保険 |

推奨配置：

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 自動インストールの仕組み

`./start.sh` 実行時に `scripts/install_hailo.py` が走り、

1. venv 内で `import hailo_platform` が成功するかチェック
2. 失敗した場合のみ、上記の探索先から **現在の Python バージョン (cp313) + アーキ (aarch64) に一致する** wheel を検索
3. 見つかった最新の wheel を `uv pip install` する
4. wheel が無い・既にインストール済みの場合は何もしない (silent no-op)

つまり手動の `uv pip install` は不要です。wheel をホームディレクトリに置いて `./start.sh` を再起動するだけで復旧します。

---

## 4.4 HEF モデルファイルの配置

各拡張が使う HEF ファイル (NPU 用にコンパイル済みのモデル) を `~/hailo_models/` に置きます。

| ファイル | 用途 | サイズ目安 |
|---|---|---:|
| `yolov8n.hef` | YOLO 物体検出 | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **セマンティック検索 (CLIP 画像)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | セマンティック検索 (CLIP テキスト, 任意) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | 音声認識 | 75-405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM チャット | 2.9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (画像+テキスト) | 3.2 GB |

Hailo Model Zoo の S3 バケットから認証なしで直接ダウンロードできます (URL 形式):

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

例 (CLIP 画像エンコーダ):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **HEF ファイルが足りないと拡張は `利用不可` 表示になります**。例えばセマンティック検索のステータスに `hailo-10h (CLIP HEF 未配置)` と出る場合は `clip_vit_b_16_image_encoder.hef` が `~/hailo_models/` に無いということです。ハードウェアや Python ランタイムの問題と切り分けやすいよう、`runtime_ok` / `hardware_ok` / `hef_ok` の 3 段で原因がレスポンスに含まれます (ステータス文字列にマウスオーバーで詳細表示)。

`HAILO_HEF_DIR` 環境変数で別のディレクトリにすることもできます。

---

## 5. カーネルパラメータ (CMA)

Hailo の GenAI モデル (LLM/VLM/Whisper) は DMA 用に CMA (Contiguous Memory Allocator) を必要とします。

`/boot/firmware/cmdline.txt` の末尾に追加：

```
cma=256M
```

> **Pi 5 (8 GB) で `cma=1G` や `cma=512M` は静かに失敗します**。デフォルトカーネルが `numa=fake=8` を適用するため CMA は単一 NUMA ノード境界 (1 GB) 内に収まる必要があり、`256M` を超えると `CmaTotal=0` になります (パニックなし)。詳細: [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

再起動後に確認：

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB なら成功
```

`0 kB` の場合は値を確認し、必要なら下げてください。

---

## 6. hailo-ollama との共存 (任意)

`hailo-ollama` (Ollama の Hailo NPU 版) を同じデバイス上で走らせる場合：

- **HailoRT 5.3.0 以降**: `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` で起動すれば、yu_ai_manager 側 (group_id `YU_SHARED`) と物理デバイスを共有し、HailoRT スケジューラが ROUND_ROBIN で time-slicing します
- **5.2.0 以前**: group_id を受け付けないため、yu_ai_manager 起動前に `systemctl stop hailo-ollama` で止める必要があります

---

## 7. 動作確認

`./start.sh` 起動後、WebUI の **設定 → 拡張機能** で以下が有効になっていれば成功：

- `builtin_hailo_genai` (Hailo チャット / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP セマンティック検索)
- `builtin_hailo_yolo_detect` (YOLO 物体検出)

または CLI で直接：

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. トラブルシューティング

### Hailo 系拡張がすべて「読み込まれませんでした」になる

→ Python wheel が未インストールの可能性が高い。以下を確認：

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

`ModuleNotFoundError` なら、wheel をホームディレクトリに置いてから `./start.sh` を再起動してください (§4.2)。

### `hailortcli fw-control identify` が `HAILO_OPEN_FILE_FAILURE` で失敗

→ ドライバまたはデバイスノードの問題。`lsmod | grep hailo1x` で `hailo1x_pci` がロードされているか、`ls /dev/h1x-0` が存在するかを確認。両方欠けている場合は §2 をやり直し、再起動。

### LLM/VLM ロード時に `HAILO_OUT_OF_HOST_MEMORY` / Pi が固まる

→ CMA 不足。`grep CmaTotal /proc/meminfo` で 256 MB あるか確認 (§5)。`VDevice.release()` は CMA を返さないため、複数モデル切替を繰り返した後はプロセス再起動が必要なことがあります。

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ 他プロセスが VDevice を占有中。`lsof /dev/h1x-0` で犯人を特定 (典型的には `hailo-ollama` か、Ctrl+C で終了し損ねた前回プロセス) し、`kill` してから再起動。

### Python が 3.14 になっていて wheel と非互換

→ 本リポジトリは `pyproject.toml` で `requires-python = ">=3.13,<3.14"` に固定済みです。clone 直後の最初の `uv sync` で 3.13.x が選ばれます。手動で `.python-version = 3.14` を書いた場合は元に戻してください。

---

## 9. 関連ドキュメント

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Hailo-10H 開発ドキュメント目次
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — HailoRT 5.2.0 → 5.3.0 移行ノート
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Pi 5 の CMA 制約詳細
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — wheel 自動検出スクリプト本体
