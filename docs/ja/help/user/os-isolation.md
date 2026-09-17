# OS レベル隔離ガイド

Extension（拡張機能）がシステムに与える影響を、OS のセキュリティ機構で制限する機能です。

## 1. OS 隔離とは

スマートフォンでアプリをインストールするとき、「このアプリはカメラへのアクセスを要求しています」と表示されますよね。OS 隔離はそれと同じ考え方です。

Extension が宣言した権限（ファイル読み書き、ネットワーク通信、外部コマンド実行など）に基づいて、**OS のカーネルが許可されていない操作を物理的にブロック**します。Python のコード内でどんなテクニックを使っても、カーネルレベルの制限は迂回できません。

> **注意**: この機能は主にサードパーティ（第三者）製の Extension を安全に使うためのものです。`builtin-*` Extension は信頼済み（L0）として扱われ、制限なしで動作します。

---

## 2. 対応プラットフォーム

| OS | 隔離方式 | 成熟度 |
|----|---------|--------|
| **Linux** | AppArmor（Mandatory Access Control） | 推奨・本番対応 |
| **macOS** | sandbox-exec（Seatbelt） | 実験的（Apple により非推奨） |
| **Windows** | Restricted Token + Job Object | 基本的なリソース制限 |

Linux の AppArmor が最も完成度が高く、推奨される環境です。

---

## 3. Linux セットアップ（AppArmor）

### 3.1 AppArmor とは

AppArmor は Linux カーネルに組み込まれたセキュリティモジュールです。プロセスごとに「どのファイルを読み書きできるか」「ネットワーク通信を許可するか」をプロファイルで定義し、カーネルが強制します。

Ubuntu / Debian では標準で有効になっていることが多いですが、Raspberry Pi OS など一部のディストリビューションでは手動で有効化が必要です。

### 3.2 自動セットアップ

付属のセットアップスクリプトで一括設定できます。

```bash
sudo bash scripts/setup-apparmor.sh
```

このスクリプトは以下を行います:

1. **AppArmor パッケージの確認・インストール** — `apparmor`, `apparmor-utils` がなければ自動インストール
2. **カーネルパラメータの追加** — `/boot/firmware/cmdline.txt` に `lsm=apparmor` を追加（バックアップ付き）
3. **sudoers ルールの設置** — `apparmor_parser` コマンドのみパスワードなしで実行可能に設定（最小権限）
4. **AppArmor サービスの有効化** — systemd で自動起動を設定

> **Raspberry Pi OS 以外の場合**: GRUB を使う環境では、スクリプトが案内するように `/etc/default/grub` の `GRUB_CMDLINE_LINUX` に `lsm=apparmor` を手動で追加し、`sudo update-grub` を実行してください。

### 3.3 再起動

カーネルパラメータを追加した場合は再起動が必要です。

```bash
sudo reboot
```

### 3.4 動作確認

再起動後、以下のコマンドで AppArmor が有効か確認します。

```bash
# カーネルモジュールが有効か
cat /sys/module/apparmor/parameters/enabled
# → "Y" と表示されれば有効

# ロード済みプロファイルの一覧
sudo aa-status
```

### 3.5 config.json で有効化

AppArmor が動作していることを確認したら、`config.json` に以下を追加します。

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    }
  }
}
```

これで、サードパーティ Extension の起動時に AppArmor プロファイルが自動生成・ロードされるようになります。

---

## 4. 設定項目リファレンス

`config.json` の `os_isolation` セクションで制御します。

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    },
    "macos": {
      "sandbox_exec": false
    },
    "windows": {
      "restricted_token": true,
      "job_object": true,
      "job_limits": {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10
      }
    }
  }
}
```

