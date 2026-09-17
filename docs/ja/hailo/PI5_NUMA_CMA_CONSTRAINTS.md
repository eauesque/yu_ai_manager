# Pi 5 における `numa=fake=8` 下での CMA 制約

Hailo-10H ワークロード実行時の Raspberry Pi 5（8 GB）における CMA 割り当ての実用的な知見。
`cma=` の上限、512M を超える値がサイレントに失敗する理由、およびディスプレイドライバが消費した CMA の回復方法について記述します。

**対象者**: Raspberry Pi 5 上で Hailo GenAI モデル（LLM、Speech2Text）を実行する開発者
（AI HAT / AI HAT+ 使用）。

---

## ⚠️ 2026-05 firmware リグレッション注意

**2026-05-13 リリースの `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11` 以降**、`/boot/firmware/cmdline.txt` に `cma=` を書くとサイズ問わず VC firmware mailbox が完全沈黙する（`vcgencmd ioctl_set_msg failed:-1`、`raspberrypi-clk -22`、HEVC `-517`、cpufreq sysfs 欠落）。

**2026-05-16 以降の確定推奨方法**：cmdline `cma=` ではなく `/boot/firmware/config.txt` に `dtoverlay=cma,cma-512` を書く。DT の `linux,cma` reserved memory node 経由で確保されるため新 firmware と衝突しない。詳細は §6 と [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md) 参照。

以下の旧記述（cmdline `cma=512M` 推奨）は 2026-04-15 時点の検証結果。NUMA ノード境界による上限値（512M）の知見は依然有効だが、**設定箇所は cmdline ではなく config.txt の overlay 引数に移行**。

---

## TL;DR

