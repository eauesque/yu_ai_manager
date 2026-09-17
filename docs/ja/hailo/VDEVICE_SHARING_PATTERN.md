# パターン: 複数モデル Hailo-10H アプリケーション向け共有 VDevice マネージャー

Python アプリケーションで複数の Hailo モデル (YOLO / CLIP / LLM / VLM / Whisper など) を同じプロセス内の Hailo-10H NPU で動作させたい場合の実装パターン。

**対象読者**: Hailo-10H チップ上の単一アプリケーション内で複数モデルを共存させたい開発者。

---

## TL;DR

- Hailo-10H は **物理デバイスがちょうど 1 つ**。
- 同じプロセス内で `VDevice()` を 2 回作成するとこれで失敗します：
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- 一般的な原因：モデル交換時のレイジーリリース、バックグラウンドプリローダーの競合、内部で `VDevice` を構築して破棄する `is_available()` チェック。
- 解決策：**単一プロセス全体の `VDevice` シングルトン** を導入し、全モデルがオーナーキー付きレジストリを通じてアクセスします。
- `VDevice.create_params().group_id` を設定すると、同じ物理デバイスを **複数プロセス間でも共有** できます (HailoRT スケジューラが時間スライシングでアクセスを仲介)。

---

## 症状

```
[HailoRT] [error] Failed to create vdevice. there are not enough free devices. requested: 1, found: 0
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_OUT_OF_PHYSICAL_DEVICES(74)
hailo_platform.pyhailort.pyhailort.HailoRTStatusException: 74
```

スタックトレースは通常 YOLO、CLIP、または LLM の初期化を指していますが、本当の原因は **別のコンポーネント** が以前に `VDevice` を取得し、リリースしなかった場合です。

---

## 典型的な失敗シナリオ

### シナリオ 1: バックグラウンドプリローダーの競合

```
app startup
  └─ preloader thread
       ├─ CLIP init → VDevice() [A]
       └─ YOLO init → VDevice() [B]  ← [A] がデバイスを持ち続けている → 失敗
```

### シナリオ 2: 破壊的な `is_available()` チェック

```python
class YoloEngine:
    @staticmethod
    def is_available():
        try:
            vd = VDevice()   # チェックのために取得
            del vd            # 即座にリリースされない可能性 (GC タイミング)
            return True
        except Exception:
            return False

# 呼び出し元
if YoloEngine.is_available():     # ここで VDevice を取得して破棄
    engine = YoloEngine()          # 再度取得しようとする → 失敗する可能性
```

### シナリオ 3: モデル交換時のレイジーリリース

```python
# del だけでは VDevice はすぐにリリースされません
del self.vd                 # 参照カウントが下がる
self.vd = VDevice()         # 前の VDevice がまだ GC 待ちの可能性 → 失敗
```

修正は新しいものを作る前に `self.vd.release()` を明示的に呼ぶことです。

### シナリオ 4: 独立したモジュールが独立して初期化

複数の機能モジュール (エクステンション、プラグインなど) が各々ロード時に `VDevice()` を呼ぶと、ほぼ確実に衝突します。

---

## アンチパターン

```python
# ❌ module_yolo.py
from hailo_platform import VDevice

class YoloEngine:
    def __init__(self):
        self.vd = VDevice()    # 独立した取得
        self.model = self.vd.create_infer_model("yolov8n.hef")
        self.configured = self.model.configure()

    @staticmethod
    def is_available():
        try:
            VDevice()              # 破壊的なヘルスチェック
            return True
        except Exception:
            return False


# ❌ module_clip.py
class ClipEngine:
    def __init__(self):
        self.vd = VDevice()    # YoloEngine と衝突
        ...
```

---

## 推奨パターン: オーナーキー付き共有マネージャー

