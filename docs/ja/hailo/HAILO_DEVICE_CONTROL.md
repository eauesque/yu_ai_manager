# Hailo-10H デバイス制御

## 概要

Hailo-10H NPU は **複数のモデルを同時に実行** できる。
内蔵の ROUND_ROBIN スケジューラが、ハードウェアアクセスをモデル間で自動的に時分割する。

yu_ai_manager では単一の共有 VDevice を保持し、CLIP・YOLO・LLM・VLM・Speech2Text が
同時にロード・推論可能。外部プロセス (hailo-ollama) との共有も `group_id` で対応する。

## アーキテクチャ

```
┌─────────────────────────────────────────────┐
│              Shared VDevice                  │
│         (group_id = YU_SHARED)               │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │  CLIP   │ │  YOLO   │ │  LLM (GenAI)  │  │
│  │InferMdl │ │InferMdl │ │  VLM / S2T    │  │
│  └─────────┘ └─────────┘ └───────────────┘  │
│                                              │
│     HailoRT ROUND_ROBIN Scheduler            │
└─────────────────────────────────────────────┘
```

- InferModel API (CLIP, YOLO) と GenAI API (LLM, VLM, S2T) は同一 VDevice 上で共存する
- 全モデルを **同一の VDevice インスタンス** に作成する必要がある（別インスタンスでは動作しない）

## 2 つのモード比較

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (OpenAI互換) |
|---|---|---|
| デバイス管理 | yu の device_manager | 外部 C++ サーバー |
| CLIP 検索と共存 | 可（同時動作） | 可（group_id 共有、v5.3.0+） |
| 推論速度 | 同じ | 同じ |
| オーバーヘッド | ~15ms | ~200-400ms (base64+HTTP) |
| 複数クライアント | 不可 | 可能 |
| Flask スレッド | 推論中ブロック | HTTP 待機のみ |

## VDevice 共有 (group_id)

### プロセス内共有

`device_manager.py` が自動で管理。全モデルが同一 VDevice を共有する。

環境変数で group_id を変更可能:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

デフォルト: `YU_SHARED`

### hailo-ollama との共存 (v5.3.0+)

hailo-ollama v5.3.0 以降は `HAILO_OLLAMA_VDEVICE_GROUP_ID` 環境変数をサポートする。
yu_ai_manager と同じ group_id を設定すると、両プロセスがデバイスを共有できる:

```bash
# yu_ai_manager 側
export HAILO_VDEVICE_GROUP_ID=SHARED

# hailo-ollama 側
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**注意**: yu_ai_manager は HailoRT 5.2.0 以降で group_id が機能する。
hailo-ollama は v5.3.0 以降でないと group_id を受け付けない。

## device_manager API

### モデル取得

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- 同一 owner + 同一 HEF → 既存セッション再利用
- 同一 owner + 別 HEF → 旧モデルを解放して新モデルを作成
- 別 owner → **共存**（旧モデルは解放されない）

### モデル解放

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # CLIP のみ解放、他は継続
shutdown_all()            # 全モデル + VDevice を解放（プロセス終了時）
```

### 状態確認

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## トラブルシューティング

### VDevice 作成エラー

**症状**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` や `Failed to create VDevice`

**原因**: 別のプロセスが異なる group_id でデバイスを占有している

**対処**:
1. hailo-ollama が稼働中か確認:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. group_id を合わせるか、停止する:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### デバイスが解放されない

**対処**:
1. yu のプロセスを再起動
2. ゾンビプロセスを確認:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Hailo ドライバをリセット:
   ```bash
   sudo systemctl restart hailort.service
   ```

## API 使い分けガイド

| モデル構造 | 推奨 API | 理由 |
|---|---|---|
| 単純 (1入力, YOLO 等) | `InferModel` | `create_infer_model()` + `configure()` で動作 |
| 複雑 (2入力+, Whisper 等) | `GenAI SDK` | InferModel は `INVALID_ARGUMENT` を返す |
| CLIP エンコーダ | `InferModel` | 1入力1出力で問題なし |
| LLM (qwen2.5 等) | `GenAI SDK` | 自己回帰デコードが必要 |

## 履歴

- **v4.61.0**: 共有 VDevice 方式に移行。排他 acquire/release を廃止し、CLIP + YOLO + LLM の同時動作に対応。
- **v4.60.1**: 全消費者を device_manager 経由に統一（排他方式）。
- **v4.60.0 以前**: 各消費者が個別に VDevice() を呼び出し、競合エラーが頻発。