- **設定箇所は `config.txt` の `dtoverlay=cma,cma-512`**（2026-05-16 確定。cmdline `cma=` は新 firmware で mailbox を壊す）
- `cma-1024` および `cma-768` は Pi 5（8 GB）で**サイレントに失敗** — `CmaTotal` が 0 になり、カーネルパニックや警告も出ない（NUMA ノード境界による上限。overlay 経由でも同じ制約が残ると推定）
- **`cma-512` が確認された上限値であり、推奨値** （overlay 経由で 2026-05-16 に Pi 5 8 GB で再検証、`CmaTotal: 524288 kB` 確保確認）
- 根本原因：デフォルトの Pi 5 カーネルが `numa=fake=8` を適用し、連続割り当てを 1 NUMA ノード（1 GB）に制限
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` はブート時に ~157 MB の CMA を消費** — DRM ドライバの初期化に失敗した場合でも（2026-04-15 で検証）
- **`camera_auto_detect=1`** は `pisp_be` と `videobuf2_dma_contig` をロードし、追加の CMA を消費。ヘッドレスシステムでは無効化推奨
- **ヘッドレス最適化のベースライン**（両オーバーレイ無効化）：ブート時に ~98 MB の CMA 使用、Hailo モデル用に ~414 MB 空き
- **YOLO InferModel は 0 MB CMA を使用**（2026-04-15 で確認） — GenAI モデル（LLM、Speech2Text）のみ CMA から割り当て
- LLM（qwen2.5-1.5b）+ Whisper-base 同時ロード：合計 ~328 MB — ヘッドレス最適化ベースライン内に収まる
- CMA はサーバー再起動では回収されない — フルシステム再起動（PCIe 電源再投入）でのみ解放（`hailo1x_pci` ドライババグ、Hailo に報告済み）
- VDevice を**プロセスライフタイムシングルトン**として扱う。追い出し/リロード禁止

---

## 1. 症状

`/boot/firmware/cmdline.txt` で `cma=1G`（または `cma=768M`）を設定して再起動すると、以下のようになります：

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

システムは正常に起動します。カーネルパニックもエラーメッセージもありません。`cmdline.txt` の CMA 設定は**サイレントに無視**され、CMA に依存するもの（Hailo-10H NPU、V4L2 カメラなど）の初期化に失敗します。

**`cmdline.txt` の変更後は常に CMA 割り当てを検証してください：**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. 根本原因：`numa=fake=8` ノード境界

Pi 5 用のデフォルト Raspberry Pi OS カーネルは `numa=fake=8` を適用し、物理メモリ 8 GB を**各 1 GB の 8 つの仮想 NUMA ノード**に分割します：

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

Linux CMA（`cma_init_reserved_mem`）は、ブート時に**NUMA ノード境界を越えない連続物理メモリ**として割り当てられる必要があります。
これにより、1 つのノード = 1 GB の厳密な上限が課されます。カーネル自体が同じノードのメモリを占有するため、ちょうど 1 GB を予約することはできません：

> **以下の表は 2026-04-15 時点の cmdline 方式での測定記録である。**
> NUMA ノード境界に由来する上限値（512M）の知見は現在も有効だが、**cmdline `cma=` は現在用いてはならない**（冒頭の firmware リグレッション参照）。
> 現行の設定方法は `config.txt` の `dtoverlay=cma,cma-512`（§6）。

| `cmdline.txt` 設定（2026-04-15 当時の記録） | 結果 |
|---|---|
| `cma=1G` | ノード全体を消費しようとする。カーネル用の余地なし → **サイレント失敗**、CmaTotal=0 |
| `cma=768M` | 信頼できる連続範囲を超過 → **サイレント失敗**、CmaTotal=0（2026-04-15 で検証） |
| `cma=512M` | 1 ノードの半分 → **確認済み安定** ✓（2026-04-15 で検証） ← 当時の推奨。**現在は `dtoverlay=cma,cma-512` を用いること** |
| `cma=384M` | 未検証（512M が確認済み。384M は不要） |
| `cma=256M` | 安定だが、LLM + Whisper 同時使用時は窮屈 |
| `cma=128M` | 安定だが、Hailo GenAI には不足（LLM だけで ~234 MB 必要） |

### 失敗がサイレントである理由

`cma_init_reserved_mem` は割り当て失敗時にパニックしません。カーネルは `CmaTotal=0` で起動し、CMA が要求されなかったかのように動作します。
`cmdline.txt` に書き込まれた値は事実上無視されます。

---

## 3. Hailo-10H CMA 要件

Raspberry Pi 5、AI HAT+、HailoRT 5.3.0 で測定：

| モデル / 組み合わせ | CMA 使用量 | 注釈 |
|---|---|---|
| LLM — qwen2.5-1.5b-chat（単独） | **~234 MB** | 2026-04-15 で測定 |
| YOLO InferModel（yolov8n、configure + bindings） | **0 MB** | 2026-04-15 で確認 |
| Whisper-tiny（単独） | ~70 MB | 推定 |
| Whisper-base（単独） | ~100 MB | 推定 |
| Whisper-small（単独） | ~150 MB | 推定 |
| **LLM + Whisper-tiny（同時）** | **~246 MB** | CMA 256 MB で測定 |
| **LLM + Whisper-base（同時）** | **~334 MB** | 推定。ヘッドレスベースライン内に収まることを期待 |

**YOLO は 0 MB CMA を使用**：HailoRT 5.3.0 では YOLO InferModel、`configure()`、`create_bindings()` は CMA をまったく割り当てません。
入力・出力 DMA バッファは、CMA ではなく `set_buffer()` 経由で事前割り当て numpy 配列からマッピングされます。
したがって YOLO は CMA 予算計算の要因ではありません。

CMA 512 MB でヘッドレス最適化（§5 参照）を適用した場合、以下の構成が動作すると予想されます：

- LLM のみ（~234 MB、~180 MB のヘッドルーム）
- Whisper-tiny / Whisper-base のみ（簡単に収まる）
- LLM + Whisper-base 同時（合計 ~334 MB、~80 MB のヘッドルーム）

Whisper-small と LLM の組み合わせ（推定 ~384 MB）は理論上の限界に近づきます — 信頼する前に実際の測定で確認してください。

詳細は [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md) の同時ロードテスト結果を参照。

---

## 4. CMA はフルリブートまで回収されない

HailoRT で割り当てられた CMA は、フルシステム再起動までメモリーにとどまります。
`VDevice.release()`、サーバープロセスの終了、カーネルモジュールのリロードに関わらず同様です。

**根本原因**（2026-04-15 で確認）：`hailo1x_pci` は、デバイス fd をクローズしたりモジュールをリロードした後でも DMA コヒーレント割り当てを保持します。
フルリブート（PCIe 電源再投入）のみで解放されます。バグは Hailo に報告済み。

| フェーズ | CmaFree（CMA 512 MB、ヘッドレス最適化） |
|---|---|
| ブート | **~426 MB** |
| LLM ロード後（~234 MB） | ~192 MB |
| Whisper-base ロード後（~100 MB） | ~92 MB |
| `VDevice.release()` 後 | ~92 MB（**返却されない**） |
| サーバープロセス終了後 | ~92 MB（**返却されない**） |
| `rmmod hailo1x_pci && modprobe hailo1x_pci` 後 | ~92 MB（**返却されない**） |
| フルシステム再起動後 | **~426 MB（復元）** |

**含意**：CMA 消費は同じブートセッション内のサーバー再起動を超えて累積されます。
サーバー再起動で CMA が回収されることを期待しないでください。VDevice を**プロセスライフタイムシングルトン**として設計してください。
CMA が枯渇した場合、フルシステム再起動でのみそれが復元されます。

---

## 5. ヘッドレス最適化：`/boot/firmware/config.txt`

デフォルトの Pi OS `config.txt` には、ヘッドレス（ディスプレイなし）システムでさえ大量の CMA を消費する 2 つの設定が含まれています。

### 5.1 `dtoverlay=vc4-kms-v3d` および `max_framebuffers=2`

**効果**：Pi 5 ファームウェアはブート時にディスプレイパイプライン用の CMA フレームバッファを事前割り当てします。
`max_framebuffers=2` では、これが**ユーザースペースプロセスが実行される前に** ~157 MB の CMA を消費します。

割り当ては、Linux DRM ドライバが後で初期化に失敗した場合でも（例：`[drm] Couldn't stop firmware display driver: -22` または `dmesg` の `Couldn't get core clock`）持続します。

| `config.txt` 状態 | ブート時 CmaFree |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` 有効（デフォルト） | **~257 MB** |
| 両方コメント化 | **~305 MB**（+~48 MB） |