```python
"""device_manager.py — プロセス全体の Hailo VDevice オーナー。"""
import gc
import os
import threading
from typing import Callable, Dict, Optional, Tuple

_lock = threading.Lock()
_vdevice = None
_models: Dict[str, dict] = {}

# 他のプロセスとの物理デバイス共有に使用。
_GROUP_ID = os.environ.get("HAILO_VDEVICE_GROUP_ID", "MY_APP_SHARED")


def _ensure_vdevice():
    """単一の VDevice を遅延作成（呼び出し元は _lock を保持する必要があります）。"""
    global _vdevice
    if _vdevice is not None:
        return _vdevice
    from hailo_platform import VDevice
    params = VDevice.create_params()
    params.group_id = _GROUP_ID
    _vdevice = VDevice(params)
    return _vdevice


def acquire_infer_model(owner: str, hef_path: str) -> Tuple:
    """共有 VDevice 上で (InferModel, ConfiguredInferModel) を取得。

    同じオーナー + 同じ HEF は既存セッションを再利用。同じオーナーですが
    異なる HEF の場合は、古いものをリリースしてから新しいものを取得。
    """
    with _lock:
        existing = _models.get(owner)
        if existing and existing["hef"] == hef_path:
            return existing["infer_model"], existing["configured"]

        if existing:
            _release_internal(owner)

        vd = _ensure_vdevice()
        infer_model = vd.create_infer_model(hef_path)
        configured = infer_model.configure()

        _models[owner] = {
            "type": "infer",
            "infer_model": infer_model,
            "configured": configured,
            "hef": hef_path,
        }
        return infer_model, configured


def acquire_genai(
    owner: str,
    model_path: str,
    factory: Callable,
) -> object:
    """GenAI モデル (LLM / VLM / Speech2Text) を取得。

    `factory` は `(vdevice, model_path) -> 構築済み インスタンス`。
    例： `lambda vd, p: LLM(vd, p)`
    """
    with _lock:
        existing = _models.get(owner)
        if existing and existing["hef"] == model_path:
            return existing["instance"]

        if existing:
            _release_internal(owner)

        vd = _ensure_vdevice()
        instance = factory(vd, model_path)

        _models[owner] = {
            "type": "genai",
            "instance": instance,
            "hef": model_path,
        }
        return instance


def release(owner: str) -> bool:
    """`owner` が保持するモデルをリリース。VDevice 自体は生存させます。"""
    with _lock:
        return _release_internal(owner)


def _release_internal(owner: str) -> bool:
    entry = _models.pop(owner, None)
    if entry is None:
        return False
    if entry["type"] == "genai":
        try:
            entry["instance"].release()
        except Exception:
            pass
    # InferModel は Python の参照をドロップするだけです
    gc.collect()
    return True


def shutdown() -> None:
    """プロセス終了時に呼び出し：全モデルと VDevice をリリース。"""
    global _vdevice
    with _lock:
        for owner in list(_models.keys()):
            _release_internal(owner)
        if _vdevice is not None:
            try:
                _vdevice.release()
            except Exception:
                pass
            _vdevice = None
        gc.collect()


def is_hailo_available() -> bool:
    """非破壊的チェック — VDevice を構築しません。"""
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## 使用例

### YOLO (InferModel)

```python
from device_manager import acquire_infer_model, release, is_hailo_available
import numpy as np

class YoloEngine:
    def __init__(self, hef_path: str):
        self.infer_model, self.configured = acquire_infer_model("yolo", hef_path)
        self.input_shape = tuple(self.infer_model.inputs[0].shape)

    def detect(self, image_uint8: np.ndarray):
        bindings = self.configured.create_bindings()
        bindings.input().set_buffer(image_uint8)
        for out in self.infer_model.outputs:
            fmt = str(getattr(out.format, "type", "")).lower()
            dtype = np.float32 if "float" in fmt else np.uint8
            buf = np.zeros(tuple(out.shape), dtype=dtype)
            bindings.output(out.name).set_buffer(buf)
        self.configured.run([bindings], timeout=10000)
        return bindings

    def close(self):
        release("yolo")

    @staticmethod
    def is_available() -> bool:
        return is_hailo_available()   # VDevice に触りません
```

### LLM (GenAI)

```python
from hailo_platform.genai import LLM
from device_manager import acquire_genai, release

class MyLlm:
    def __init__(self, hef_path: str):
        self.llm = acquire_genai(
            "llm", hef_path,
            lambda vd, p: LLM(vd, p),
        )

    def generate(self, prompt: list, **kwargs) -> str:
        return self.llm.generate_all(prompt=prompt, **kwargs)

    def close(self):
        release("llm")
```

### YOLO + CLIP + LLM の共存

異なるオーナー名を使用することで、同じ VDevice 上で **2 つの InferModel と 1 つの GenAI モデルを同時にロード** することができます。内部の HailoRT スケジューラ (ROUND_ROBIN) がハードウェアアクセスを自動的に時間スライシングします：

```python
yolo = YoloEngine("yolov8n.hef")           # owner="yolo"
clip = ClipEncoder("clip_vit_b_16.hef")    # owner="clip"
llm = MyLlm("Qwen2.5-1.5B-Instruct.hef")   # owner="llm"

# 1 つの物理デバイス上で 3 つのモデルがアクティブ
bbox = yolo.detect(image)
embedding = clip.encode(image)
text = llm.generate([{"role": "user", "content": "..."}])
```

---

## 重要な設計ポイント

### 1. `is_available()` は破壊的であってはいけません

`VDevice` を構築して破棄する "ヘルスチェック" はこの種のバグの最も一般的な原因です。これをしてはいけません。

代わりに、インポートが動作することを確認します：

```python
def is_hailo_available() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False
```

単なる破棄目的で `VDevice` を構築せずハードウェアプレゼンスを確認したい場合は、ファイルシステムレベルで `/sys/class/hailo*` または `/dev/h1x-*` をチェックしてください。

### 2. オーナー名の名前空間設計

同じ HEF を共有すべきコンポーネントは **同じオーナー名** を使用します。複数のモジュールが全て同じ YOLOv8n を使用する場合、全て `"yolo"` オーナーで取得すると、自動的にセッションを共有します：

```python
# モジュール A
yolo_a = acquire_infer_model("yolo", "yolov8n.hef")

