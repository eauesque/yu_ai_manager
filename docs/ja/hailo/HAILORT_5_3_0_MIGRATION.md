# HailoRT 5.2.0 → 5.3.0 マイグレーションノート

Raspberry Pi 5 + AI HAT 2（Hailo-10H）上で HailoRT 5.2.0 から 5.3.0
へのアップグレードから得られた知見です。エンドツーエンド実装テストと、
公式 `v5.2.0` / `v5.3.0` タグの直接 git diff 分析に基づいています。

**対象者**: Python（`pyhailort`）を使用して Hailo-10H NPU で推論を実行する開発者。

---

## TL;DR

- **典型的な Python 推論アプリケーションにおける実質的な破壊的変更は基本的にゼロです**。
  ヘッドライン数値（688 ファイル変更、+12,035 / −8,987 行）は多いですが、
  `VDevice`、`InferModel`、GenAI（`LLM` / `VLM` / `Speech2Text`）の表面は完全に
  後方互換です。
- 変更量のほとんどは **Hailo-8 カメラ / ISP / ファームウェア管理 API の削除**
  および内部リファクタリングです。裸の NPU 推論には影響ありません。
- **v5.2.0 時代の `.hef` ファイルは 5.3.0 ランタイムで変更なしにロードされます。**
  5 つのモデル（YOLOv8n、CLIP ViT-B/16、Qwen2.5-1.5B、Qwen2-VL-2B、Whisper-Base）
  で検証済み。
- Linux ドライバが `hailo_pci` から `hailo1x_pci` に、デバイスノードが
  `/dev/hailort0` から **`/dev/h1x-0`** に変更されました。`pyhailort` は
  新しいノードを内部で解決するため、`VDevice()` を使用する Python コードは
  変更不要です。**Docker デバイスパススルーのみ更新が必要です。**
- `Speech2Text.SegmentInfo` は `text` / `start_sec` / `end_sec` 属性を公開します
  （v5.2.0 と同じ）。`start` や `start_time` は公開されておらず、これらの名前を
  使用した防御的なコードは黙って 0.0 を返します。

---

## 1. 変更スコープ

公式 HailoRT GitHub リポジトリの `v5.2.0` と `v5.3.0` タグの直接 diff：

| スコープ | ファイル数 | 追加 | 削除 |
|---|---:|---:|---:|
| 合計 | 688 | +12,035 | −8,987 |
| パブリック C++ ヘッダー（`include/hailo/`） | 27 | +205 | **−383** |
| Python バインディング（`bindings/python/`） | 35 | +306 | **−413** |
| `pyhailort.py` のみ | 1 | +98 | **−158** |

**削除が追加を上回っています**。これは「簡素化」リリースです。
削除されたほとんどは NPU 推論パスとは関係ありません。

---

## 2. 削除された API — Hailo-8 カメラ / ISP / ファームウェアのみ

`hailort/libhailort/include/hailo/device.hpp` は 169 行を失い、
`platform.h` は 75 行を失いました。削除されたすべては低レベルデバイス制御：

- `firmware_update()` / `second_stage_update()`（ファームウェア書き換え）
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` /
  `write_user_config()` / `erase_user_config()`

これらはすべて **Hailo-8 AI Vision カメラモジュール**（Hailo チップが
ISP と画像センサーを直接制御する SoC スタイルボード）用の API です。
裸の Hailo-10H NPU での典型的な `VDevice` → `InferModel` → `generate`
フローでは呼び出されません。

**影響**: 純粋な NPU 推論アプリケーションではゼロ。実際に Hailo-8
カメラモジュールを制御するアプリケーションのみ使用状況を監査する必要があります。

---

## 3. Python シグネチャ変更

| API | v5.2.0 | v5.3.0 | 互換性 |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | デフォルト `10000` | デフォルト `600000` | ✅ デフォルトのみ、既存の呼び出しは変更なし |
| `Speech2Text.generate_all_text(timeout_ms=)` | 同じ | 同じ | ✅ 同じ |
| `LLM.read_all(timeout_ms=10000)` | デフォルトあり | デフォルト **削除**（必須） | ⚠️ 引数なしの `read_all()` → `TypeError` |
| `DeviceArchitecture.__init__` | 9 個の位置引数 | +`chip_serial_number`（10 個） | ⚠️ 直接構築は破壊 |

**`read_all()` 修正は 1 行の変更**：

```python
# Before (v5.2.0 スタイル、10 秒デフォルト)
text = generator.read_all()

