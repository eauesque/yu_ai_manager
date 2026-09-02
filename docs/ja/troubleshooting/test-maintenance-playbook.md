# テスト保守プレイブック

古いテスト基盤や環境依存で pytest が止まったときに、最初に見るポイントをまとめる。

## 目的

- `failed` と `skipped` を切り分ける
- 正常な環境依存 skip と、修理すべき stale test を区別する
- broad run (`pytest tests -q --maxfail=1`) が止まったときの最短導線を固定する

## 基本コマンド

通常の全体確認:

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

skip 理由も確認:

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

shared test server を strict に扱う:

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

ライセンス監査:

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## 現在の skip の読み方

2026-04-21 時点の broad run では、skip の主因は以下の 5 系統に偏っている。

### 1. Shared Test Server 未起動

もっとも多い skip。`tests/conftest.py` の shared server は best-effort 起動で、起動できなければ browser / server 依存群を fail ではなく skip に落とす。

代表的な理由:

- `Shared test server unavailable on port <PORT>`

主な対象:

- `tests/api/`
- browser UX review 系
- LAN Cowork / Fleet の browser/server 依存テスト
- `TARGET_URL` / `BASE` / `TARGET` を使う live browser test
- `page` fixture ではなく独自 Playwright/WebKit fixture を使う監査系テスト

これは通常 run では **正常な skip**。ただし以下の場合は要調査:

- shared server 前提ではない unit test まで同じ理由で skip している
- 以前通っていた shared server 系が急に大量 skip 化した
- `PYTEST_STRICT_AUTOSTART_SERVER=1` でも原因が見えない

### 2. OS 固有テスト

Linux 専用の sandbox / AppArmor / process isolation 系。Windows では skip が正しい。

代表例:

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

代表的な理由:

- `Linux only`
- `AppArmor は Linux 専用`

これは **正常な skip**。

### 3. 任意依存・外部コンポーネント不足

特定パッケージや外部ノードがない環境では走らないテスト群。

代表例:

- mDNS 実機 E2E: `optional zeroconf package is not installed`
- browser 起動: `Playwright unavailable`, `launch failed`
- ONNX / YAML / ComfyUI / 外部 inference node 未接続

これは **正常な skip**。修理対象ではなく、前提環境が揃っていないだけ。

### 4. テスト用データ不足

画像・検索結果・会話ログ・複数件データなどが必要な browser テストで、軽量 DB では成立しないため skip する。

代表的な理由:

- `No search results available in database`
- `DB に画像がないためスキップ`
- `2件以上のファイルが必要`
- `No prompts to test copy`

これは **概ね正常な skip**。ただし、本来 fixture が必要データを用意すべきテストなら stale 化を疑う。

### 5. レートリミット・外部 API 保護

integration の一部は外部サービスやレート制限を尊重して skip する。

代表例:

- `レートリミットに達したためスキップ`

これは **正常な skip**。

### 6. 長時間 fuzz / burn-in

`tests/fuzz/` 配下の burn-in は、通常の回帰確認ではなく耐久・クラッシュ耐性の追加確認に使う。

既定では `pytest.ini` の marker 式で除外される。

実行したいとき:

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

必要に応じて:

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

これは **通常 broad run に混ぜない**。

## 異常扱いすべきパターン

以下は「skip だから問題なし」と片付けず、テスト保守対象として見る。

### A. 以前は pass していた軽量テストが setup skip に落ちる

例:

- app/client fixture ベースで完結するはずの API smoke が shared server 前提に巻き込まれる
- migration / schema / DB helper の unit test が runtime global state 初期化前提で落ちる

この場合は test harness と実装の前提ズレを疑う。

### B. broad run は通るが、単体実行でだけ落ちる

典型例:

- process-global state に依存
- broad run 中にたまたま先行テストが初期化した副作用に乗っている

単体実行も再現性のある状態に戻すこと。

### C. skip 理由が曖昧

悪い例:

- `failed`
- `not ready`
- `something wrong`

skip reason は「何が足りないから飛ばしたのか」を短文で書く。

## 修理の優先順

1. broad run を止める hard failure を直す
2. 単体実行でだけ崩れる stale test を直す
3. shared server / browser 系の skip を fail ではなく安全な skip に寄せる
4. 任意依存や実機依存は optional skip を維持する

## 今回の整備で固定したこと

- browser / server 依存は shared server unavailable を fail ではなく skip に統一
- license audit は venv 全体ではなく `requirements*.txt` 宣言依存だけを見る
- test DB は現行 search schema の path FTS 前提を満たす
- migration 54 / 55 は、ベーススキーマ進化や runtime state 未初期化に対して脆くないよう修正

## 迷ったときの判断基準

- 前提環境が無いだけなら skip でよい
- 現行実装に追従できていない古い期待値ならテストを直す
- broad run の副作用に依存しているなら実装かテストを直す
- unit test が process-global state を要求するなら設計を疑う
