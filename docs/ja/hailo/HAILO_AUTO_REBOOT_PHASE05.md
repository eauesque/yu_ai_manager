# Hailo Auto-Reboot Phase 0.5 運用ガイド

**作成**: 2026-05-17 (v4.215.0)
**対象**: Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0 の CMA leak 観測運用
**ステータス**: 観測フェーズ。実 reboot は行わず、`would_fire` event を記録する。

---

## 1. Phase 0.5 の目的

Phase 0.5 は、HailoRT 5.3.0 + `hailo1x_pci` の CMA leak に対する自動 reboot 設計の観測フェーズです。

このフェーズでは判定器が以下の状態を計算します。

| 状態 | 条件 |
|---|---|
| `idle` | 通常状態 |
| `prewarn` | `CmaFree < 80 MB` が 180 秒継続 |
| `draining` | `CmaFree < 30 MB` が 60 秒継続、または `acquire_genai` の事前 reject が 3 回連続 |
| `would_fire` | `draining` から 120 秒経過 |

重要: Phase 0.5 では `would_fire` に到達しても Pi を再起動しません。`logs/hailo_auto_reboot.log` に JSON Lines で記録するだけです。

---

## 2. 既定値が `mode = "off"` の理由

`hailo.auto_reboot.mode` の既定値は `"off"` です。自動 reboot はユーザーの作業を中断し得るため、運用者が明示的に opt-in した環境だけで観測を開始します。

Phase 0.5 の推奨設定は以下です。

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` は Phase 0.5 の前提です。現実の reboot 経路は Phase 4 以降で扱います。

### 2.1 opt-in 手順

起動時 config は `--config` または `TAGDB_CONFIG` で指定したファイルを優先します。未指定の場合は、リポジトリ直下の `config.json`、次に `tagdb_config.json` を読みます。

例:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

`<repo>/config.json` または運用時に `--config` / `TAGDB_CONFIG` で指定している JSON に、次の設定を追加します。

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

サーバを再起動して設定を反映します。起動形態に合わせて、実際に使っている引数を維持してください。

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

systemd で運用している場合は、その unit を再起動します。

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 無効化手順

同じ config で `hailo.auto_reboot.mode` を `"off"` に戻し、サーバを再起動します。

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

`mode = "off"` では JSON Lines の観測 event は残りますが、`error.log` への WARN summary は出しません。

---

## 3. ログの読み方

観測ログは次のファイルに出ます。

```text
logs/hailo_auto_reboot.log
```

形式は JSON Lines です。主な event は以下です。

| event | 意味 |
|---|---|
| `boot_baseline` | 起動時の観測開始点 |
| `prewarn_entered` | PREWARN 条件が成立 |
| `drain_entered` | DRAIN 条件が成立 |
| `would_fire` | Phase 1+ なら reboot 発火候補になる時点 |
| `drain_cleared` | CMA が回復し DRAIN が解除 |

例:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

確認コマンド例:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

`would_fire` が頻発する場合は、現在の閾値では実運用中に Pi reboot が必要になる可能性が高いことを示します。逆に `prewarn_entered` だけで `drain_entered` へ進まない場合は、閾値または猶予時間を Phase 1 前に再調整できます。

---

## 4. API 確認手順

admin API key で `/api/system/cma` を確認します。

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

レスポンス内の `cma.auto_reboot.enabled`、`cma.auto_reboot.mode`、`cma.auto_reboot.state`、`cma.auto_reboot.consecutive_rejects` を見ます。

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. 観測期間

目安は 1〜2 週間です。最低限、次のパターンを含む期間を取ってください。

- LLM の通常チャット利用
- 長時間チャット利用
- Hailo GenAI model の load 失敗または事前 reject が起きる操作
- Pi reboot 後の初回 load

観測完了の目安は、1〜2 週間分の `prewarn_entered` / `drain_entered` / `would_fire` 発生頻度を集計できていることです。観測後は `would_fire` の回数、`drain_entered` の理由 (`cma` / `rejects`)、`CmaFree` の低下速度を見て、Phase 1 投入前に閾値を再確定します。

集計例:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. 関連資料

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