# After (v5.3.0 は明示的なタイムアウトが必須)
text = generator.read_all(timeout_ms=600000)  # 10 分
```

`DeviceArchitecture` はユーザーコードで直接構築されることはまれなため、
そのシグネチャ変更はほとんど影響しません。

---

## 4. C++ ヘッダー名の変更（Python を通じて透過的）

HailoRT を C++ から直接使用するアプリケーションでは破壊的：

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`**（10 秒）→
  **`DEFAULT_GENERATE_ALL_TIMEOUT`**（10 分）、名前変更かつ延長
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** 追加、同様に 10 分
- `vlm.hpp` に 4 つの `generate_from_embeddings()` オーバーロードを追加

これらの名前変更は Python バインディングを通じては伝播しません。

---

## 5. NMS バウンディングボックス座標修正（動作変更）

`pyhailort.py` の NMS 後処理のロジック修正：

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

改善点：

- 画像境界 `max(0, …)` / `min(image_width, …)` クリッピング追加
- `ceil` → `floor`（オーバーシュート防止）
- `bbox_width` をクリップされた `x_max - x_min` から再計算

**動作の違い**: 同じモデルと同じ画像でも、NMS 出力は境界付近で ±1 ピクセル
シフトする可能性があります。独自の NMS 後処理を書くアプリケーションは影響を
受けません。pyhailort の `_output_raw_buffer_to_nms_with_byte_mask_*` ヘルパーを
呼び出すアプリケーションは、画像エッジ近くのバウンディングボックスが形状を
変える可能性があります。

---

## 6. 新 API（追加的）

- **`VDevice::create_session(uint16_t port)`** — ネットワークベースの推論
  セッション API（新機能）
- **`VLM::generate_from_embeddings()`** — 4 つのオーバーロード。
  事前計算された画像/動画埋め込みを `MemoryView` 入力として受け入れます。
  画像埋め込みを 1 回計算して複数の VLM 呼び出しで再利用し、
  エンコードの再実行をスキップできます。
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — NMS 出力用の
  クラスレベルフィルタリング（オンチップ）
- **`Device::query_performance_stats(sampling_period_ms)`** —
  設定可能なサンプリング周期
- **`Device::get_current_limit()`** — 電流制限を照会
- **`DeviceArchitecture.chip_serial_number`** — チップシリアルを読み込み

すべて追加的なので、既存コードは破壊されません。必要に応じて採用してください。

---

## 7. 環境変更

### 7.1 新 Linux PCI ドライバ

| 項目 | 旧 | 新 |
|---|---|---|
| カーネルモジュール | `hailo_pci` | `hailo1x_pci` |
| デバイスノード | `/dev/hailort0`（または `/dev/hailo0`） | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` は新しいデバイスノードを内部で解決**するため、
`VDevice()` を使用する Python コードは変更なしで動作し続けます。
`/dev/hailo*` または `/dev/hailort0` を直接開くコードのみ更新が必要です。

#### Docker / Podman パススルー

デバイスパススルー宣言を更新してください：

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # was: /dev/hailort0:/dev/hailort0
```

systemd ユニット `DeviceAllow=` 行と udev ルールも更新してください。

### 7.2 numpy 制約の緩和

- v5.2.0 `setup.py`: `numpy<2`（固定）
- v5.3.0 `setup.py`: `numpy`（上限なし）

以前 numpy 1.x に固定されていたアプリケーションは、HailoRT バンプと
一緒に numpy 2.x にアップグレードできます。

### 7.3 HEF バイナリ互換性

**v5.2.0 バケットの下でダウンロードされた `.hef` ファイルは、
5.3.0 ランタイムで変更なしにロードおよび実行されます。**
5 つのモデル（Raspberry Pi 5 + AI HAT 2）で検証：

