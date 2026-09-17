# HailoRT / driver 5.4.0 CMA 未解放判定の訂正と検証記録

作成: 2026-08-16 / 最終更新: 2026-08-24 / 対応バージョン: yu_ai_manager 4.661.1

CMA 未解放と判定していた事象（`docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` 参照）について、`hailo-ai/hailort-drivers` v5.4.0（2026-08-16 公開、GPL-2.0、ソース公開）で仮説検証と公式 vanilla / `FOLL_LONGTERM` 修正版の A/B 試験を行い、測定側の誤判定を訂正した記録。

---

## 1. 結論

**2026-08-17 最終追試（第4回）: 第3回までの `VERDICT: FAIL` は、初回 HEF ロード後の `CmaFree` 絶対回復量だけをリーク判定に用いたことによる誤判定だった。公式 vanilla 5.4.0 と `FOLL_LONGTERM` 修正版を A/B 比較し、低 `CmaFree` からの連続ロード、同一プロセス内の解放・再ロード、20回生成、さらに低 `CmaFree` 状態からの全試験反復がすべて成功した。生成中の RSS と `CmaFree` に単調増減はなく、CMA 割当失敗も0。初回の `CmaFree` 低下は multi-GB HEF のページキャッシュ増加と対応し、`MemAvailable` は約7GBを維持した。今回試験した Pi 5 + Hailo-10H + HailoRT/driver 5.4.0、単一モデル・単一デバイス・短時間の反復条件では、実用上の CMA リークは再現せず、`FOLL_LONGTERM` 修正にも測定可能な改善はない。長時間連続稼働、複数モデル同時使用、Hailo-8、IOMMU 配下は未試験であり、この結論の適用範囲外である。**

### 1.1 判定の変遷

| 回 | 日付 | その時点の判定 | 更新・訂正の根拠 |
|---|---|---|---|
| 第1回 | 2026-08-16 | 判定不能 | driver だけを 5.4.0 にすると library 5.3.0 との完全一致チェックで API が拒否された（§3） |
| 第2回 | 2026-08-17 | 限定的な試験のみ完了 | driver / library / firmware 5.4.0 を揃え、`run2` 反復はプラトー化したが、pyhailort 経由の直接 repro は未実施だった（§4） |
| 第3回 | 2026-08-17 | 暫定 `FAIL`（後に誤判定） | 初回 HEF ロード後の `CmaFree` 絶対回復量だけを判定した旧診断結果。単発測定ではメモリ喪失とページキャッシュ利用を区別できなかった（§5、§7） |
| 第4回 | 2026-08-17 | 実用上のリークは再現せず | vanilla / `FOLL_LONGTERM` A/B、低 CMA 反復、同一プロセス再ロード、20回生成、RSS・`MemAvailable`・割当失敗を測定して第3回を訂正した（§8） |

---

## 2. v5.3.0 → v5.4.0 ソース差分（`hailo-ai/hailort-drivers`）

GitHub API で両タグ間の全ファイルを diff。単一スカッシュコミットのため commit message からは何も読めず、実ファイル diff で確認。CMA 確保・解放の**ロジック自体**（`dma_alloc_coherent`/`dma_free_coherent` ペア）に変更はなく、以下はリファクタ・防御的修正が中心:

