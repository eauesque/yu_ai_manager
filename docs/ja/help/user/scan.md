# スキャン

## スキャンフォルダの登録

Settings > Scan タブでスキャン対象フォルダを追加します。

- ドラッグ＆ドロップで並び替え可能
- チェックボックスで有効/無効を切り替え
- 複数フォルダを登録可能

## スキャンの実行

- フォルダ追加後に自動でスキャン開始
- 手動スキャンは Tools ページまたは MCP の `trigger_scan` で実行
- スキャン中の進捗は SSE でリアルタイム通知

## 自動スキャン（Watcher）

Auto Scan Watcher 拡張機能を有効にすると、登録フォルダ内のファイル変更を自動検出してスキャンします。

## リモートファイルシステム

WSL / NAS / SMB などのリモートパスをスキャンする場合、Settings > Remote FS タブでタイムアウト設定を調整してください。

## 大規模ライブラリでのスキャン

数十万〜100万件以上のファイルをスキャンする場合の注意点:

- **スキャン中も画像検索は可能**: 検索 API は読み取り専用 DB 接続を使用するため、スキャン中の書き込みロックの影響を受けません
- **WAL 自動管理**: スキャン中は 2000 ファイルごとに WAL チェックポイントを自動実行し、WAL ファイルの肥大化を防ぎます
- **scan.db_busy イベント**: スキャン開始/完了時に SSE イベントが送信されるため、フロントエンドでビジー状態を表示できます

## スキャンワーカープロセス

v3.27.0 以降、スキャンは web_ui.py とは独立した別プロセスで実行されます。
これにより **web_ui を再起動してもスキャンが中断されません**。

### 動作の仕組み

- WebUI からスキャンを開始すると、バックグラウンドでワーカープロセスが起動します
- ワーカーは `/tmp/yu-scan/` に進捗ファイル (JSON) と PID ファイルを書き出します
- WebUI はこの進捗ファイルをポーリングして SSE でフロントエンドに中継します
- WebUI を再起動すると、実行中のワーカーを自動検出して進捗表示を再接続します

### CLI から操作する

ワーカーは CLI からも直接操作できます。WebUI が停止中でも使用可能です。

```bash
# 状態確認
python -m core.scan.scan_worker status

# 実行中のスキャンを停止 (graceful shutdown — DB に中断位置を保存)
python -m core.scan.scan_worker stop

# CLI から直接スキャンを開始
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# オプション
#   --recursive / --no-recursive  サブディレクトリを含むか (デフォルト: recursive)
#   --scan-zips                   ZIP/7z 内の画像もスキャンする
#   --force                       既存ファイルも再スキャンする
#   --resume                      中断したスキャンを再開する
#   --config config.json          設定ファイルを指定
```

### 安全機構

- **親プロセス監視**: WebUI から起動されたワーカーは、WebUI プロセスの生存を 60 秒間隔で監視します。WebUI が異常終了した場合、ワーカーは自動的に中断保存して停止します
- **SIGTERM 対応**: `stop` コマンドや `kill` で SIGTERM を送ると、現在の処理を完了してから DB にコミットし、中断位置を保存して終了します
- **重複防止**: 同時に複数のワーカーが起動することはありません

### トラブルシューティング

ワーカーが応答しない場合:

```bash
# PID を確認
cat /tmp/yu-scan/worker.pid

# プロセスを強制終了
kill -9 $(cat /tmp/yu-scan/worker.pid)

# 残留ファイルをクリーンアップ
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## スキャンエラー

スキャン中にエラーが発生した場合、MCP の `get_scan_errors` で確認できます。
