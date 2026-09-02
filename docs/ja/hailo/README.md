# Hailo-10H AI Hat+ 開発資料

Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H) を使った AI 推論の実装記録。

公式ドキュメントが不十分な領域について、実際の開発で得た知見を公開しています。

## ドキュメント一覧

| ファイル | 内容 |
|---------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | HailoRT 5.2.0 → 5.3.0 移行ノート。API 差分・デバイスノードリネーム (`/dev/h1x-0`)・HEF 互換性・スモークテストスクリプト |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | 複数モデル (YOLO/CLIP/LLM/VLM/Whisper) を同一プロセスで共存させるための共有 VDevice マネージャの実装パターン |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Pi 5 の CMA 割り当て制限 (`numa=fake=8` 下での動作)。なぜ `cma=1G` は静かに失敗するのか、確認済みの上限かつ推奨値である `cma-512` (`config.txt` の `dtoverlay=cma,cma-512`)、Hailo GenAI のメモリ要件、`VDevice.release()` の CMA 非返却動作 |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | CLIP セマンティック検索の開発ログ。Phase ごとの実装記録、遭遇した問題と解決策 |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Hailo デバイスの制御方法、VDevice 管理、排他制御、モデル切替 |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | ONNX → HEF 変換手順。Dataflow Compiler、量子化、トラブルシューティング |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | 変換検証レポート (DFC v5.2.0)。WD-Tagger 3 モデルの失敗詳細分析 |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | DFC v5.3.0 続報。同じ WD-Tagger 3 モデルを再検証 (依然失敗)、加えて v5.3.0 で確認できた改善点 (新 `_create_layer_normalization_layer`・onnxsim 再試行フロー・end-node 推薦) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | CLIP ONNX マルチバックエンド開発ログ。Hailo ハードウェアなし環境向けフォールバック |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **CMA leak の構造的制約と実測**。`VDevice.release()` が回収しないこと、推論中の継続 leak (約 14 MB/分)、そして **子プロセス kill でも process exit でも module unload でも回収されない**こと (Phase 0 PoC で 2 回独立に実測、SIGTERM + 30 秒待機で +8 MB のみ)。確実な回収手段は Pi 本体の reboot のみ **(旧結論。HailoRT / driver 5.4.0 での再試験により [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 で訂正済み)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **上記 CMA leak 判定の訂正と再検証**。HailoRT / driver 5.4.0 で公式 vanilla と `FOLL_LONGTERM` 修正版を A/B 比較し、旧判定が初回 HEF ロード後の `CmaFree` 絶対回復量だけを見た誤判定であったと訂正。v5.3.0 → v5.4.0 のソース差分、自前ビルド手順の罠、実測データ付き。**§10**: apt 版と自前ビルド版の `libhailort.so` が共存する環境で `yu_ai_manager`（Rust）の `-lhailort` が旧 5.3.0 側へ静かにリンクされ、実機推論が全滅していた問題と `-L` による恒久対処 |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | 上記を受けて採用された自動 reboot 路線の運用ガイド。観測フェーズ (`would_fire` を記録するのみで再起動しない)、判定閾値、既定 `mode = "off"` の理由 |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | 同フェーズの当環境向けランブック。観測の開始・確認・終結手順 |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | cold_load (~71 秒) 中に Quart event loop が GIL で固まる問題を、LLM chat 推論の subprocess 隔離で解消した実装ログ |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Hailo-10H エコシステム評価 (2026-03-19、HailoRT/DFC v5.2.0 時点) |

## 重要な既知事項

### 環境 / Raspberry Pi 5

- **Pi 5 (8 GB) での CMA 上限は 512 MB、設定箇所は `config.txt`**: デフォルトカーネルが `numa=fake=8` を適用し、RAM を 8 × 1 GB の NUMA ノードに分割。CMA は単一ノード境界内に収まる必要があり、`cma-1024` と `cma-768` は静かに失敗する (`CmaTotal=0` でカーネルパニックなし)。**`cma-512` が確認済みの上限かつ推奨値** (2026-05-16 に overlay 経由で再検証、`CmaTotal: 524288 kB`)。2026-05 の firmware リグレッションにより、cmdline `cma=` ではなく `/boot/firmware/config.txt` の `dtoverlay=cma,cma-512` を用いること。詳細は [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) 参照
- **リブート後は必ず CMA を検証**: `grep CmaTotal /proc/meminfo` で確認。0 の場合は設定が無視された状態
- **`VDevice.release()` は CMA を返却しない**: CMA は OS セッション全体で保持される。VDevice はセッションスコープのシングルトンとして扱うこと。**プロセス再起動でも回収されない** —— 子プロセス kill・process exit・module unload のいずれでも回収されないことが Phase 0 PoC で 2 回独立に実測されている (SIGTERM + 30 秒待機で +8 MB のみ、期待値 ≥250 MB)。確実な回収手段は Pi 本体の `sudo reboot` (PCIe power-cycle) のみ。詳細と採用された対処は [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) 参照。**訂正**: 本項は旧測定に基づく。HailoRT / driver 5.4.0 での A/B 再試験では実用上の CMA リークは再現せず、[HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 で訂正済み
- **`numa=fake=8` は Node.js インストール影響**: NUMA ノード単位のメモリ (1 GB) を総 RAM と誤認識され、npm/node インストーラが中止。上流で報告済み: [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python wheel はソースビルド**: PyPI にも Hailo Developer Zone にも aarch64 wheel がない
- **hailo-ollama との排他**: VDevice 使用中は hailo-ollama を停止する必要がある
- **プロセス終了時の VDevice リーク**: `lsof /dev/hailo*` で確認し `kill PID` で対処
- **長時間の連続実機セッションはサーマルスロットリングを疑うこと**: cargo ビルド＋複数回の実機推論試験を連続実行すると CPU 温度が 80°C 台まで上昇し、`vcgencmd get_throttled` が現行スロットリング中（ビット3 `0x8`）を報告する状態になる。この状態では GenAI 生成が数秒で終わるはずの処理が 90 秒のタイムアウト上限まで張り付いて空応答になるなど、著しい遅延として現れる（2026-08-24 実測: 82.9°C で発生、約10分の冷却で 73.6°C まで下がると 9.76 秒に復帰）。生成の極端な遅延・タイムアウトに遭遇したら、コードの瑕を疑う前に `vcgencmd measure_temp` と `vcgencmd get_throttled` で温度状態を確認すること。詳細は `yu_ai_manager` CHANGELOG `[4.661.2]` 参照

### VDevice / API

- **InferModel API を使うこと**: `VDevice.create_infer_model()` が正しい。旧 VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`) は Hailo-10H で `HAILO_NOT_IMPLEMENTED`
- **InferModel は単純なモデルのみ対応**: 1入力の YOLO HEF は動作するが、2入力4出力の Whisper HEF では `configure()` が `HAILO_INVALID_ARGUMENT` を返す。複雑なモデルには GenAI SDK を使用
- **VDevice は物理デバイス 1 つにマップ**: `VDevice()` インスタンスを 2 つ同時に作成すると `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **モデル切替時は VDevice を完全解放**: Python 参照を `None` に設定するだけでは不十分。`VDevice.release()` で物理デバイスを明示的に解放してから新しい VDevice を作成
- **`set_format_type(FormatType.FLOAT32)` は hailort 5.2.0 で非対応**: `format_type` 属性が存在しない。手動で uint8 量子化/逆量子化するか、GenAI SDK を使用
- **出力は uint8 量子化**: float32 で出力バッファを確保すると `buffer size mismatch`。uint8 で確保し、脱量子化パラメータ (scale, zero_point) で float32 に変換

### GenAI (LLM / VLM / Speech2Text)

- **HailoRT 5.3.0 では `temperature=0.0` が拒否される**: `LLM.generate()` が `temperature=0` で `HAILO_INVALID_ARGUMENT` を発生させる。呼び出し前にクランプ: `temperature = max(temperature, 0.01)`。OpenAI 互換クライアントがデフォルトで `temperature=0` を送信する場合に影響
- **GenAI × 2 の同時読み込みが可能**: LLM + Whisper-tiny は同一 VDevice 上に同時読み込み可能 (HailoRT 5.3.0 で確認)。両者を読み込んだ時の CMA 余裕: 256 MB 中約 10 MB。Whisper-base 以上はメモリ溢れの可能性高い
- **LLM + Whisper-tiny CMA 予算**: 合計約 246 MB (測定値)。全モデルの CMA 数値は [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) 参照
- **Speech2Text の segment 単位タイムスタンプは `generate_all_segments()` を使うこと**: `generate_all_text()` は平坦な1文字列しか返さず、区間の開始/終了時刻が失われる。`Speech2Text::SegmentInfo{start_sec, end_sec, text}` の配列を返す `generate_all_segments()`（同一クラスのオーバーロード）を使えば区間情報を保てる（`yu-hailo-infer` v0.4.0 相当、2026-08-24 実機検証）

### Whisper (音声認識)

- **GenAI SDK を使うこと**: `hailo_platform.genai.Speech2Text` がフルパイプラインを提供。エンコーダ+デコーダを NPU 上で完全実行
- **HEF はデコーダのみ**: `Whisper-Base.hef` は 2 入力 (encoder_features + token_embeddings) と 4 出力 (vocab を 4 分割)。InferModel API では動作しない
- **GenAI SDK の入力**: little-endian float32 (`<f4`)、[-1,1] 正規化の PCM 音声データ
- **ONNX フォールバック**: GenAI SDK が使えない場合は HuggingFace の ONNX モデルでエンコーダ+デコーダを CPU 実行

### YOLO (物体検出)

- **InferModel API で動作**: 1入力の HEF は問題なし
- **ONNX フォールバック**: Hailo が使えない場合は `yolo11n.onnx` を自動ダウンロード。出力 `(1,84,8400)` は yolov8n と互換
- **初期化失敗クールダウン**: エンジン初期化失敗後 60 秒間リトライしない

### 分散推論

- **ヘルスチェック必須**: `filter_available()` でリモートノードの生死を確認してから分散開始
- **リモート障害時**: 残りアイテムをローカルにフォールバック。復帰時は次バッチで自動検出
- **ワークロード配分**: GPU vs NPU の速度差が大きく、均等分割では効率が悪い。スループット計測ベースの動的配分が今後の課題