| ファイル | 変更内容 |
|---|---|
| `linux/utils/compact.h` → `compat.h` | カーネル互換レイヤーのファイル名リネーム |
| `linux/vdma/memory.c` | `hailo_desc_list_release()` に NULL チェック追加、解放後にポインタを NULL クリア（**二重解放防止**の防御的修正） |
| `linux/vdma/vdma.h` | `hailo_descriptors_list_buffer` から冗長フィールド `kernel_address` を削除（`desc_list.descs` に統合） |
| `common/vdma_common.c` | DMA 転送完了判定を `hw_num_proc` 直接計算方式から `num_proc`/`num_avail` 比較方式に書き換え（転送完了トラッキングのバグ修正の可能性） |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync`（新しいカーネル API 名への追従） |
| `common/pcie_common.c` | FW 制御プロトコルから md5 フィールド削除、SCU ログ破損判定を先頭 4 バイトのみ→先頭 5 ワード全チェックに強化 |

エラーメッセージ文言も変更（長い説明文 → `out of CMA memory.` に短縮）されているが、確保・解放の制御フローは同一。**この diff だけからは、当時の仮説（モデル再ロード時の CMA 未解放）に対応する変更は読み取れない**。

---

## 3. 実機での入れ替え作業と詰まった点（2026-08-16、第1回試行）

Raspberry Pi 5 + Hailo-10H、稼働中の `hailo1x_pci 5.3.0`（dkms 管理）を対象に、手動ビルドで v5.4.0 に入れ替えを試行。

### 3.1 `make install` は `all` に依存しない

`linux/pcie/Makefile` の `install` ターゲットは `modules_install` のみで、ビルド成果物 (`.ko`) が存在しない状態でも警告なく完了する（正確には `System.map` 欠如の警告は出るが、ビルド未実施が原因とはわからない）。

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**必ず `make all && sudo make install` の順で実行すること。**

### 3.2 Raspberry Pi のカーネルヘッダに `System.map` が同梱されていない

`modules_install` 実行時に以下の警告が出て `depmod` が黙ってスキップされる:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

`/usr/src/linux-headers-<kernelver>/System.map` が存在しないため。`/boot/System.map-<kernelver>` は存在するのでコピーすれば解決:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

これをやらないと `modprobe` が新しくインストールした `.ko` を解決できず `FATAL: Module hailo1x_pci not found` になる（`.ko` ファイル自体は `/lib/modules/<kernelver>/kernel/drivers/misc/` に存在するのに、である）。

### 3.3 udev ルールは reload/trigger しないと即時反映されない

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

モジュール入れ替え直後は `/dev/h1x-0` が `crw-------`（root 専用）になる。以下で解決:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 ドライバとライブラリのバージョン不一致は致命的

カーネルドライバのみ 5.4.0 に上げた状態で `hailortcli` を実行すると:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

HailoRT ライブラリはカーネルドライバとの**完全一致**を要求しており、片方だけ先行アップグレードすると全 API 呼び出しが即座に拒否される。ドライバ単体でのバニラ検証は不可能で、`hailort`（SDK 本体）のユーザ空間パッケージも同時に上げる必要がある。

- `apt-cache policy hailort` → 候補 5.3.0（本日時点、公式 apt に 5.4.0 未配布）
- `gh api repos/hailo-ai/hailort/releases` → `v5.4.0` タグは存在するが `assets` は空（ビルド済み deb 無し、ソースのみ）

つまり **HailoRT 本体を deb で入れるか、ソースからフルビルドするかしないと 5.4.0 の実地検証はできない**。フルビルドは C++ CMake + Python バインディングの大掛かりなビルドになり、`hailo-tappas`・`python3-hailort` 等の依存パッケージも巻き込むリスクがあるため、第1回ではいったん見送り、公式 deb 配布を待つ判断とした。

---

## 4. 自前ビルド手順記録（2026-08-17、第2回試行）

apt/公式 deb の配布を待たず、GitHub ソース（driver: GPL-2.0、`hailort` 本体: MIT）から自前でビルドし、システムに投入した際の手順・詰まった点。

### 4.1 ビルド環境

- `checkinstall` を導入（`sudo apt-get install -y checkinstall`）。ただしカーネルモジュールの `xz` 圧縮ステップと `installwatch`（checkinstall の LD_PRELOAD ベースのファイル追跡機構）が競合し、`make install` を checkinstall 経由で実行すると `xz: ... そのようなファイルやディレクトリはありません` で毎回失敗した。**カーネルモジュールのパッケージ化には checkinstall を使わず、dkms（driver 本体の場合）または素の `make install`（ユーザ空間ライブラリの場合）を使うこと**
- ビルド前にメモリを確保: `headroom mcp serve` の重複プロセスおよび `rust-analyzer` を一時停止（合計 1GB 弱を解放）。Pi のメモリは 7.9Gi、ビルド中も available 3.8Gi 程度を維持できた

### 4.2 `hailort`（ユーザ空間ライブラリ）ビルド

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # ディレクトリを作成してから
cmake .. -DCMAKE_BUILD_TYPE=Release   # 外部依存(protobuf/spdlog/eigen等)を FetchContent で自動取得、約4分
cmake --build . -j2   # -j2 に制限(メモリ逼迫回避)、約15分
sudo make install     # /usr/local/{include,lib,bin} に配置。apt 版(5.3.0, /usr 配下)と共存可能
```

デフォルトの `option()` 値はすべて重量級コンポーネント（GStreamer・テスト・サーバ・Ollama連携等）が OFF のため、`libhailort.so`・`hailortcli`・`libhailopp` のみがビルドされる、比較的軽量な構成だった。

**注意**: `make install` の成果物は `/usr/local` 配下に入り、apt 版（`/usr` 配下、5.3.0）を上書きしない。動作確認時は `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...` のように明示的にパスを指定する必要がある。

### 4.3 driver（カーネルモジュール）入替と firmware 更新

driver 自体は dkms 経由（付録 A の復旧手順と同じ要領で `-v 5.4.0` に差し替え）でビルド・インストールし、`rmmod`/`modprobe` で読み替え。この時点で `hailortcli` は `HAILO_DRIVER_OPERATION_FAILED(36)` / dmesg 上 `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0` となり、**デバイス上のファームウェア（SoC 側、pci_ep）も別途 5.4.0 に上げる必要がある**ことが判明。

