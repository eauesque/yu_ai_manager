# Hailo Auto-Reboot Phase 0.5 — 当環境向け運用ランブック

**作成**: 2026-05-17 (v4.215.1)
**対象環境**: 本リポジトリ運用 Pi 5
**本書の目的**: 別セッションのチャットログが失われても、このランブックだけで Phase 0.5 観測を開始・確認・終結できる手順を残す。
**設計仕様**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**一般 operator guide**: `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (本書はそれの当環境固有版)

---

## 0. 前提と既に済んでいる作業

- v4.215.1 で Phase 0.5 観測実装が main にマージ・push 済 (commit `80af4fb73` + merge `69be148c6`)
- `config.json` (リポジトリ直下) に `hailo.auto_reboot` ブロックを **2026-05-17 時点で追加済**
  - 推奨設定: `mode = "lazy"` + `dry_run = true`
  - バックアップ: `config.json.bak.<タイムスタンプ>`
- **実 reboot は呼ばれない** (`dry_run = true` + Phase 0.5 設計で `would_fire` event を記録するのみ)

config.json 確認:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → {"mode":"lazy","dry_run":true,...} が出れば OK
```

---

## 1. 初回起動・有効化手順

### 1.1 サーバ再起動

config 変更を反映するため必ず再起動が必要。**現在の起動形態を維持して再起動**してください。

代表的な起動コマンド (実環境に合わせる):

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

systemd 化していれば該当 unit を `sudo systemctl restart <unit>` で再起動。

### 1.2 起動後 30 秒以内の確認 (3 点)

#### A. `boot_baseline` event が記録されているか

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

期待: `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}` が 1 行ある。

**出ない場合のトラブルシュート**:

- `logs/hailo_auto_reboot.log` 自体が無い → judge loop が起動していない (`build_background_tasks` の `["full"]` mode でない可能性、または `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` env が設定されている)
- ファイルはあるが空 → `core/hailo_device_core/auto_reboot_logger.py` の path 解決失敗。`logs/` ディレクトリの permission を確認
- `cma_free_mb: null` → `/proc/meminfo` 読込失敗 (Pi 以外で起動した場合の挙動、害なし)

#### B. `/api/system/cma` レスポンスで opt-in が効いているか

ブラウザで PIN ログイン中なら API key 不要。直接 curl で確認するか、ブラウザ DevTools のコンソールで PIN ログイン中に:

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

期待:

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

`enabled: false` または `mode: "off"` の場合 → config.json の `hailo.auto_reboot.mode` が `"lazy"` になっているか、サーバ再起動が完了しているか確認。

#### C. `error.log` に起動エラーが出ていないか

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

何も出なければ OK。エラーが出ていれば本書末尾「8. 既知の落とし穴」を参照。

---

## 2. 観測期間中の日常運用

### 2.1 普段通りの利用

**メインのアクション**:

- `/ext/hailo-genai/chat` または `/tools` 経由で **LLM チャットを普段通り使う** (Qwen3-1.7B 等)
- 必要なら VLM / S2T も使う
- 長時間チャット (30 分以上連続) や複数モデル切替も意図的に試すと、観測データの幅が広がる

特殊な検証は不要。**普通に使うほどデータが集まる**のが Phase 0.5 の設計。

### 2.2 週次レビュー (週 1 回、5 分)

