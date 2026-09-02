# YU QR プロトコル v1 — 統一ペイロード仕様

**バージョン:** 1.3
**策定日:** 2026-02-23
**対象アプリ:** YU AI Manager (TagDB)

---

## 概要

YU AI Manager は QR コードを使ったプロンプト共有・エラー診断機能を持つ。
本ドキュメントはその QR ペイロード仕様を統一的に記述する。

### 使用ライブラリ

| 用途 | ライブラリ | バージョン |
|------|-----------|-----------|
| QR 生成 | QRCode.js | 1.0.0 |
| QR 読取 | jsQR | 1.4.0 |

### QR 容量上限

- 最大文字数: **2953 字**（誤り訂正レベル M）
- 2500 字超の場合: メタ JSON を最小化して再試行
- 2953 字超の場合: エラー（`qr.info.too_long`）

---

## ペイロード型 1 — Prompt Share

### 生成元

- `GET /api/share/<file_id>` → Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### JSON スキーマ

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### フィールド定義

| キー | 型 | 必須 | 説明 | 上限 |
|------|-----|------|------|------|
| `v` | string | ✅ | プロトコルバージョン。現在 `"1.0"` | — |
| `t` | string | ✅ | ペイロード種別。現在常に `"prompt"` | — |
| `p` | string | ✅ | ポジティブプロンプト | 2000 字 |
| `n` | string | ✅ | ネガティブプロンプト | 1000 字 |
| `src` | string | ✅ | 発行元識別子。現在常に `"TagDB"` | — |
| `m` | string | — | モデル名 | — |
| `s` | string | — | シード値 | — |
| `st` | string | — | ステップ数 | — |
| `cfg` | string | — | CFG スケール | — |
| `sa` | string | — | サンプラー名 | — |
| `sz` | string | — | 画像サイズ `"WxH"` 形式 | — |

---

## QR モード — 4 種類

### `positive` モード

```
qrText = shareData.p
```

- 内容: ポジティブプロンプトのテキストのみ
- 用途: プロンプトのテキスト直貼り共有

### `negative` モード

```
qrText = shareData.n
```

- 内容: ネガティブプロンプトのテキストのみ

### `meta` モード

```
qrText = JSON.stringify(shareData, null, 0)
```

- 内容: Prompt Share JSON ペイロード全体をコンパクト化
- 2500 字超の場合は改行付き `JSON.stringify` に戻して再試行

### `url` モード

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- 内容: YU AI Manager の share ページへの URL
- ローカルホスト (`localhost` / `127.0.0.1`) では無効化

---

## ペイロード型 2 — Error Diagnostic

### 生成元

- HTTP エラー発生時 → `render_error_page()`
- `core/web/error_handlers.py`

### JSON スキーマ

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### フィールド定義

| キー | 型 | 説明 | 上限 |
|------|-----|------|------|
| `s` | string | HTTP ステータスコード (`"404"`, `"500"` 等) | — |
| `p` | string | リクエストパス | 80 字 |
| `v` | string | アプリバージョン (`APP_VERSION` ファイルから) | — |

---

## ペイロード型 3 — Bug Report

### 生成元

- 未処理 Python 例外発生時 → `render_error_page()` に `exc` を渡して生成
- `core/web/error_handlers.py` の `handle_unexpected_error()`

### JSON スキーマ

```json
{
  "schema": "yu://error-bundle/1",
  "error_id": "<stable error id>",
  "captured_at": "<UTC ISO8601 timestamp>",
  "capture_mode": "api|page",
  "app": {
    "name": "YU AI Manager",
    "version": "<APP_VERSION>",
    "ui": "<active ui>",
    "mode": "<server mode>"
  },
  "request": {
    "request_id": "<request id>",
    "method": "<HTTP method>",
    "path": "<request path>",
    "query": {},
    "body_preview": {},
    "headers": {
      "user_agent": "<user agent>",
      "referer": "<referrer>"
    },
    "endpoint": "<endpoint>"
  },
  "error": {
    "class": "<ExceptionClass>",
    "message": "<message>",
    "status_code": 500,
    "traceback": "<traceback tail>",
    "frames": []
  },
  "state": {
    "server_info": {},
    "extensions": [],
    "db": {}
  },
  "artifacts": {
    "recent_logs": []
  }
}
```

