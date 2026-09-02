# API セキュリティ指針

この文書は、API を追加・変更するときに同じ種類の問題を再発させないための最低基準です。

## 最初に決めること

新しい endpoint は、必ず最初に次のどれかへ分類する。

- `public`
- `session/user`
- `admin`
- `localhost-only`

迷ったら `admin` に倒す。

## 基本原則

1. `GET` は安全だと思わない。
2. `read-only API key` は薄い read だけを許す。
3. 内部 path、inventory、履歴、本文、ログ、解析結果は原則 `admin`。
4. localhost 判定は proxy-aware helper を使う。
5. 設定 API は allowlist と strict validation を必須にする。
6. secret は共通 helper で encrypt / redact する。

## read-only API key に残してよいもの

残してよいのは、外部に見えても問題がない薄いデータだけです。

例:

- help
- 静的 capability 情報
- 単純な availability 表示

残してはいけない例:

- 内部 path
- file/member id inventory
- prompt、annotation、transcript、chatlog
- OCR / analysis result
- queue、history、audit、approval、scheduler、scan error
- extension / profile / backup / webhook / secret backend 状態
- 保存済み資格情報を使った代理 fetch の結果

## localhost 判定

禁止:

- `request.remote_addr == "127.0.0.1"`
- `request.remote_addr in (...)`

必須:

- `get_client_ip()`
- `is_local_request()`
- `is_loopback_request()`

same-host reverse proxy 配下では raw `remote_addr` 判定は壊れる前提で考える。

## 設定 API のルール

必須:

- key の allowlist
- 型検証
- range / enum / URL validation
- secret の redaction
- secret の暗号化保存

禁止:

- `config.update(request_json)`
- `bool(value)` による boolean 解釈
- secret を generic merge で扱うこと

boolean は JSON `true/false` のみ受ける。
`"false"`、`"0"`、`"no"` のような文字列を受け入れない。

## secret の扱い

守ること:

- `GET` では current value を返さない。必要でも masked のみ
- `list` API に token / header / secret blob を混ぜない
- masked 値で既存 secret を上書きしない
- 専用 store か共通 helper を通す

## outbound request を伴う API

`GET` で upstream probe、model discovery、market fetch、private API 呼び出しをしない。

必要なら:

- `admin` scope 必須
- timeout 短め
- validator で localhost / private IP / metadata endpoint を拒否

## 最低限必要なテスト

敏感な endpoint には少なくとも次を入れる。

1. `read-only key -> 403`
2. `admin key -> 200`
3. invalid input -> `400`
4. secret redaction の確認
5. localhost 制限があるなら proxy-aware regression test

## PR レビュー checklist

- この `GET` は本当に public/read-only でよいか
- path / inventory / prompt / transcript / history / raw metadata を返していないか
- secret を漏らしていないか
- proxy-aware helper を使っているか
- `bool(...)` 直変換をしていないか
- allowlist なしの config merge をしていないか
- outbound request を勝手に発生させていないか
- `admin` scope regression test があるか

## 実装方針

API 境界は「あとで締める」より「最初から狭く作る」方が安い。

順序はこれで固定する。

1. まず `admin` で作る
2. 本当に必要なものだけ公開範囲を広げる
3. 広く開けた endpoint を後から正当化しない
