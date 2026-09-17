# トラブルシューティング

## よくある問題

### サーバーが起動しない

- Python 仮想環境が有効化されているか確認: `source venv/bin/activate`
- 依存パッケージがインストールされているか確認: `uv pip install -r requirements.txt`
- ポートが使用中でないか確認: `ss -tlnp | grep 5000`

### 画像が表示されない

- サムネイル API は画像ファイルの実体が必要です
- `files` テーブルのパスが実際のファイルパスと一致しているか確認
- スキャンルートのパスが正しいか確認

### LAN からアクセスできない

- Settings > Server で「LAN Access」が ON になっているか確認
- PIN 認証が設定されているか確認（LAN 公開時は必須）
- ファイアウォールで該当ポートが開放されているか確認
- サーバーの IP アドレスが正しいか確認

### MCP 接続エラー

- `YU_BASE_URL` が正しいか確認
- サーバーが起動しているか確認
- API キーが有効か確認
- LAN 経由の場合、HTTP/SSE エンドポイント (`/mcp`) が使用可能か確認

### スキャンが遅い

- `compute_hash` を OFF にすると高速化されます
- リモートパスの場合、Remote FS のタイムアウト設定を調整
- 大量のファイルがある場合、初回スキャンには時間がかかります

### サムネイル生成が遅い

- スキャン中はディスク I/O が飽和するため、サムネイル生成が遅くなります。スキャン完了後にプリウォームが自動実行されます
- **pyvips (オプション)**: 大きい JPEG 画像が多い場合、libvips の shrink-on-load で高速化されます
  - Linux: `sudo apt install libvips-dev && uv pip install pyvips`
  - macOS: `brew install vips && uv pip install pyvips`
  - Windows: [libvips リリースページ](https://github.com/libvips/libvips/releases)から DLL をダウンロードして PATH に追加後 `uv pip install pyvips`
  - インストールされていれば自動検出。なくても Pillow で動作します
- **Pillow-SIMD (オプション)**: ARM NEON / x86 AVX2 で画像リサイズを 2-4 倍高速化
  - `uv pip install pillow-simd` (Pillow と置き換わる drop-in replacement)
  - ARM NEON 最適化ビルド: `CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - wheel がない環境ではビルドツール (gcc 等) が必要です

## デバッグ

- Settings > Logs タブでサーバーログを確認
- MCP デバッグモード: `YU_DEBUG_MODE=1` で追加ツールが利用可能
- DB 整合性チェック: `python db_health.py`
