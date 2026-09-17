# ffmpeg インストールガイド

Tag Database は動画ファイル（WebM、MP4 など）のサムネイル生成に ffmpeg を使用します。

## Windows

### オプション 1: Scoop（推奨）
```powershell
# Scoop をインストール（未インストールの場合）
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# ffmpeg をインストール
scoop install ffmpeg
```

### オプション 2: Chocolatey
```powershell
# Chocolatey をインストール（未インストールの場合）
# 管理者権限で実行
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# ffmpeg をインストール
choco install ffmpeg
```

### オプション 3: 手動ダウンロード
1. 以下からダウンロード: https://www.gyan.dev/ffmpeg/builds/
2. `C:\ffmpeg` に展開
3. PATH に追加:
   - 「環境変数」を開く
   - 「Path」を編集
   - `C:\ffmpeg\bin` を追加
4. ターミナルを再起動

---

## macOS

### Homebrew（推奨）
```bash
# Homebrew をインストール（未インストールの場合）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ffmpeg をインストール
brew install ffmpeg
```

---

## Linux

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Fedora
```bash
sudo dnf install ffmpeg
```

### Arch
```bash
sudo pacman -S ffmpeg
```

---

## インストール確認

```bash
ffmpeg -version
```

バージョン情報が表示されれば成功です。

---

## 動画サムネイルのテスト

```bash
# WebUI を起動
python web_ui.py --db tags.db

# WebM ファイルに移動
# サムネイルが自動生成されます
```

---

## トラブルシューティング

### 「ffmpeg not installed」エラー

**症状**: 動画サムネイルにエラーメッセージが表示される

**解決策**:
1. ffmpeg がインストールされているか確認: `ffmpeg -version`
2. ターミナル / PowerShell を再起動
3. WebUI を再起動
4. PATH 設定を確認

### サムネイルが生成されない

**症状**: サムネイルに「Failed to extract video frame」と表示される

**考えられる原因**:
- 動画ファイルが破損している
- 動画コーデックが非対応
- ffmpeg タイムアウト（10 秒超過）

**デバッグ**:
```bash
# 手動でテスト
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# ログを確認
# "[ERROR] ffmpeg" メッセージを探す
```

---

## オプション: GPU アクセラレーション

高速な動画処理のために（上級者向け）:

### Windows (NVIDIA)
```bash
# NVIDIA ビルドをダウンロード:
# https://www.gyan.dev/ffmpeg/builds/
# 「ffmpeg-release-full.7z」を選択
```

### macOS (VideoToolbox)
```bash
# Homebrew ビルドに含まれています
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## パフォーマンスに関する注意

- 初回サムネイル生成: 約 1-3 秒
- キャッシュ済みサムネイル: 100ms 未満
- ZIP ファイル: 一時ディレクトリに展開後処理
- タイムアウト: 動画ごとに 10 秒

---

## ffmpeg なしの場合

ffmpeg が利用できない場合:
- 動画ファイルのサムネイルにエラーが表示されます
- メタデータによる動画検索は引き続き可能です
- 完全な機能を利用するには ffmpeg のインストールをお勧めします