| キー | 型 | デフォルト | 説明 |
|------|------|-----------|------|
| `enabled` | bool | `false` | OS 隔離機能全体の有効/無効 |
| `linux.apparmor` | bool | `true` | AppArmor プロファイルを使用する |
| `macos.sandbox_exec` | bool | `false` | macOS sandbox-exec を使用する（実験的） |
| `windows.restricted_token` | bool | `true` | 制限付きトークンでプロセスを起動する |
| `windows.job_object` | bool | `true` | Job Object でリソース制限する |
| `windows.job_limits.memory_mb` | int | `512` | Extension あたりの最大メモリ (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | Extension あたりの CPU 使用率上限 (%) |
| `windows.job_limits.max_processes` | int | `10` | Extension が生成できる最大プロセス数 |

---

## 5. Extension 権限と AppArmor ルールの対応

Extension が `extension.json` で宣言した権限に応じて、AppArmor プロファイルが自動生成されます。

| Extension 権限 | AppArmor での制御 |
|---------------|-------------------|
| `db:read` | `data/` ディレクトリの読み取りのみ許可 |
| `db:write` | `data/` ディレクトリの読み書きを許可 |
| `fs:read:scan_roots` | 設定されたスキャンルートの読み取りを許可 |
| `fs:write:any` | 全パスの読み書きを許可 |
| `network:local` | TCP/Unix ソケットを許可（UDP は拒否） |
| `network:internet` | TCP/UDP/Unix ソケットを全て許可 |
| `subprocess` | `/usr/bin/`, `/bin/` 等の実行を許可 |
| ネットワーク権限なし | TCP/UDP を明示的に拒否、IPC 用の Unix ソケットのみ許可 |
| subprocess 権限なし | `/usr/bin/`, `/bin/` 等の実行を明示的に拒否 |

Extension 自身のディレクトリ（`extensions/<name>/`）は常に読み書き可能です。

---

## 6. API からの確認

OS 隔離の状態は API から確認できます。

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

レスポンス例（Linux / AppArmor 有効時）:

```json
{
  "platform": "linux",
  "available": true,
  "method": "apparmor",
  "details": {
    "apparmor_kernel": "enabled",
    "apparmor_tools": true,
    "apparmor_sudoers": true,
    "aa_exec_path": "/usr/sbin/aa-exec"
  }
}
```

`available` が `false` の場合、`setup` フィールドにセットアップ手順が含まれます。

---

## 7. トラブルシューティング

### AppArmor が有効にならない

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" または ファイルが存在しない
```

**原因**: カーネルパラメータが適用されていない。

**対処**:
- Raspberry Pi OS: `/boot/firmware/cmdline.txt` に `lsm=apparmor` があるか確認し、再起動
- GRUB 環境: `/etc/default/grub` で `GRUB_CMDLINE_LINUX="... lsm=apparmor"` を確認し、`sudo update-grub && sudo reboot`

### Extension 起動時に「sudoers not configured」と出る

**原因**: `apparmor_parser` の NOPASSWD sudoers ルールが設定されていない。

**対処**:
```bash
sudo bash scripts/setup-apparmor.sh
```

スクリプトが `/etc/sudoers.d/yu-ai-apparmor` に必要なルールを設置します。

### Extension が権限不足で動作しない

**原因**: Extension の `extension.json` に必要な権限が宣言されていない。

**対処**: Extension の `extension.json` の `permissions.required` に必要な権限を追加するか、Settings > Extensions から権限を手動で付与してください。

### AppArmor プロファイルの手動確認

生成されたプロファイルは `/tmp/yu_ai_apparmor/` に保存されます。

```bash
# プロファイルの内容を確認
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>

# 現在ロードされている YU AI Manager のプロファイル一覧
sudo aa-status | grep yu_ai_ext
```

---

## 8. セキュリティに関する注意

OS 隔離は多層防御の一部です。YU AI Manager は以下の層でセキュリティを確保しています。

1. **静的解析**（Phase 1）— Extension のコードをインストール時に AST 解析し、危険な import を検出
2. **権限ゲートキーパー**（Phase 2-3）— ServiceRegistry 経由のアクセスを権限チェック付き Proxy で制御
3. **OS 隔離**（Phase 4）— カーネルレベルでファイル・ネットワーク・プロセス実行を強制制限

OS 隔離だけで全てのリスクを排除できるわけではありませんが、他の防御層と組み合わせることで、サードパーティ Extension を安全に利用できる環境を提供します。

信頼できない Extension をインストールする場合は、OS 隔離を有効にした Linux 環境での利用を推奨します。