```bash
cd /home/pi/GitHub/yu_ai_manager

# event 種別の発生回数
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# would_fire の発生時刻と CmaFree
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# drain_entered の reason (cma / rejects のどちらで入ったか)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**チェックポイント**:

- `would_fire` が 1 件以上出ている → Phase 1 移行のメリットあり (記録された時刻に Pi reboot が必要だった = 手動 reboot していたタイミングと一致するか確認)
- `prewarn_entered` が頻発するが `drain_entered` に進まない → `prewarn_threshold_mb` (80 MB) が低すぎる可能性、要再確定
- `drain_entered` の reason が `rejects` ばかり → reject 起因の DRAIN なので閾値再確定とは別の対策が必要

---

## 3. 観測終了・Phase 1 投入判断基準

### 3.1 必要な観測期間

**最低 7 日 / 推奨 14 日**。少なくとも以下のパターンを含む期間を取る:

- LLM 通常チャット
- LLM 長時間連続チャット (30 分以上 1 セッション)
- VLM / S2T 切替
- `acquire_genai` 事前 reject (CmaFree 不足) が少なくとも 1 回発生する操作
- Pi reboot 後の初回 load

### 3.2 Phase 1 投入の数値基準

集計:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

判断:

| 観測結果 | Phase 1 判断 |
|---|---|
| `would_fire` ≥ 1 件 | **GO** (実 reboot 自動化に価値あり) |
| `would_fire` = 0、`drain_entered` ≥ 1 件 | 閾値再調整して Phase 1 投入を検討 (DRAIN まで来るが would_fire に届かない = `fire_grace_seconds` 短縮の余地) |
| `prewarn_entered` のみ、`drain_entered` = 0 | 現状の閾値だと一度も「重症」にならない → 利用パターン次第で Phase 1 移行不要 |
| 全 event 0 (`boot_baseline` のみ) | CMA 枯渇しない使い方 → Phase 1 不要 |

### 3.3 観測完了後の作業

1. 集計結果を `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (新規) に保存
2. Phase 1 投入の場合: spec rev3 §5.2 の Phase 1 (UI DRAIN バナー + i18n) に進む。本仕様 §3.1 閾値を観測ベースで再確定
3. Phase 1 不要の場合: `config.json` で `mode = "off"` に戻し、観測ログをアーカイブ

---

## 4. 無効化手順 (緊急時 / 観測停止時)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# サーバ再起動
```

`mode = "off"` でも JSONL event は記録される (`error.log` への WARN は抑制)。完全に止めるには env で:

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. ログファイル一覧 (関連)

| ファイル | 用途 |
|---|---|
| `logs/hailo_auto_reboot.log` | **本機能の主ログ**。JSONL、10 MB × 30 backups で rotation |
| `logs/hailo_cma.log` | 既存の CMA event logger (v4.214.10〜)。`acquire_genai` 等の VDevice/モデル lifecycle event |
| `logs/error.log` | アプリ全体のエラー。`mode != "off"` のとき `drain_entered` / `would_fire` の WARN サマリも出る |

---

## 6. 関連コードの場所 (将来の調査用)

| 機能 | ファイル |
|---|---|
| state machine + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| Background loop entry | `core/web/startup_background_hailo_judge.py` |
| Background task 登録 | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Config defaults | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| acquire_genai hook | `core/hailo_device_core/device_manager_genai.py` |
| `/api/system/cma` 拡張 | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| 単体テスト | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. レビュー履歴 (参照用)

本実装は AGENTS 規定のフルフローを通過済 (v4.215.1 commit message 参照)。各レポートファイルは `.claude/agent-outputs/` 配下に書き出されたが、これらは `.gitignore` 対象で git 管理外。必要時は再生成可能。

---

## 8. 既知の落とし穴

| 症状 | 原因と対処 |
|---|---|
| `logs/hailo_auto_reboot.log` に何も出ない | サーバ未再起動 / `mode = "off"` のまま / `["full"]` mode で起動していない / `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` env が立っている |
| `cma_free_mb: null` 続き | Pi 以外 (WSL2 等) で起動した、または `/proc/meminfo` 読込失敗。Pi 実機で再確認 |
| `hailo_runtime_version: null` | `hailo_platform` パッケージが未インストール環境。実 Pi 5 では HailoRT 5.3.0 ランタイムがあれば取得される |
| `would_fire` が一切出ない | 利用負荷が軽すぎる、または閾値が緩い。長時間連続チャット / モデル切替を試して再観測 |
| `eager` mode を設定したのに動かない | Phase 0.5 では `eager` は意図的に `off` fallback (warning ログ出力)。Phase 1+ で実装予定 |

---

## 9. 緊急ロールバック

万一 Phase 0.5 実装自体に問題が出た場合 (実 reboot は呼ばれないため可能性は低いが):

```bash
cd /home/pi/GitHub/yu_ai_manager
# v4.215.1 → v4.214.13 (spec のみ、実装前) にロールバック
git revert -m 1 69be148c6
git push
```

または **設定だけで完全無効化** (推奨):

```bash
# 起動 env に追加してサーバ再起動
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. 本書のメンテナンス

- 観測完了時に **§3.3 集計結果を本書末尾に追記** すること (将来のチャットセッションで Phase 1 判断時に必要)
- Phase 1 投入後は本書を `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` にリネームし、Phase 1 用ランブックを新規作成
- 本書は `/home/pi/GitHub/yu_ai_manager/docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` に置く (git 管理下)