| モデル | ファイル | 結果 |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 画像エンコーダ | `clip_vit_b_16_image_encoder.hef` | ✅ 512 次元出力 |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` は有効なテキストを返す |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` は有効なテキストを返す |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` は `SegmentInfo` を返す |

HEF バイナリ形式は理論的には大きなランタイム更新間で破壊される可能性がありますが、
**5.2.0 から 5.3.0 の間では発生しませんでした**。

### 7.4 HEF ダウンロード URL バケット

Hailo Developer Zone（`dev-public.hailo.ai`）は v5.2.0 と v5.3.0
バケットを並行でホスト：

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

2026-04-06 現在の v5.3.0 バケット状態：

| モデル | v5.3.0 バケット |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Llama-3.2-1B が必要なアプリケーションは、今のところ v5.2.0 バケットから
引き続き取得する必要があります。v5.2.0 HEF は 5.3.0 ランタイムで正しく
ロードされます。

---

## 8. `Speech2Text.SegmentInfo` 属性名

v5.2.0 と v5.3.0 の両方で、`Speech2Text.generate_all_segments()` は
これらのパブリック属性を持つ `SegmentInfo` オブジェクトを返します：

```python
seg.text        # str
seg.start_sec   # float（秒）
seg.end_sec     # float（秒）
```

**`seg.start` や `seg.start_time` は存在しません。** 古いドキュメントと
サンプルコードはこれらの名前を参照することがありますが、`AttributeError`
を発生させるか、より危険なことに、`getattr(seg, "start", 0.0) or getattr(seg, "start_time", 0.0)`
のような防御的コードでラップされるとき黙って 0.0 を返します。

ランタイム上で実際の属性名を確認するには：

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

## 9. スモークテストスクリプト

5.3.0 へのアップグレード後、実際に環境が動作することを確認する
最小限のスクリプト：

```python
"""HailoRT 5.3.0 スモークテスト — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. VDevice 作成
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. InferModel パス（YOLOv8n または任意の既存 HEF）
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

# 3. GenAI LLM パス
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

# 4. Speech2Text パス
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

## 10. アップグレードチェックリスト

5.2.0 → 5.3.0 アップグレード前または最中にコードで監査するポイント：

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` —
      **変更不要**
- [ ] `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)`
      コンストラクタ — **変更不要**
- [ ] `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` /
      `.generate_all()` キーワード引数 — **変更不要**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=,
      timeout_ms=)` — **変更不要**（`timeout_ms` を明示的に渡す場合）
- [ ] `LLM.read_all()` を `timeout_ms` 引数なしで呼び出しているか確認 →
      ある場合は明示的なタイムアウトを追加
- [ ] `DeviceArchitecture` を直接構築しているか確認 → ある場合は
      `chip_serial_number` を追加
- [ ] `/dev/hailo*` または `/dev/hailort0` の直接オープンを `grep` →
      ある場合は `/dev/h1x-0` に置き換え（または、pyhailort を通す方が良い）
- [ ] Docker / Podman `devices:` セクションを `/dev/h1x-0` に更新
- [ ] systemd ユニット `DeviceAllow=` 行と udev ルールを更新
- [ ] `.start` または `.start_time` を使用した `SegmentInfo` 属性アクセスを `grep` →
      `.start_sec` / `.end_sec` に切り替え。Whisper 出力タイムスタンプが
      アプリで黙って 0.0 にならないことを確認
- [ ] numpy を 1.x に固定した場合（v5.2.0 の `numpy<2` のため）、
      ピンを今なら外せます
- [ ] 既存 `.hef` ファイルを再ダウンロードする必要は **ありません**
- [ ] HEF ダウンロード URL に `v5.2.0` バケットをハードコードしている場合、
      `v5.3.0` に昇格（Llama-3.2-1B は `v5.2.0` を保持）
- [ ] pyhailort の組み込み NMS 後処理に依存する場合、
      画像エッジ付近のバウンディングボックスが ±1 ピクセル
      シフトする可能性があることに注意

---

## 11. 調査に使用したコマンド

公式 HailoRT リポジトリがクローンされていることを前提とします：

```bash
cd ~/hailort

# 全体的な diff サイズ
git diff --stat v5.2.0 v5.3.0 | tail

# パブリック C++ ヘッダー diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Python バインディング diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# pyhailort.py の完全な diff
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# 特定ヘッダーのパブリック API diff（関数シグネチャのみ）
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# device.hpp から削除された API
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

API 分析には C++ ヘッダーが行あたり最も多くの情報を含みます —
Python バインディングはほぼすべて pybind11 ボイラープレートなので、
素朴な行数 diff は誤解を招きます。代わりにパブリックシンボルで grep してください。

---

## 12. 結論

「688 ファイル変更」というヘッドラインは、実際の影響からはかけ離れています。
典型的な Hailo-10H NPU 推論アプリケーション上では：

- **コア NPU 推論 API（`VDevice` / `InferModel` / GenAI）は
  完全に後方互換**
- 削除されたすべての API は Hailo-8 カメラ / センサー / ISP /
  ファームウェア管理表面で、NPU のみの使用とは何も関係ありません
- **既存の `.hef` ファイルはすべて再ダウンロードなしでロード**
- 環境レベルでの唯一の必須変更は Docker デバイスパススルーを
  `/dev/h1x-0` に更新することです

アップグレード後の主な生活の質の改善：

- タイムアウトデフォルトが大幅に延長（10 秒 → 10 分）され、
  長文生成での偽タイムアウトが減少
- `FormatType.FLOAT32` が利用可能に（v5.2.0 では手動量子化/逆量子化が必須）
- NMS 座標クリッピングバグ修正
- numpy 2.x アップグレードパスが開放
- `VLM.generate_from_embeddings()` により、事前計算された画像埋め込みを
  複数の VLM 呼び出しで再利用可能

5.2.0 に固定されていた Hailo-10H Python アプリケーションを保守し、
アップグレードを先延ばしにしていた場合、この文書はマイグレーションがほぼ
ノーオペレーション（何もしなくて良い）であることを確認させるはずです。