```bash
# 公式 S3 から firmware を取得（driver リポジトリ同梱のスクリプトを使用）
bash hailort-drivers/download_firmware_hailo10h.sh
# 既存 firmware をバックアップしてから新版に差し替え
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <展開先>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

ここでモジュール再ロード（`rmmod`/`modprobe`、`support_soft_reset=1` 指定含む）を試みたが、dmesg は一貫して `SOC Firmware batch was already loaded` を返し続けた。ドライバソースを確認したところ、`load_soc_firmware()`（Hailo-10H の SoC ファームウェア読込み経路）には `support_soft_reset` によるソフトリセット処理が実装されておらず（Hailo-8 の `load_nnc_firmware()` にのみ実装）、`hailo_pcie_is_firmware_loaded()` が true を返す限り無条件にスキップされる実装だった。つまり **SoC 上のファームウェア状態はモジュール再ロードでは変更できず、実機の電源再投入が必須**である。

再起動後、dmesg は firmware batch の書込み（`customer_certificate.bin`・`scu_fw.bin`・`u-boot-*.dtb.signed`・`u-boot-spl.bin`・`fitImage`・`image-fs` の順、4064ms）→ `SOC Firmware Batch loaded successfully` を記録し、`hailortcli fw-control identify` が `Firmware Version: 5.4.0 (release,app)` で正常応答した。

### 4.4 簡易 CMA 挙動確認と限界

`hailortcli run2`（resnet_v1_18.hef、`hailo_tutorials` パッケージ同梱の小型モデル）で単発 load/run/exit、および 8 回連続実行時の `CmaFree`（`/proc/meminfo`）推移を観測:

| 実行 | CmaFree (kB) |
|---|---|
| baseline (再起動直後) | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3〜8 | 133744（変化なし、プラトー） |

数回でプラトーに達し、8 回目まで追加リークは観測されなかった。ただしこれは CLI 経由の単純な load/run/exit（別プロセスごとの起動）であり、`docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` が報告する 2 つの既知リーク——(a) **同一プロセス内**での `VDevice.release()`/モデル再ロード時の未解放、(b) `generate_stream()`（LLM 推論）実行中の継続的リーク——のどちらとも異なる経路であり、この結果は「解決した」ことの証拠にはならない。

本命の repro（`tools/diag_hailo_cma_reclaim.py` および forum-followup doc 記載のスクリプト）は Python の `hailo_platform`（pyhailort）バインディング経由で GenAI LLM を読み込む方式のため、そのまま 5.4.0 環境では動かせなかった:

```
$ .venv 内の hailo_platform は libhailort.so.5.3.0 に固定リンク（ldd で確認）
$ VDevice() 構築時に driver(5.4.0)/library(5.3.0) のバージョン不一致で同じ HAILO_INVALID_DRIVER_VERSION に該当する見込み
```

この時点では pyhailort（Python バインディング）を 5.4.0 ソースから再ビルドし `.venv` に差し替える作業は未着手だったが、第3回試行（§5）で実施した。

---

## 5. pyhailort 再ビルドと repro 再実行（2026-08-17、第3回試行）

本節は第3回試行時点の暫定判定を記録する。判定方法と結論は、第4回 A/B 試験（§8）で訂正済みである。

### 5.1 pyhailort（Python バインディング）のビルド

`hailort` 本体リポジトリの `hailort/libhailort/bindings/python/platform/` が pyhailort の pip パッケージソース（`pyproject.toml`、scikit-build-core + pybind11 ベース）。§4.2 で `/usr/local` に配置済みの libhailort 5.4.0 を明示的にリンクさせてビルド:

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

build isolation 内で `scikit-build-core`/`pybind11` を PyPI から自動取得してビルド、`.venv` の `hailort` を 5.3.0 → 5.4.0 wheel に差し替え。`ldd` で `_pyhailort*.so` が `/usr/local/lib/libhailort.so.5.4.0` にリンクしていることを確認し、`VDevice()` の construct/release も単体で正常動作した。

### 5.2 既存 repro（`tools/diag_hailo_cma_reclaim.py`）の再実行

2026-05 と同一の repro スクリプト・同一の判定基準・同一 HEF（`~/hailo_models/Qwen3-1.7B-Instruct.hef`）で、`.venv` の `hailo_platform` を 5.4.0 に差し替えた同一環境のまま再測定した:

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

結果（`logs/hailo_cma_reclaim_poc.json`）:

| イベント | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22（消費 137 MB） |
| child kill (`terminate`) 直後 | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s〜+30s | **0**（29 MBからさらに約28.5 MB低下し、以後数分経過後も `CmaFree` は512 kB付近に張り付いたまま） |

この 29 MB → 512 kB 付近の再低下は、同時刻の他プロセス競合とは確認できなかったが、今回の計測だけでは原因を特定できない未解明の観測として残す。初回ロード後のページキャッシュ利用（§8.4）だけではこの途中経過を説明できず、RSS・`MemAvailable`・割当失敗を同時採取した反復試験もこの実行にはないため、§8 の最終判定の根拠には用いない。

ただし、この 512 kB 付近は §8.3 の `FOLL_LONGTERM` 試験中に観測した 464→1,648 kB と同じ帯域であり、その状態から20回生成、解放、再ロードまで成功している。低値へ至った過程は未解明のままだが、**この帯域の `CmaFree` 自体は直ちに危険状態やロード不能を意味しない**ことは実機で確認済みである。

旧診断ツールが出力した原文（第3回時点の暫定判定。最終判定は §8 で訂正済み）:

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

この試行で確定したのは、初回 HEF ロード後の `CmaFree` が旧判定基準どおりには回復しなかったことだけである。プロセス終了後の利用可能メモリ喪失や v5.4.0 のリーク未修正までは立証していない。第3回では暫定的に未解放と解釈したが、その解釈と判定方法は §8 で訂正した。

---

## 6. 第3回試行中のカーネルクラッシュと CMA デバッグコードの復旧（2026-08-17）

### 6.1 事象と原因候補

CMA の解放経路を調べるため、ローカル DKMS ソースの `linux/vdma/memory.c` に `linux/mm.h` の include と、`dma_free_coherent()` の直前で `virt_to_page()` / `page_count()` を呼ぶ計測コードを追加していた。この変更を含むモジュールをロードすると Hailo 利用時にハングし、起動不能となったため、現在は `/boot/firmware/cmdline.txt` の `module_blacklist=hailo1x_pci,hailo_pci` で自動ロードを止めている。

`dma_alloc_coherent()` が返す CPU 仮想アドレスを `virt_to_page()` で直接ページへ変換することは DMA API の契約ではない。返却アドレスのマッピング形式は allocator 側に委ねられるため、ここから得る `page_count()` は CMA の参照数を正しく観測する手段ではなく、不正なページ参照を生み得る。計測コードは descriptor list と continuous buffer の両方の解放経路で実行される。

追加時刻が 10:15:36、当該 DKMS ビルド開始が 10:15:39 であり、ハングしたモジュールにはこのコードが含まれていたと判断できる。クラッシュ直前のスタックトレースは取得できていないため、厳密な原因確定ではないが、バニラ v5.4.0 に存在しない唯一のローカルな実行コード変更であり、最有力の原因候補とする。

### 6.2 復旧済み状態

以下の 7 行（`linux/mm.h` の include、二箇所の `virt_to_page()` / `page_count()` ログ）を除去し、DKMS を再ビルドして `depmod` まで完了した。

- カーネル: `6.18.39+rpt-rpi-2712`
- 再ビルド済みモジュール: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- `modules.dep` には上記モジュールが登録済み
- blacklist は維持中で、再ビルド後のモジュールはまだロードしていない

次回はシリアルコンソールなどの復旧経路を確保してから blacklist を外し、再起動による初回ロードを確認する。CMA 未解放問題そのものの調査では、DMA API の返却アドレスを内部ページへ変換する計測を再導入せず、ドライバが保持するバッファ台帳・割当てサイズ・`dma_free_coherent()` 呼出し回数を観測対象とする。

**追記（2026-08-17 後刻）**: `cmdline.txt` バックアップ（`cmdline.txt.bak-blacklisted`）を用意した上で blacklist を外して再起動し、正常に起動することを確認済み（シリアルコンソール `console=serial0,115200` も設定済みで復旧経路は確保されている）。以降 §7 の安全な計装（生ページ検査なし、既存カウンタ・サイズのログ出力のみ）で調査を継続した。

---

## 7. 原因仮説の形成と除外 — `FOLL_LONGTERM` の検証と反証（2026-08-17）

本節は第3回試行を受けた原因仮説の形成と、実験で除外できた原因候補を記録する。ここでの役割は候補の絞り込みであり、CMA リーク有無の最終判定は第4回 A/B 試験（§8）に依存する。

§6 のクラッシュを踏まえ、`virt_to_page()` 等のページ内部への直接アクセスを避けた安全な計装（`dev_err()` によるログ出力のみ。生ポインタの検査・変換なし）で調査を継続した。

### 7.1 計装内容

`linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` の以下の箇所に、既存のアトミックカウンタ（`controller->desc_cma_in_use` / `controller->cma_in_use`）と割当てサイズを出力するログを追加（ページ内部へのアクセスは一切行わない）:

- `hailo_desc_list_create`/`hailo_desc_list_release`（descriptor list の alloc/free）
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free`（continuous buffer の alloc/free）
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl`（明示的解放 ioctl 経路）
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy`（ユーザ空間バッファの DMA マッピング・アンマッピング経路。`buffer_type`/`is_mmio`/`is_dmabuf` も出力）
- `hailo_vdma_file_context_finalize`（fops_release 時の一括クリーンアップ、ENTER/EXIT でカウンタを出力）

