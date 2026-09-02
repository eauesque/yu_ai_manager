# 設定

## サーバー設定

| 項目 | 説明 |
|------|------|
| Host | バインドアドレス（LAN OFF 時は 127.0.0.1 固定） |
| Port | Web サーバーポート番号 |
| LAN Access | ON で LAN 内の他デバイスからアクセス可能 |
| PIN Auth | アクセス時に PIN 入力を要求 |
| Boss Mode | 新聞風の PIN ログイン画面 |

## スキャン設定

登録フォルダの追加・削除・並び替え・有効/無効切り替え。

## パーサー設定

| 項目 | 説明 |
|------|------|
| Extract A1111 | Stable Diffusion WebUI 形式のメタデータを抽出 |
| Extract ComfyUI | ComfyUI ワークフローメタデータを抽出 |
| Normalize tags | タグを小文字に統一 |
| Compute hash | ファイルハッシュを計算（重複検出用） |
| FTS | 全文検索インデックスを有効化 |

## API キー

外部ツール（MCP サーバー、スクリプト、エージェント）用の API キーを管理。
Bearer 認証で使用します。

## 外観

テーマ、アクセントカラー、背景画像、サウンドエフェクトなどのカスタマイズ。

## 暗号化シークレットストア

PIN、Bluesky パスワード、Webhook シークレットなどの機密値は `cryptography` パッケージの Fernet 暗号化で保護されます。

- **暗号化形式**: `enc:` プレフィックス付き文字列
- **互換性**: 既存の平文値はそのまま動作（新規保存時のみ暗号化）
- **インストール**: `uv pip install cryptography` (未インストール時は暗号化機能が無効)

### 鍵バックエンド

暗号化鍵は以下の優先順で取得されます:

1. **パスフレーズ** — 環境変数 `YU_SECRET_PASSPHRASE` を設定すると、PBKDF2-HMAC-SHA256 (600,000 iterations) で鍵を導出。ソルトは `data/secret.salt` に自動保存
2. **OS キーチェーン** — `keyring` パッケージがインストール済みの場合、Windows Credential Manager / macOS Keychain / Linux Secret Service に鍵を保管
3. **ファイル** — `data/secret.key` (従来互換、初回自動生成)

```bash
# パスフレーズの設定例
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# キーチェーンの利用
uv pip install keyring
```

### 鍵のエクスポート/インポート

別マシンへの移行やバックアップ用に、パスワード保護 JSON 形式で暗号化鍵をエクスポート/インポートできます。

- `POST /api/settings/secrets/export` — パスワード (8文字以上) で保護してエクスポート
- `POST /api/settings/secrets/import` — エクスポートデータとパスワードで鍵を復元
- `POST /api/settings/secrets/migrate-keychain` — ファイルからキーチェーンに移行
- `GET /api/settings/secrets/status` — バックエンド状態を確認

### キーチェーンへの移行

ファイルに保存された鍵をキーチェーンに移行するには、`/api/settings/secrets/migrate-keychain` を呼び出します。移行後、`data/secret.key` は自動削除されます。

## 1Password CLI 統合

`op` CLI がインストール済みの環境では、1Password Vault からシークレットを動的取得できます。

### セットアップ

1. [1Password CLI](https://developer.1password.com/docs/cli/) をインストール
2. `op signin` でサインイン
3. `config.json` に `op_secrets` マッピングを追加:

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. Settings API または MCP ツールで `op_uri` を指定して設定:

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### 動作

- `op_secrets` にキーが登録されている場合、`op read` でシークレットを取得
- 取得値は 5 分間メモリキャッシュ
- `op` CLI がない環境ではローカル暗号化ストアにフォールバック
- `GET /api/settings/op-status` で 1Password の認証状態を確認可能

## Settings MCP ツール

MCP クライアント (Claude Desktop 等) から設定を管理できます。

| ツール | 説明 |
|--------|------|
| `settings_get_schema` | 全設定のスキーマ (型、説明、カテゴリ) を取得 |
| `settings_get_all` | 全設定値を取得 (シークレットはマスク) |
| `settings_get` | 単一設定値を取得 |
| `settings_set` | 設定値を更新 (シークレットは自動暗号化) |
| `secrets_status` | 暗号化鍵バックエンドの状態を取得 |
| `secrets_export` | パスワード保護 JSON で鍵をエクスポート |
| `secrets_import` | エクスポートデータから鍵をインポート |