**修正**（ヘッドレス / サーバーモード）：

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**トレードオフ**：ハードウェアアクセラレーション表示と 3D（V3D）には `vc4-kms-v3d` が必要です。
システムに SSH またはウェブインターフェースでのみアクセスする場合、無効化しても安全です。

### 5.2 `camera_auto_detect=1` および `display_auto_detect=1`

**効果**：これらのオーバーレイはブート時に CSI カメラと DSI ディスプレイをプローブし、`pisp_be`（Pi ISP バックエンド）と `videobuf2_dma_contig` をロードします。
ロードされるモジュールと検出されたハードウェアは各種追加 CMA を事前割り当てします。

| `config.txt` 状態 | ブート時 CmaFree |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 MB（vc4 無効化後） |
| 両方 0 に設定 | **~426 MB**（+~121 MB） |

**修正**：

```ini
camera_auto_detect=0
display_auto_detect=0
```

**注釈**：`camera_auto_detect=0` は CSI カメラのみに影響します。USB カメラ（UVC / `uvcvideo`）は影響を受けず、正常に動作し続けます。

### 5.3 ヘッドレス AI HAT+ 用途向け推奨最小 `config.txt`

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

この設定でのブート時 CMA 推定値：**~98 MB 使用**、Hailo モデル用に ~414 MB 空き。

### 5.4 CMA 予算サマリー（CMA 512 MB、ヘッドレス最適化）

| 構成 | CmaFree | Hailo 用に利用可能 |
|---|---|---|
| デフォルト（vc4-kms-v3d + カメラ有効） | ~257 MB | ~257 MB |
| vc4-kms-v3d + max_framebuffers 無効化 | ~305 MB | ~305 MB |
| + camera/display_auto_detect=0 | **~426 MB** | **~426 MB** |
| LLM ロード後（~234 MB） | ~192 MB | Whisper 用 |
| LLM + Whisper-base ロード後（~100 MB） | ~92 MB | （ヘッドルーム） |

---

## 6. 推奨構成

### `dtoverlay=cma,cma-512` を設定（2026-05-16 確定）