### 7.2 観測結果

再起動直後（`CmaFree` ≈ 451 MB）から `tools/diag_hailo_cma_reclaim.py --signal terminate` を実行し、`sudo dmesg | grep CMA_DBG` で全ログを回収・集計した。

- **`/proc/meminfo` の `CmaFree`**: 451 MB → 195 MB（**256 MB 消費**）→ kill+30秒待機後も 204 MB（**baseline 比で 247 MB 低い値**）
- **ドライバ自身の `desc_cma_in_use`（descriptor list、`dma_alloc_coherent` 経由）**: 最大でも 2〜4 MB 程度。`file_context_finalize` の EXIT 時点で確実に 0 に戻っている
- **`cma_in_use`（continuous buffer、`dma_alloc_coherent` 経由）**: このセッション中、常に 0（continuous buffer は一度も使われていない）
- **ユーザ空間バッファの DMA マッピング（`hailo_vdma_buffer_map`、`buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`、`is_mmio=0`、`is_dmabuf=0`）**: 621 回呼ばれ、うち **342 回が 8 MB（`0x800000`）サイズ**（合計 2.7 GB 分のマッピング呼出し。同じホスト側ステージングバッファがパイプライン処理で使い回されているとみられる）。`hailo_vdma_buffer_destroy` は 628 回呼ばれ、`buffer_map` とほぼ 1 対 1 で対応しており、**ドライバ自身のマッピング台帳としては破綻していない**（`dma_unmap_sg` は正しく呼ばれている）
- **SWIOTLB（`/sys/kernel/debug/swiotlb/`）**: `io_tlb_used_hiwater=0`。バウンスバッファは一度も使われていない
- Hailo デバイスは IOMMU 配下にない（`/sys/bus/pci/devices/0001:01:00.0/iommu_group` なし）

この時点では、`dma_alloc_coherent()` 系のドライバ自身の割当て（desc list・continuous buffer）ではなく、`hailo_vdma_buffer_map()` が扱う「ユーザ空間が確保した既存メモリを DMA 用にマッピングする」経路（`HAILO_DMA_USER_PTR_BUFFER`）を CMA 低下の原因候補と解釈した。この経路ではドライバは新規に CMA を確保せず、既存のユーザページを DMA 可能にするために固定化（pin）する。