# モジュール B (同じ HEF)
yolo_b = acquire_infer_model("yolo", "yolov8n.hef")
# → 同じ infer_model / configured を返す、リロードなし
```

ユニークな HEF を持つコンポーネントはユニークなオーナー名を得ます：

| コンポーネント | オーナー | 備考 |
|---|---|---|
| 汎用 YOLO | `"yolo"` | 共有 |
| 汎用 CLIP | `"clip"` | 共有 |
| カスタムタガー (ユニーク HEF) | `"my-tagger"` | ユニーク |
| LLM | `"llm"` | GenAI |
| VLM | `"vlm"` | GenAI |
| Speech2Text | `"s2t"` | GenAI |

### 3. クロスプロセス共有に `group_id` を使用

`VDevice.create_params().group_id` を設定すると、**異なるプロセス** が同じ物理デバイスを共有できます：

```python
params = VDevice.create_params()
params.group_id = "MY_APP_SHARED"   # env 変数、設定などで統一
vd = VDevice(params)
```

同じ `group_id` で `VDevice(params)` を呼ぶ別のプロセスは、HailoRT スケジューラによってお互いの並列にリクエストが時間スライシングされます。これが `hailo-ollama` のような外部ツールが独自の推論プロセスと並列に動作する仕組みです。

### 4. シャットダウンフックは必須

プロセスがクラッシュすると、`VDevice` はリリースされず `/dev/h1x-0` はゾンビファイルディスクリプタによって保持され続けます。その後の起動は `/dev/h1x-0` を殺すまで `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` を得ます。シャットダウンフックをインストールしてください：

```python
import atexit
import signal
from device_manager import shutdown

atexit.register(shutdown)

def _signal_handler(signum, frame):
    shutdown()
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
```

問題が発生したときの回復：

```bash
# デバイスを保持するプロセスを見つける
lsof /dev/h1x-0        # hailort 5.3.0+
lsof /dev/hailort0     # hailort 5.2.0 以前

# 強制的に殺す
kill -9 <PID>
```

### 5. 同じ VDevice 上で InferModel と GenAI を混在

HailoRT 5.2.0 と 5.3.0 で検証済み：**複数の InferModel (例：YOLO + CLIP) と複数の GenAI モデル (LLM、VLM、Speech2Text) を同じ `VDevice` 上で同時に共存させることができます。**

注意点：

- `VDevice` を作成した後は、同じインスタンスに対して `create_infer_model()` と `LLM(vd, path)` の両方を呼び出すことができます。
- しかし、`VDevice` インスタンス自体は **同じ Python オブジェクト** である必要があります。同じ `group_id` で 2 番目の `VDevice()` を作成し、別の Python 変数からセッションを再利用しようとすると、`InferModel.run()` は失敗します。

### 6. 初期化失敗時のクールダウン

Hailo 初期化は高価です (~1 秒)。失敗直後の即座の再試行はしばしば更なる失敗をもたらします。短いクールダウン (例：60 秒) を導入して再試行ストームを抑制してください：

```python
import time
from typing import Optional

_init_failed_at: Optional[float] = None
_INIT_COOLDOWN_SEC = 60.0

def try_initialize():
    global _init_failed_at
    now = time.time()
    if _init_failed_at and (now - _init_failed_at) < _INIT_COOLDOWN_SEC:
        return None  # まだクールダウン中
    try:
        return acquire_infer_model("yolo", "yolov8n.hef")
    except Exception:
        _init_failed_at = now
        raise
```

---

## HailoRT 5.2.0 と 5.3.0 の両方で検証済み

このパターンは Raspberry Pi 5 + AI HAT 2 で以下の環境で検証されています：

- HailoRT 5.2.0 と 5.3.0
- 2× InferModel (YOLOv8n + CLIP ViT-B/16) + 1× GenAI LLM (Qwen2.5-1.5B) を同時に
- 2× InferModel + 1× GenAI VLM (Qwen2-VL-2B) を同時に
- 2× InferModel + 1× GenAI Speech2Text (Whisper-Base) を同時に

物理的制約 (プロセスごとに 1 つの物理デバイス) は 5.3.0 でも変わりません。`group_id` ベースの共有と内部 ROUND_ROBIN スケジューラは引き続きサポートされます。

---

## 関連

- HailoRT 5.2.0 → 5.3.0 マイグレーション注記 (`HAILORT_5_3_0_MIGRATION.md`)
- 5.3.0 の新しい `hailo1x_pci` ドライバ下では、デバイスノードが `/dev/hailort0` から `/dev/h1x-0` にリネームされました