```bash
# 現在の CMA 状態を確認
grep CmaTotal /proc/meminfo

# 1) cmdline.txt から既存の cma= を削除（新 firmware で mailbox を壊すため）
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) config.txt の [all] セクションに dtoverlay=cma,cma-512 を追記
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) コールド再起動推奨（電源プラグ抜き差し）
sudo sync && sudo poweroff

# 再起動後に検証（4 項目すべて確認すること）
vcgencmd version                                # Broadcom 応答必須（沈黙なら失敗）
grep CmaTotal /proc/meminfo                     # 524288 kB 期待
journalctl -b -k | grep 'linux,cma'             # initialized node linux,cma が出ること
journalctl -b -k | grep '0x00030087'            # 出ないこと
```

dmesg に `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool` が出ていれば DT 経路で確保された証拠。
逆に `Reserved memory: bypass linux,cma node, using cmdline CMA params instead` が出ていたら cmdline に `cma=` が残っているので削除する。

### `vc4-kms-v3d` を有効化する場合

ディスプレイ KMS DRM が必要なら overlay 引数の形で統合可能：
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
ただし vc4-kms-v3d は §5.1 のとおり ~157 MB の CMA を食うので、Hailo GenAI 用途では無効化を推奨。

### 毎回カーネル / firmware / 設定変更後に検証

`/boot/firmware/cmdline.txt` や `config.txt` への変更、カーネル/firmware アップグレード後は CMA 状態と mailbox 応答がサイレントに変わる可能性があります。
上記 4 項目の検証を再起動後のルーティンにしてください。

---

## 7. 他の `numa=fake=8` 問題との相互作用

`numa=fake=8` はこのプロジェクトに関連する少なくとも 2 つの異なる問題を引き起こします：

| 問題 | 症状 | 根本原因 |
|---|---|---|
| CMA サイレント失敗 | `cma=1G`、`cma=768M` 後に `CmaTotal=0` | NUMA ノード境界が連続割り当てを制限 |
| Node.js インストール失敗 | npm/node インストーラがメモリエラーで中止 | NUMA ノード当たりメモリ（1 GB）が総 RAM として誤検出。[anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) としてアップストリームに報告 |
| `vc4-kms-v3d` CMA ドレイン | ブート時に ~157 MB 消費。DRM init が失敗しても返却されない | `max_framebuffers=2` がファームウェアに CMA フレームバッファを予約させる。Linux ドライバ起動前 |

サイレント失敗と vc4 ドレイン両方は、同じ根本的な制約（低 4 GB の DMA ゾーン、NUMA ノード境界）に起因します。
予期しないメモリ関連の障害が発生した場合、まず `/proc/meminfo` と `config.txt` を確認してください。

---

## 8. クイック診断チェックリスト

```bash
# 1. mailbox 応答（新 firmware で最優先確認）
vcgencmd version                     # 沈黙なら cmdline に cma= が残っている疑い

# 2. CMA 割り当てを確認
grep CmaTotal /proc/meminfo          # 0 kB = サイレント失敗

# 3. DT 経路 vs cmdline 経路の確認
journalctl -b -k | grep 'linux,cma'
# 期待: "initialized node linux,cma, compatible id shared-dma-pool" （DT 経路 = 正常）
# NG:   "bypass linux,cma node, using cmdline CMA params instead" （cmdline 残存）

# 4. NUMA トポロジを確認
numactl --hardware                   # ノード数とノード当たりメモリを表示

# 5. 現在のコマンドラインと overlay 設定を確認
cat /boot/firmware/cmdline.txt       # cma= が含まれていないことを確認
grep '^dtoverlay=cma' /boot/firmware/config.txt   # dtoverlay=cma,cma-512 が存在

# 6. Hailo デバイス可用性を確認
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # NPU がアクセス可能なことを確認

# 7. CMA コンシューマについて config.txt を確認
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. ロード済みカーネルモジュール（CMA ユーザー）を確認
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**検証環境**：Raspberry Pi 5 8 GB、Raspberry Pi OS
（Linux 6.12.62+rpt-rpi-2712、aarch64）、HailoRT 5.3.0、AI HAT+、CMA=512M
（**2026-05-16 再検証**: Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT で `dtoverlay=cma,cma-512` 経由で 524288 kB 確保、mailbox 応答確認）