### フィールド定義

| キー | 型 | 必須 | 説明 | 上限 |
|------|-----|------|------|------|
| `schema` | string | ✅ | AI 向け構造化診断 bundle 識別子。現在 `"yu://error-bundle/1"` | — |
| `error_id` | string | ✅ | エラー識別子 | 32 字 |
| `captured_at` | string | ✅ | UTC 時刻（ISO 8601） | — |
| `capture_mode` | string | ✅ | エラー発生経路 (`api` / `page`) | 8 字 |
| `app` | object | ✅ | アプリ要約 | — |
| `request` | object | ✅ | マスク済み request 要約 | — |
| `error` | object | ✅ | 例外クラス・メッセージ・traceback・frames | — |
| `state` | object | — | server / extension / DB の要約 | — |
| `artifacts` | object | — | recent logs などの補助情報 | — |

### 転送形式

Type 3 は JSON 全体をそのまま URL に載せず、次の順で圧縮して `d` パラメータへ入れる。

1. JSON を最小化して生成
2. UTF-8 エンコード
3. gzip 圧縮
4. Base64URL（パディングなし）へ変換
5. クエリパラメータ `d` に格納

互換用として `v` `p` `e` も URL に残す。圧縮デコードに失敗しても relay page 側で最低限の内容は表示できる。
bundle が QR 容量を超えそうな場合は、recent logs、traceback 長、request body preview、extension 一覧、server-info 詳細の順で縮約する。

### スキャン先

QR は次の URL をエンコードする。

```text
https://eauesque.github.io/yu_ai_manager/bugreport.html
  ?v=<APP_VERSION>
  &p=<request path>
  &e=<exception class: message>
  &d=<gzip+base64url payload>
```

### relay page の復号

`docs/bugreport.html` は最初に `d` を展開し、失敗時は旧 `v/p/e/tr` にフォールバックする。展開した bundle JSON は relay page 上に表示され、そのまま GitHub Issue 本文の `AI Error Bundle` ブロックにも埋め込まれる。

```javascript
const packed = params.get('d') || '';
const stream = new Blob([b64UrlToBytes(packed)]).stream()
  .pipeThrough(new DecompressionStream('gzip'));
const payload = JSON.parse(await new Response(stream).text());
```

---

## URL Share デコード手順

Share ページ (`/share?data=...`) でのデコード:

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## QR 生成パラメータ

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // エラーページは 180
  height:       200,   // エラーページは 180
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 誤り訂正 15%
});
```

---

## 将来拡張 (v1.x)

| 機能 | 状態 | 備考 |
|------|------|------|
| コレクション QR エクスポート（複数画像） | 未実装 | ペイロード型 4 として定義予定 |
| `t: "collection"` 型 | 未定義 | ファイル ID リスト + コレクション名 |
| 圧縮（gzip + Base64URL） | bug report のみ実装済み | Prompt Share 圧縮は未実装 |

---

## 実装ファイル一覧

| ファイル | 役割 |
|----------|------|
| `routes/share.py` | Share API Blueprint |
| `routes/share_ops/payload_build.py` | ペイロード生成 |
| `routes/share_ops/prompt_extract.py` | プロンプトデータ抽出 |
| `core/web/error_handlers.py` | エラー QR データ生成 |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | QR ビルド & レンダリング |
| `static/js/runtime/tools/runtime-tools-qr.js` | QR UI ハンドラ |
| `static/js/share/share-qr.js` | QR 画像デコード |
| `static/js/share/share-page.js` | Share ページ表示 |
| `static/vendor/qrcode.min.js` | QRCode.js 本体 |
| `static/vendor/jsQR.min.js` | jsQR 本体 |
| `docs/bugreport.html` | GitHub Pages バグレポート relay page |
