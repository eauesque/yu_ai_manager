# HailoRT 5.3.0 の CMA leak — 確定診断と運用上の制約

> **訂正注記**: 本書は旧測定に基づく CMA リーク診断の記録であり、`release()` 後も CMA が回収されない、推論中に約14 MB/分で継続的に漏れる、Pi 本体再起動だけが確実な回復手段である、という旧結論は撤回されている。HailoRT/driver 5.4.0 の再試験による最終判定は [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 で訂正済み。本書の旧結論を現行の実用判定として参照しないこと。

**作成**: 2026-05-17 (v4.214.11 にて発見・記録)
**影響範囲**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (`hailo_platform.genai` 利用経路)
**症状**: 一度 LLM をロードすると、`VDevice.release()` / `LLM.release()` を呼んでも CMA がほぼ回収されない。加えてインファレンス中も継続的に CMA が漏れる。Pi 本体再起動以外に回復手段がない。
**ステータス**: ドライバ側の構造的制約として確認済。回避策の検討中。

---

## 1. 確定診断の根拠

`v4.214.10` で導入した CMA イベントロガー (`logs/hailo_cma.log`、`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`) で、2026-05-17 に以下のシーケンスを実測した。

### 1-1. 観測ログ (raw)

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 分間チャット利用 (5〜10 メッセージ程度のインファレンス)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. 解釈

| フェーズ | CmaFree 差分 | 意味 |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB (≈ 0)** | VDevice 作成自体は CMA をほぼ消費しない |
| `acquire_pre` → `acquire_post` (Qwen3-1.7B-Instruct ロード) | **−285 MB** | LLM 1 個で 285 MB 消費 |
| `acquire_post` → `release_pre` (6 分間のインファレンス) | **−84 MB / 6 min ≒ −14 MB/min** | **インファレンス中も連続リーク** |
| `release_pre` → `release_post` (LLM unload) | **+1 MB** | **`release()` で事実上 CMA が戻らない** |

### 1-3. 旧仮説との比較

これは 2026-05-16 に作成した `SQLCIPHER_MMAP_CORRUPTION.md` §7 + 旧ドキュメントの初期仮説「VDevice の保持戦略 (我々の `_maybe_reset_vdevice` が空) が leak を増幅している」を一部否定する観測結果。VDevice 作成 0 MB / release 0 MB なので、**保持戦略を変えても (= `_maybe_reset_vdevice` を毎回 reset するように変えても) 効果はない**。

---

## 2. 構造的制約

実測結果から、HailoRT 5.3.0 (community build, `hailo_platform.genai` API) には次の 3 つの問題が同居する:

1. **`VDevice.release()` / GenAI モデルの `release()` が host CMA を回収しない** (実測確認済)
   - 単一プロセス内では PCIe driver (`hailo1x_pci`) が DMA 領域を保持し続け、`munmap` 相当の動作が起きない
2. **インファレンス中の継続的 CMA leak (約 14 MB/分)** (実測確認済)
   - 本日観測では Qwen3-1.7B-Instruct 利用中に 6 分で 84 MB を失った
   - load/unload とは独立した別経路。アンロードしなくても枯渇する
3. **Pi 本体の reboot 以外で CMA を確実に回収する方法が確認されていない** (実測 + community 報告)
   - `systemctl restart yu-ai-manager` 相当のサーバプロセス再起動でも、`hailo1x_pci` が PCIe power-cycle まで DMA を保持するため不完全。完全回復には Pi 本体の `sudo reboot` が必要 (本リポジトリでの実測)
   - Hailo community でも複数の独立報告がある: <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> および <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (`VDevice.release()` / process exit / driver reload で戻らず、host reboot のみ回復、と明記)
   - これは `acquire_genai` の事前 reject エラーメッセージ (`core/hailo_device_core/device_manager_genai.py::acquire_genai`) にもユーザー向けに記載済 ("a full system reboot is required")

### 2-1. 「子プロセス kill で CMA が戻るか」: **実測で反証** (2026-05-17 Phase 0 PoC)

旧版 (rev1) では「Linux kernel が `mm_struct` teardown 時に DMA pages を回収するため、子プロセス kill で CMA が完全回収される」と理論的に断定していたが、Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`) で**実測した結果、子プロセス kill では CMA はほぼ回収されないことを 2 回独立に確認**した。

**測定結果 (2 回目、厳密版)**:

| 測定点 | CmaFree | Δ |
|---|---:|---:|
| baseline (PoC 開始前) | 503 MB | — |
| VDevice 作成後 | 372 MB | **-131 MB** (cold-spawn 子プロセスでは VDevice 構築で消費) |
| LLM ロード後 | 372 MB | 0 MB (LLM は VDevice の DMA pool 内で完結、新規消費なし) |
| SIGTERM 送信 + join 後 | 378 MB | +6 MB |
| **30 秒待機後** | **380 MB** | **累計 +8 MB のみ回収** |

期待値 ≥ 250 MB の回収に対し実測値はわずか +8 MB (1 回目の偶発測定では +1 MB)。これは system jitter レベルで、**有意な CMA 回収は発生していない**。

**確定診断**:

- `hailo1x_pci` ドライバは DMA pool を user process の `mm_struct` ではなく **driver 内 global state** で管理している (推定)
- `process exit` でも `kill` でも `module unload` でも回収されない (community 報告と整合)
- **唯一の確実な回収手段は Pi 本体の `sudo reboot` (= PCIe power-cycle)** ← §2 row 3 で記載した実測事実が正

詳細レポート: `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

この結果により `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` は **REJECTED** にマークされ、subprocess 隔離による緩和路線は廃止。代替策として §4 (D) の自動 reboot 路線が採用される。

---

## 3. 運用上の含意

### 3-1. 「1 モデル / Pi reboot」が事実上の上限

- Pi 5 (CMA 512 MB 上限、Pi 仕様で増やせない) + Qwen3 系 LLM (285 MB) の組み合わせでは:
    - reboot 直後 CmaFree ≒ 480 MB
    - LLM 1 個 load → CmaFree ≒ 190 MB
    - 数十分のインファレンス → CmaFree ≒ 50 MB 以下
    - **2 個目のモデル load は永久に不可能** (250+ MB 必要に対し残量不足、release しても戻らない)

### 3-2. LLM + VLM / LLM + S2T の同時使用は不可

- VLM (llava 系、~300 MB)、S2T (whisper-small、~175 MB) を LLM と切り替えで使うユースケースは、上記制約により **load → reboot → load** の手順を取らない限り実現不能。
- 「会話中に画像を添付して別モデルに切り替える」「会話の音声を文字起こしする」等の **マルチモデル UX は HailoRT 5.3.0 では設計上成立しない**。

### 3-3. インファレンスの長時間連続利用が困難

- 14 MB/分の leak は、CmaFree が 200 MB 時点でも 14 分で half、30 分でほぼ枯渇。
- 30 分以上のチャットセッションは Pi 再起動を挟まないと安定しない。

---

## 4. 取り得る対策

優先度・工数つきで列挙:

| 案 | 効果 | 工数 | 副作用・リスク |
|---|---|---|---|
| ~~(A) Hailo 操作を subprocess に隔離、定期 kill で kernel に CMA を返させる~~ | ❌ **REJECTED** (Phase 0 PoC で反証、2 回再現)。kill 後の回収量は累計 +8 MB のみで仮説不成立 | — | 採用しない |
| **(B) `_CMA_ESTIMATES_MB` を実測値 + マージンに更新** | 事前 reject の精度向上 (false-positive load 試行を減らす) | ✅ 即適用可、1 行 | 既存ユーザーで 250 MB 想定でギリギリ動いていたケースが reject されるが、それは元々失敗していた | 
| **(C) `CmaFree < 80 MB` で UI バナー / `< 30 MB` で error.log に WARN** | 利用者が状況把握できる、Pi 再起動を促せる | 中 | 警告疲労 / 過剰通知のリスク |
| **(D) `CmaFree < 30 MB` を検知し supervisor に SIGTERM** | 自動復旧 (ただし Pi 全体再起動が必要なので `systemctl reboot` 経由) | 中 | supervisor 権限の付与が必要 / 他作業中のセッション切れ |
| **(E) HailoRT 修正待ち + 制約のドキュメント明記** | コスト 0 | 0 | Hailo の release サイクル次第 (数ヶ月〜) |
| **(F) Hailo の issue tracker / forum に修正要請を投げる** | 修正タイミングが早まる可能性 | 小 | 反応速度はサポート契約と community 状況に依存 |

短期方針 (v4.214.11 で実施): **(B) 適用 + 本ドキュメント (E と (F) の出発点)**。
中期方針 (別 spec): **(C) UI 警告 → (D) 自動 reboot** の順。

> **2026-08-08 訂正**: 先行する記述は中期方針を「(C) UI 警告 → (A) subprocess 隔離」と
> していたが、**(A) は同じ表で REJECTED になっている**。Phase 0 PoC (§2-1) より前に
> 書かれた行が残っていたもの。実際に採用されたのは (D) で、
> [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) として Phase 0.5 まで
> 実装済み (v4.215.0、観測フェーズ、既定 `mode="off"`)。
>
> この 1 行が残っていたために、2026-08-08 のセッションで「プロセスを作り直せば CMA が
> 戻る」型の設計が再度書かれた。却下済みの案を指す行は消すか、却下と明記すること。

長期: HailoRT の release を監視し、修正されたら本ドキュメントを更新して制約を外す。

---

## 5. 関連ドキュメント / コード

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — 事前 CmaFree チェック + ユーザー向けエラーメッセージで本制約を明示済
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — モデル別 CMA 必要量見積もり (v4.214.11 で qwen を 250 → 300 に bump)
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — v4.214.10 で導入した計測 instrumentation。本ドキュメントの実測データもここから
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — 「VDevice を process lifetime 保持」する設計 (空関数)。本実測結果により、これを reset するように変更しても CMA 回収には寄与しないことが確定
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Phase 0.5 観測フェーズの operator guide。`mode=lazy` + `dry_run=true` で `would_fire` ログのみを収集する手順
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Pi5 全体の CMA 上限と各 driver (camera / KMS / Hailo / HEVC) の baseline 消費量
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — HailoRT 5.3.0 へ移行した経緯と既知差分

---

## 6. 再現手順 (Hailo issue 報告用)

外部に bug 報告する場合の最小再現手順:

```bash
# 1. Pi reboot 直後の baseline 確認
grep CmaFree /proc/meminfo
# CmaFree: 480000 kB 前後

# 2. サーバ起動 + 1 個目の LLM ロード (例: /tools の GenAI で 1 通送信)
# /api/llm/generate もしくは /api/chat/send を 1 リクエスト

# 3. CmaFree 確認
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. モデルアンロード
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. CmaFree 確認
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (戻らない ← bug)

# 6. 同じモデル / 別モデルの再ロード試行 → insufficient CMA で reject
```

期待される動作: 手順 5 で CmaFree が手順 1 のベースラインに近い値 (>400 MB) まで戻ること。
実際の動作: +1 MB 程度しか戻らず、再ロード不能。