### 7.3 原因仮説: `get_user_pages()` に `FOLL_LONGTERM` が指定されていない

`linux/vdma/memory.c` の `prepare_sg_table()`（`hailo_vdma_buffer_map()` の内部で呼ばれる）を確認したところ:

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages` は（本カーネル 6.18.39 は `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)` に該当するため）単なる `get_user_pages()` のエイリアスであり、**`FOLL_LONGTERM` フラグが指定されていない**。解放側（`clear_sg_table()`）も対応する `put_page()` を呼んでおり、新しい `pin_user_pages()`/`unpin_user_pages()` API 系ではなく旧来の `get_user_pages()`/`put_page()` のままである。

Linux カーネルの文書化された作法（`Documentation/core-api/pin_user_pages.rst`）では、DMA 転送のように**長時間ページ参照を保持するコードは `pin_user_pages()` を `FOLL_LONGTERM` 付きで使うべき**とされている。`FOLL_LONGTERM` を指定しない場合、たまたま CMA 領域内に存在していたユーザページが `get_user_pages()` で固定化されても、CMA が本来持つ「必要な時に他の用途へ動かせる（migratable）」性質が長期間にわたって無効化される。CMA アロケータは通常、長期固定前にそのページを CMA 領域外へマイグレーションするが、`FOLL_LONGTERM` を使わない経路ではこの migration が起こらないため、**固定化されている間は CMA 領域からその分だけ実質的に失われ、解放（`put_page()`）後も即座には CMA の空き領域として認識されない**（マイグレーション・コンパクションが別途必要になるため）。

この仮説は第3回時点の単発測定（§7.2）とは整合した:
- ドライバ自身の CMA カウンタは無関係（`get_user_pages` は `dma_alloc_coherent` を経由しない）
- map/destroy 呼出し回数は正しくバランスしている（`put_page()` 自体は正しく呼ばれている。問題は解放後の CMA への"戻り"が遅い/不完全なこと）
- Qwen3-1.7B-Instruct のような大きな LLM を読み込むと大量の 8 MB バッファが host メモリ上に確保・DMA マッピングされ、その一部が CMA 領域内のページを含んでいた場合に本問題が顕在化する
- kill 後の緩慢かつ部分的な `CmaFree` の回復（30秒で+15〜30MB程度、その後も数分かけて緩やかに増加）とも整合する（`put_page()` 自体はプロセス終了時に確実に呼ばれるが、CMA の空き領域としての回収にはさらに追加の処理が必要と見られる）

### 7.4 修正候補の実装と実機検証 → 反証（2026-08-17 続報）

`prepare_sg_table()` を `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` から `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()` へ実際に置き換え、`<linux/mm.h>` の include を追加した上でビルド・dkms 再登録・実機ロードまで完了させた（`pin_user_pages`/`unpin_user_page` シンボルは `modprobe --dump-modversions` で正常に解決していることを確認）。

再起動直後の高 `CmaFree`（453 MB）状態から同一 repro を実行した結果:

| | 修正前（n=複数ラン） | 修正後（n=1） |
|---|---|---|
| baseline | 436〜451 MB | 453 MB |
| after_llm_loaded | 173〜195 MB（消費 256〜263 MB） | 180 MB（消費 273 MB） |
| after_post_wait | 188〜204 MB（回収 9〜15 MB） | 190 MB（**回収 10 MB**） |
| 旧判定基準による `VERDICT` | `FAIL` | **`FAIL`（変化なし）** |

> この表はラン数と集計方法が非対称であり、厳密な A/B 比較ではない。A/B の判定は、同一条件で反復した §8 の結果による。

`dmesg` で `CMA_DBG buffer_map` を確認したところ、修正後も同じ 0x800000（8 MB）サイズのバッファが `pin_user_pages` 経由で問題なくマッピングされており（pin 失敗やカーネルの警告は一切出ていない）、コード経路自体は意図通り実行されていた。`echo 1 > /proc/sys/vm/compact_memory` による強制コンパクションも効果なし。`MemAvailable` は 7.1 GB と健全なままで、システム全体のメモリ不足ではなく `CmaFree` という特定の会計だけが回復しない点も修正前と同じだった。

**結論: `FOLL_LONGTERM` 欠落仮説は実験により反証された。** `get_user_pages()`→`pin_user_pages()`+`FOLL_LONGTERM` への置換は Linux カーネルの文書化された作法に沿う正当な改善ではあるものの、本セッションで観測している CMA 未解放症状の直接原因ではなかった。仮説自体は理論的に筋が通っており（CMA のマイグレーション機構と長期固定の相互作用は実在する既知の問題種別）、コード品質上の指摘としては依然有効だが、**今回の実測結果を単独で説明する根本原因ではない**と判断する。

### 7.5 原因候補の除外（最終判定は §8）

以下は実験によって明確に**除外**できた原因候補である。このリストは仮説検証の成果として有効だが、リーク有無の判定そのものではない。

- ドライバ自身の `dma_alloc_coherent()` 経由の割当て（desc list・continuous buffer）— 数MBのみ、正しく0に戻る
- SG マッピングの map/destroy 呼出しの不整合 — バランスしている
- SWIOTLB バウンスバッファ — 一度も使われていない（`io_tlb_used_hiwater=0`）
- `get_user_pages()` の `FOLL_LONGTERM` 欠落 — 修正を実装・実機検証したが改善なし

第3回試行までに残った事実は、`MemAvailable` が健全なまま `CmaFree` だけが初回ロード後に低下することだった。当時はこれを未解放と解釈したが、単一試行では「利用可能メモリの喪失」と「movable CMA ページのページキャッシュへの転用」を区別できない。第4回では低 `CmaFree` のまま再試行し、実際のロード可否・反復時の純減・RSS・CMA 割当失敗を測定して判定を訂正した。

---

## 8. 第4回試行: vanilla / `FOLL_LONGTERM` A/B 追試と誤判定の確定（2026-08-17）

### 8.1 比較対象

- `FOLL_LONGTERM` 修正版: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`、ロード時 `srcversion=C84A00ABB326748A1832CE1`
- 公式 vanilla 5.4.0: tag `v5.4.0`、commit `b6dd17c609504e648eb516ff4a867167edf56f3c`、`get_user_pages()` / `put_page()`、ロード時 `srcversion=A260C39C9F2C06DD4FB072E`
- カーネル: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef`（2,880,748,478 bytes）

### 8.2 独立プロセスでの2回連続ロード

| ドライバ | 試行 | baseline | loaded | exit後 | baseline比増減 | ロード |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB（減少）** | 成功 |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB（増加）** | 成功 |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB（減少）** | 成功 |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB（減少）** | 成功 |

両ドライバとも、初回だけ `CmaFree` が大きく低下し、その低い値からの2回目ロードは成功して純減がほぼ0になった。従来の診断は「ロード中に消費した量のうち何MB戻ったか」だけで判定したため、2回目のように開始時点から既に `CmaFree` が低い正常ケースまで `FAIL` にしていた。

### 8.3 同一プロセス内の生成・解放・再ロード

| 指標 | `FOLL_LONGTERM` | vanilla 1回目 | vanilla 低CMA反復 |
|---|---:|---:|---:|
| 生成完了 | 20/20 | 20/20 | 20/20 |
| 1回目ロード | 成功 | 成功 | 成功 |
| 解放後の2回目ロード | 成功 | 成功 | 成功 |
| 生成1→20の `CmaFree` | 464→1,648 kB | 115,376→123,728 kB | 82,320→83,296 kB |
| 生成1→20の `MemAvailable` | 6,706,208→6,788,432 kB | 6,830,352→6,910,560 kB | 6,871,504→6,906,368 kB |
| 生成中 RSS | 63,888 kB固定 | 63,904〜63,920 kB | 63,936〜63,952 kB |
| CMA割当失敗 | 0 | 0 | 0 |

vanilla 低CMA反復は `CmaFree=87,424 kB` から開始し、全解放直後は79,520 kB、その後87,344 kBまで戻った（純差80 kB）。ロード・生成・解放を繰り返すほど失われる挙動はない。vanilla の `nr_foll_pin_*` が0なのは `FOLL_PIN` APIを使わないためで、pin解放の成否比較には利用できない。

### 8.4 初回低下の解釈

vanilla 再起動直後から全追試後までに `Cached` は1,845,872 kBから約4,988,224 kBへ増えた一方、`MemAvailable` は7,071,280 kBから約6,962,816 kBを維持した。増加量はmulti-GB HEFの読込みと整合し、初回の `CmaFree` 低下がアクセス不能なメモリの喪失ではなく、movable CMAページを含む空きページのページキャッシュ利用として説明できる。

### 8.5 運用上の結論

1. `CmaFree` の絶対値だけでモデルロードを拒否してはならない。実機では1 MB未満からもQwenロードに成功した。
2. 低 `CmaFree` はテレメトリとして記録し、実際のHailoRTメモリ割当エラーを失敗判定に用いる。
3. `CmaFree` の観測値、実ロード失敗、リーク診断を混同せず、次の3状態で扱う。

| 状態 | 判定条件 | 製品上の処置 | 再起動・調査 |
|---|---|---|---|
| `INCONCLUSIVE` | 初回低下だけ、3回未満、または下記 `FAIL` 条件を満たさない | テレメトリを記録してロードを試行する。低 `CmaFree` 単独では拒否しない | 再起動しない。同一条件で測定を追加する |
| `OPERATIONAL_FAIL` | HailoRT が実際の host-memory allocation error を返した | そのロード要求だけを失敗とし、不要な Hailo workload を停止して再試行する | 単発では再起動しない。実失敗が反復し workload 解放後も回復しない場合だけ運用ポリシーに従う。現行 Phase 0.5 は `would_fire` の記録のみで自動再起動しない |
| `FAIL` | 低 CMA 状態から同一条件を3回反復し、解放後の baseline 比純減が **1回10 MB超となる試行が3回中2回以上**、3回の正の純減合計が **20 MB超**、かつ RSS の単調増加または `MemAvailable` の128 MB超低下を伴う | 個々のロード可否とは別のリーク診断として記録する | カーネル / HailoRT 側の調査を再開し、直接証拠を採取する。診断成立だけで自動再起動しない |

この3回基準は今後の診断用であり、独立プロセス試行が各ドライバー2回だった本節の §8.2 へ遡及適用していない。第4回の結論は §8.2 の A/B に加え、§8.3 の同一プロセス20回生成・解放・再ロードと低 CMA 反復を総合している。
4. `FOLL_LONGTERM` 置換はLinux DMA APIの一般的作法としては妥当だが、本件への効果はなく、実機は公式vanilla 5.4.0へ戻した。
5. 自動再起動判定は低 `CmaFree` 単独では発火させず、実ロード失敗の観測を必須条件とする。

---

## 9. 今後のアクション（2026-08-17 時点）

1. `FOLL_LONGTERM` 修正の検討と実機反証は完了した。再現用の差分と復元方法は付録 B に保存し、本番ドライバーへは適用しない。
2. **製品側は対応済み**: `core/hailo_device_core/device_manager_genai.py::acquire_genai` は v4.620.8 で、推定必要量より `CmaFree` が低くても `acquire_low_cma_observed` を記録して実ロードを続行するよう改修した。拒否 tracker へ記録するのは factory が返した実 HailoRT host-memory error だけであり、`tests/test_hailo_cma_false_positive.py` で低値からのロード継続を固定している。
3. 旧フォーラム草稿の「後続 `LLM(...)` が HailoRT に insufficient host CMA で拒否された」という記述をログと旧実装で再監査した。引用元の PID 3237 セッションには release 後の acquire 記録がなく、同日ログで追跡できる低 CMA 拒否はすべて HailoRT 呼出し前の自前イベント `acquire_rejected_low_cma` だった。別セッションで factory まで到達した失敗は status 8 (`HAILO_INTERNAL_FAILURE`) であり、host-memory error の status 3 ではない。従って旧記述を裏付ける HailoRT OOM 証拠はなく、`docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` では自前ガード由来の拒否を報告に混入した旨を明記して撤回する。
4. 訂正投稿は §8 の数値・適用範囲、実装ガードの訂正、`FOLL_LONGTERM` 反証、計装上の警告を一つの現行ドラフトへ統合し、旧英文草稿をコピー可能な形で残さない。
5. 実ロード失敗または反復ごとの累積的な利用可能メモリ喪失が再現した場合だけ、カーネル / HailoRT 側のリーク調査を再開する。その際は `page_owner`、CMA debug 情報、割当失敗 status、RSS、`MemAvailable` などの直接証拠を採取する。

---

## 10. yu_ai_manager (Rust) 側のビルドが旧 library へリンクされていた問題（2026-08-24）

§4 の手順で `hailort` 5.4.0 をソースからビルドし `/usr/local/lib` へ導入した後も、`hailortcli` は正常に動作する一方、`yu_ai_manager` の `yu-infer`（sidecar、`yu-hailo-infer` crate）を経由した実機推論は**全経路**が次のエラーで即座に失敗し続けた。

```
[HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
[HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

`hailortcli` 自体は 5.4.0 で動くのに `yu-infer` だけ 5.3.0 を見ている、という食い違いが手がかりだった。

### 10.1 原因: ヘッダとリンク先ライブラリで探索順が違う

`yu-hailo-infer` の `build.rs` は次の順でヘッダを探す（コード引用、要旨）:

```rust
["/usr/local/include", "/usr/include"]
    .iter()
    .any(|d| Path::new(d).join("hailo/hailort.hpp").exists())
```

`/usr/local/include` を先に見るため、ソースビルドした 5.4.0 のヘッダが選ばれてコンパイルは通る。ところが実際にリンクする段は `println!("cargo:rustc-link-lib=hailort")` で `-lhailort` を発するだけで、`-L` によるサーチパス指定が一切無い。リンカの既定サーチパス（`gcc -print-search-dirs` の `libraries:` 行）には `/usr/local/lib` が含まれておらず、`/usr/lib`（apt の `hailort` 5.3.0 が入っている場所）だけが見える。結果、**ヘッダは 5.4.0・実際にリンクされる `.so` は 5.3.0** という不一致がコンパイルエラーなしに成立してしまう。

確認方法:

```bash
ldd crates/target/debug/yu-infer | grep hailort
# 修正前: libhailort.so.5.3.0 => /lib/libhailort.so.5.3.0
```

apt の `hailort`（`/usr/lib/libhailort.so` → `.so.5.3.0`）と、本ドキュメント §4 の手順でソースビルドした版（`/usr/local/lib/libhailort.so` → `.so.5.4.0`）が同一マシン上に共存する構成では、`-lhailort` の解決先は明示しない限り**未定義に近い**（ディストリのデフォルトサーチパス次第）。

### 10.2 対処: `crates/.cargo/config.toml` に `-L` を追加

`yu_ai_manager` リポジトリ側で恒久対処した（`yu-hailo-infer` の `build.rs` 自体は変更していない）:

```toml
# crates/.cargo/config.toml
[build]
rustflags = ["-L", "/usr/local/lib"]
```

`cargo clean -p yu-hailo-infer -p yu-hailo-infer-core` の後に再ビルドし、`ldd` で `libhailort.so.5.4.0 => /usr/local/lib/libhailort.so.5.4.0` になることを確認した。HailoRT ヘッダが存在しない環境（WSL2 の stub ビルド等）では `-lhailort` 自体が発行されないため、この設定は無害。

対応コミット: `9369e5f9e`（`yu_ai_manager` v4.661.1、CHANGELOG 参照）。

### 10.3 教訓

- **apt 版とソースビルド版の `libhailort.so` を同一マシンに共存させる場合、ヘッダの探索順とライブラリのリンク順は別物として扱うこと。** ビルドが通ることは版が揃っていることの証明にならない。
- **driver をアップグレードする度に、ヘッダだけでなく実際にリンクされたライブラリの版も再確認すること。** `hailortcli --version`（あるいは `hailortcli fw-control identify` の Firmware Version）が期待通りでも、別バイナリ（本件では `yu-infer`）が別の版にリンクされている可能性は否定できない。`ldd <バイナリ> | grep hailort` で都度確認するのが最も確実。
- 実行時のエラーメッセージ（`Driver version (X) is different from library version (Y)`）は driver とライブラリの不一致であって、ヘッダとライブラリの不一致ではない。後者は `ldd` でしか見えない。

---

## 付録 A. v5.3.0 への復旧手順

dkms から一度 `remove --all` した後の復旧は、apt キャッシュに `.deb` が残っていないと `apt-get install --reinstall` が失敗する（本件でも失敗した: `ダウンロードできないため、再インストールは不可能`）。dpkg は `hailort-pcie-driver` パッケージを `ii`（インストール済み）のまま認識しているため、パッケージのソース展開先 `/usr/src/hailort-pcie-driver/` が消えていなければ、そこから dkms ツリーを手動再構築できる:

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf はツリー直下に置く必要がある（linux/pcie/ 配下ではエラーになる）
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

復旧確認:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → 正常応答なら復旧完了
```

---

## 付録 B. 反証実験用ドライバーパッチの保存・適用・vanilla 復元手順

### B.1 保存物と位置付け

A/Bで実際に使用したドライバー差分を、次のファイルへそのまま保存した。

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- 基準ソース: `hailo-ai/hailort-drivers` tag `v5.4.0`、commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- 対象ファイル: `linux/vdma/ioctl.c`、`linux/vdma/memory.c`、`linux/vdma/vdma.c`

この patch は `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()` への置換だけでなく、§7.1 で使用した `CMA_DBG` 計装も含む。すなわち、A/B 時の実験モジュールを再現するための**検証用完全差分**であり、本番推奨 patch ではない。実験では効果が認められず、現在の実機は公式 vanilla 5.4.0 へ復元済みである。HailoRT ユーザー空間ライブラリには変更を加えていない。

同じカーネル・ソース・ビルド環境で確認した識別値は次のとおり。

| 状態 | `srcversion` |
|---|---|
| 実験patch | `C84A00ABB326748A1832CE1` |
| 公式vanilla 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 適用前の確認

以下はRaspberry Pi上の `/usr/src/hailo1x_pci-5.4.0` が上記公式commitを指し、対象3ファイルにローカル変更がない場合だけ実行する。commit、patch checksum、vanilla `memory.c` checksumのいずれかが一致しなければ停止し、patchを強制適用してはならない。

```bash
set -euo pipefail

REPO=/home/pi/GitHub/yu_ai_manager
SRC=/usr/src/hailo1x_pci-5.4.0
PATCH="$REPO/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch"
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_PATCH_SHA=7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
printf '%s  %s\n' "$EXPECTED_PATCH_SHA" "$PATCH" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" apply --check "$PATCH"
```

### B.3 実験 patch の適用

確認がすべて成功した場合に限り、patchを適用してDKMSモジュールを次回boot用にインストールする。ロード中のモジュールを `rmmod` / `modprobe` で手動交換せず、ビルド後に通常の再起動で切り替える。

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
PATCH=/home/pi/GitHub/yu_ai_manager/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch
KERNEL_VERSION="$(uname -r)"

sudo git -c safe.directory="$SRC" -C "$SRC" apply "$PATCH"
sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -n hailo1x_pci
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

`modinfo` は次回boot用にインストールされたモジュール、`/sys/module/.../srcversion` は現在ロード中のモジュールを示す。この時点で値が異なるのは正常である。準備ができた時点で再起動し、起動後に両者が一致することを確認する。

```bash
sudo reboot

# 再接続後
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

同じ検証環境では、patch適用後の期待値は `C84A00ABB326748A1832CE1` である。異なる場合は推測で試験を続けず、ソース差分、カーネル、DKMSビルドログを確認する。

### B.4 公式 vanilla 5.4.0 への復元

復元ではpatchの逆適用に依存せず、検証済みcommitから対象3ファイルを明示的に戻す。これにより、部分適用や計装だけが残る状態を避ける。

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c
KERNEL_VERSION="$(uname -r)"

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
sudo git -c safe.directory="$SRC" -C "$SRC" restore --source="$EXPECTED_HEAD" -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -

sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

同じ検証環境では、インストール済みvanillaモジュールの期待値は `A260C39C9F2C06DD4FB072E` である。現在ロード中の値が異なることを確認した上で再起動し、再接続後に両方が `A260C39C9F2C06DD4FB072E` となることを確認する。

---

## 参考: 関連ドキュメント

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — 旧測定に基づく CMA リークの実測データ・repro スクリプト・フォーラム投稿ドラフト（結論は本書 §8 で訂正済み）
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — v5.2.0 → v5.3.0 移行時の記録（デバイスノード名 `/dev/h1x-0` への変更等）
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — 旧診断に基づく CMA リーク問題の日本語記録（結論は本書 §8 で訂正済み）
- `hailo-ai/hailort-drivers` GitHub リポジトリ（GPL-2.0、ソース公開）: <https://github.com/hailo-ai/hailort-drivers>
