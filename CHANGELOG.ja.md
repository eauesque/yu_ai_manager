## [4.689.41] - 2026-09-03

### 修正

- **設定から追加したスキャンフォルダーが Windows で一つも認識されないことがありました。**
  エクスプローラーの「パスのコピー」は `"C:\Users\me\Pictures"` のように引用符付きで
  コピーします。これをそのまま貼り付けると引用符ごと保存され、フォルダーとして開けず、
  **スキャン対象が一つも無い状態のまま静かに動いていました**。貼り付け時と読み込み時の
  両方で引用符を取り除くようにしたので、すでに引用符付きで保存されている設定も
  入力し直さずに復旧します。
- **PDF のサムネイルが、サーバー起動後の最初の一枚しか描画されませんでした。**
  二枚目以降は代替画像がキャッシュに恒久的に書き込まれていました。
- **設定ファイルが二重に存在すると、Python 版と Rust 版で拡張機能の設定が互いに見えなく
  なっていました。** `config.toml` を優先し、読み込んだ形式のまま書き戻すよう統一しました。
- **`launch-args.txt` の `--host` / `--port` / `--db` が設定ファイルに負けて無視されて
  いました。** また yu-server が受け付けない項目を書くと、理由を告げずに Python 版へ
  切り替わっていました。
- **登録済みのスキャンフォルダーが画面から消え、ファイルの増減が反映されないことが
  ありました。**
- **統計画面 (`/api/stats/*`) の集計が毎回やり直しになり、数秒かかっていました。**
- **スキャンフォルダーの復旧操作 (recovery) が設定画面で 400 エラーになっていました。**
- **Bluesky 連携の設定画面が、保存した値を表示しませんでした。**
- **バックアップ一覧・バックアップ状態が「バックアップはありません」「機能は無効です」と
  事実に反する応答を返していました。** この機能はまだ Rust 版に無いため、正直に
  「利用できません」と返すようにし、画面も「無い」と「使えない」を区別します。
- **中断したスキャンの再開案内が表示されませんでした。** サムネイルキャッシュの容量表示が
  常に 0 だった問題、ゲートウェイのバックエンド一覧が常に空だった問題も同時に直しました。

### アクセシビリティ

- **配色のコントラスト不足を 4 か所直しました。** テーマ用の色が一部未定義で、明るいテーマでも
  暗いテーマ向けの色が使われており、文字が読み取りにくくなっていました。72 か所に影響します。
- **設定画面のサイドバー項目が小さすぎました**（19.5px、WCAG の最小 24px 未満）。
- **確認ダイアログがスクリーンリーダーに「名前のない領域」として読まれていました。**
  役割と読み上げ名を与えました。

### 高速モード

- **取得方法を 3 種類から選べるようにしました**（自動 / ダウンロード / 自前ビルド）。
- **自前ビルドの進捗を設定画面に表示するようにしました。** 以前は出力が詰まって
  ビルドが止まったように見えることがありました。
- **「有効にしても何も起きない」状態の原因を解消しました。** 高速モードが別のデータベースを
  読んでいた問題、設定が読まれていなかった問題も直しました。
- **Hailo 用サイドカー (`yu-infer`) が配布物に含まれていませんでした。**

### セキュリティ

- **設定ファイルの生編集画面を、同じ端末からのみ利用できるようにしました。**
- **拡張機能のサンドボックス設定が、誰でも書き込める場所に予測可能な名前で置かれて
  いました。**
- **ブリッジの HTTP 通信が `file://` をたどれてしまう経路がありました。**
- **設定の読み取りが、書き込みと同じ厳しい回数制限を消費していました。** 自分の設定を
  数回読み直しただけで拒否されることがありました。
- **LAN 共有の取り込みで、相手が申告したファイルサイズと実際の受信量を照合するように
  しました。** 途中で切れたファイルが正常なものとして扱われることを防ぎます。

### その他

- ポータブル版に同梱する Python を 3.13 に更新しました。
- ページのタイトルが 12 ページ分翻訳されていなかったため対応し、製品名を
  `YU AI Manager` に統一しました。

## [4.681.3] - 2026-08-29

### Fixed

- **LAN Cowork の修正 4 件が、ようやく実際のビルドに入りました。** 本体が参照していた lan-cowork の版がこれらの修正より古く、v4.681.2 までは Python 経路でしか効いていませんでした。参照を更新し、Rust 経路でも有効になりました。
  - **リモート取り込み中の転送失敗を、成功として扱わないようにしました。** ZIP の一部が正常に取得できなかった場合は個別取得へ切り替え、認証エラー (401) が返った場合はバッチ全体を中止します。
  - **リモートからの取り込みが、自分でつけた評価を上書きしなくなりました。**
  - **ログ配信と `fleet/update/status` を「リモート操作を許可する」マスタースイッチの配下に入れました。** これまでこの 2 つだけがスイッチの外にあり、無効にしていても到達できました。
  - **フリート権限一覧 (my-permissions) の取得を高速化しました。** ノード 1 台ごとに identity seed をデータベースから読み直していたものを、リクエストにつき 1 回に改めました。

## [4.679.24] - 2026-08-29

### Fixed

- **`hailort.rs::llm_generate`(admin診断経路)を見落としていた分の HAILO_TIMEOUT 誤検知対策を追加した(Codex stop-time review 指摘)。** 前回リリースでネイティブ chat/completions/caption の全経路を `DEFAULT_GENERATE_TIMEOUT_MS = 120_000` に統一したが、この admin 診断ルートだけは `body.timeout_ms.map(...)` が呼出元省略時に `None` のまま sidecar へ転送され、依然 30 秒既定が生きていた。呼出元が指定した場合は既存の `MAX_TIMEOUT_MS` 上限のまま、未指定時は新既定値へ落ちるよう `.unwrap_or(DEFAULT_GENERATE_TIMEOUT_MS)` を追加した。

## [4.679.21] - 2026-08-29

### Fixed

- **低 `CmaFree` 下での HAILO_TIMEOUT 誤検知に対処した。** 実機で計測した「低 CmaFree 下では読込・生成に既定30秒を超えて108秒かかることがあり、生成自体は成功するのに既定 `timeout_ms` のままでは HAILO_TIMEOUT を誤って返す」問題(前回リリース参照)を受け、`infer_client.rs` に `DEFAULT_GENERATE_TIMEOUT_MS = 120_000` を新設し、ネイティブ chat/completions/caption の全経路(`hailo_genai_chat.rs` 2箇所、`auto_stubs.rs` 3箇所、`caption_runner.rs` の旧30秒定数)をこの値に統一した。CmaFree 連動の動的調整は複雑化を避けるため見送り、固定引き上げのみとした。

## [4.679.20] - 2026-08-29

### Fixed

- **`infer_manager::supervise()` の shutdown 競合を再修正した(Codex stop-time review 指摘・第二回)。** v4.679.11 の修正は `stop` の再確認と `child` ミューテックスの取得を別々に行っており、その間の隙間で shutdown が割り込む余地が残っていた。`stop` の再検査と設置(または破棄)を同一の `child.lock()` 保持下に一体化し、shutdown 側の「`stop` を立ててから同じロックを取って terminate する」手順と排他にした。これにより、どちらが先にロックを取っても孤児プロセスが生じない2通りの決定的な結果にのみ収束する。

## [4.679.16] - 2026-08-29

### Fixed

- **Linux/macOS の開発ツール確認を `setup-dev-tools.sh --check` に一本化した。** 24時間以内は存在確認だけを行い、`./bin` と `~/.local/bin` を作成しない。期限切れ・state 欠損・未来時刻の場合は不足ツールの導入と旧版更新を行い、全項目成功時のみ `~/.local/share/ai-tools-check.json` を更新する。重複していた `setup-ai-tools.sh` は削除し、agent-env の案内も正本へ切り替えた。

## [4.679.11] - 2026-08-29

### Fixed

- **`infer_manager::supervise()` の shutdown 競合を修正した(Codex stop-time review 指摘)。** v4.679.7 で追加したクラッシュ復帰ロジックは `spawn_with_restart` の `await` 完了後に `stop` フラグを再確認しておらず、shutdown が古い子プロセスを terminate している間に新しい子プロセスが生まれ終えると、それが孤児として `AppState.infer_child` に設置され得た。respawn 成功直後にも `stop` を確認し、立っていれば新しい子をその場で terminate して設置しない分岐を追加した。直接の結合試験は本物の respawn 成功を要するため未追加(条件分岐の論理のみ)。

## [4.679.7] - 2026-08-29

### Fixed

- **yu-infer(Hailo sidecar)がクラッシュ後に回復しない欠陥を修正した。** `infer_manager::spawn_with_restart` は起動時のみのリトライ輪で、健全になった後は誰も子プロセスを監視しておらず、稼働中のクラッシュ(OOM-kill・panic・segfault 等、既知の CMA 非回収問題とは無関係)は `yu-server` 自身の再起動まで回復しなかった。`AppState.infer_child` を `Arc<Mutex<Child>>` に改め、新設の `infer_manager::supervise()` が3秒毎に `try_wait()` で生死を確認し、死んでいれば既存の `spawn_with_restart`(同一 port・auth_token・instance_id 等を再利用)で差し替える。graceful shutdown は新設の stop フラグを先に立ててから子を terminate し、shutdown 中の誤 respawn を防ぐ。単体試験 `supervise_detects_crash_and_attempts_respawn_without_panicking` を追加。sidecar 監督設計自体は審査で NO-GO だったが、このクラッシュ復帰部分のみ CMA と無関係な実在の欠陥として独立に直した。

## [4.679.6] - 2026-08-29

### Fixed

- **Hailo-10H 実機にて CMA 回収の TODO 記述(v4.598.6/677)を再検証し訂正した。** reboot 直後(CmaFree 16→490,608 kB で枯渇・全回復を確認済み、firmware/driver 共に vanilla 5.4.0、pin `9537678`)から現行 sidecar を手動起動し `POST /v1/infer/llm/generate` を複数回実測。CmaFree は初回生成後にページキャッシュ相当の一回性低下(473,904→341,616 kB)を見せた後は単調減少せず 305,000〜341,000 kB 台で推移し、旧記述の「請求毎に約59 MiB 漏らす」は再現しなかった(`docs/ja/hailo/HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` 第4回試行の誤判定訂正と整合)。**新たに確認した実害**: 低 CmaFree 下では同一プロンプトの読込・生成が既定 30 秒を大幅に超え(60〜108秒)、既定 `timeout_ms` のままでは HAILO_TIMEOUT(status 4) を誤って返す。プロセス kill では CmaFree は戻らないこと、kill 後もデバイス自体は健全(`hailortcli run2 yolov8n` は 227 fps で正常動作)であることも実機で再確認した。詳細は `TODO.md` の該当項を参照。

## [4.679.5] - 2026-08-29

### Fixed

- **`register_path` の重複防止を、修正前(v4.679.4 以前)に verbatim 冠形で登録済みの既存行にも効かせた(Codex stop-time review 指摘への対応)。** v4.679.4 の `de_verbatim()` は新規登録の書き込み値を生パス化したが、`INSERT OR IGNORE` は文字列完全一致でしか照合しないため、その fix より前に verbatim 形(`\\?\D:\...`)で登録済みだった行に対して同じファイルを再度 `register_path` すると、生パス側の新しい行が INSERT され二重登録が**再発**し得た。INSERT 前に verbatim 形での既存行も検索し、見つかれば(生パス側の INSERT を試みず)409 で返すよう変更。**既存の verbatim 行そのものはこの増分では削除しない**(データ移行は別関心事) —— 既存の重複掃除は `delete_duplicates` ツール(唯一許可されているファイル操作)に委ねる。

## [4.679.4] - 2026-08-29

### Fixed

- **`files.path` の二重登録(B 軸)を修正。** `register_path`(`tools_ops.rs`)は `std::fs::canonicalize` の結果をそのまま `files.path` へ INSERT していたため、Windows では `\\?\D:\...` の verbatim 冠形が入り、走査経路(`upsert_file`／watcher)が書く生パス `D:\...` と文字列表現が食い違って `UNIQUE` 制約をすり抜け、同一ファイルが 2 行に増えていた(直前の Verified 項参照)。`de_verbatim()` を追加し、INSERT/応答直前に verbatim 冠形(`\\?\`・`\\?\UNC\`)を剥がすことで解決。**スキーマ変更なし** —— `canonicalize`(`GetFinalPathNameByHandleW`)は実ディスク上の表記を返すため、剥がした文字列は走査経路の生パスと一致し、当初検討していた `path_key` 別カラム＋migration 案は不要と判明した。応答契約は「新規登録 200」では不変、Windows で verbatim ゆえ誤って 200 を返していた重複ケースのみ正しく 409 へ転じる。
  - 単体試験 `de_verbatim_strips_windows_prefixes`(`#[cfg(windows)]`)を追加。
  - **既知の制約**: この環境では `yu-server` の vendored OpenSSL ビルドが Perl `Locale::Maketext::Simple` 欠如で失敗し(この環境で yu-server バイナリがビルドされた形跡なし、この増分と無関係の既存環境課題)、`cargo test -p yu-server` を実行できなかった。`de_verbatim` のロジック自体は実測した verbatim/UNC 冠形の実データで単体 rustc スクラッチ検証し、`rustfmt --check` は該当ファイルで通過を確認した。

## [4.679.3] - 2026-08-29

### Verified

- **TODO(yu-server) の Windows 実機限定検証項目二件（843・846・847）を win64 実機で実施した。** `std::fs::canonicalize` の verbatim/失敗挙動をスクラッチ Rust バイナリ（`rustc` 単体コンパイル）で直接実測：(1) 既存ローカルディレクトリ → `\\?\O:\...`、(2) 存在しないパス → `Err`、(3) admin 共有 `\\localhost\c$\Windows` → `\\?\UNC\localhost\c$\Windows`、(4) **同一ディレクトリを指す raw/canonical の両表現で `Path::starts_with` が双方向とも `false`**（A 軸の核心を確定）。`freeze_pullback.rs:241` の「出力先不在」シナリオも再現し、base 側が生パスへ落ちても candidate（未存在ファイル）側も canonicalize に失敗して素通り分岐へ落ちるため、文書が想定した「常に None（全拒否）」には単純な単発呼出しでは至らないことも確認した。残る 3 箇所（`source_api.rs:265`・`cross_search.rs:687`・`scan_roots.rs:747`）はコード読解で同型と確認、`files.path` 二重登録（`register_path`、B 軸）もコード上で成立を確認した。**修正自体（応答契約に影響）は別増分のまま TODO に残す。**
  - 検証手段: `.claude/worktrees/*/tmp/win_canon_check.rs`（スクラッチ、使用後削除）。詳細: `docs/development/development_docs/WINDOWS_VERBATIM_PATH_PITFALL.md`、`TODO.md`。

## [4.679.1] - 2026-08-29

### Fixed

- `setup-dev-tools.sh` は `lean-ctx update` によるバイナリ更新を先に試み、失敗時のみ cargo ソースビルドへフォールバックするよう改めた。

## [4.670.2] - 2026-08-26

### Fixed

- **`dev-docs-index.yaml` ノ CRLF 偽 drift ヲ「Windows デハ regen スルナ」ノ回避策デハナク根ヲ直セリ。**
  `gen_docs_index.py::_sha256` ト `pre_push_check.py::check_index_v2_sync` ノ双方ガ
  `path.read_bytes()` ノ生バイトヲ其ノ儘 hash シテ居タ為、CRLF 作業ツリー(`core.autocrlf=true`)ノ
  Windows デハ LF 版ト全件不一致トナリ偽 drift ヲ生ンデ居タ（前例 commit `b03b51e8f`）。
  両所ニ `\r\n → \n` 正規化ヲ揃ヘテ入レ、Windows 上デモ LF チェックアウトト同一ノ hash ヲ得ラレル様ニシタ。
  前回(v4.670.1)ハ Windows デノ regen ヲ skip スルノミノ回避策ダッタガ、之ハ検証其ノ物ヲ無効化スルダケデ
  直シテハ居ラナカッタ(Codex stop-time review 指摘)。併セテ `sorted(DOCS_DIR.rglob(...))` ガ
  WindowsPath ノ大小文字非区別比較ニ依リ Linux ト異ナル順ニ並ブ瑕疵モ、posix 化シタ文字列キーデ整列スル
  様ニ直セリ。Windows 上デ `check_index_v2_sync` ガ skip 無シニ PASS スルコトヲ実測。

## [4.670.1] - 2026-08-26

### Fixed

- **`hook-post-edit-regen-index.sh`: Windows デ `dev-docs-index.yaml` ヲ再生成セヌ様ニセリ。**
  作業ツリーガ CRLF（`core.autocrlf=true`）ナル Windows デ `gen_docs_index.py` ヲ走ラセルト
  `doc_sha256` ガ LF 版ト全件不一致トナリ偽 drift ヲ生ム（前例 commit `b03b51e8f`）。
  `uname -s` ニテ msys/cygwin/mingw ヲ検知シ、該当時ハ regen ヲ skip シテ案内ノミ出ス様ニ改メタリ。
  **→ v4.670.2 ニテ根本修正ニ差シ替ヘ済ミ。**

- **`check_native_only_endpoints.py`: Windows(cp932 既定ロケール)デ `pre_push_check.py` ガ落チル瑕疵ヲ直セリ。**
  `_baseline_paths()` ノ `subprocess.run(text=True)` ガ `encoding` 未指定ノ儘 `git show` ノ UTF-8 出力ヲ
  読ミ、日本語ヲ含ム doc デ `UnicodeDecodeError` ガ背景スレッド内ニテ握リ潰サレ `proc.stdout` ガ
  `None` ト成リ `AttributeError` ニテ例外化シ居タリ。`encoding="utf-8"` ヲ明示シテ解消（fast-mode
  QA-windows.md ノ実機検証中ニ発見）。

## [4.629.4] - 2026-08-20

### Changed

- **公開頒布ノ後始末トシテ `PUBLIC_RELEASE_REF` ヲ `b585dbbe3` ヘ上ゲタリ。**
  同 commit ノ樹ガ v4.629.3 トシテ公開サレタル物ナリ。script 自身ガ
  「公開倉庫ヲ頒布シタラ此ノ値ヲ上ゲヨ」ト述ブル手順ノ実施ナリ。
  上ゲタル後ニ走ラセ、初公開ノ門ハ 0 件、ミラーハ既ニ現在化済ミ
  （`crates/` ハ v4.629.0 以降変ハラズ）ナルヲ確メタリ。

## [4.629.3] - 2026-08-20

### Changed

- **`sync_yu_server_mirror.sh` ヲ `scripts/internal/` 配下ヘ移セリ。** 公開頒布ノ除外規則ハ
  `scripts/internal/` ヲ除クガ `scripts/` 直下ハ除カズ、**前版ノ儘ナラバ本 script ハ公開サレ居タリ**。
  中身ハ内部運用ノ手順ニシテ、`PUBLIC_RELEASE_REF` ニ**公開倉庫ニ存在セヌ内部 commit ノ SHA** ヲ
  抱ヘ居ル。頒布物ニ在ルベキ物ニ非ズ。
  依リテ 4.629.1／4.629.2 ノ記載中ノ径ハ現在 `scripts/internal/sync_yu_server_mirror.sh` ナリ。
  移設後モ repo 根ノ解決・初公開ノ門・後始末ノ悉クガ従前ノ通リ動クヲ確メタリ。

## [4.629.2] - 2026-08-20

### Fixed

- **`sync_yu_server_mirror.sh` ガ、検証セザル環境変数ノ指ス径ヲ `rm -rf` シ居タルヲ正セリ。**
  作業域ハ `MIRROR_WORKDIR` ニテ差シ替ヘ得、其ノ値ハ何ノ検メモ無ク削除ニ渡サレ居タリ。
  打チ間違ヒ一ツ、或ハ敵意アル環境ニテ、無縁ノ資料ヲ消シ得タリ。
  Codex ノ停止時査閲ノ指摘ナリ。前版ニテ本 script ヲ**新設シタ其ノ場デ持チ込ミタル瑕**ナリ。

- **検メヲ足サズ、類ソノモノヲ消セリ。** 作業域ハ `mktemp -d` ニテ script 自ラ作ル。
  **既ニ在ル物ヲ消ス機会ガ生ゼズ**、並行実行モ衝突セズ、`trap ... EXIT` ニテ後始末サル。
  径ヲ検証スル関門ヲ書クヨリ短ク、抜ケ道ガ無シ。`MIRROR_WORKDIR` ハ廃セリ
  （試験ノ隔離ハ `mktemp` ガ元ヨリ与フル）。

### 検証

- **囮ヲ置キテ実証セリ**――`/tmp/canary-must-survive` ヲ作リ
  `MIRROR_WORKDIR` ニ指シテ実行シタルニ、囮ハ無傷ニテ残レリ。
- 中止経路ノ退行無キコトヲ確メタリ――古キ `PUBLIC_RELEASE_REF` ニテ
  未公開四十一ファイルヲ検知シ中止、且ツ一時ディレクトリ残留 0。
- 通常実行ハ `no change; mirror already current`、一時ディレクトリ残留 0。

## [4.629.1] - 2026-08-20

### Fixed

- **台帳ガ「yu-server repo 分離ノ実行ソノモノガ残作業」ト記シ居タルヲ正セリ。**
  分離ハ**同ジ 2026-08-19 ノ内ニ実行済ミ**ナリキ（`eauesque/yu-server`、276 ファイル）。
  本書初版ノ棚卸シ時点デハ未了ナリシガ、其ノ後同日中ニ着手サレ、記述ダケガ取リ残サレタリ。
  **此ノ記述ヲ根拠ニ着手先ヲ選ベバ空振リス**。§2-6 ト §3 ノ優先表・結語ノ三箇所ヲ改メタリ。

### Added

- **`scripts/sync_yu_server_mirror.sh` ヲ設ケタリ。** ミラー同期ハ従前手作業ニシテ、
  **一度十一日放置サレ、削除済ミノ `crates/lan-cowork` 四十九件ヲ抱ヘタ儘ト成レリ**。
  手順ヲ script ヘ固メ、三ツノ規則ヲ其ノ中ニ書キ込メリ:

      git archive ヲ用ヰヨ（rsync ハ crates/.git・cache/・config.json ヲ巻キ込ム）
      push ハ SSH（gh ノ token ニ workflow scope 無ク HTTPS ハ拒マル）
      ミラー経由デ file ヲ初公開スル勿レ

- **初公開ノ門ヲ設ケタリ。** `--diff-filter=A` ノ件数ガ 0 ナラザレバ中止ス。
  内容ガミラー側デ新シキハ想定内ナリ（README ガ「private repo カラ mirror ス」ト述ブ）。
  害ハ**ファイルガ此処ヘ先ニ現ハルル**コトナリ。

### 検証

- v4.629.0 ノ `crates/` 差分三ファイルヲ同期セリ（`d014777`）。禁止経路四種トモ 0 件。
- **門ノ掴ミヲ実証セリ**――`PUBLIC_RELEASE_REF` ヲ古キ ref ヘ差シ替ヘ、
  未公開四十一ファイルヲ検知シテ中止スルヲ確メタリ。
- 冪等性ヲ確メタリ――再実行ハ `no change; mirror already current`。

## [4.629.0] - 2026-08-20

### Added

- **`PUT /api/analysis/servers/{id}` ヲ Rust ネイティブ化セリ。** 従前ハ 501 ヲ返ス stub
  （`analysis_servers.rs::update_server_fwd`）ニテ、Python 側 `core/analysis_api/server_crud.py`
  ノ `update_server` ガ実体ナリキ。`do_update` ヲ純関数トシテ切リ出シ、`do_add`／`do_remove`
  ト同ジ形ニ揃ヘ、`settings_lock` 下ノ read-modify-write ト `cleanup_discovery_metadata` ヲ通ス。

- **`legacy-default` 経路ニ於テ、暗号化サレタ儘ノ鍵ヲ保存スル。** 是ハ**意図的ナル差異**ナリ。
  Python ノ `_legacy_to_entry` ハ `decrypt()` ヲ呼ビ、`update_server` ハ其ノ復号済ミ entry ヲ
  `config.json` ヘ書ク。即チ**平文ノ API 鍵ガ盤上ニ残ル**（`save_config_json` モ `config_io::write`
  モ再暗号化セズ、両方トモ実測セリ）。Rust 側ハ格納形ノ儘 append シ、`all_servers` ガ応答時ニ
  復号スル既存経路ニ委ヌ。API 応答ハ同一、盤上ノ秘密ノ形ノミ異ナリ、斯ク在ル方ガ安全ナリ。

### Fixed

- **空ノ `ai_analysis` ガ claude_api ノ既定 entry ヲ捏造シ居タルヲ正セリ。** Python ノ
  `_legacy_to_entry` ハ falsy ナ `ai_config` デ `None` ヲ返スガ、Rust `all_servers` ハ
  `is_object()` ノミ検メ居タリ。`{}` モ object ナル故、従前ハ `Claude (claude-sonnet-4-6)` ヲ
  生ジ居タリ。読取専用ノ間ハ実害小ナリシガ、本版デ書込経路ガ native ト成ル以上、
  `PUT legacy-default` ガ有リモセヌ server ヲ config へ**書キ込ム**ニ至ル。

### Changed

- **台帳（`MIGRATION_PORTFOLIO_STATUS.md`）ヲ実測ニテ改メタリ。** 「Python 転送 22 件」ノ他ニ
  **第二ノ系統――Rust ガ 501 ヲ返ス 18 件**ガ在ル旨ヲ節ヲ設ケテ記シタリ。正本ハ
  `scripts/parity_no_python_known_fails.txt`（30 行）ニシテ、其ノ内訳ハ 501 十八件ト、
  **実装済ミナルニ FAIL シ居ル十件**ナリ。

- **`auto_stubs.rs` トイフ名ヲ証拠トスル勿レ。** 同ファイルニハ stub ト完全実装ガ同居ス。
  `/api/profiles` 九 route ハ「Rust stub。stub 503。」ト記録サレ居タルガ、実際ハ
  `write_profile_atomic` ニヨル完全実装ニシテ、FAIL ノ実体ハ harness ノ fixture 不整合ナリ。
  `POST /api/scan/resume` モ同ジク実装済ミ（501 ハ `scan_manager` 未初期化時ノミ）。
  allowlist 側ニ `STALE` ト注記シ、退役サスルニハ handler ニ非ズ fixture ヲ直スベキ旨ヲ記セリ。

### 検証

- `analysis_servers::tests::update*` **14 件**（実装者 8・監督者注入 6）全通過。
- **掴ミヲ実証セリ**――本番側ヘ三種ノ故障ヲ注入シ、其ノ都度当該試験ガ落ツルヲ確メタリ:
  `priority` 書込ヲ落トス（2 件 FAILED）／空 `ai_analysis` ノ検査ヲ戻ス（1 件 FAILED）／
  legacy 経路ガ平文鍵ヲ格納スル（1 件 FAILED）。復旧後ハ 14 件全通過。
- `analysis::` 17 件全通過（`GET /api/analysis/servers` ニ退行無キコト）。
- `cargo clippy -p yu-server` 警告無シ。

## [4.628.13] - 2026-08-20

### Fixed

- **CMA ガイドガ、冒頭デ危険ト宣言セシ設定ヲ、下段ノ表デハ「推奨」ト記シ居タルヲ正セリ。**
  同書ハ冒頭ニ「cmdline ニ `cma=` ヲ書ケバ VC firmware ノ mailbox ガ沈黙ス」ト述ベナガラ、
  §2 ノ失敗態様表ハ `cma=512M` ノ行ニ「← **推奨**」ヲ掲ゲ、其ノ表ガ 2026-04-15 当時ノ
  cmdline 方式ノ記録デアル旨ヲ表自身ハ何モ示サザリキ。**表マデ読ミ飛バシタ読者ハ、
  文書ガ危険ト述ベタ操作ヲ其ノ儘行フ**。十一言語全テニ伝播シ居タリ。
  Codex ノ停止時査閲ガ之ヲ指摘セリ（前版 4.628.12 ノ同期デハ本文ヲ写シタルノミニテ、
  此ノ矛盾ハ ja 原本ニ在リ続ケタル故、十言語ヘ其ノ儘運バレタ）。

- **表ヲ歴史的記録トシテ枠付ケ、「推奨」ヲ現行方法ヘ繋ギ直セリ。** 表ノ直前ニ
  「本表ハ 2026-04-15 時点ノ cmdline 方式ノ測定記録ナリ。NUMA 境界由来ノ上限（512M）ノ
  知見ハ今モ有効ナレド cmdline `cma=` ハ用フベカラズ。現行ハ `dtoverlay=cma,cma-512`」
  ノ注記ヲ置キ、表頭ヲ「（2026-04-15 当時ノ記録）」ト改メ、`cma=512M` 行ノ末尾ヲ
  「← 当時ノ推奨。**現在ハ `dtoverlay=cma,cma-512` ヲ用フルコト**」ト改メタリ。

- **容量ヲ指ス `cma=512M` 表記ヲ改メタリ。** 四箇所ハ設定文字列デハナク「CMA 512 MB」
  ノ意ナリシガ、cmdline 記法ノ儘ナル故ニ入力スベキ設定ト紛レ得タリ。平文ノ容量表記ヘ改メ、
  `cma=` ノ形ハ歴史的記録ノ表ト、削除・確認ノ命令ダケニ残セリ。

### Notes

- **検メ其レ自体ガ欠陥ヲ見逃セリ。** 本件用ニ書キタル検査器ハ十一言語悉ク OK ヲ返セシガ、
  故意ニ欠陥ヲ注入シテ試スニ三件中二件ヲ取リ零セリ。推奨語ノ走査ガ**表ノ内側ヲ除外シ居タリ**
  （元ノ欠陥ハ表ノ内側ニ在リ）、且ツ歴史注記ノ検メガ `>` ノ有無ノミヲ問ヒ、
  中身ヲ問ハザリキ。両者ヲ直シ、三件全テヲ検出スルコトヲ確メタ上デ再度全言語ニ掛ケタリ。

## [4.628.12] - 2026-08-20

### Fixed

- **公開 `PI5_NUMA_CMA_CONSTRAINTS.md` 十言語ガ、実害アル旧手順ヲ教ヘ居タルヲ正セリ。**
  前版（4.628.11）ニテ README ヲ `dtoverlay=cma,cma-512` ヘ改メタレド、其ノ README ガ
  「詳細ハ同書参照」ト誘導スル先ノ十言語ハ悉ク旧版ニシテ、`dtoverlay=cma,cma-512` ノ記述ハ
  **十言語トモ零件**、cmdline `cma=512M` ヲ書ケト教ヘ居タリ。2026-05 ノ Raspberry Pi firmware
  リグレッション以後、cmdline ニ `cma=` ヲ書ケバ VC firmware ノ mailbox ガ完全ニ沈黙シ、
  復旧ニハ電源ノ抜キ差シヲ要ス。**読者ガリンクヲ辿レバ結局旧手順ニ行キ着ク**状態ナリキ。
  Codex ノ停止時査閲ガ之ヲ指摘セリ。

- **部分改メニ非ズ、ja ヨリノ全面同期トセリ。** 十言語ハ省略ノ度合ヒ区々ニシテ（ru ハ表 22 行・
  it ハ 38 行、ja ハ 46 行）、章ノ有無自体ガ異ナル故、狙ヒ撃チノ patch ハ当タラズ、
  且ツ三百行ノ何処カニ旧 cmdline 手順ガ生キ残レバ危険ナリ。全言語 ja ト同ジ
  見出シ十九・code fence 十八・表四十六ニ揃ヘタリ。

- **ja 原本ノ壊レタル相対 link ヲ正セリ。** `hailo_genai_concurrent_2026-04-15.md` ヘノ参照ガ
  `../../../development/…`（repo 根ヲ指ス）ナリシヲ `../../development/…` ヘ改メタリ。
  十言語ヘ写ス前ニ直セリ。

- **翻訳ノ落トシ二件ヲ捉ヘテ復セリ。** zh-cn ハ NUMA 図ノ下枠ヲ八桝カラ七桝ヘ崩シ（上枠ト
  内容行ハ八桝ノ儘）、es ハ図中ノラベルヲ訳出セリ（他九言語ハ原文維持）。何レモ揃ヘタリ。
  code block 九個ノ命令行ガ ja ト byte 一致スルコトヲ全言語ニテ確メタリ（行末注釈ノ訳出ハ除ク）。

## [4.628.11] - 2026-08-19

### Fixed

- **公開 hailo README 十言語ガ ja ヨリ古ク、撤回済ミノ CMA 設定ヲ推奨シ居タルヲ正セリ。**
  十言語トモ「Pi 5 ノ推奨 CMA 上限ハ `cma=256M`、`cma=512M` ハ静カニ失敗ス」ト述ベ居タレド、
  参照先 `PI5_NUMA_CMA_CONSTRAINTS.md` ハ「`cma-512` ガ確認サレタ上限値デアリ推奨値」
  （2026-05-16 ニ overlay 経由デ再検証、`CmaTotal: 524288 kB`）ト述ベ、失敗スルハ
  `cma-1024` ト `cma-768` ナリ。**読者ガ其ノ儘従ヘバ確認済ミ上限ノ半分デ運用スル**誤リナリキ。
  併セテ設定箇所モ cmdline `cma=` カラ `config.txt` ノ `dtoverlay=cma,cma-512` ヘ改メタリ
  （2026-05 ノ firmware リグレッション対応）。

- **ja README 自身ノ内部矛盾ヲ正セリ。** 目次ノ `PI5_NUMA_CMA_CONSTRAINTS.md` 行ハ
  「推奨サレル `cma=256M`」ト記シ、同ジ file ノ既知事項節（`cma-512` ガ推奨）トモ、
  参照先文書本体トモ食ヒ違ヒ居タリ。十言語ヘ写ス前ニ原本ヲ正セリ。

- **十言語ノ目次ガ欠キ居タル四行ヲ補ヒタリ。** `HAILO_AUTO_REBOOT_PHASE05`・同 `_RUNBOOK`・
  `HAILO_LLM_SUBPROCESS_DEVLOG`・`HAILO_10H_ECOSYSTEM_ASSESSMENT` ノ四件ハ訳文自体ハ既ニ
  各言語ニ在リナガラ、目次カラ辿レザリキ。全言語十五行ニ揃ヘタリ。

- **`VDevice.release()` ノ項ヲ ja ノ現行文ヘ揃ヘタリ。** 十言語ノ多クハ Phase 0 PoC ノ実測
  （子プロセス kill・process exit・module unload ノ何レデモ回収サレズ、SIGTERM + 30 秒待機デ
  +8 MB ノミ、期待値 ≥250 MB）ト `sudo reboot` ノ記述ヲ欠ク簡略版ナリキ。訂正注記ハ
  重複サセズ同一項ヘ畳ミ込メリ。

## [4.628.10] - 2026-08-19

### Changed

- **HailoRT / driver 5.4.0 ノ CMA 検証記録ヲ公開 docs ヘ移シ、十一言語ニ配置セリ。**
  `docs/development/development_docs/HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` ヲ
  `docs/ja/hailo/` ヘ移シ（開発 docs 専用ノ frontmatter ヲ除キ、公開 docs ノ体裁ニ揃ヘタリ）、
  en / de / es / fr / it / ko / pt / ru / zh-cn / zh-tw ノ十言語ヘ訳シテ各 `docs/<lang>/hailo/` ニ置キタリ。

- **旧結論ヲ載スル `HAILO_CMA_LEAK_HAILORT_5_3_0.md` ノ訂正注記ヲ十言語ヘ及ボセリ。**
  同注記ハ ja ニノミ在リ、他十言語ハ撤回済ミノ旧結論（`release()` 後モ CMA ハ回収サレズ、
  推論中ニ約 14 MB/分デ漏レ、Pi 本体ノ再起動ノミガ確実ナ回復手段デアル）ヲ
  訂正ナキ儘ニ載セ居タリ。新文書ノミヲ公開セバ言語間デ矛盾スル故、同時ニ揃ヘタリ。

### Fixed

- **移動ニ伴ヒ切レル参照四箇所ヲ繋ギ直セリ。** 開発 docs 三件（`QA_HANDOFF.md`・
  `INVESTIGATION_PROCESS_RETRO_2026_08.md`・`HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`）ノ
  wikilink ハ移動先ヲ指セズ、公開側十一言語ノ `HAILO_CMA_LEAK_HAILORT_5_3_0.md` ハ
  `docs/development/development_docs/` 配下ヘノ路ヲ指シ居タリ。前者ハ新路ヘ、後者ハ同階層ノ相対 link ヘ改メ、
  `dev-docs-index.yaml` ヲ再生成セリ。

- **翻訳ガ落トシタル検証手順ヲ四言語ニテ復セリ。** 構造（見出シ・表・code fence ノ数）ハ全言語一致セシモ、
  中身ハ其レダケデハ守ラレザリキ。en ハ `sudo dmesg | grep CMA_DBG` ヲ散文ニ置キ換ヘ、
  es ハ `System.map` 複写ト `udevadm` 再読込ノ code block 二個ヲ散文化シ、
  it ハ `# → 5.3.0` 等ノ行内注釈四行ヲ削リ、ko ハ `glossary-candidate` ノ HTML 注釈五個ヲ公開文書ニ残シ居タリ。
  何レモ復シ、code block 十九個ノ ASCII 内容ト行数ガ ja ト一致スルコトヲ全言語ニテ確メタリ。

## [4.628.9] - 2026-08-19

### Fixed

- **`検証判定則` の引金が通常の再測定まで行き詰まり扱いしていた。** Codex の停止時査閲が指摘した。
  引金は「同一指標に依る**判定**が二度目に出れば発火」で、判定の**値**を問うていなかった。
  実験は同一指標を何度も測るのが常であり、A/B の対照測定・再現確認・回帰試験でも計数が 2 に達して
  発火する。**通常の再測定を「行き詰まりの兆候」として誤判定する規則**になっていた。
  図上演習は4版にわたってこれを合格と判定している。

  修正の過程で穴が2つ連鎖した。

  1. 「同一指標に依り、非終結判定（FAIL / 判定不能）が二度目」としたが、出典事例の第1回は
     版不一致で**指標を測る前に**判定不能になったもので「同一指標に依る判定」と読めない。
     FAIL は第3回の1回だけになり、rev1 と同じ不発火に戻る。計数の単位を指標から調査へ移し、
     **値では絞る（非終結判定のみ）、手段では絞らない（指標の異同を問わず）**形にした。
  2. その単位変更が下流3箇所へ伝播していなかった。`事前宣言` と `作業開始宣言.上申引金` が
     計数の鍵でない「指標名」を宣言させ、`発火時処置` の停止範囲「該指標に依る深掘り」に
     一意の指示対象がなく（第1回と第3回で指標が異なる）、さらに**リセット条件がないため
     計数が単調増加**していた（一度 2 に達した調査はその後の非終結判定がすべて閾値超過）。
     単位語を全箇所で揃え、`再発火`（最小反証実験を了えて判定基準へ反映した後に零から数え直す。
     実験は発火と同一作業単位で行い、先送りで再発火を止めない）を新設した。

  併せて範囲宣言を整理した。4キーに膨れており、うち `再測ハ引金ニ非ズ`（回帰試験は幾度重ねても
  発火させるな）と `引金ノ内`（失敗→成功→失敗は算入する）が**同一の系列に逆の指示**を与えていた。
  rev6 の引金が非終結判定のみを数えるため「測定そのもの」「PASS の反復」は既に対象外で冗長でもあった。
  4キーを `計数ノ外` 1キー3項へ統合して逆指示を解消し、`同時発火ノ順序` は `諮問接続` へ、
  `verdict符号` は `校正` へ吸収した（`前提再審` は 13→8 キー）。

  他に `記録必須.三値全域`（三値のいずれにも当てはまらない結果は「判定不能」とみなす。
  写像の穴を実時の判断に委ねないため）、`自動上申則.禁止` への例外1行（同則だけを読む経路には
  例外が見えなかった）を追加した。

### Docs

- **反省文書に §5.2・§5.3 を追加した。** §5.2 は「引金を主観から観測へ移したら、次にその観測が
  **何を数えているか**を問え。観測可能性は必要条件であって十分条件ではない。検算は、規則を
  **それが止めるべきでない作業に当ててみる**こと」。私も図上演習も、出典事例（止めるべき作業）にだけ
  当てて発火を確認し、止めるべきでない作業に当てていなかった。加えて出典事例の三判定が偶然すべて
  非終結だったため、**この事例は「判定を数える設計」と「行き止まりを数える設計」を区別できない**。
  規則が要求する「その指標が区別できないものは何か」を、検証 fixture の側に立てていなかった。

  §5.3 は「**置換の完了は、置換した文字列ではなく変更した概念で数えよ**」。単位変更のとき
  `指標名ト閾値` が 0 件になったことを assert で確認して伝播済みと報告したが、
  「別手段にて同一指標の判定を重ぬるは…」という根拠コメントが残っており、本文が
  「指標の異同を問わず」と言っているのに根拠は旧い狭い形のままだった。
  単位変更の未伝播が、それを直したはずの検証手段の側で一度だけ再現している。

  判定変遷表は rev1〜rev8 の8行になった（`未発火ノ検分` が唯一の器具として指定する表）。

---

## [4.628.8] - 2026-08-19

### Added

- **調査プロセスの反省を `検証判定則` として制度化した。** 2026-08-16〜17 の HailoRT/driver 5.4.0
  CMA 検証で第1〜3回の判定が誤り第4回で訂正された事例の反省を、`.claude/agent-workflows.yaml` の
  規則として取り込んだ（59→60節）。根拠事例は
  `docs/development/development_docs/INVESTIGATION_PROCESS_RETRO_2026_08.md`（新規）。

  根本原因は「初回 HEF ロード後の `CmaFree` 絶対回復量」という判定基準が、実験を回す過程で暗黙に
  確立され、一度も明文化されないまま3回の判定に使われたことである。基準が文字になっていれば、
  単発測定では「メモリ喪失」と「movable ページのページキャッシュ転用」を区別できないことが
  レビュー時点で見えた。判定を覆した操作は「低い `CmaFree` の状態からもう一度ロードする」だけで、
  ビルドもカーネル計装もパッチも要らず、最初の10分で実施可能だった。

  規則の骨は2つ。(1) 着手前に判定基準（指標・PASS/FAIL 境界・**その指標が区別できないもの**）と
  疑っていない前提を調査文書へ記す。(2) 記録した同一指標に依拠する判定が二度目に出たら深掘りを止め、
  判定基準を1つ選んで反証する最小実験を先に実行する。

  置き場所は `agent-workflows.yaml` 一箇所とし、`QA_HANDOFF.md` には規則を書かなかった
  （同文書は事案台帳であり、両方に書けば drift を作る）。反省文書 §6 の未処理実務2件
  （`acquire_genai` の事前 `CmaFree` チェック改修、旧フォーラム投稿の「HailoRT に拒否された」の
  発生源確定）のみ `QA_HANDOFF.md` の `(C)` 節へ起票した。

  `予行演習則` に従い design-advisor の図上演習を3回通した。rev1・rev2 とも NO-GO で、
  原因はいずれも「閾値を持つ条件を置かない」という判断だった。`design-review.yaml` は
  `aggregation: all_must_pass` で、その `escalation_timing_appropriate` が主観的確信に置かれた
  発火条件を観測条件へ差し替えることを求めている。また `自動上申則` の閾値には根拠
  （「1回は偶発的フレーク、2回は構造的問題」）と `accept_rate < 40%` による校正機構があり、
  数字を消すと校正の対象からも外れる。さらに rev1 の発動条件は**出典事例そのものに発火しない**
  ことも判明した（3回の判定値は「判定不能／限定的な試験のみ／FAIL」で文字通り一致していない）。

  併せて、同一セッションで「委譲先の計器を確認せずに書き込む」失敗を3度踏んだ経緯を記録した——
  rev1 は `仮設敵則` の腐敗検知の分母、rev2 は `自動上申則` の accept_rate、rev3 は書き込み側に
  弁別子を付けたが読み出し側（`ledger report` の label_cut 別集計）が rule を分離していなかった。
  3度目が最も見つけにくい。書き込み側の対処が済んでいるため、対処済みに見えるからである。

### Changed

- **`作業開始宣言.上申引金（着手前宣言）` に第4項を追加した。** `検証判定則.前提再審` の指標名と閾値を
  着手前に宣言させる。同欄の一括規定は発火時に `自動上申則` の処置（無限定の即停止）を課すため、
  この項のみ `検証判定則.発火時処置`（該指標に依る深掘りの停止と最小反証実験の先行実行）に従う
  例外を明記した。

- **`.claude/commands/yaml/debug.yaml` の `s1.action` に逆参照を追加した。** 「直らない」
  「原因がわからない」状態であれば着手前に `検証判定則.記録必須` を調査文書へ記す旨。
  義務を課す側に参照がないと、使用時点で規則が不可視になるため。

### Fixed

- **起票した2件が既に対処済みだったので撤回し、規則に「起票の前に現物を読む」を足した。**
  `QA_HANDOFF.md` へ起票した CMA 誤診断関連の2件（`acquire_genai` の事前 `CmaFree` チェック改修、
  旧フォーラム投稿の「HailoRT に拒否された」の発生源確定）は、main 側で**両方とも完了していた**——
  前者は v4.620.8（低 `CmaFree` でも `acquire_low_cma_observed` を記録して実ロードを続行し、
  拒否 tracker には factory が返した実 HailoRT host-memory error のみ記録。
  `tests/test_hailo_cma_false_positive.py` が固定）、後者は v4.623.1（追跡できる低 CMA 拒否は
  すべて自前の `acquire_rejected_low_cma`、factory 到達後の失敗は status 8 で
  host-memory error の status 3 ではない）。

  反省文書の「未処理」という記述を、実装と主記録を確認せずに引いたための誤りである。
  起票を残せば、対処済みの項を残件として蘇らせ、**同じ commit で新設した
  `検証判定則.文書統廃合`（同一主題で結論の異なる文書の並立を禁ず）に自分で違反する**。
  起票を撤回し、対処済みの事実と版だけを記した。

  併せて `検証判定則.判定反転時.同一作業単位ニテ起票スベシ` の第1項を
  「洗い出しに先立ち現行の実装と主記録を読み、対処済みなら起票せず版のみを記す」に改めた。
  反省文書 §4.4 は「旧結論に基づく実装を洗い出して起票せよ」と命じていたが、洗い出しの前に
  **現物を読む**ことを書いていなかった。「未処理」と書かれた記述は観測ではなく、
  書かれた時点の写しである。
## [4.628.7] - 2026-08-19

### Fixed

- **未終端の通常文字列が後続の無関係な引用符と対になり、その間の climb を隠していた**
  （Codex の stop-time review、**同じ門で七度目**）。門が**黙る**側である。

      let a = "opened here;      // この行に閉じ引用符が無い
      let p = Path::new(env!("CARGO_MANIFEST_DIR")).parent().and_then(|q| q.parent());
      let b = "later string";    // この引用符が最初のものを閉じる

  **字句解析の誤りではない。** ast-grep（tree-sitter＝実 Rust パーサ）へ同じ入力を与えると、
  **まったく同じ二つの引用符を対にする**。正しい字句解析器なら必ずこの範囲をマスクする。
  成立には invalid Rust が要る。よって走査器を八度書き直しても直らない。

  **六度目と七度目は直接矛盾する。** 六度目は「複数行 cooked string 内の climb を報告するな」、
  七度目は「その範囲で climb を隠すな」。形だけでは判別できない。
  「複数行 cooked string を疑う」は採れない —— `crates/` に**正当なものが 322 件**ある（複数行 SQL）。

  **形ではなく中身で解いた。** 複数行に跨る cooked string が `_MANIFEST_ROOT_RE` に合致する場合のみ
  マスクせず報告する。実測: 322 件中**合致は 0 件**。production の挙動は変わらない。

  この判断は v4.628.6 の fixture を一件意図的に反転させる。門はその範囲を「隠された実 climb」と
  区別できない以上、黙るのではなく**上申する**。理由を fixture の傍らに残した。

  自己診断は 32 ケース。独立検証で回帰 28 件＋監督者側の注入 4 件（単行文字列は依然マスク／
  manifest はあるが parent が無い場合は静か／複数行 raw string は対象外／SQL 文字列は静かなまま）。

---

## [4.628.6] - 2026-08-19

### Fixed

- **複数行に跨る通常文字列の中身が code として走査されていた**
  （Codex の stop-time review、**同じ門で六度目**）。**今回は偽陽性のみ**である。

  Rust は `"…"` も複数行に跨れる。走査が改行で文字列を打ち切っていたため、
  2 行目以降が code と判断され、文字列中に climb らしき記述があれば報告された。
  埋め込まれた hatch が後続を免除しない点と、文字列が閉じた後の実 climb が
  報告される点は正しく動いていた。

  終端を**エスケープされていない `"` のみ**とし、`\\` と `\` + 改行の継続を追跡する形へ改めた。

  **逆向きの危険を明示的に確かめた。** この修正は偽陰性を作り得る —— 閉じ引用符を欠いた
  文字列があると、走査がファイル末尾まで「文字列の中」と判断し、後続の実 climb を隠す。
  v4.628.5 で踏んだのがまさにこの型なので、次を試験で固定した:

  - 閉じられていない `"` の後の実 climb → **報告される**
  - コメント内の `"` や `don't` を文字列開始と誤認しない
  - char literal `'"'` を文字列開始と誤認しない

  自己診断は 27 ケース——六度分の穴すべてと、上記の逆向き 3 件を含む。

---

## [4.628.5] - 2026-08-19

### Fixed

- **byte / C の raw string が、その後ろにある実コードの escape を隠していた**
  （Codex の stop-time review、**同じ門で五度目**）。**前四回と種類が違い、これは偽陰性**である。

  前四回は「免除を偽造できる」＝門が余計に通す話だった。今回は `br#"…"#` などが正しく
  解析されず、**その後ろの実コードの climb が丸ごと報告されなくなる**。門が黙る側の失敗であり、
  いちばん悪い形である。実測:

      *** MASKED ***  br#"unpaired " quote"#;  の後の実 climb
      *** MASKED ***  br"unpaired " quote";    の後の実 climb
      *** MASKED ***  cr#"unpaired " quote"#;  の後の実 climb

  **原因は v4.628.3 で入れた条件**——「raw string 開始の直前が識別子文字なら raw string では
  ない」。`myvar` の末尾 `r` を誤認しないための条件だったが、**`b` と `c` は Rust の正当な
  接頭辞**（`br"…"` / `cr#"…"#`）であり、条件が広すぎた。

  Rust Reference のリテラル節を確認し、接頭辞を網羅した——`"`, `r`, `b`, `br`, `c`, `cr`、
  char、byte char。ライフタイム `'a` を char literal と誤認して以降を食い潰さないこと、
  閉じ引用符のない不正リテラルが後続コードを隠さないことも扱う。

  > **一つずつ潰すのをやめる、という判断が二度必要だった。** 四度目で「行単位をやめて
  > ファイル全体の状態付き走査へ」と種類を消したつもりだったが、**リテラルの語彙が不完全**
  > という別の穴が残っていた。記憶から列挙すると漏れる（現に漏れた）。**仕様を引いて
  > 網羅すること。**

  自己診断は 21 ケース——五度分の穴すべてを含む。

---

## [4.628.4] - 2026-08-19

### Changed

- **`crate-escapes-root` を行単位の判定からファイル全体の状態付き走査へ改めた**
  （Codex の stop-time review、**同じ門で四度目**）。

  指摘は「複数行 raw string で免除を偽造できる」。**11 通り試して、実コードの climb が
  偽造免除される形は再現できなかった** —— 免除された 4 形はいずれも climb 自体が
  文字列またはコメントの中身で、実コードではなかった。

  それでも直した理由は、**行単位で判定していること自体**が問題だからである。三度、
  指摘された穴だけを塞いできた（理由なし → 文字列リテラル → raw string）。行単位である限り、
  同種の形を探し続けることになる。

  各位置が `code` / 通常文字列 / raw string（複数行）/ 行コメント / block comment
  （複数行・入れ子）のどれに属するかを一度の走査で決める形にした。その上で

  - **climb は `code` 領域のものだけ報告する** —— 文字列やコメント内の見た目だけの climb は
    実コードではないので報告しない（誤検出も同時に消えた）
  - **hatch は comment 領域のものだけ有効**とする

  これで「行単位ゆえの取り違え」という**種類が丸ごと消える**。

  自己診断は 14 ケース。複数行 raw string の内外、複数行 block comment の内外、
  入れ子 `/* /* */ */` の深さ計数、raw string 内に埋めた hatch が後続の climb を
  免除しないこと、を含む。

---

## [4.628.3] - 2026-08-19

### Fixed

- **raw string で `crate-escapes-root` の免除を偽造できた**（v4.628.0 の欠陥。
  Codex の stop-time review が検出。**同じ門で三度目**）。

  v4.628.2 で「raw string（`r#"…"#`）は解析しない」と限界を書いたが、**この記述自体が誤り
  だった**。未対応で無視されるのではなく、raw string 内の**対にならない `"` がパーサの
  状態を反転させ**、以降が「文字列の外」に見える:

      let s = r#"unbalanced " quote // crate-escapes-root: <十分に長い理由>"#;
      let p = Path::new(env!("CARGO_MANIFEST_DIR")).parent().and_then(|q| q.parent());

  実測すると `r#"…"#` と `r##"…"##` の 2 形で**免除が通った**。「解析しないだけ」ではなく
  **偽造の手段**であり、限界の記述として事実に反していた。

  raw string を正しく解析する形へ改めた（`r` ＋ `#` × N ＋ `"` で開始し、`"` ＋ `#` × N で
  終了。開始直前が識別子文字なら raw string ではない）。誤っていた限界記述は削除した。

  **確かめていないことを限界として書かない。** 今回それで誤りを残した。

  自己診断は 12 ケース——偽造 2 形、balanced raw string、`r"…"`、通常の文字列リテラル、
  文字列内の `//`、`//` と `/* */` コメント、理由が空／短い、`r` で終わる識別子の誤認防止。

---

## [4.628.2] - 2026-08-19

### Fixed

- **`crate-escapes-root` の逃げ道が文字列リテラルでも成立していた**（v4.628.0 の欠陥。
  Codex の stop-time review が検出。**同じ門で二度目の「効いていない」**）。
  marker が行の**どこ**にあるかを見ていなかったため、次が免除された:

      let e = err("crate-escapes-root: not a comment, just a string literal");
      let p = Path::new(env!("CARGO_MANIFEST_DIR")).parent().and_then(|q| q.parent());

  理由文の長さは足りているので、v4.628.1 の 20 文字要件では防げない。

  marker は **Rust のコメント内にある場合のみ**有効とした。行を左から走査して `"` 文字列の
  内外を追い（`\"` のエスケープ込み）、**文字列の外にある** `//` または `/*` より後ろの
  marker だけを認める。

  **限界をコードコメントに明記した** —— raw string（`r#"…"#`）は解析しない。これは
  例外が気づかれずに紛れ込むのを防ぐ門であって、意図的な回避への防御ではない
  （この repo を編集できる者は門自体を消せる）。守るのは「コメントか、コードか」の境界である。

  自己診断に 7 ケースを置いた。抜け穴そのもの（文字列リテラル）に加え、
  `let url = "http://x"; // crate-escapes-root: …` のように**文字列内の `//` を
  コメント開始と誤認しない**ケースも含む。

---

## [4.628.1] - 2026-08-19

### Fixed

- **`crate-escapes-root` の逃げ道が理由なしで通っていた**（v4.628.0 の欠陥。
  Codex の stop-time review が検出）。判定が
  `if "crate-escapes-root:" not in line` の部分一致だったため、
  **`// crate-escapes-root:` とだけ書けば黙らせられた**。

  逃げ道の存在意義は「例外を足す者に**理由を書かせること**」である。空の marker を
  許すと、将来ここを増やす者が何も考えずに通せてしまう。**門はあるが効いていない**型。

  コロン以降を取り出し、空白を除いて **20 文字以上**を要求する形へ改めた。
  満たさない場合は逃げ道として認めず、`justification too short` を含めて報告する
  （単に「escape」と出すと、書いた本人が理由の不足に気づけない）。

  自己診断に**この抜け穴そのもの**を fixture として足した —— 理由なし／空白のみ／
  1 文字。いずれも検出されることを確認済み。現在の 2 箇所は長い英文なので通る。

---

## [4.628.0] - 2026-08-19

### Added

- **`crates/` が外へ出ることを禁じる門を新設した**（`crate-escapes-root`。門は 54 → 55）。
  `crates/` は `eauesque/yu-server` へミラーされ単独でレビューされるため、
  **外へ出てはならない**（逆に外側の repo が `crates/` の中を参照するのは構わない。
  `crates/` は yu_ai_manager に同梱されるため）。

  既存の `crate-include-paths` は `include_str!` / `include_bytes!` の**パス文字列**しか見ない。
  ところが v4.627.0 で見つかった欠陥は**テスト時に登る**形で、`cargo check` も `cargo build` も
  通り、**切り出した木で `cargo test` を回して初めて 5 件落ちた**。静的な include 検査では
  原理的に捕まらない。

  新しい門は `CARGO_MANIFEST_DIR` を起点とする `.parent()` の連鎖を数える。crate は全て
  `crates/<name>` 直下にあるので、**1 回は `crates/`（内側）で許し、2 回以上を脱出として落とす**。
  `.and_then(|p| p.parent())` の形も親取得として数える。

  **故障注入 3 方向で発火を確認済み**——(一) v4.627.0 の `repo_root()` を戻すと落ちる、
  (二) `detect.rs` の `.parent()` を 1 回から 2 回へ増やすと落ちる（境界が効いている証明）、
  (三) 逃げ道コメントを外すと落ちる（逃げ道が効いている証明）。

- 既存の脱出 2 箇所に理由付きの逃げ道を付けた。`mcp_client.rs` と `comfyui_bridge.rs` の
  `test_state()` は `project_root` を repo root に向けるが、これは**意図的**である——
  どちらも Python 実装（`extensions/` 配下）と突き合わせる試験で、ミラー単体では
  比較相手が存在しない。実際 `comfyui_bridge` の
  `delete_model_registry_entry_refuses_builtin_without_override` は、切り出した木で
  落ちる 5 件の 1 つである。

  > 検出された 3 件のうち `hailo_yolo_stream/detect.rs` は**門の誤検出**だった。
  > `.parent()` を 1 回だけ呼び `crates/Cargo.toml` を読むもので、`crates/` の中に留まる。
  > 「`.parent()` を呼ぶこと」ではなく「**2 階層以上上へ登ること**」が脱出である。

---

## [4.627.1] - 2026-08-19

### Added

- **`crates/yu-server/tests/fixtures/secret_store/` に README を追加した。**
  この fixture の鍵は**何も守っていない** —— `src/secret_store.rs` の試験が literal
  `python-fixture-secret` / `rust-to-python-secret` を暗号化・復号し、Rust と Python が
  暗号化秘密の形式で一致することを示すためだけに在る。公開しても露見するのは、
  隣の試験ソースに書かれている 2 つの文字列だけである。

  公開リリースの直前に気づいた: **素性を説明する生成器
  `scripts/internal/gen_secret_store_fixture.py` は `.public-exclude` により公開対象外**である。
  よって公開 repo には `secret.key` という名前のファイルだけが説明なしで置かれる。
  yu-server の分離先は**独立したセキュリティレビュー**のための repo なので、
  レビュアーが最初に見るべき情報が欠けているのは良くない。

  README には「何も守っていない」「なぜ commit したか（`.gitignore` の包括的 `data/` と
  `*.key` が飲んでおり、fixture が repo に無い鍵を参照していて fresh clone では
  原理的に通らなかった）」「再生成手順と、passphrase 環境変数を先に消す理由」を記した。

---

## [4.627.0] - 2026-08-19

### Changed

- **`crates/` をテスト時も自己完結させた**（`eauesque/yu-server` へのミラー分離の前提）。
  `crates/meta-extract/tests/conformance.rs` の `repo_root()` が `CARGO_MANIFEST_DIR` から
  **二つ上（= repo root）へ登り**、`tests/compat_goldens/meta_extract/` と
  `tests/fixtures/inspect_parity/` を読んでいた。

  **これは v4.620.12 で塞いだ repo root 越え `include_str!` と同型の欠陥が、
  コンパイル時ではなくテスト時に残っていたもの**である（`crate-include-paths` 門は
  `include_str!`/`include_bytes!` しか見ない）。切り出した木では 5 件が落ちていた。

  golden 6 件を `crates/meta-extract/tests/goldens/` へ、fixture 6 件を
  `crates/meta-extract/tests/fixtures/inspect_parity/` へ**移動**し、
  参照側（`conformance.rs`・`gen_meta_extract_goldens.py`・`make_conform_fixtures.py`・
  `parity_seed_helper.py`・`test_inspect_modal_parity.py`・`test_extension_contract_coverage.py`・
  `rust_builtin_map.yaml`・`compat_goldens/manifest.yaml`）を新しい位置へ向けた。

  **コピーではなく移動**である点が要点。生成器は元の場所しか見ないため、複製すると
  再生成で crate 側が黙って古くなり、conformance テストが「古い画像」に対して
  「新しい goldens」を検証することになる。

  golden の内容変化は `fixture` パス文字列のみ（crate 相対へ）で、解析結果の JSON は同一。
  fixture 6 件はバイト一致。

  **方向の原則**: `crates/` は外へ出てはならないが、**外側の repo が `crates/` の中を
  参照するのは構わない**（`crates/` は yu_ai_manager に同梱される）。この非対称が分離の要件。

- 現行仕様書 `docs/superpowers/specs/2026-06-13-python-rust-parity-mechanism-design.md` の
  旧パス参照 6 箇所を更新（`capability_matrix.yaml` を「conformance から外す理由の唯一の正」と
  する記述を含む）。実施記録である `docs/superpowers/plans/2026-05-08-...` は履歴なので触っていない。

---

## [4.626.3] - 2026-08-19

### Fixed

- **`profile_test` の status 写像に試験を足した**（v4.626.0 の `Known gaps` 二件目を解消。
  これで移植に伴う試験の負債はすべて閉じた）。
  写像を `profile_test_status(code) -> StatusCode` として切り出し、応答生成は
  `profile_test_error()` が必ずそこを通る形にした。
  `timeout` → 408、`ssrf_blocked` / `hf_unavailable` → 502、その他 → 400。

  **両方向で発火を確認済み** —— (一) 写像そのものを変える（`"timeout"` を別 status へ）と
  落ちる、(二) **応答が写像を通らなくする**（`profile_test_error` を固定 status へ）と落ちる。
  容量上限で踏んだ「述語は正しいが誰も呼んでいない」状態を避けるため、後者を必ず確かめた。

### Changed

- **移植の終端状態を `MIGRATION_PORTFOLIO_STATUS.md` に確定させた。**
  残存 Python 依存 22 件のうち純転送は 13 件で、**そのいずれも「本 repo でハンドラを移植して
  終わる」種類ではない**:
  - hailo-genai s2t 5 —— **別リポジトリ**（`infer_client` に transcribe が無く、
    yu-hailo-infer 側に endpoint を足すのが先）
  - hailo-semantic `caption/*` 3 —— 意図的に対象外（v4.496.0 spec）
  - `model/unload`・`llm/clear-context` 2 —— `group_id` 設計未決に従属
  - tagger-servers 2 —— **新規サブシステムが要る**。背後は LAN Cowork の推論メッシュ
    （peer 列挙・multipart 転送・remote client 5 種・`core/mesh_inference/` 928 行）で、
    Rust に対応物が一つも無い
  - `chat_search` 1 —— **移植すべきでない**。実体は `ddgs`（DuckDuckGo 検索ライブラリ）への
    薄いラッパで、Rust へ移すと DDG スクレイピングの自前実装か脆弱な crate の追加になる

  ⟹ **本 repo で移植可能なハンドラは出し尽くした。** 次の一手は移植ではなく、
  yu-server repo 分離の実行か、上記いずれかの前提条件を解くこと。

---

## [4.626.2] - 2026-08-19

### Fixed

- **容量上限の判定を Python と揃え、試験が seam を通るようにした**（v4.626.0 の
  `Known gaps` 一件目を解消）。
  Rust は `reqwest::Response::content_length()` を使っていたが、これは**ボディの
  サイズヒント**を返す。Python は `_content_length(resp.headers)` で**ヘッダを読む**。
  実網では reqwest がヘッダから導くので挙動は一致していたが、
  **構築した response ではヘッダを無視する**ため試験が書けなかった。
  `hf_declared_content_length()` を追加して `Content-Length` ヘッダを直接読む形へ改めた。
  Python 準拠であり、かつ試験可能になる。
  chunked 応答（ヘッダ無し）はストリーム中の累積チェックが引き続き受け持つ。

  `download_hf_file_with_request()` を seam として切り出し、偽 response を注入する
  試験を足した。**呼出を `if false {` にすると落ちる／ヘッダではなくボディヒントを
  読むよう戻すと落ちる**——両方向で発火を確認済み。

### Known gaps

- `profile_test` の status 写像（408/502/502/400）の試験は**未着手のまま**。
  `TODO.md` の `todo(test/wd-tagger)` に残る。

---

## [4.626.1] - 2026-08-19

### Fixed

- **同時ダウンロードが一時ファイルを共有し、壊れたモデルが恒久的に cached となり得た**
  （v4.626.0 の欠陥。Codex の stop-time review が検出）。
  `download_hf_file` の一時パスが `{name}.{pid}.tmp` で、**同一プロセス内では同じ
  destination に対して常に同一**だった。同時に 2 つの download が走ると
  (一) 双方の `File::create` が互いを truncate し、(二) 書込が交錯し、
  (三) `rename` で**半端なファイルが destination に載る**。
  しかも `cached` 判定は**存在するかしか見ない**（内容を検証しない）ため、
  **壊れたモデルが以後ずっと「cached」として返り続ける**。破損が恒久化するのが最も悪い。

  一時パス生成を `hf_temporary_path()` へ切り出し、`AtomicU64` のカウンタを足して
  `{name}.{pid}.{seq}.tmp` とした。各 download が自分だけの一時ファイルへ書き、
  `rename` は完全なファイルを last-writer-wins で置く（＝atomic replace の本来の意味論）。
  **カウンタを 0 に固定するとこの試験が落ちる**ことを確認済み。
  「cached は存在のみを信頼するので、一時パスの一意性が破損防止の唯一の砦である」旨を
  コメントに残した（将来ここを簡素化する者への警告）。

  ⚠ **Python 側（`model_download.py:281`）は同型のまま**である。`os.getpid()` を使うので
  同じ衝突が起こる。Python 併走モードでは現に起こり得るため `TODO.md` に起票した。

---

## [4.626.0] - 2026-08-19

### Added

- **wd-tagger の HuggingFace 取得 2 経路を Rust ネイティブ化**
  （`POST /api/wd-tagger/profiles/{id}/test`・`POST /api/wd-tagger/model/download`）。
  残存 Python 依存は **24 → 22**。Python 実装は残置（撤去は別作業）。

  SSRF 防御は Python `_hf_request`（`model_download.py:84`）の規則を逐一移した:
  scheme は http/https のみ／**userinfo を含む URL を拒否**／ホストは
  `huggingface.co`・`hf.co` への完全一致か `"." + allowed` 接尾辞一致／
  **リダイレクトを自動追従せず各ホップを再検査**（上限 5）／User-Agent 必須。
  土台は既存の `analysis_engines/http_client.rs::build_pinned_client` で、
  **解決 IP を pin して DNS rebinding を塞ぐ**（Python 側より強い）。`allow_local` は false 固定。

  併せて **Python に無い防御を足した**: `files[].name` は profile JSON 由来で保存先パスの
  一部になるため、保存先がモデルディレクトリ配下にあることを逐次 canonicalize で検証する。

  > **⚠ `/profiles/{id}/test` は名前に反して dry run ではない。** HEAD の後、`required` な
  > ファイルを**実際にダウンロードする**（上限 8 GiB）。Python 側がそうであるため
  > parity 優先で挙動は変えていない。挙動変更は利用者判断。

### Fixed

- 上記に伴い parity の ENDPOINTS 註記を「Rust forwarder」から実態へ改めた。

### Known gaps

- **サイズ上限の試験が seam を通っていない。** `hf_content_length_allowed` は述語として
  試験されているが、`download_hf_file` 内の**呼び出し**（`wd_tagger.rs:2205`）を
  `if false {` に差し替えても全試験が緑のままである。述語の正しさは固定されているが、
  誰かがそれを呼んでいることは固定されていない。
- **`profile_test` の status 写像（408/502/502/400）に試験が無い。**

  いずれも実装は正しく、上記以外のガード（ホスト allowlist・リダイレクト毎ホップ再検証・
  ホップ上限・パス脱出・cached）は**故障注入で発火を確認済み**である。
  詳細と再現手順は `TODO.md` の `todo(test/wd-tagger)` を見よ。

---

## [4.625.1] - 2026-08-19

### Fixed

- **retag のキャンセルが最大 63 件遅れて効いていたのを直した**（v4.625.0 の欠陥。
  Codex の stop-time review が検出）。`run_batch_worker_with_tagger` の cancel 判定が
  `idx % cancel_every == 0` で、retag は `cancel_every = batch_size`（最大 64）を渡していた。
  ⟹ cancel 後も**最大 63 ファイルが余分にタグ付けされ得た**。
  batch 側は `1` を渡していたため無傷で、retag だけの問題だった。

  **原因は移植仕様の側にある。** Python がチャンク境界で判定するのは
  `adapter.tag_images_batch(paths, batch_size)` が **1 チャンクを 1 回の推論呼出で
  まとめて処理する**ため途中で割り込めないからである。Rust は `call_wd_infer` を
  1 件ずつ叩くので、チャンク化は推論上の利益を一切生まず**キャンセルを遅らせるだけ**だった。
  Python の形だけを写し、その形が存在する理由を検めなかったのが誤り。

  `cancel_every` 引数を削除し、token は**毎ファイル前に**確認する（batch と retag で同一）。
  `batch_size` は API 互換のため範囲検証（[1,64] 外は 400）は続けるが、実行時には使わない。
  誤った註釈（「batch_size は意図的にキャンセル粒度」）を、上記の理由込みの説明へ改めた。
  **64 件の targets を即 cancel して処理数が 1 件以下であることを固定する試験**を足し、
  `idx % 64` 判定へ戻すと落ちることを確認した。

---

## [4.625.0] - 2026-08-19

### Fixed

- **`/api/search-grouped` が条件付き検索で 500 を返していた既存バグを直した**（retag 移植の副産物）。
  `fetch_matching_ids`（`search.rs`）は `"SELECT f.id FROM files f WHERE "` から組み立て、
  続く `push_where_filters` は **`" AND f.is_deleted=0"` から始まる**（`search.rs:638`）。
  よって生成される SQL は `WHERE  AND f.is_deleted=0 …` で **SQLite の構文エラー**だった。
  `has_conditions` が真になる要求（`q`・`tag`・`wd_model` 等が付いたもの）はすべて
  `search_grouped` で 500 になっていた。**テストが一つも無かったため出荷されていた** ——
  同関数への参照は定義・呼出 2 箇所・コメントのみで、既存の 2 試験は自前の
  `WHERE 1=1` builder を組んでおりこの経路を通らない。
  起点を `WHERE 1=1` へ改め、`search_grouped` を条件付きで叩く回帰試験を足した。
  **本番の当該 1 行だけを戻すと（試験補助の builder は無傷のまま）当該試験が落ちることを確認済み。**

- **`wd_tagger` job id の split-brain を解消した**（TODO.md の `todo(bug/wd-tagger)`）。
  `POST /api/wd-tagger/batch` は Rust native で `state.job_manager` に `"wd_tagger"` を立て、
  `retag/{batch,backfill,query}` は Python へ転送され Python 側 `job_manager` に同じ id を
  立てていた。別プロセスの別 map で `start_if_idle` は相手を見ないため、
  **「同時に一つだけ」の排他が壊れ**、`retag/cancel` と `batch/cancel` は id を共有しながら
  互いを止められなかった。retag async を Rust ネイティブ化し同一 `JobManager` の
  同一 job id を使うことで、排他も cancel も**構造的に**得られる形にした。

### Added

- **`retag/{batch,backfill,query,cancel}` を Rust ネイティブ化**（Python 転送を廃止）。
  残存 Python 依存は **28 → 24**（`rust-python-forwarders.txt`）。
  Python 実装は残置（撤去は parity 確認後の別作業）。
  - ワーカーは既存の `run_batch_worker_with_tagger` を再利用（tagger 関数で汎用化済み）。
    推論〜書込は `retag_single` の native 経路を共通関数へ切り出して両者で使う。
  - backfill の `NOT EXISTS` は**要求本文の model_id** を解決して使う
    （設定側の active model ではない）。`query_backfill_targets` を model 引数化したが、
    **batch 側は従来通り設定側 model** を使うことを試験で固定した。
  - `query` scope は**方針 C**（2026-08-19 利用者判断）——対象を「検索結果の 1 ページ」から
    「**検索条件に一致する全件**」へ改めた。`search()` には手を入れないので、
    regex 検索・folder ソート時の後処理乖離が原理的に生じない。**挙動変更である。**
  - `query_params` は JSON object で届くのに `SearchQueryRaw` は全フィールドが
    `Option<String>`（query-string 用）なので、`{"limit":50}` のような数値・真偽値が
    deserialize で落ちる。**移植で欠けやすい変換層**であり、scalar を文字列へ正規化して補った。
  - retag/query は `fetch_matching_ids` を直接呼ぶため、`search()` 本体が持つ事前ガード
    （`files` 不在なら空、`files_path_fts` 不在なら `also_path` を落とす）を飛ばしていた。
    同等のガードを retag 側にも入れた。**ガードを外すと試験が落ちることを確認済み。**

### Changed

- 応答封筒: retag の 4 経路は Python と同じく `api_result(json!({"data": {...}}))` と
  **`data` で包む**。`api_result` は payload のキーをトップレベルへ置き `data` を null に
  するため、包まないと `body["data"]["status"]` が null になる。
  共通化の際にこの包みが落ち、既存試験 `retag_single_native_success_uses_sanitized_model_and_nested_data`
  が回帰していたのを併せて直した。

- **意図的な parity 差異を 1 件登録した**（`verify_rust_compat.py` の ENDPOINTS）。
  Rust は未知の `model_id` を **404 `model_not_found`** で先に弾く（`retag_single` と同じ契約）。
  Python は弾かずに job を起動し、engine ロード時に失敗する。**Rust 側が正しい**ため差異を残し、
  受理ステータスへ 404 を加えて理由を註記した。
  なお本件は parity harness が**転送を native 化した瞬間に初めて比較可能になった**ために
  露呈したものである（転送していた間は自明に一致していた）。

---

## [4.624.2] - 2026-08-19

### Fixed

- **hailo-genai の実機検証を「未了」と誤報していた。** 利用者の指摘で CHANGELOG を検め直した結果、
  (A) 実機生成は **v4.618.4**、(A-2) `prompt_based` の tool 呼出しは **v4.620.1** で既に合格しており
  （`steps[]` に実際の `list_scan_roots`・`get_stats` 呼出しが入ることを実機で二度確認）、
  v4.620.11 の `QA_HANDOFF.md` 棚卸し表にも「解決」と明記されていた。
  根拠にした記述は v4.618.0 時点の「実機生成検証は未了」であり、**その後の 3 版を読んでいなかった**。
  `TODO.md` の hailo 着手不能項目 4 つのうち 1 を解決済みへ、`MIGRATION_PORTFOLIO_STATUS.md` §2-4 も訂正。
  残る blocker は `group_id` 設計のみで、それが塞ぐのは `model/unload` と `llm/clear-context` の 2 本。
- **残作業の規模を handler 本体から見積もっていた（同日に二度）。**
  `tagger_servers::{batch_tag,batch_cancel}` を「✅ 着手可・小」と記していたが、背後には
  `core/mesh_inference/` 928 行（peer 分散ディスパッチ・独自 job id `tagger_cluster`）があり
  **Rust 側に対応物が一つも無い**。`wd_tagger::{model_download,profile_test}` も同様で、
  実体は HuggingFace への外部通信＋SSRF 遮断＋`TaggerRegistry` 解決である。
  `hailo_genai_chat_search` に至っては DB ではなく **web 検索**（`search_web`）だった。
  ⟹ **設計分岐の無い小さな残項目は一つも存在しない。** 表を実態へ改め、
  「見積もる前に呼び先を辿れ」という注意書きを添えた。

### Changed

- **残存 28 件を「純転送 19」と「native + Python fallback 9」へ切り分けた。**
  後者（`hailo_genai_{llm_generate,v1_chat_completions,v1_embeddings,vlm_generate}`・
  `chat_send`・`files::serve_{original,preview}`・`wd_tagger::{tag_file,retag_single}`）は
  既に Rust ネイティブ実装を持ち、`infer_client` 不在や ZIP 内画像といった**特定条件でのみ
  Python へ落ちる degradation 経路**であって残作業ではない。**真の残作業は 19 件**、
  うち hailo-semantic `caption/*` 3 件は意図的に対象外なので実質 16 件。
  門は両者を区別せず凍結するが、ratchet としてはそれが正しい。
- **`retag/query` scope の設計分岐を方針 C で決着**（2026-08-19 利用者判断）。
  対象集合を「検索結果の 1 ページ」から「**検索条件に一致する全件**」へ改め、
  `fetch_matching_ids`（`search.rs:1263`）をそのまま使う。`search()` に手を入れないため
  regex 検索・folder ソート時の後処理乖離が原理的に生じない。件数上限は retag の `limit` が担う。
  **挙動変更である**旨と、UI 文言・`limit` 既定値（Python 側は 0＝無制限）の確認要を明記した。
  これで retag async 移植（`retag/{batch,backfill,query,cancel}`）は決定待ちが無くなり、
  `wd_tagger` job id の split-brain を構造的に消せる。

---

## [4.624.1] - 2026-08-19

### Fixed

- **前版で入れた `python-forwarder-ratchet` 門の誤検出二件を直した。31 → 28 件。**
  - **転送先を見ていなかった。** `fwd_get_sd` は Python ではなく**外部 Stable Diffusion
    バックエンド**（`sd_backend_url()`）へ転送する。名前が `fwd_*` だという理由だけで
    `/sd/{config,info,internal/ping}` の 3 件を Python 依存と数えていた。
    列挙器を「`config.python_url` へ**解決する**助力関数を呼ぶ handler」だけ数える形へ改めた。
    `fwd_ext_*` は自前の URL を持たず `fwd_get`/`fwd_post` へ委譲するだけなので、
    委譲の推移閉包を取る。
  - **cfg 違いの二重定義で本物が隠れていた。** `fwd_post_stream`・`fwd_post_passthrough`・
    `fwd_put`・`fwd_patch` は cfg 別に二度定義されており、片方は URL に触れない stub。
    助力関数の本体を**名前で辞書に入れていた**ため stub が本物を上書きし、それに依存する
    hailo-genai の 6 handler が一時的に一覧から消えた。名前ごとに全定義を保持し、
    **いずれかが `python_url` に達すれば該当**と判定する形へ改めた。
- **自己診断が本番経路を通っていなかった。** `_self_check` が数え上げロジックの**写し**を
  持っていたため、本番の判定規則を壊しても全 fixture が緑のままだった（故障注入 B が
  発火しないことで発覚）。判定を `_classify()` 一箇所に集約し、本番も自己診断も
  そこを通す。改めて注入すると A・B とも発火する。
  fixture は上記二件をそのまま加えて 5 件（`fwd_get_sd` は数えない／cfg stub は本物を隠さない）。

### Added

- **`wd_tagger` job id の split-brain を記録した**（`MIGRATION_PORTFOLIO_STATUS.md` §3）。
  `POST /api/wd-tagger/batch` は Rust native で `state.job_manager` に `"wd_tagger"` を立て、
  `POST /api/wd-tagger/retag/{batch,backfill,query}` は Python へ転送され Python 側
  `job_manager` に**同じ id** を立てる。両者は別プロセスの別 map で `start_if_idle` は
  相手を見ない（pull-merge も無い）。⟹ **「同時に一つだけ」の排他が壊れており**、
  `retag/cancel` と `batch/cancel` は id を共有しながら互いを止められない。
  standalone では retag/* が 503 のため顕在化しないが、Python 併走モードでは起こり得る。
  正しい直し方は retag async の Rust 移植そのものであり（同一 JobManager を使えば
  排他も cancel も構造的に得られる）、プロセス跨ぎ mutex は移植が消す配線なので採らない。
  移植を阻む設計分岐は `retag/query` scope 1 点のみ —— 詳細は同節に記した。

---

## [4.624.0] - 2026-08-19

### Added

- **残存 Python 依存を実測し凍結する門を新設**（`python-forwarder-ratchet`）。
  `scripts/internal/rust_python_forwarders.py` が Rust ソースから「`fwd_*` を呼び、
  **かつ** `main.rs` から到達可能な handler」を数え、`docs/development/rust-python-forwarders.txt`
  に凍結する。**2026-08-19 時点で 31 件**。
  門は三方向で落ちる —— (a) 新たな転送が増えた、(b) 移植したのに一覧から消し忘れた、
  (c) 登録されていない転送関数が残っている。**故障注入で三方向すべての発火を確認**し、
  復元後に PASS へ戻ることも確かめた。列挙器自体にも自己診断 4 件を持たせ、
  「未登録を live と数える」「`#[cfg(test)]` 内の `fwd_*` を数える」
  「動詞以外の helper 名（`fwd_post_wt` 等）を取り逃がす」という、
  本作業中に実際に踏んだ誤りをそのまま fixture にした。

### Removed

- **`auto_stubs.rs` の死んだ Python 転送関数 10 件を削除**（44 行）。
  hailo-yolo 8 件（`detect/{start,status,stop,search,clear,results}`・`labels`・`runtime`）と
  hailo-genai 2 件（`api/runtime`・`v1/models`）。いずれも移植完了後の置き去りで、
  `main.rs` は既に native handler へ結線しており、**どこからも呼ばれていなかった**。

### Fixed

- **テストの競合二件を構造で塞いだ**（いずれも本作業の変更とは無関係な既存欠陥）。
  - `cross_search`: `FILE_LAUNCHER` はプロセス大域なのに二つのテストが素で入れ替えており、
    互いのモックを観測して `open_file_uses_db_record_path_and_ignores_user_path` が落ちた。
    入替から復元までを 1 本の Mutex で直列化する RAII guard を導入し、
    **panic しても前の launcher を戻す**ようにした（手動の復元行は削除）。
  - `source_browser`: `tmp_root()` は共有ディレクトリを返すのに
    「Per-test unique dir」と**事実に反するコメント**が付いており、六テストが同じ場所へ
    書込・`remove_dir_all` していた。テスト名で分けた専用ディレクトリを返す形へ改めた。
  どちらも「緑が続いたから直った」ではなく**構造上起こり得ない**形にした
  （guard は lock を保持せねば入替できず、ディレクトリは名前で分離される）。
  傍証として全 suite 連続 9 回が緑（従前は数回に一度落ちた）。

- **移植台帳の読み方を訂正した。** `rust-migration-inventory.yaml` の `status` は
  **Rust ソースを一切見ていない** —— `carry_over_status()` が前回 YAML の値を持ち越し、
  手書きの `NATIVE_ROUTES`（34 件）/ `NATIVE_PREFIXES`（1 件）だけが `native` へ昇格させる。
  Rust 側 handler が入ってもその表を編集しなければ `proxied` のまま腐る。
  実際、非 native 50 件のうち **22 件は既に `main.rs` に登録済み**だった。
  生成器の docstring にこの盲点を明記し、代わりに使うべき計測（上記 txt）を指した。
- **`TODO.md:54` の「hailo-semantic ハ NO-GO 記録済ミ」は誤り。**
  `RUST_MIGRATION_STANDALONE_EXCLUSION_SCOPE_DESIGN.md` §4 は 2026-07-18 に再審査され
  **GO へ改訂**、v4.496.0 で `usearch` + `clip_index.rs` + `/v1/infer/clip-{image,text}` により
  Rust ネイティブ化を完了している。残る `caption/*` 3 本は同 spec が意図的に対象外としたもの。
  元記述は消さず日付付きの訂正を下に足した。
- **「hailo-yolo 完了」は stream 限定ではない。** detect 8 経路も `main.rs:2707-2748` で
  native 結線済み。`MIGRATION_PORTFOLIO_STATUS.md` の当該節を訂正した。
  本書の旧版がこれを「Python 転送のまま」と誤記した原因は、**登録の有無を確かめずに
  `fwd_*` の呼出だけを数えた**ことであり、新設の列挙器はまさにその誤りを塞ぐ。

---

## [4.623.0] - 2026-08-17

### Fixed

- **yu-server ノ赤キ試験十二件ヲ悉ク直シ、main ヲ緑ト為セリ**（1341 passed / 12 failed → 1353 passed / 0 failed）。**十二件悉ク単独・直列ニテモ落ツル決定論的失敗ニシテ、並列干渉ニ非ザリキ。** 内訳ハ左ノ如シ:
  - **nai_bridge 五件** —— 試験ガ旧キ `{"data": {...}}` 包ミヲ前提トセリ。`api_ok` ハ Python `api_success` 互換ニテ payload ヲ**トップレベルヘマージ**シ `data` ハ null ノ儘ナリ。併セテ **`api_ok` ノ挿入順ヲ是正セリ** —— payload ヲ先ニ入レ base ヲ後ニ上書キシ居タル故、payload ガ `data`／`ok`／`error` ヲ持テバ黙シテ潰レ、Python（base ヲ payload ニテ update＝payload ガ勝ツ）ト逆ナリキ。兄弟ノ `sd_webui_bridge.rs:68` ハ正シキ順ナリ。現状之等ノ鍵ヲ載スル呼出ハ無ク実害ハ出デ居ラザレド、地雷ナル故除ケリ。
  - **scan_roots 一件** —— `/home/pi` ヲ直書キシ `exists == true` ヲ主張シ居タリ。書カレタル Raspberry Pi 以外ノ何処ニテモ満タサレヌ。試験ガ自ラ作ル一時ディレクトリヘ改メ、DB 行モ其ノ下ヘ入レ、ネスト算入・削除除外ノ意図ハ保テリ。
  - **tags 一件** —— 204 → 200 `{"ok": true}` ハ `197ba88ef` ニテ「parity schema 適合」トシテ**意図的ニ**変ヘラレ commit 本文ニモ明記アリ。試験ノミ取リ残サレ居タリ。parity harness ノ註（尚 204 ト記ス）モ改メタリ。
  - **pages 一件** —— `expand` モードノ Python 中継ヲ検ムル試験ナリシガ、`expand` ハ UI ニモ Python 拡張ニモ存在セズ、handler ハ `nai_to_sd`／`sd_to_nai` 以外ヲ 400 トス。死ンダ機能ノ試験ナル故削除ス（未知 mode ノ振舞ハ既存試験ガ固定ス）。
  - **annotations 一件** —— 試験ハ「値」検索ヲ期待セシガ、実装ハ Python 互換ニテ**ファイル path** ヲ LIKE 検索ス（`notes_data` ニ註記アリ）。検索語ヲ path 断片ヘ改メタリ。
  - **settings 一件** —— 導入時（`e28ab37f7`）ハ試験用 router ニ `secrets/export` ヲ登録シ 501 ヲ期待シ居タルニ、後ノ改変ニテ登録ヲ除キ乍ラ期待ノミ 404 ヘ書キ換ヘラレ、**実行サレザル儘残リ居タリ**。path 一致・method 不一致ハ axum モ Quart モ 405 ナル故、405 ヘ改メ理由ヲ註ス。
  - **secret_store 二件** —— 次節。
- **secret_store ノ golden fixture ガ**「**何処ノ機械ニテモ通ラヌ**」**状態ナリシヲ直セリ。** `tokens.json` ハ key_id `k_20260610b7a1daa4` ヲ指スニ、ディスクノ `keyring.json` ニハ `k_20260612484cf0f3` シカ無ク、**鍵ハ 2026-06-13 ニ別ノ鍵ニテ上書カレ居タリ**。原因ハ構造的ナリ —— `.gitignore` ノ包括的 `data/` 規則（及ビ後段ノ `*.key`）ガ鍵ヲ飲ミ、**golden vector ナルニ鍵ガ repo ニ入リ居ラザリキ**。新規 clone ニテハ `data/` 自体無ク、原理上通ラヌ。

### Added

- **`scripts/internal/gen_secret_store_fixture.py`（fixture 生成器）。** `TAGDB_DATA_DIR` ヲ fixture ヘ向ケ（Rust モ同ジ変数ヲ見ル故、Python ノ書ク場所ヲ Rust ガ読ム）、`YU_SECRET_PASSPHRASE` ヲ明示的ニ除キ（環境ニ残レバ鍵導出ガ passphrase 経路ト成リ、他者ノ復号シ得ヌ fixture ガ黙シテ出来ル）、key_id ヲ固定シ（再生成ノ度ノ差分ヲ避ク）、v2 トークンハ本番ノ `secret_store.encrypt()` ニ作ラセ形式ヲ production コード由来ト為ス。**自己診断**トシテ Python 自身ガ書キタルモノヲ読ミ返セルコトヲ確メテヨリ書キ出ス（Python ニテモ復号シ得ヌ fixture ヲ渡セバ Rust 側ガ幻ノ欠陥ヲ追フ故）。鍵ハ試験専用ニシテ literal `python-fixture-secret` ヲ暗号化スルノミ、何モ守ラズ。

### Changed

- **`.gitignore` ニ fixture 鍵ノ否定規則ヲ二箇所加フ**（`data/` 規則ノ直後ト、後段 `*.key` ノ直後。gitignore ハ**後ノ規則ガ勝ツ**故、片方ノミニテハ `*.key` ガ再ビ除外ス）。既存ノ update 署名公開鍵ノ例外ト同ジ形ナリ。
- **`encrypt_uses_python_generated_keyring_fixture` ガ key_id ヲ直書キシ居タルヲ、`tokens.json` ヨリ読ム形ヘ改ム。** 直書キナレバ fixture ヲ再生成スル度ニ落ツル。
- **`comfyui_bridge.rs` ノ `proxy_generic` 及ビ `proxy_to_python` ヲ削除セリ（四十八行）。** 前者ハ呼出零ニシテ、後者ノ唯一ノ呼出ガ前者ナリキ。

### Docs

- **`BUILTIN_EXTENSIONS_RUST_MIGRATION_PLAN.md` ノ E5／E6b／E7 ヲ完了ヘ改ム。** 三ツトモ既ニ完了シ居タリ —— E5 ハ `sse/`（889 行）ト `jobs/`（`JobManager`、523 行）ガ実装済ミニシテ本番配線モ済ミ（`job_manager` 参照 122 箇所・20 route 超）、**「実装着手可」ハ E6 ✅ ト矛盾シ居タリ**（E6 ハ E5 ヲ前提トスル故）。E7 ハ `meta-extract` ニ五パーサ、前処理モ `prompt_parse.rs` ヘ移植済ミ、Rust scan モ `/api/scan/start` ニテ本番配線済ミ。**但シ E7 ノ受入条件「実 DB 各 100 件ニテ Python パーサト一致」ノ検証記録ハ見当タラズ**、其ノ旨ヲ記ス。

## [4.622.0] - 2026-08-17

### Fixed

- **SD proxy ニ gateway scope gate（L3）ヲ結線セリ。** `crates/yu-server/src/routes/gateway_proxy.rs` ノ `sd_handler` ハ loopback ・ Origin ・ path allowlist ノ三層ヲ持チ乍ラ、**`check_request` モ `has_scope` モ一度モ呼バズ**、`/sd/sdapi/v1/{*sub}` トシテ本番配線サレ居タリ（`main.rs:3157`）。依リテ loopback ノ任意ノプロセスガ gateway 鍵無シニ `POST /sdapi/v1/options`（走行中 model ノ切替）ヲ叩キ得、`sd:query` シカ持タヌ鍵デモ `sd:admin` 相当ガ通リ、`gateway.auth.allow_loopback_bypass: false` ハ無視サレ居タリ。
  - **欠陥ノ実体ハ「gate ノ書キ忘レ」ニ非ズ「移植時ニ写像ノ落チタルコト」ナリ。** Python ノ `core/gateway/sd_proxy.py:SD_ALLOWED_ENDPOINTS` ハ `dict[(method, path) -> Scope]` ニシテ、20 path 各々ニ `sd:generate`／`sd:query`／`sd:admin` ヲ割リ当ツ。Rust 側ハ之ヲ `&[(&str, &str)]` トシテ移シ、**Scope 列ノミ落チ**、表ガ素ノ allowlist ト成リ居タリ。表ヲ三ツ組ヘ戻シ `sd_scope_for()`（Python `get_sd_scope` 相当）ヲ設ク。
  - **判定順序ハ Python（`routes/gateway_sd.py:179-198`）ト同一トス** —— Origin → path→scope 引当（未登録ハ **404**。認証ヨリ先ニ答フル故、未認証ノ者ガ転送対象 path ヲ数ヘ得ズ）→ `check_request` → `has_scope`。L3 ハ **body ヲ読ム前**ニ置ク（拒ム請求ニ無制限ノ upload ヲ先ニ払ハヌ為）。`allow_loopback_bypass` ハ Python 同様 config 値ヲ尊重ス。
  - **comfy／gradio／agentmemory ハ Rust 側ニ proxy handler 自体ガ無ク**、Python ヘ落チ（standalone ニテハ 503）、Python 側ハ四経路悉ク gate 済ミナル故、穴ハ SD 一本ノミナリキ。
  - **挙動ノ変ハル配備アリ**: `gateway.auth.allow_loopback_bypass: false` ヲ置キ、且ツ Rust ノ SD proxy ヲ用ヰ居タル者ハ、以後 `sd:generate`／`sd:query`／`sd:admin` ノ孰レカヲ持ツ鍵ヲ要ス（従前ハ鍵無シニテ通リ居タリ）。既定（bypass 有効）ノ配備ハ従前ノ儘ニシテ、試験 `sd_without_bearer_still_works_by_default` ガ之ヲ固定ス。

### Added

- **SD scope gate ノ試験九本。** 中核ハ (一)`sd:query` 鍵ガ `POST /sdapi/v1/options` ニテ 403 `insufficient_scope`（表ヲ二ツ組ヘ戻セバ此レガ通ル）、(二)`sd:generate` 鍵ガ query／admin path ヘ届カヌコト、(三)未登録 path ハ bypass 断チテ鍵無キ時モ 401 ニ非ズ **404**（順序ノ固定）、(四)拒マルル請求ハ body ヲ読マヌ（読メバ即 error ト成ル body ヲ与ヘ 401 ヲ確ム）、(五)**Python `sd_proxy.py` ヲ実際ニ読ミテ写像ヲ突合スル試験**（片側ノミ広グレバ落ツ。件数一致ノ assert ガ解析器ノ黙シタル失敗モ捕ラフ）。
  - 故障注入三種ニテ検知力ヲ確メタリ —— `has_scope` 無効化=2 件発火、表ノ緩和（admin→query）=3 件発火（写像突合モ同時ニ落ツ）、404→401 ノ順序破壊=1 件発火。

## [4.621.2] - 2026-08-17

### Docs

- **HailoRT 5.4.0 CMA 検証記録を再整理セリ。** 旧診断資料への訂正注記、適用範囲、29 MB→512 kB の未解明観測、A/B 比較結果と非対称性、符号統一、数値化した FAIL 閾値を追記し、フォーラム用ドラフトと旧日本語記録にも §8 参照の撤回注記を付した。

## [4.621.1] - 2026-08-17

### Docs

- **`MIGRATION_PORTFOLIO_STATUS.md` 初版ノ誤記ヲ訂シ、招キタル TODO 二項ヲ done ヘ変換セリ。** 初版ハ `meta_source` 語彙統一ヲ「🔴 未着手・E2 ハ判断不要ニテ着手可」ト記シタレド、**E1〜E7 ハ 2026-08-09 ニ全段決着済ミ**ナリ（E2 ノ修復 migration ハ `crates/tagdb-core/src/migrations/004_meta_source_vocabulary.sql` ニ在リ `db/migrate.rs:29` ニテ登録済ミ、v4.599.13）。原因ハ TODO.md ノ `todo(bug/yu-server)` 二項ガ決着後モ done ヘ変換サレズ残リ居タルこトナリ —— **同書 §6-1 ガ自ラ警告スル罠（`todo(` 接頭辞ハ完了報告ニモ用ヰラル）ソノモノ**ニ掛カリタリ。実コードヲ見テ居レバ防ゲタリ。併セテ doctor 回収（v4.621.0）及ビ枝整理ノ結果ヲ §5 ヘ反映シ、`origin/worktree-wd-tagger-yu-infer-spec`（62 commits、main ハ其ノ後 846 commit 進ミ居ル）ヲ判断保留トシテ記ス。

## [4.621.0] - 2026-08-17

### Added

- **`/api/diagnostics/doctor` ノ起動・照会 二 route ヲ native 実装ヘ改メタリ**（`worktree-hailo-infer-wiring` ニ四日間埋モレ居タル実装ノ回収。2026-08-13 ノ作業ナリ）。従前ハ無条件 501 ヲ返ス**空ノ handler** ナリシガ、router ニハ配線済ミナリシ故、静的走査器ハ之ヲ native ト数ヘヰタリ —— 未配線 forwarder ニ非ズ、空ノ handler ナリキ。検査本体ハ既ニ `mcp/diagnostics.rs` ヘ native 移植済ミナリシ故、`collect_checks` ヲ切リ出シテ再用シ、一行モ書キ直サズ。加ヘタルハ job registry（上限十件・FIFO 追出シ。既存 key ヘノ更新ハ順序ヲ動カサズ、Python ノ `OrderedDict` ニ倣フ）ト Python 形式ノ `render_markdown`／`render_json`／`write_report_files` ナリ。
  - **意図的差分（互換性計上）**: `results` 配列ノ各要素ニ `name` ヲ含ム。Python ノ `CheckResult` ハ `status`／`message`／`fix_hint` ノ三 field ノミナリ。診断成果物トシテ情報ノ増ユルノミナル故、之ヲ容ル。
  - 検査ノ範囲ハ standalone Rust ノ部分集合ナリ（Python toolchain・torch・CUDA・ONNX ノ検査ハ対象外）。
  - 併セテ枝ノ CHANGELOG ガ主張セル「forwarder 未配線 十一 route」ハ**既ニ別途 main 入リ済ミ**ナリ（`187e7dd19`・`8261397a2`・`d5d1f2712`・`5487d8a56`・`0d5cef77c`）。枝ハ版番号 4.615.0 ヲ main ト重複シテ用ヰ居タル故、本版ヘ立テ直シ、重複部分ハ採ラズ。

## [4.620.14] - 2026-08-17

### Docs

- **並行スル移植・移行スレッド十二件ノ現況ヲ一枚ニ棚卸シセリ（`MIGRATION_PORTFOLIO_STATUS.md`）。** 各スレッドノ設計ハ夫々ノ正本 doc ニ在レド、「今何処マデ進ミ、次ニ何ガ着手可能カ」ヲ横断シテ見ル面ガ無ク、TODO.md ノ `todo(` 接頭辞ガ完了報告ニモ用ヰラルル為ニ件数モ実態ヲ映サザリキ。route 台帳ハ `gen_route_inventory.py` ヲ再走ラセ差分ゼロヲ確メタル上デ 438 中 388 native・proxied 46 ト記シ、**台帳自身ノ盲点**（Python 定義ヲ撤去シ了ヘタル endpoint ハ台帳カラ消ユル故、完了スル程見エナク成ル）ヲ明記ス。併セテ**正本ト実態ノ食ヒ違ヒ六件**ヲ挙グ —— hailo-genai ノ native 分岐（`auto_stubs.rs:2291`）ヲ「今モ Python forwarder」ト記ス節、lan_cowork ヲ「部分実装」ト記ス Tier C 表、既ニ解決セル TODO 三件。**未 merge ノ実装一本**（`worktree-hailo-infer-wiring` ノ doctor native）モ発見セリ。

## [4.620.13] - 2026-08-17

### Fixed

- **`config.toml` 配備ニテ、`config_io` ヲ経由セヌ本番読取点九箇所ガ尚空ノ設定ヲ見居タルヲ修ス（前版ノ修正漏レ）。** v4.620.12 ハ `config_io` 自身ヲ拡張子分岐サセタルモ、`config_path` ヲ自前ニテ読ミ `serde_json::from_str` ヘ渡ス経路ガ残リ居タリ。就中 `auth/apikey.rs:50` ハ**Bearer API キーガ一ツモ一致セズ成ル**認証経路ナリ（キー一覧ガ空ト成ル）。他ハ `ext_config.rs`・`scan_roots.rs`・`analysis_servers.rs`・`wd_tagger.rs`・`auto_stubs.rs` 三箇所・`misc_admin.rs`。悉ク `config_io::parse` / `parse_strict` 経由ヘ寄セタリ。

### Added

- **`config_path` ノ自前 JSON 解析ヲ阻ム門（`scripts/internal/config_read_format.py`）。** 読取ノ中枢ヲ直セドモ各自デ読ム呼出側ガ残レバ直リ居ラヌ故、網羅性ヲ門ニテ固ム。apikey ノ壊レ居タル形ヲ戻ス故障注入ニテ発火ヲ確認シ、自己診断ハ検出器自身ノ正規表現ノ瑕疵ヲ一件捕ラヘタリ。

## [4.620.12] - 2026-08-17

### Fixed

- **`config.toml` ヲ用フル配備ニテ、route 側ノ設定読取ガ悉ク空ト成リ、書込ガ TOML ヲ JSON ニテ潰シ居タルヲ修ス。** `main.rs` ハ `config.toml` 在ラバ之ヲ `config_path` トシテ `AppState` ヘ載スルニ、`config_io::load()` ハ拡張子ヲ見ズ `serde_json` ニテ読ミ居タリ。故ニ設定ハ空オブジェクトト成リ、続ク `config_io::write()` ガ其ノ `config.toml` ヘ JSON ヲ書キ、次回起動デ TOML トシテ解ケヌ状態ヲ生ジ居タリ。拡張子ニテ分岐シ、TOML ハ TOML トシテ読ミ書キスル形ト為ス。TOML ニ表現シ得ヌ値（`null`）ハ**書込ヲ拒ミ**、既存設定ヲ残ス（黙シテ落トセバ設定ガ消ユル故）。
- **背景ジョブノ経過時間表示ヲ下部進捗バーヘ復シ、一秒刻ミト為ス。** 表示ハ既ニ `nav/job-progress-ui.ts` ヘ移設サレ乍ラ経過時間ヲ一切描画セズ、旧根本原因タリシ `scan-banner/ui-render.ts` ハ caller ゼロノ死骸ナリキ。ポーリング値ト `Date.now()` ヲ anchor トシ ticker ニテ外挿、次ノポーリングデ再 anchor ス。SSE 由来ノ `elapsed_seconds: 0` デハ再 anchor セズ走行中ノ時計ヲ零ヘ戻サズ、終了時ハ最終値デ凍結ス。死骸ト成リタル `ui-render.ts` `ui-utils.ts` ヲ削除セリ。

### Changed

- **yu-server ノ repo root 越エ `include_str!` ヲ全廃ス（分離ノ前提条件）。** 実測ハ三ファイル八箇所ナリキ。本番二箇所（`misc_admin.rs`）ハ実行時読取ヘ移シ、設定スキーマハ既存ノ `routes::settings::schema_path()` ヲ再利用、拡張 manifest ハ `extensions/<name>/extension.json` ヨリ読ム（欠落時ノ既定ハ従前ト同ジ）。golden fixture ハ `crates/yu-server/tests/fixtures/` ヘ移シ、拡張テンプレート試験ハ実行時読取（`extensions/` 自体ガ無キ時ノミ skip、在ルニ当該ファイル無キ時ハ落ツ）ト為ス。

### Added

- **`include_str!` ノ crate 越境ヲ阻ム門（`scripts/internal/crate_include_paths.py`）。** Cargo ハ `include_str!` ヲ依存ト見ザル故、越境シテモ build モ test モ通ル。素ノ相対形ト `concat!(env!("CARGO_MANIFEST_DIR"), …)` 形ノ双方ヲ検メ、故障注入ニテ発火ヲ確認セリ。
- **文書カラ静カニ消ユル endpoint ヲ捕ラフル門。** `check_native_only_endpoints.py` ハ manifest 自身ノ挙グル `rust_module` ノミ走査シ居タリ。commit 済ミ生成物 `docs/ja/api/all-endpoints.md` ヲ HEAD ヨリ読ミテ基準線トシ、「基準線ニ在リ・現生成物ニ無ク・Rust ガ尚提供スル」path ヲ違反トス。Flask ト axum ノ path 記法差ハ正規化シテ吸収シ、正規化ヲ殺ス改変ハ自己診断ガ捕ラフ。

## [4.620.11] - 2026-08-17

### Docs

- **Hailo 5.4.0 CMA 検証記録ノ暫定判定ト最終判定ヲ分離シ、時系列ニ再編セリ。** 第1〜4回ノ判定変遷ヲ一表ニ集約シ、第3回ノ `VERDICT: FAIL` ヲ旧診断出力ト明記、第4回ノ vanilla / `FOLL_LONGTERM` A/B ヲ唯一ノ最終判定トシタ。原因候補ノ除外ハ最終判定ニ非ザルコトヲ明示シ、旧「次ノアクション」ヲ実測結果ニ合ハセテ改訂、v5.3.0 復旧及ビ実験 patch 適用・vanilla 復元手順ヲ付録ヘ分離シタ。
- **`QA_HANDOFF.md` ノ「未修正」「未検証」項ヲ実コードニ照ラシテ棚卸シシ、最新状態ヘ改メタリ。** 冒頭ニ実測日附キノ棚卸シ表ヲ置キ、(A) hailo-genai 実機生成ト (A-2) `prompt_based` tool 呼出シハ既ニ実機合格（v4.618.4 / v4.620.1）ナルニ節冒頭ガ「未着手・501」ノ旧記述ノ儘ナリシヲ状態註記ニテ是正ス。`config.json` ノ read-modify-write 調停ハ `AppState::settings_lock`（`state.rs:154`、55 箇所）ニテ解決済ミ、`routes/.claude` ノ 208MB 堆積ハ解消済ミト改メ、逆ニ未修正ノ儘ナル項（スキャンバナー経過時間・repo root 越エ `include_str!`・`main.rs` ノ 14 本目設定ロード・win64 実機三項目・numkong 環境依存 FAIL）ハ確認日ヲ付シテ据置ク。行番号ノ移動（`misc_admin.rs:34,36`→`30,32`、`main.rs:393`→`411`）モ再測シテ更新ス。

## [4.620.10] - 2026-08-17

### Fixed

- **Hailo WebUI ニ残存セル「低 `CmaFree`」・同時利用禁止ノ誤表示ヲ除去。** GenAI画面ノCMA残量バナー及ビ11 localeノ警告key、YOLO/S2T画面ノ「YOLO・S2T・LLM同時起動デhangシfull reboot必須」表示トS2T表示切替ヲ削除シタ。同一shared VDevice上ノ複数model利用ハ実機検証済ミデアルタメ、実HailoRT host-memory allocation error発生時ノミ不要workload停止・retryヲ案内シ、低 `CmaFree` 単独デrebootヲ要求セザル文面ニ統一シタ。

## [4.620.9] - 2026-08-17

### Docs

- **Hailo PCIe driver 5.4.0 ノ `FOLL_LONGTERM` 反証実験patch及ビ適用・復元手順ヲ保存。** A/Bニ実際ニ用ヰタ `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()` 置換ト安全ナ `CMA_DBG` 計装ノ完全差分ヲ、公式 `v5.4.0` commit・SHA-256・対象ファイル・期待 `srcversion` ト共ニ追跡対象化シタ。適用前ノcommit/checksum/clean-tree検査、DKMS build/install、再起動後ノ識別、検証済ミcommitカラノvanilla復元ヲ `HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` 付録Bニ記録シ、本番推奨patchニ非ザル反証実験物デアルコトヲ明記シタ。

## [4.620.8] - 2026-08-17

### Fixed

- **Hailo GenAI ノ `CmaFree` 絶対値ニ基ヅク事前拒否・自動再起動・診断誤判定ヲ修正。** 実機A/B追試ニテ vanilla 5.4.0 / `FOLL_LONGTERM` 修正版ノ双方ガ1MB未満ヲ含ム低 `CmaFree` カラQwenヲロード・再ロードシ、20回生成中ノRSS/CMA純減及ビCMA割当失敗ガ無キコトヲ確認シタ。`acquire_genai` ハ低値ヲテレメトリ警告ニ留メ実ロードヲ試行シ、実際ノHailoRT host-memory errorノミ reject tracker ヘ記録ス。auto-reboot judge ハ低 `CmaFree` 単独デ遷移セズ、診断ツールハ初回純減ヲ `INCONCLUSIVE`、反復純減ノミ `FAIL` ト判定スル。

### Docs

- **vanilla / `FOLL_LONGTERM` A/B実測ヲ `HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` §8 ニ追記。** 独立プロセス2回ロード、同一プロセス20回生成・解放・再ロード、低CMA反復ノ全結果ヲ記録シ、初回 `CmaFree` 低下ハmulti-GB HEFノページキャッシュ増加ト整合シ、実用上ノ累積リークニ非ズト結論ヲ訂正シタ。

## [4.620.7] - 2026-08-17

### Docs

- **`FOLL_LONGTERM` 欠落仮説ヲ実装・実機検証シ反証。** 前版（4.620.6）デ特定シタ仮説（`prepare_sg_table()` ノ `get_user_pages()` ニ `FOLL_LONGTERM` ガ無イ）ニ基ヅキ `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()` ヘ実際ニ置換、ビルド・dkms 再登録・実機ロードマデ完了サセ、再起動直後ノ高 `CmaFree`（453MB）状態カラ同一 repro（`tools/diag_hailo_cma_reclaim.py`）ヲ再実行シタ。結果ハ消費273MBニ対シ回収10MBノミデ **修正前ト全ク変化ナシ（VERDICT: FAIL 継続）**。`dmesg` デ `pin_user_pages` ガエラーナク実行サレテヰルコトモ確認済ミ。強制コンパクション（`vm.compact_memory`）モ効果ナク、`MemAvailable` ハ7.1GBト健全ナママ `CmaFree` ダケガ回復セズ、トイフ症状自体ハ修正前ト同一デアッタ。**`FOLL_LONGTERM` 欠落仮説ハ理論的ニハ正当（Linux カーネルノ作法違反トシテノ指摘価値ハ残ル）ダガ、今回観測サレテヰル症状ノ根本原因デハナカッタ**ト結論。除外デキタ原因（ドライバ自身ノ `dma_alloc_coherent` 経路・SG map/destroy 不整合・SWIOTLB・FOLL_LONGTERM）ヲ整理シ、次ノ調査方向（HailoRT ユーザ空間側ノバッファアロケータ由来ノ可能性、`CONFIG_CMA_DEBUGFS`/`page_owner` ヲ用ヰタ直接観測）ヲ記録。詳細ハ `HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` §7.4–7.5。

## [4.620.6] - 2026-08-17

### Docs

- **Hailo-10H CMA 未解放問題ノ根本原因ヲ特定シ記録。** `virt_to_page()` 等ノ危険ナページ検査ヲ避ケタ安全ナ計装（`dev_err()` ニヨル既存アトミックカウンタ・確保サイズノログ出力ノミ）ニ切替ヘ、実機ニテ再現・分析ヲ実施。結果、ドライバ自身ノ `dma_alloc_coherent()` 経由ノ割当テ（descriptor list・continuous buffer）ハ数MB程度ニ過ギズ問題ノ原因デハナク、ユーザ空間確保済ミメモリヲ DMA 用ニマッピングスル経路（`hailo_vdma_buffer_map()`、`HAILO_DMA_USER_PTR_BUFFER`）ガ Qwen3-1.7B-Instruct ロード時ニ 8MB バッファヲ大量ニ扱ッテヰルコトヲ確認。ソースヲ辿ルト `prepare_sg_table()` ガ `get_user_pages(FOLL_WRITE | FOLL_FORCE)` ヲ使用シ **`FOLL_LONGTERM` フラグヲ指定シテヰナイ**コトガ判明。Linux カーネルノ文書化サレタ作法（DMA 長期転送ハ `pin_user_pages()` + `FOLL_LONGTERM` ヲ用ヰルベシ）ニ反シテヲリ、タマタマ CMA 領域内ニアッタユーザページガ固定化サレルト CMA ノ migration 機構ガ働カズ、解放後モ CMA ノ空キ領域トシテ即座ニ認識サレナイ、トイフ実測結果ト完全ニ整合スル根本原因ヲ特定シタ。修正候補（`pin_user_pages` + `FOLL_LONGTERM` ヘノ置換ヘ）モ記録シタガ、実機検証ハ未実施。詳細ハ `HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` §7。次ハコノ知見ヲ Hailo フォーラム投稿ヘ反映シ、可能ナラ修正実装ヲ試ミル方針。

## [4.620.5] - 2026-08-17

### Docs

- **Hailo-10H の起動不能化を招いた CMA デバッグ計測を記録。** ローカル DKMS ソースの `linux/vdma/memory.c` に追加していた `virt_to_page()` / `page_count()` 計測は、`dma_alloc_coherent()` の返却アドレスを DMA API の契約外で直接ページ変換するものであり、ハングしたモジュールに含まれた唯一のローカル実行コード差分だった。7行を除去して DKMS 再ビルド・`depmod` まで完了。blacklist は維持し、復旧経路を確保した初回ロード試験を次段階とした。詳細は `HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` §6。

## [4.620.4] - 2026-08-17

### Docs

- **pyhailort ヲ 5.4.0 デ再ビルドシ、既存 CMA repro（`tools/diag_hailo_cma_reclaim.py`）ヲ実機再実行シタ結果、v5.4.0（driver/library/firmware/pyhailort 全テ自前ビルドデ完全一致）デモ CMA 未解放問題ハ再現シ、`VERDICT: FAIL` ト確定シタ。** `hailort/libhailort/bindings/python/platform/` ノ pyproject（scikit-build-core + pybind11）ヲ `LIBHAILORT_PATH`/`HAILORT_INCLUDE_DIR` デ既存 `/usr/local` ビルドニ明示的ニリンクサセテ `.venv` ヘインストール（`ldd` デ `libhailort.so.5.4.0` リンク確認）。2026-05 ト同一手法・同一 HEF（Qwen3-1.7B-Instruct）デ子プロセス VDevice/LLM ロード→`SIGTERM`→30秒待機ヲ再測定シタトコロ、消費 137MB ニ対シ回収 -22MB（`CmaFree` ハ数分後モ 512kB 付近ニ張リ付イタママ）ト、5.3.0 時点ト定性的ニ同一ノ結果ト成ッタ。v5.4.0 ハ本問題ヲ修正シテヰナイコトガ確定シ、次ハ GPL-2.0 公開ドライバソースヘノ自前パッチ検討ニ進ム方針。

## [4.620.3] - 2026-08-17

### Docs

- **`HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` ニ自前ビルド追試ノ記録ヲ追記。** apt/公式カラ `hailort` 5.4.0 deb ノ配布ヲ待タズ、`hailort`（MIT、C++/CMake）本体ヲソースヨリ `/usr/local` ヘ自前ビルド、driver（GPL-2.0）ヲ dkms 経由デ 5.4.0 ニ入替、firmware モ公式 S3 カラ 5.4.0 取得ノ上デ入替エ、driver/library/firmware 完全一致ノ検証環境ヲ実機ニ構築スルコトニ成功シタ。過程デ Hailo-10H ノ SoC ファームウェアハモジュール再ロードダケデハ再書込サレズ（`support_soft_reset` ハ Hailo-8 ノ NNC 経路ノミ対応、Hailo-10H ノ SoC 経路ニハ未実装）、実機ノ電源再投入ガ必須ト判明。再起動後、`hailortcli fw-control identify` ガ正常応答シ、`hailortcli run2` ニヨル単発・8回連続 load/run/exit デハ明確ナ CMA リークハ観測サレズ数回デプラトー化シタ。タダシ既知ノ2大リーク（同一プロセス内 `VDevice.release()` 未解放・`generate_stream()` 継続リーク）ノ直接再検証ハ pyhailort（Python バインディング）ガ `libhailort.so.5.3.0` ニ固定リンクサレテヰルタメ未達。次回 pyhailort ヲ 5.4.0 カラ再ビルドシテカラ本格再検証スル方針。checkinstall トカーネルモジュールノ xz 圧縮ステップガ競合スル既知ノ罠（installwatch トノ相性問題）モ記録。

## [4.620.2] - 2026-08-16

### Docs

- **CMA 未解放問題ノ調査記録トシテ `HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md` ヲ新設。** `hailo-ai/hailort-drivers` v5.4.0（2026-08-16 公開）ヲ実機（Raspberry Pi 5 + Hailo-10H）ニ手動ビルド・投入シテバニラ状態デ問題ガ直ッテヰルカ検証ヲ試ミタガ、HailoRT ユーザ空間ライブラリガドライバトノ完全一致バージョンチェックヲ行フタメ `hailortcli` ヲ含ム全 API 呼出シガ `HAILO_INVALID_DRIVER_VERSION` デ拒否サレ、検証未達ノママ v5.3.0 ヘ復旧。v5.3.0→v5.4.0 ノソース diff（CMA 確保・解放ロジック自体ハ不変）、ビルド手順ノ罠（`make install` ガ `all` ニ依存セズ・System.map 欠如ニヨル depmod スキップ・udev trigger 未実施ニヨル権限問題）、dkms 手動復旧手順ヲ記録。apt/公式カラ `hailort` 5.4.0 ノ deb 配布ヲ待ッテ再検証スル方針。

## [4.620.1] - 2026-08-16

### Fixed

- **`parse_tool_call_with_known_names` ノ tool 呼出シ抽出ヲ全面書キ換ヘ、実機（Qwen3-1.7B-Instruct）ガ吐ク出力ヲ正シク解析可能ト成シタ。** v4.620.0 ノ native tool 配線ヲ実機再検証中ニ発見：モデルハ `{"arguments": {...}, "name": "..."}`（`arguments` ガ `name` ヨリ先ノ逆順）ヲ末尾ニ `<|im_end|>` ヲ直接連結シテ返スコトガアリ、旧ノ順序依存正規表現（`TOOL_CALL_RE`/`TOOL_CALL_SIMPLE_RE`）ハコレヲ解析デキナカッタ。ブレース深度ヲスタックデ追跡スル単一パス O(n) ノ `extract_json_objects()` ヘルパー（文字列リテラル内ノブレースヲ正シク無視、順序ニ依存セズ）ニ全面置キ換ヘ。
  - **Codex stop-time review 三件ノ追加指摘ヲ経テ収斂**：(1) 最初ノ候補ガ tool 呼出シデ無ケレバ即座ニ諦メ後続ノ正当ナ tool 呼出シヲ見逃ス件 → 全候補ヲ走査、(2) (1) ノ単純修正（未終端 `{` ヲ 1 文字ズラシテ再走査）ガ O(n²) ト成ル件 → スタックデ開キ位置ヲ push・閉ジデ pop シテ記録スル単一パス方式ニ根本的ニ改メ、(3) 候補ヲ固定件数デ打チ切ル方式ダト正当ナ兄弟候補群ノ末尾ガ捨テラレ得ル件 → 件数デハナク累積パース文字数ノ予算（`text.len()*4` 以上）デ制限（兄弟候補ハ合計シテモ高々 O(n) ナノデ予算ヲ使ヒ切ラズ全テ試セル一方、深イネストノ重複候補ノミ予算ヲ速ヤカニ消費シテ打チ切ラレル）。
  - `cargo test -p yu-server` 33 件全通過（新規回帰試験含ム）・clippy 警告ゼロ・`pre_push_check.py` 通過ヲ確認済ミ。詳細ハ `QA_HANDOFF.md` (A-2)。

### Verified

- **TODO(hailo-genai) (A-2) ノ合格条件ヲ実機ニテ達成（Raspberry Pi 5 + Hailo-10H FW5.3.0, フレッシュ release ビルド）。** パーサー修正ヲ反映シタフレッシュビルドデ `POST /api/llm/agent` ヲ二回実行、両方トモ `steps[]` ニ実際ノ tool 呼出シガ入ッタ：「スキャンルート一覧」→ `list_scan_roots` 呼出シ、「サーバー統計情報」→ `get_stats` 呼出シ（実データヲ正確ニ要約シタ自然文回答ヲ生成）。TODO(hailo-genai) 段階1（自前配線）ヲ完全ニ完了。

## [4.620.0] - 2026-08-16

### Added

- **HailoRT native tool 呼出シ対応ヲ hailo prompt-based agent ニ配線セリ（TODO(hailo-genai) 段階1）。** `yu-hailo-infer`（別リポジトリ、private/public 双方 push 済ミ、pin rev 更新済ミ）ノ `LLMGenerator::write(messages, tools)` ヲ実機（Qwen3-1.7B-Instruct.hef）ニテ検証シ、モデルガ `<tool_call>{"name":...,"arguments":...}</tool_call>` 形式（既存正規表現ガ既ニ解析可能）デ応答スルコトヲ確認セリ。`InferClient::llm_generate_stream()` ニ `tools` 引数ヲ追加、`auto_stubs.rs::hailo_genai_chat_completions_native()` ガ受信シタ OpenAI 形式 `tools` ヲ読ミ取リ転送、`llm_agent_prompt.rs::run_agent_prompt_based` ガ `chat()` 呼出シ前ニ tools ヲ native 形式ヘ正規化シテ渡ス。
  - **Codex stop-time review 三件ノ指摘ヲ即時是正**：(1) 正規化ガ OpenAI ラッパー（`{"type":"function","function":{...}}`）ヲ剥ガサズ渡シテヰタ件 → 共通ヘルパー `llm_client::unwrap_openai_tools()` ヲ新設シ `chat()` 呼出シ直前デ正規化、(2) 正規化ヲ無条件ニ適用シ外部設定 OpenAI 互換エンドポイント宛ノ `prompt_based` 呼出シヲ破壊シテヰタ件 → エンドポイントガ実際ニ自サーバー自身ノ hailo-genai 自己呼出シデアル場合ニノミ正規化スル形ト成シタ、(3) 判定ニ `base_url.contains("hailo-genai")` トイフ部分一致ヲ用ヰ外部 URL ノ偽装ヲ許シテヰタ件 → PIN 認証転送修正（v4.618.3）デ既ニ厳密検証済ミノ `is_own_loopback()` ヲ `pub(crate)` トシテ再用シ厳密一致ニ変更。
  - **残ル**: 実機デノ本格的ナ agent ループ再検証（`/api/llm/agent` エンドポイント経由デ tool 呼出シ成功率ガ実際ニ向上スルカ）ハ未了。TODO.md 参照。

## [4.619.1] - 2026-08-16

### Fixed

- **`max_rounds=1` ノ場合ニ約束シタ自己修正リトライガ黙ッテ発火セザル欠陥ヲ修正ス。** `run_agent_prompt_based` ノ round ループヲ `for round in 0..max_rounds` カラ `while round < max_rounds` ニ改メ、correction retry ノ `continue` ガ round budget ヲ消費セヌ形ト為シタ。従前ハ `continue` ガ for ループノ次ノ反復ヘ進ムダケデ round ガ暗黙ニ進ミ、`max_rounds=1` ナラバ最初ノ（失敗シタ）試行ガ唯一ノ round ヲ使ヒ切リ、約束シタ再要求ガ一度モ送ラレヌママ `[Agent reached maximum tool call rounds]` ヲ返シテヰタ（Codex stop-time review 指摘）。回帰試験 `llm_agent_prompt_based_correction_retry_fires_even_with_max_rounds_one` ヲ追加シ、`max_rounds:1` デモ矯正リクエストガ確カニ送ラレルコトヲ担保。

## [4.619.0] - 2026-08-16

### Added

- **hailo prompt-based agent ノ tool 呼出精度ヲ三段構エニテ改善ス。** 実機再検証（v4.618.4）ニテ判明シタ「小型量子化モデルガ厳密 JSON 形式ヲ安定シテ出力セヌ」問題ニ対シ、(一) システムプロンプトニ最初ノ tool カラ組ミ立テタ具体例（few-shot）ヲ追加、(二) `parse_tool_call` ニ寛容フォールバックヲ追加（既知 tool 名ト完全一致スル裸ノ文字列ヲ引数無シ呼出シト看做ス。未知ノ語ハ一切通サズ、引数ノ検証ハ引キ続キ `execute_tool` 側ニ委ヌ）、(三) 一回限リノ自己修正リトライヲ追加（応答ガ `{...}` フラグメント内ニ引用符付キ `"name"` キーヲ含ミ乍ラ完全ナ tool 呼出シトシテ解析デキヌ場合ノミ、正シイ形式ヲ再要求スル）。
  - Codex stop-time review ニテ二件ノ誤検知ヲ指摘サレ即時是正：(1) 応答文中ニ tool 名ガ偶然出現スルダケデ再試行ヲ誘発スル件（ヒューリスティックカラ tool 名ノ部分一致判定ヲ削除）、(2) `{name}` ノ如キプレースホルダー表記ヲ誤ッテ tool 呼出シ試行ト見做ス件（`{` ト未引用ノ語 "name" ガ独立ニ出現スルダケデナク、引用符付キ `"name"` キーガ同ジ `{...}` フラグメント内ニ在ルコトヲ要求スル形ニ絞ッタ）。回帰試験ヲ追加。
  - **残ル**: HailoRT 側デノ構造化出力強制（grammar-constrained decoding）ハ本セッションデハ未着手。次セッションノ TODO ト為ス（詳細ハ TODO.md）。

## [4.618.5] - 2026-08-16

### Changed

- Codex subagent の選定を routing 規則の必須工程として `CLAUDE.md` に明記。`.claude/agent-routing.yaml` と `agent-workflows.yaml` の `Codex委譲前`・`難易度評価委譲則` を参照し、その規則に従って選定する。

---

## [4.618.3] - 2026-08-16

### Fixed

- **Windows の `setup-ai-tools.ps1 update` が、yu の build 成功後に存在しない `target/release/ai-coreutils.exe` をコピーし、古い既存 binary を新規成功として `[OK]` 表示していた問題を修正。** 現在の artifact `yu.exe` を `yu.exe` と互換用 `ai-coreutils.exe` へ配置し、artifact 不在・copy 失敗時はそこで停止する。
- `--version` の先頭行が警告だった `sg` を `?` と誤判定する問題を修正。aider は `audioop` が削除された Python 3.14 環境を Python 3.13 で再作成する。lean-ctx は GitHub release と同版なら self-update を呼ばず、失敗時も既存 executable の存在だけで成功扱いしない。
- pre-push の lan-cowork clippy checker が UTF-8 の cargo 出力を Windows cp932 で decode して例外化し、真の clippy 失敗を隠す問題を修正。numkong 7.8.0 までの既知 `-std:c99` failure は Windows 限定で許可するが、毎回 crates.io 最新版を確認し、新版が出た時点で gate を閉じて MSVC 検証と即時 bump を要求する。

---

## [4.599.1] - 2026-08-08


### Security

- **脆弱な依存を 3 系統で引き上げた。** 警告 38 件は重複を畳むと 11 パッケージ。PR は 1 件も無い —— private repo で PR を無効にしている設定どおりで、dependabot のブランチ 22 本は PR 化されないまま残っていたもの。系統ごとに 3 回に分けた（一括だと壊れたときに切り分けられない）。
  - **rust**: `quinn-proto` 0.11.14 → 0.11.16。lan-cowork 511 試験通過。
  - **pip**: `pillow` 12.2.0 → 12.3.0（直接依存）、`aiohttp` 3.14.1 → 3.14.3、`cryptography` 49.0.0 → 50.0.0、`h2` 4.3.0 → 4.4.1（`hpack` も追随）。`pillow` は画像処理の本体なので PNG/WebP 往復と縮小を実際に走らせて確認し、画像関連試験 357 件通過（失敗 5 件はすべて playwright のブラウザ未導入で本件と無縁）。
  - **npm**: `undici` 7.28.0 → 7.29.0、`hono` 4.12.32 → 4.13.1、`fast-uri` 3.1.4 → 3.1.5、`dompurify` 3.4.11 → 3.4.13（唯一の直接依存）。ビルドと TS 試験 122 件通過。

### Discovered

- **`nanoid` と `postcss` は意図して動かしていない。** 連鎖は `nanoid ← postcss ← vite ← vitest ← devDependencies` で、**本番の配布物に載らない**。`vitest` を 4.1.10 へ上げても `vite` 8.0.16 が古い版を要求し続ける。`pnpm.overrides` で強制できるが、それは**テストランナーの内部依存を上書きする**行為で壊れたときの原因が見えにくくなり、得られるのは開発時依存の警告解消のみのため採らない。
- **`quinn-proto` は `cargo tree -i` が空を返す** —— 現在のビルドグラフに存在せず、`Cargo.lock` に版が残っていただけだった。危険は元から無い。**「使っていないものに警告が出る」型**があるということ。
- ⟹ **ブランチ 22 本 ≠ 警告 38 件。** ブランチが無い警告（推移的依存）も、ブランチがあるのに実体が無い警告も存在する。

---

## [4.599.0] - 2026-08-08


### Added

- **yu-server が sidecar へ VDevice group_id を渡すようになった。常駐が hybrid の本番経路に入る。** `build_startup_payload` に `vdevice_group_id` を追加し、`main.rs:578` で解決する。解決順は Python の `_resolve_group_id()`（`device_manager.py:55-67`）に合わせて **env `HAILO_VDEVICE_GROUP_ID` > config `hailo.vdevice_group_id` > `"YU_SHARED"`**。Python は `if env:` なので**空文字は素通りして config へ落ちる** —— この挙動も写した（`env::var().unwrap_or(...)` と素直に書くと違う）。
- **解決は pre-profile の `app_config` から行う。** `main.rs` は `app_config` を 572 行（pre-profile）と 669 行（`merge_profile` 後、同名 shadow）で 2 回束縛し、sidecar の spawn（862 行）は後者を見る。一方 Python の `load_config_json()` は**生読み**で profile merge は別関数のため、**merged 側から解決すると profile を使う配備で値が食い違い、共有が黙って成立しなくなる**。同ファイル 684 行の「Deliberate asymmetry」コメントが示す既存の区別に倣った。

### Changed

- **sidecar の pin を常駐版へ進めた**（`e652474f` → `68898b47`、2 箇所とも同一 rev）。先立って public mirror へ同期（16 ファイル、+1190/−356、新規は `shim.h` のみ、削除ゼロ）。`docs/superpowers`・`.claude`・`.yu`・`CLAUDE.md`・`TODO.md` は除外設定どおり private に残る。public mirror CI 緑を確認してから pin を進めた。

---

## [4.598.13] - 2026-08-08


### Measured

- **Python 拡張との共存が実機で成立した。hybrid の既定構成が確認できた。** Python 側を `start.sh` で通常起動し UI から Hailo チャットを 1 ターン実行して LLM を保持した状態（`CmaFree` 372,080 kB）で、`vdevice_group_id: "YU_SHARED"` を指定した sidecar から `/v1/infer/clip-image` を実行 → **`ok: true, dim: 512`**。`HAILO_OUT_OF_PHYSICAL_DEVICES(74)`・`not configured as view`・CMA 系のいずれのエラーも出なかった。**`YU_SHARED` の VDevice 共有は実機で機能する。**
- これで**実機検証は全項目完了**した。実 shim のコンパイル／常駐と CMA の安定／`clear_context()` がゲートを開くこと／Python との共存。

### Fixed

- **仕様の「InferModel 級の常駐は CMA を消費しない（0 MB）」を実測で補正した。** あの 0 MB は Python 側 `acquire_device` の分類であって sidecar の実測ではなかった。**sidecar の CLIP 1 回で `CmaFree` は −14,272 kB**（372,080 → 357,808）。「上限を置かない」という結論は変わらない（512 MB のプールに対し十数 MB なら数個は収まる）が、**0 ではない**。なお 1 点測定では、これが CLIP のロード費用なのか推論中の継続 leak（約 14 MB/分）なのかを区別できていない —— 数値が近いのは偶然かもしれない。

### Remaining

- pin 更新と public 同期のみ（公開が近いためそのときにまとめて）。これが済めば yu-server 側の配線（起動契約の 1 項目）に着手できる。

---

## [4.598.12] - 2026-08-08


### Measured

- **常駐が実機で機能することを確認した。** 同一 HEF へ 5 回連続で generate を投げ、`CmaFree` は `279,088 kB` から**一切動かなかった**（初回ロードで 516,320 → 278,992）。応答は約 0.6 秒。従前は毎回 5.86 秒かかり 1 請求ごとに約 59 MiB を永久に失っていたので、**「1 boot につき実質 1 リクエスト」だった状態が解消された。**
- **実 shim が Pi でコンパイルされた。** SDK ヘッダ無しで推測した C++ 3 行（`HailoRTDefaults::get_vdevice_params()` / `params.group_id` / `VDevice::create_shared(params)`）は当たっていた。唯一の「落ち得る」箇所が解消。
- **`clear_context()` が system role のゲートを開き直すことを差分測定で確認した。** clear 有り（現行）では 2 ターンとも成功し `CHECK failed` は出ない。`llm.clear_context()?;` の 1 行だけをコメントアウトして実 SDK でビルドし直すと**ターン 2 が失敗する** —— `HailoRT llm_generate_stream_start failed with status 6` / `CHECK failed - System role messages can only be provided on the first prompt` / `HAILO_INVALID_OPERATION(6)`。**対策は実機で有効。** 併せて仕様 §2.2b の順位付け（前者は「音を立てて落ちる」）も裏付けられた —— 将来 clear を外す変更は黙って壊れず即座に失敗する。

### Fixed

- **前回の「項 4 失敗」は実装ではなく私のテスト設計の不備だった。** 観測項目に「フランス語で 1 語」を選んだが、**「Tokyo」は仏英で同綴り**のため基準線が取れず、ターン 2 の「Roma」が「ゲートが閉じた」のか「1B モデルがフランス語を間違えた」のかを区別できなかった。clear が効いている状態でのターン 2 は `The capital of Italy is Rome.` と正常であり、後者だったことが確定した。⟹ 観測をモデル能力に依存しない差分測定へ差し替えて決着。

### Discovered

- **プロセス終了でも CMA は返らない（3 例目）。** sidecar 停止直後の `CmaFree` は +4 MB のみ。Phase 0 PoC（SIGTERM + 30 秒で +8 MB、2 回再現）と一致する。2026-08-08 に sidecar 側で観測した「終了後 +49,936 kB」とは矛盾するが、**2 対 1 で PoC 側を採る**。当該の読みは既に撤回済みで、設計はいずれにせよ解放しないため依存していない。

### Remaining

- **Python 拡張との共存は保留。** 差分測定で 2 モデルを載せた後 `CmaFree` が 300,416 kB となり、共存試験は CMA 枯渇の危険があるため reboot 後に実施する。これは flag-day 前の hybrid 構成が成立するかを決める。
- pin 更新と public 同期は引き続き保留（公開が近いためそのときにまとめて）。

---

## [4.598.11] - 2026-08-08


### Added

- **Hailo sidecar のモデル常駐を実装した（3 段、CI 緑）。** 仕様は `docs/superpowers/specs/2026-08-08-sidecar-single-vdevice-design.md`（rev4、GO。rev1〜rev3 は NO-GO で、各 rev の誤りは §0 / §0b に残した）。sidecar 側 commit: `5418143`（段 1）→ `e64c6de`（段 2）→ `084374e`（段 3）。
  - **段 1: プロセスに 1 つの VDevice、group_id 付き。** 従前は `VDevice::create_shared()` を種別ごとに 4 箇所で引数なしに呼んでいた。同一プロセスに VDevice 2 つは `74` で失敗し、**同じ group_id でも別インスタンスなら `InferModel.run()` が「not configured as view」で失敗する**（`hailo_vdevice_concurrent_2026-04-06.md:198-206` の実測）。解放はしない —— `VDevice.release()` が CMA を返さないため、解放は何もしない。
  - **段 2: 専有デバイススレッド。** ハンドルは `NonNull` で `!Send` のため、`spawn_blocking` の閉包内で作って捨てる形では常駐できない。グローバル mutex を、ハンドルを所有するスレッドへ置き換え、`run_hailort_task` を `FnOnce(&mut DeviceCtx)` 化して **14 経路（12 + streaming 2）**を書き換えた。**閉包と結果だけがスレッドを跨ぐ**ので `unsafe impl Send` は不要（1 つも足していない）。
  - **段 3: 常駐。** 鍵は create 引数の全体。許容規則は 2 段 —— InferModel 級（`ShimYolo`）は別 HEF の併存を許し（`clip-image` と `yolo/detect` が両方これを別 HEF で通るため、先着勝ちは片方を永久に壊す）、GenAI 級は同時 1 つで別 HEF には現載 HEF を添えて 409。`Speech2Text` は `clear_context` が無いため常駐させない。

### Fixed

- **常駐が「改善しようとしている当の機能」を壊すところだった。** HailoRT は system role を**文脈が空のときのみ**受け付ける。呼出側は毎ターン system を積んで直近 20 件を再送するため、今日は請求毎 create で文脈が常に空だから壊れない。**ハンドルを使い回せば 2 ターン目で落ちる** —— 実機で既に見つかり修正された障害（`HAILO_LLM_SUBPROCESS_DEVLOG.md` §7、`cdd9e26fe`）。⟹ **生成のたびに `clear_context()` を呼ぶ。** 併せて、clear しなければ会話 B のターンが会話 A の生きた文脈へ積まれる（LAN Cowork 配下では利用者を跨ぎ得る）。**この試験の掴みは実演で確認**（clear を外すと 2 件落ち、戻すと 63 passed）。
- **段 1 のテストが生んだ FFI 再宣言警告 4 件を「再宣言しない」形で解消した**（段 2 に同梱）。今日たまたま一致する 2 つ目の宣言は明日ずれる 2 つ目の宣言であり、しかもこれは**この FFI でコンパイラが唯一捉えられるずれ**である。

### Discovered

- **私の検証コマンドに `--all-targets` が抜けており、テストプロファイルが lint されていなかった。** そのため上記 4 件は「通過」の裏に立っていた。**CI には穴が無く（`--all-targets` あり）、段 1 の push は実際に落ちていた。それを見ずに次へ進んでいた。** 以後 `--all-targets` を既定とする。

### Remaining

- **C++ の API 形は依然として未検証**（`HailoRTDefaults::get_vdevice_params()` / `params.group_id`）。SDK ヘッダが手元に無く、実 shim は Pi でしかコンパイルされない。誤っていればそこで落ちる。
- **推論中の約 14 MB/分の継続 leak は常駐では消えない。** load/unload と独立の別経路であり、対処は既存の自動 reboot 機構（Phase 0.5）。
- pin 更新は保留（2026-08-08 判断）。pin は public mirror を指し開発は private で行うため同期が要る。公開が近いため、そのときにまとめて行う。

---

## [4.598.10] - 2026-08-08


### Fixed

- **sidecar の 2 つの shim 実装が共有 C ABI を各自に宣言しており、片方だけ変えても沈黙して壊れる状態だった**（sidecar `0eeb65d`）。`build.rs` は SDK の有無で `shim.cpp` / `shim_stub.cpp` を切り替えるが、`extern "C"` は arity も型も記号名に含めないため、**片方に引数を足しても両機でコンパイル・リンク・試験がすべて通り、実行時に沈黙する未定義動作になる**。`src/hailort/shim.h` に POD 3 種・opaque 6 種・全 30 宣言を集約し、両実装が include する形にした。**継ぎ目が閉じたことは実演で確認**（ヘッダのみ arity を変えると `conflicting declaration of C function` でビルドが落ち、復元で green）。**閉じたのは C++ 同士の 2 面のみで、Rust の `ffi.rs` は手写しのまま**である旨をヘッダ冒頭に明記した。

### Rejected

- **group_id 単独の設計は NO-GO。** 事実確認 4 点は真だったが推論が誤っていた。(1) **「FFI なら型検査される」が偽** —— 上記のとおり宣言が共有されていなかった（この面は `0eeb65d` で対処済み）。(2) **group_id は常駐の前提条件ではない** —— `hailo_vdevice_concurrent_2026-04-06.md` の実測が「同一 group_id の別 VDevice は生成に成功するが `InferModel.run()` が『not configured as view』で失敗する」と記録しており、4 箇所の生成を残す設計は**文書が「動かない」と記録した構成そのもの**。本当の前提条件は **VDevice の単一化**で、sidecar 側の常駐 spec §12/§13 が既に名指ししていた。⟹ **group_id と常駐は同じ変更の一部**である。
- 併せて訂正: group_id 不在は記録済みの決定（M3、「VDevice open の失敗が検知器」）であり反転には検知器喪失の引き受けが要る／「CMA 上限は動かない」は cold-spawn の VDevice 構築だけで 131 MB という実測と矛盾／必要なのは解決順序でなく解決**値**の一致で、**yu-server は config.toml、Python は config.json** と読む先が違う。
- 良い方向の訂正: hailo-ollama（C++ バイナリ、同じ API + env group_id）と Python の同時保有は **lsof 付きで実証済み**だった。未検証なのは我々の params 構築だけ。ただし同じ検証が **×8.08 の減速**（CLIP 18.8 → 152 ms）を測り GenAI 並走禁止と結論している。

---

## [4.598.9] - 2026-08-08


### Discovered

- **モデル切替は「高価」ではなく「不可能」だった。** `HAILO_CMA_LEAK_HAILORT_5_3_0.md` §3-1〜§3-2 —— reboot 直後 CmaFree ≒ 480 MB、LLM 1 個 load で ≒ 190 MB、**2 個目の load は永久に不可能**。同 §3-2 は「マルチモデル UX は HailoRT 5.3.0 では設計上成立しない」と結論する。**1 GenAI モデル / Pi reboot が上限。** 常駐設計で論点だった「切替時の eviction」は、切替自体が存在しないため消滅する。
- **sidecar が `group_id` を一切渡していない。** `shim.cpp:293, 395, 501, 758` が `VDevice::create_shared()` を引数なしで呼び、sidecar 全体に group_id が無い。これが 2 つの問題を同時に起こす: (1) **常駐できない** —— LLM を保持したまま YOLO/CLIP を呼ぶと 2 つ目の VDevice が `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` で失敗する（`VDEVICE_SHARING_PATTERN.md` TL;DR）。今は create/drop がロック内で完結するため露見していないだけ。(2) **hybrid で Python 拡張とデバイスを奪い合う** —— `group_id` はプロセスを跨いで効き（`HAILO_DEVICE_CONTROL.md`）、Python 側は `YU_SHARED` で保持するため、group_id が違えば共有できない。今日の既定構成の話であり実機確認の価値がある（未確認）。
- **ただし 2× InferModel（YOLO + CLIP）+ 1× GenAI は共存可能。** `VDEVICE_SHARING_PATTERN.md` が 5.2.0/5.3.0 で検証済み。同一の共有 VDevice 上で ROUND_ROBIN が時分割する。制約は「GenAI が 1 つまで」。
- **結論が反転した: 常駐は性能改善ではなく、機能が成立する唯一の形。** 請求毎 create は制約と合わせると実質 1 boot につき 1 リクエストしか成立しない（実測の「2 ターンで枯渇」と整合）。

### Fixed

- **`HAILO_CMA_LEAK_HAILORT_5_3_0.md` §4 の中期方針が、同じ表で REJECTED になっている案 (A) subprocess 隔離を指していた。** Phase 0 PoC より前の行が残っていたもの。実際に採用されたのは (D) 自動 reboot で、Phase 0.5 として実装済み。**この 1 行が残っていたために、2026-08-08 のセッションで「プロセスを作り直せば CMA が戻る」型の設計が再度書かれた。**

### Documented

- Rust 側の順序を確定: (1) sidecar に `group_id` を通す（他の全ての前提条件であり、単独でも共存問題を直す。C++ の overload は SDK ヘッダが手元に無く未確認）、(2) create-once の常駐（切替が無い以上スロットも eviction も不要）、(3) 自動 reboot 機構への参加方法を決める（**新規設計はしない**）、(4) `model/unload` のパリティ対象を Python の実挙動に合わせる（実装不能のため）。

---

## [4.598.8] - 2026-08-08


### Fixed

- **`docs/ja/hailo/README.md` の既知事項 2 件が古く、読んだ者を誤った設計へ導く状態だった。** (1) 「推奨 CMA 上限は `cma=256M`、`cma=512M` は静かに失敗する」は詳細文書と逆 —— `PI5_NUMA_CMA_CONSTRAINTS.md` は `cma-512` を確認済みの上限かつ推奨値とし、2026-05-16 に `CmaTotal: 524288 kB` で再検証している（今回の実機測定値と一致）。併せて設定箇所が cmdline から `config.txt` の `dtoverlay=cma,cma-512` へ移行済みであることも反映。(2) 「CMA 枯渇時はプロセス再起動を計画」は 2026-05-17 の Phase 0 PoC が反証済み。
- **同 README の一覧表が 9 件で、実ファイルは 15 件だった。** 載っていなかった 5 件に `HAILO_CMA_LEAK_HAILORT_5_3_0.md` と `HAILO_AUTO_REBOOT_PHASE05.md` —— この領域で最も決定的な 2 文書 —— が含まれていた。

### Documented

- **`HAILO_RUST_MIGRATION_REMAINING_WORK.md` の冒頭に `docs/ja/hailo/` への相互参照を追加した。** `dev-docs-index.yaml` は `docs/development/development_docs/` のみを索引するため、指示どおり索引から辿っても Hailo の実測知見 15 文書には到達しない。**この相互参照が無いために、同一セッションで 2 つの設計が既に実測で反証済みの前提の上に書かれた**（sidecar のモデル常駐、および sidecar 監督）。どちらも審査で NO-GO。

### Withdrawn

- **v4.598.7 の「プロセス終了後は約 83% が戻る」という結論を撤回した。** 根拠は事後の 1 点読み（`CmaFree 158,016 kB`）で、いつ何が戻したのかを特定できていない。これに対し `HAILO_CMA_LEAK_HAILORT_5_3_0.md` §2-1 は同じ実機で **2 回独立に** SIGTERM + join + 30 秒 → **+8 MB のみ**（期待値 ≥250 MB）を測定し、「process exit でも kill でも module unload でも回収されない」と結論している。**測定値そのものは有効で削除しない。誤っていたのは解釈である。** 併せて「作ったら捨てない・切替は sidecar 再起動」という床も撤回する —— 再起動が回収しない以上、切替の手段が無い。
- **sidecar 監督設計は NO-GO。** 上と同じ理由に加え、審査が独立に 4 件の must-fix を挙げた。とくに引き金が狙った失敗を見られない（ストリーミングは `Llm::create` の前に 200 を返し、エラーは 200 のボディに SSE として出るため `InferClientError` が発生しない）。クラッシュ復帰の部分のみ、CMA と無関係な実在の欠陥として別途出し直す。

---

## [4.598.7] - 2026-08-08


### Measured

- **プロセス終了後の `CmaFree` は 158,016 kB。漏れた 60,160 kB のうち約 49,936 kB（約 83%）が戻る。** baseline 168,240 に対し 10,224 kB が不足。つまり **CMA は走っているプロセス内で drop しても回収されないが、そのプロセスが終われば大半は回収される**。ただし 1 点測定のため、いつ戻ったか（遅延回収かプロセス終了か）と、残差 10 MiB が真の残留漏れかその間の別の確保かは分離できていない。

### Discovered

- **欠陥は小さくなったが、依然として自動回復しない。** 手当は「sidecar 再起動」であって機械の再起動ではない。**しかし何者も再起動しない** —— `infer_manager::spawn_with_restart(..., 5)` は起動時のリトライ輪で（healthy になるまで、`infer_manager.rs:103`）、稼働中の監督を行わない。CMA 枯渇は sidecar を殺さず `Llm::create` が失敗するだけでプロセスは健全なまま立っている。よって 2 ターン程度の後、以後の LLM 請求は悉く失敗し、**`yu-server` 自身が再起動するまで回復しない**。

### Decided

- **常駐設計に動く床が定まり、rev3 へ進める。** 捨てても返らないなら捨てない —— 各モデルをプロセスに一度だけ作り、プロセス寿命の間保つ。切替のみが eviction を要し、真の eviction はプロセス再起動のみ。**これで `model/unload` に漸く正直な実装が生まれる**（sidecar 子の再起動。`yu-server` は既に `infer_child` を持つ）。制約は「同時に載るモデルの集合が CMA 512 MiB に収まること」。共有 VDevice の spike は依然有意義だが、もはや load-bearing ではない。仕様 §13 は sidecar 側 `5fc4d30`。

---

## [4.598.6] - 2026-08-08


### Measured

- **CMA は回収されない。create → drop の 1 周で 60,160 kB（≈59 MiB）が返らなかった。** 実機 Hailo-10H・`Llama3.2-1B-Instruct.hef`・他に Hailo を使うものが無い状態で測定（`CmaTotal 524288 kB`、baseline `CmaFree 168240 kB`、cycle 0 で `108080 kB`）。安全床が cycle 0 で発動し、機材は保護された。したがって常駐設計の中核「不一致なら捨ててから作る」は何も解放しておらず、その形では書けない。
- **1 周は 34.2 秒を要した。** 先の 5.86 秒より 6 倍だが、今回の方が作業は軽く機材も清浄だった。構造上の違いは一点 —— 今回の計時は drop を囲んでいる。これが差の正体なら**解放そのものに約 28 秒かかり、しかもメモリは返らない**（二測定は他の条件を揃えていないため推論）。

### Discovered

- **設計以前に、現行実装の欠陥である。** `chat_send_native` は請求毎にハンドルを作る sidecar 経路を呼ぶ。1 請求 59 MiB・プール 512 MiB・測定開始時の空き 164 MiB から、**ネイティブ chat 経路は 2 ターン程度で CMA を使い切る**。性能の問題ではなく本番で機能しない問題で、常駐設計とは独立に存在する。

### Documented

- **測定の限界を明記した（テスト設計の穴）。** 打ち切り経路は即 return するため 10 秒待機の確認を飛ばし、「まったく回収されない」と「遅れて回収される」を区別できていない。59 MiB が `VDevice` 由来かモデル由来かも分離できていない。追加で `grep -E 'CmaTotal|CmaFree' /proc/meminfo` 1 行のみ依頼した。
- 次の設計方針は Python と同じ「プロセス寿命の単一 VDevice の上でモデルを載せ替える」だが、**それも姉妹実装から読んだ推論であって測定ではない** —— 本仕様が既に一度誤った種類のもの。rev3 の第一歩は、モデル解放が回収するか否かを測るためだけの最小 spike とする。仕様は sidecar 側 `bb34b57` §12。

---

## [4.598.5] - 2026-08-08


### Documented

- **Hailo sidecar の常駐設計は NO-GO。実機で CMA を 1 点測るまで先に進めない。** 5.86 秒の実測により「常駐が必要」の判断は変わらないが、常駐機構の*形*が実機で測らないと決まらないことが設計審査で判明した。争点は一つ — sidecar は推論の度に `VDevice` を作って捨てるのに（`shim.cpp:293, 395, 501, 758`）、設計は「捨てれば CMA が返る」に全面的に依存している。ところが本リポジトリの Python 実装が、同じ Hailo-10H・同じ HailoRT 5.3.0 で逆を記録していた（`device_manager_genai.py:95-96`「CMA is not reclaimed by VDevice.release() within a running session」）。そのため Python 側は VDevice を決して解放しない（`device_manager_state.py:58` の `_maybe_reset_vdevice()` は本体が docstring だけの意図的な no-op）。仕様は姉妹実装を prior art として引用しながら、その最も重要な判断だけを移植していなかった。**設計を否定する証拠が、設計の引用していたリポジトリの中にあった。**
- 実機で測ること: `POST /v1/infer/llm/generate` を 20 回叩き `grep CmaFree /proc/meminfo` の推移を採る。baseline に戻れば骨格は生き、単調に減れば「プロセス寿命の単一 VDevice を共有」へ設計が変わる。**併せて、非回収が sidecar の解放経路にも及ぶなら、sidecar は今すでに請求ごとに CMA を漏らしている** — 設計以前の現行欠陥たり得る。
- 仕様と引き継ぎは sidecar リポジトリ側（`9c3b652`）。審査の残る指摘 7 件は仕様 §11 に持ち越した。

---

## [4.598.4] - 2026-08-08


### Fixed

- **`DELETE /ext/hailo-genai/api/chat/conversations` の登録を削除した。** Python 側は `@bp.route("/api/chat/conversations")` を `methods=` なしで登録しており（`hailo_chat_routes_conversations.py:14`）、Flask/Quart は GET のみを提供してコレクションへの DELETE には 405 を返す。コレクションに対する DELETE はそもそも存在しない経路であり（per-id の DELETE は同ファイル :38 にあり、`hailo_genai_chat::delete_conversation` として移植済み）、Rust 側の転送は Python が拒否する要求を送るだけだった。standalone では Python 不在により 503 となり、パリティがかえって崩れていた。削除により axum 自身が 405 を返し、Python と一致する。

### Classified

- **`POST /ext/hailo-genai/api/chat/search` を proxy_keep として記録した。** チャット履歴検索ではなく web 検索であり、Python パッケージ `ddgs` / `duckduckgo_search` に依存する（`core_impl/web_search_query.py:14-18`）。新規ランタイム依存の追加は禁じられており、`chat/send` の `web_search: true` を Python へ逐語転送しているのと同一の理由による。MCP（`mcp_server/hailo_chat_tools.py:152`）から到達可能な生きた経路のため、削除はしない。
- 以上により `rust_standalone_gap.py` の remaining work は 50 → 48、no native path は 29 → 27。

---

## [4.598.3] - 2026-08-08


### Measured

- **Hailo-10H 実機で `Llm::create` を含む最小 test は 5.86 秒。** `Llm::create` 後に `"hello"` を tokenize する既存 ignored test を 1 回実行し、常駐機構が必要と判断した。現在のドライバ 5.3.0 のデバイスノードは `/dev/h1x-0` であり、再ロードは不要だった。

---

## [4.598.2] - 2026-08-08


### Documented

- **実機測定に使う Hailo sidecar は、既存のローカル checkout を使う。**
  この作業ツリーからの解決済みパスは
  `../hailo-infer/yu-hailo-infer`。引き継ぎ文書の clone 指示を置き換えた。

---

## [4.598.1] - 2026-08-08

### Documented

- **この開発環境では Hailo-10H 実機による測定が可能である。** Hailo 関連の
  実装変更は、WSL 側のコンパイル・単体試験だけで完了とせず、必要に応じて実機で
  推論結果・入出力形状・レイテンシ／スループットを確認する。過去の計画に残る
  「`/dev/hailo*` がなく実機検証不可」という記述は当時の環境に限る前提であり、
  現在の引き継ぎ条件には適用しない。

---

## [4.598.0] - 2026-08-08

### Changed

- **hailo-genai の `GET /v1/models` と `GET /api/runtime` を Rust ネイティブ化した。**
  どちらも Hailo デバイスに触れず、HEF の実在確認とモデル表の参照のみで完結する。

```
Rust standalone gap
  remaining work:  52 → 50
    no native path: 31 → 29
```

- **`runtime` の `context` は常に `null`。** これは実装の手抜きではなく、
  **sidecar が何も保持していないという事実の表現**である。sidecar は
  `Llm::create` をリクエスト毎に行い即座に破棄する（`yu-hailo-infer` の
  `router.rs:974-981`）ので、報告すべき保持文脈が存在しない。Python も非常駐時は
  `None` を返す。試験名
  `native_runtime_context_is_null_because_sidecar_retains_nothing` に理由を
  埋め、後から「実装漏れではないか」と誤解されないようにした。
- **`/v1/models` は read scope でも 200 を返す。** `require_admin_scope`
  （`core/web/auth_helpers.py:67-76`）は**認証ではなく API キーの scope 検査**で、
  「API キー無しのセッションは通過する」と docstring に明記されている。未認証は
  middleware が別途止める（`/ext/hailo-genai` は `BYPASS_ROUTES` に無い）。
  Python が `/v1/models` にだけ scope 検査を掛けていないのは、OpenAI 互換
  クライアントが `/v1/chat/completions`（admin 限定）を叩く前に一覧を引く必要が
  あるためであり、意図的な差である。試験
  `native_v1_models_allows_read_scope_for_openai_client_discovery` で固定した。
- モデル表は既存の `hailo_model_registry::genai_models()` を再利用した。
  `OnceCell` でプロセス内 1 回だけ構築され（Python の import 時 1 回と同形）、
  **リクエスト毎のネットワークアクセスは発生しない**。凍結したコピーを作ると
  Python 側の表が変わったとき静かに腐るため、出所を共有している。
- HEF の `path` は Python と同じく**設定されたまま**返す（`HAILO_HEF_DIR` が
  相対なら相対）。正規化すると Python より広く開示することになる —— 相対設定時に
  作業ディレクトリを含む完全パスが応答に出る。移植の副作用で開示範囲を広げない。

### Documented

- **指示の誤りを実装者が着手前に 3 件捕えた**（本増分のみで）。
  (1)「両 route とも admin」—— `/v1/models` に scope 検査は無い、
  (2)「認可なし＝未認証で叩ける」—— 違う、middleware が別途認証する、
  (3)「`path` は解決済みの絶対パス」—— 違う、相対設定なら相対のまま。
  いずれもコードに入る前に止まった。

---

## [4.597.0] - 2026-08-08

### Changed

- **Hailo 推論 sidecar の pin を更新した**（`7182d70` → `e652474`）。両エントリ
  （`infer-core` / `yu-infer`）は同一 rev。分けると ort/ONNX Runtime が二重
  ビルドされ feature 統合が壊れる。新 rev で `cargo build -p yu-server` の
  成功を実測した。

### Added

- **公開側 `eauesque/yu-hailo-infer` に CI を新設した**（fmt + clippy `-D warnings`
  + test）。`ubuntu-latest` で動く —— HailoRT SDK は不要で、`build.rs` が
  `hailo/hailort.hpp` を見つけられなければ `src/hailort/shim_stub.cpp` を使う。
- **同期スクリプト `scripts/sync-to-public.sh`**（private 側）。両者は履歴を共有
  しない（公開側は内容の複写から作られた）ので、同期とは**内容を写して公開側に
  新しい commit を作ること**であり、merge でも force-push でもない。`--check` は
  乖離を非零終了で報じる。除外一覧の各項に理由を付し、mirror の大半を消す同期は
  拒む自己診断を入れた。

### Fixed

- **公開側に CI が無かったため、SDK 無し構成の失敗が 2 件溜まっていた。**
  どちらも実機では再現しない。CI を足す前に `pre_push_check.sh` を回して発見した。
  - `hailort/mod.rs` の `mod tests` は中身が `#[cfg(not(hailo_stub))]` の試験 1 本
    のみで、stub 構成では `use super::*;` の消費者が消えて
    `clippy -D warnings` が落ちる。`use` に消費者と同じ cfg を付けた。
    `#[allow(unused_imports)]` は採らない —— 後日加わる真に死んだ import まで隠す。
  - `speech2text_transcribe_rejects_invalid_repetition_penalty` が 400 を期待して
    503 を受ける。`run_media_preprocessing` の permit は**プロセス大域の
    セマフォ**から取られ、音声（1 件 160 MiB）と画像の全経路が共有するため、
    並列の試験が互いの枠を奪う。**単独では通り、`--test-threads=1` でも
    49 passed** であることを実測して切り分けた。試験の直列化で本番挙動を維持した
    （各試験に guard を配る案もあるが、競合が 2 module を跨ぐため対象の特定が
    漏れやすい）。`pre_push_check.sh` と CI の双方に理由を註記して揃えた。
- 併せて `d0eee6d`「media 前処理の資源上限」が公開側へ届いた。それまで公開 crate
  には未反映で、**yu_ai_manager が pin していたのは修正前の rev** であった。

---

## [4.596.0] - 2026-08-07

### Changed

- **`POST /api/thumbnails/warmup` を Rust ネイティブ化した**（misc の 2 本目）。

```
Rust standalone gap
  remaining work:  53 → 52
    no native path: 32 → 31
```

- **従来の standalone stub は「丁寧な嘘」であった。** `files.rs:502-511` は
  Python 不在時に 503 ではなく **202 で `{"ok": true, "started": false, "count": N}`**
  を返し、何も温めずに成功のように見せていた。`ok` だけ見る呼出側には成功と
  区別が付かない。実装に置き換えて撤去した。
- 芯は既にあった —— `resolve_preview_path`（`files.rs:460`）は冷えた preview を
  **生成してキャッシュする**（native な `thumbnails_batch` が依拠している）。
  warmup はそれを背景で回すだけに還元される。
- 落としやすい仕様 3 点を保った。**2000 超はエラーでなく先頭 2000 への切り詰め**、
  `count` は**フィルタ後**の数（3000 送れば 2000 が返る）、`started: false` は
  失敗ではなく**同じ集合が既に実行中**の意。
- dedup は `JobManager` を再利用し、job id を
  `thumbnail-warmup:{sorted 先頭100 の hash}` とした。**指示では専用の in-flight
  集合を作らせようとしたが、実装者の判断の方が良い** —— 新しい状態を増やさずに
  同じ意味論が得られる。
- **試験は dedup の両面を押さえる。** 同一集合の二重投入は `started: false`、
  **別集合の同時投入は双方 `started: true`**。Python は集合ごとに dedup するので、
  後者が無いと job id が定数へ縮退しても気付けない（拙者自身が global と
  誤解しかけた）。`thumbnails_warmup_populates_preview_cache` が
  **実際にキャッシュが埋まること**を確かめる —— stub が 202 を返し続けた事態の再発を
  防ぐ唯一の試験である。

---

## [4.595.0] - 2026-08-07

### Changed

- **`GET /api/ai-context` を Rust ネイティブ化した**（misc 7 件の 1 本目）。

```
Rust standalone gap
  remaining work:  54 → 53
    no native path: 33 → 32
```

- **この endpoint は AI が instance を辿るための自己記述であり、持っていない機能を
  報告すれば唯一の消費者を能動的に誤導する。** Python は `capabilities` を Quart の
  blueprint 登録簿（`BLUEPRINT_CAPABILITY_MAP`）から引くが、Rust に対応物が無いため
  **capability probe へ写した**。写し方は機械的に決まらないので判断を明示する。
  - core 4（`llm_router`・`image_analysis`・`gateway`・`scheduler`）は常に有り。
    yu-server に常時組込まれている
  - **`lan_cowork` は route が実際に mount されている時のみ。** LAN Cowork の
    router は `native_daemon` が無効だと空の `Router` を返して 404 になるため、
    mount されていない route は capability ではない
  - `hailo` / `wd_tagger` は**「設定されている」で判定し、到達性を probe しない**。
    Python の `build_ai_context` は "IO-free within this function" と明記しており、
    自己記述 GET を network probe に変えるのは endpoint として劣化である
- 試験 `ai_context_matches_python_metadata_and_unmounted_capabilities` が
  **未 mount 時に `lan_cowork` が capabilities に現れないこと**を固定する。
  この endpoint が嘘をつかないことを担保する assertion である。
  `ai_context_capabilities_follow_actual_configuration` は `hailo` が設定有りで出現し
  `wd_tagger` が `enabled:false` で不在になることも押さえており、ハードコードした
  一覧ではないことを示す。
- `config_hints` は key / severity / message のみを返し、**設定値そのものは出さない**。
  secret 項目は「未設定であること」だけを報告する。
- `version` は `VERSION` を初回読込後にキャッシュし、読めなければ `"unknown"`。
  キャッシュ意味論（後から VERSION を書いても `"unknown"` のまま）も試験で固定した。

---

## [4.594.1] - 2026-08-07

### Fixed

- **`rust_standalone_gap.py` が `/sd/*` 3 本を誤って「未移植」と数えていた。**
  実測で発見。`/sd/config`・`/sd/info`・`/sd/internal/ping` は**既に native** で、
  Python ではなく **Stable Diffusion WebUI へ直結**している。
- 原因は判定が**宛先を見ていなかった**こと。`fwd_get_sd`
  （`misc_admin.rs:753-766`）は `sd_backend_url(&gw)` で gateway 設定から SD の
  base_url を引き（既定は SD WebUI の既定ポート `http://127.0.0.1:7860`）、
  `python_url` には一切触れない。`state.python_client` は単なる
  `reqwest::Client` であって名前が紛らわしいだけであり、宛先の証拠ではない。
  関数名も `fwd_` で始まるため、**名前による判定でも引っかかっていた**。
- 判定を「**URL が `python_url` に由来すること**」に改めた。残る 33 件すべてを
  同じ目で監査し、他に偽陽性が無いことを確認した。回帰試験
  `tests/test_rust_standalone_gap.py` を追加した。

```
remaining work:  57 → 54
  no native path: 36 → 33
```

- **測定器の数は heuristic の精度以上にはならない。** docstring に限界は書いて
  あったが、**実測で確かめたのは今回が初めて**であり、その時点で 3 件が誤りだった。
  パッチで隠さず判定自体を直し、限界の記述も実装に合わせて更新した。

### Documented

- SD gateway に**本物の parity 欠落**を別途発見した（task #42）。Python の
  `_resolve_sd`（`routes/gateway_sd.py:86-99`）は per-request の `backend_id`
  （query）と `X-Backend-Id`（header）を尊重し、`not_found` は 404、
  `type_mismatch` は 400 を返す。Rust の `sd_backend_url` は
  `defaults.default_sd_backend_id` しか見ないため、**複数 backend 構成で
  クライアントの指定を無視して常に既定へ送る**。これは「未移植」ではなく機能差
  であり、ツールが挙げていた理由（誤判定）とは別物である。

---

## [4.594.0] - 2026-08-07

### Changed

- **comfyui-bridge の Python 転送がゼロになった。** C3c で
  `check-workflow-from-file` と `queue-workflow-from-file` を Rust ネイティブ化し、
  残っていた 2 件の登録を削除して完了。

```
Rust standalone gap
  remaining work:  61 → 57
    no native path: 40 → 36
comfyui-bridge の残行: 0
```

- **この対は同じ形をしていてエラー方針が正反対である。** 前半（`file_id`(int) →
  DB 引き → ファイル検査の 5 分岐）は完全に同一だが、`check` は**fail-open** ——
  抽出失敗も editor 形式も想定外の例外も、すべて 200 の `{"status":"ok"}` に落として
  利用者の作業を止めない。`queue` は fail-closed で 422/400/502 を返し分ける。
  **前半を括る際にエラー処理まで括ると `check` が fail-closed に変わる**ため、
  そこは分けたまま実装させ、`check_workflow_from_file_fails_open_when_extraction_fails`
  で固定した。
- `migrate_clip_types` は `supplement` の真偽に関わらず**常に適用**する。古い画像の
  stale な `clip_type`（`"wan"` → `"qwen_image"` 等）を直して再投入を通すためで、
  条件付きにすると古い画像が壊れる。mock が受け取った内容で固定した。
- 新規実装は 4 helper（`check_model_nodes`・`extract_gen_params_from_image`・
  `supplement_model_nodes`・`migrate_clip_types`）。**本群で唯一、既存の Rust 実装が
  一切無かった段**である。ComfyUI への `POST /prompt` と `files.path` の id 引きは
  既存のものを使った。

### Removed

- **`POST /api/custom-nodes` と `GET /api/model-registry/{id}` の登録を削除した。**
  当初これらを「未移植の 2 件」と数えていたが、**Python 側に存在しないメソッド**
  であった —— Python が提供するのは `GET /api/custom-nodes`・
  `GET,POST /api/model-registry`・`DELETE /api/model-registry/<entry_id>` の 4 つのみ
  （`comfyui_discovery_api.py:68`・`comfyui_api_model_registry_routes.py:120,150,185`）。
  UI からの呼出もゼロ。転送しても Python が 405 を返すだけなので、**移植ではなく
  削除が正しい仕上げ**であった。axum が自ら 405 を返すようになり、往復が消える。
- 「Python-proxied complex routes (not yet migrated)」のコメントは事実でなくなった
  ため差し替えた。

### Documented

- **移植前に到達性を測ると作業内容が変わる、が本群で 3 回起きた。**
  (1) C1 で完全パス grep により生きた 6 route を「呼出ゼロ」と誤判定しかけた
  （UI が URL を動的に組むため）、(2) C3a で到達不能な分岐を試験で固定せよと
  指示していた、(3) C3c で「移植すべき 2 件」が削除対象だった。
  いずれも着手前に捕まえた。
- `proxy_generic` は呼出ゼロで残置した（削除の可否は別途判断）。
- **移植の度に「既にある部品の上に載るだけ」の形が現れた** —— custom-nodes は
  兄弟 6 本が既に native、model-registry は POST/DELETE が既に native、
  checkpoint-info は path 封じ込めの部品が両方あり、extract-workflow は
  `meta-extract` に PNG/EXIF/comfyui 判定があった。C3c だけが例外で、そこだけが
  真に新規実装を要した。

---

## [4.593.0] - 2026-08-07

### Changed

- **comfyui-bridge C3b: `POST /api/upload-controlnet-image` を Rust ネイティブ化した。**
  comfyui-bridge 10 route のうち 8 本目。

```
Rust standalone gap
  remaining work:  62 → 61
    no native path: 41 → 40
```

- 前半（multipart の `image` 部・拡張子検証・上限付き読み込み）は C3a の
  `extract-workflow` と同一なので `read_image_upload` として括り出した。
  ただし**既定ファイル名は別**（`extract-workflow` は `unknown.png`、
  こちらは `controlnet_input.png`）なので、そこは分けたまま保った。
- **拡張子は「アップロードされたファイル名」ではなく「バイト列の sniff」で決まる。**
  `_detect_image_format`（`comfyui_client_upload.py:16-21`）は先頭 2 バイトが
  `FF D8` なら jpg、`RIFF....WEBP` なら webp、それ以外は**すべて png** と見なし、
  ファイル名の stem に**その拡張子**を付け直して送る。⟹ `x.png` という名前で
  JPEG のバイト列を送ると `x.jpg` として格納される。ComfyUI は格納名で挙動を
  変えるため**意図的な仕様**であり、`upload_controlnet_image_sniffs_jpeg_under_png_filename`
  で固定した。JPEG でも WEBP でもないものは検証せず png 扱いにする点も
  Python に合わせた（Python に無い検証を足さない）。
- ComfyUI の応答 JSON に `name` が無い場合は**送信したファイル名を返す**
  フォールバックも維持した。
- 上流の失敗は **502**（500 ではない）。ComfyUI は上流サービスなので bad gateway。

---

## [4.592.0] - 2026-08-07

### Fixed

- **EXIF `UserComment` を自分で書きながら自分で読めていなかった。**
  `read_exif_tags`（`meta-extract/src/exif_reader.rs`）は全フィールドを
  `display_value()` で文字列化していたが、EXIF の `Undefined` 型はそれで
  **`0x<hex>` として描画される**。一方このアプリ自身が
  `core/bridge_core/bridge_save.py:33-50` で UserComment を
  `b"UNICODE\x00"` ＋ UTF-16 として書いており、コメントには「メタデータ
  パーサが読めるように」と明記されている。⟹ `YU_META:` の検出も JSON 解析も
  成立せず、`tagdb-core/src/import/fallback_chain.rs:81-100` が
  `exif:UserComment` として渡す値は**常に解析不能**だった。
  `comfyui.rs` がキー一覧に持つ `exif:UserComment` は一度も一致し得なかった。
- `Tag::UserComment` に限り `UNICODE\0` / `ASCII\0\0\0` の前置を剥がして復号する
  ようにした。**共有関数の出力変更なので消費者を確認した** ——
  `read_exif_tags` の呼出は `tagdb-core` の import fallback と
  `yu-server/routes/misc_admin.rs` の 2 系統のみで、いずれも復号後の方が正しい。
  `bridge_save.py` と同じ組み立て方で入力を作る往復試験を含む 4 本で固定した
  （UNICODE / ASCII / 前置なし / UTF-16 の端数バイト）。

### Changed

- **comfyui-bridge C3a: `parse-workflow-params` と `extract-workflow` を
  Rust ネイティブ化した。**

```
Rust standalone gap
  remaining work:  64 → 62
    no native path: 43 → 41
```

- 画像メタデータ解析は `crates/meta-extract` に**既にあった**ものを使った
  （`png.rs` の tEXt/iTXt、`exif_reader.rs`、`comfyui.rs` の workflow 判定）。
  再実装していない。`extract_simple_params` のみ新規 —— `simple_builder.rs` の
  `parse_params`/`build_workflow` は**逆方向**（パラメータ → workflow）であり
  流用できなかった。
- EXIF は一時ファイルを作らず `Cursor<&[u8]>` の入口を足した（パス漏洩も回避）。
- **圧縮 iTXt は専用の 422 文言で区別する** —— `png.rs` は圧縮 iTXt に非対応だが
  Python の PIL は読めるため、そのまま移すと**今は抽出できる PNG が移植後に
  「メタデータ無し」になる**。汎用の `ok:false` に混ぜず
  `Compressed iTXt workflow metadata is not supported` を返す。

### Documented

- **仕様の誤りを実装者が着手前に捕えた（通算 11 件目）。** 当初「未対応拡張子
  → 422」と書いたが、実際は `validate_image_filename` が先に走るため **400**。
  しかも `extract_workflow_from_image` 側の `"Unsupported format"` 分岐は
  `_ALLOWED_IMAGE_EXTS = {"png","jpg","jpeg","webp"}` と対応集合が**完全一致**
  するため**この route からは到達不能**であり、**到達不能な経路を試験で固定せよ**
  と指示していた。実際に出る 422 は「対応拡張子だが workflow メタデータが無い」
  場合である。plan §6.3 に元の記述を残した上で日付付き訂正を追記した。

---

## [4.591.0] - 2026-08-07

### Changed

- **comfyui-bridge C2: `GET /api/checkpoint-info` を Rust ネイティブ化した**。
  safetensors の先頭 8 byte と最大 16 MiB の JSON header のみを読み、Python と
  同じ 7 系統の family 判定、small metadata、mtime/size cache（最大 256 件）を返す。
- `source` の `header` / `unsupported` / `unavailable` 三値を維持し、remote ComfyUI、
  `models_root` 未設定、file 不在は `unavailable` の 200 とした。`models_root` 自動検出は
  localhost と既知 install path の組合せだけに限定した。
- model name の字句検査に既存 `reject_model_name` を再利用し、候補 file と root を
  canonicalize 後に既存 `path_is_within` で比較する二段 containment を実装した。
  root 外を指す symlink の実 file 試験を追加した。

```
Rust standalone gap
  remaining work:  65 → 64
    no native path: 44 → 43
```

---

## [4.590.0] - 2026-08-07

### Changed

- **comfyui-bridge C1: `GET /api/custom-nodes` と `GET /api/model-registry` を
  Rust ネイティブ化した**（残 10 route のうち 2 本）。画面は既に Rust 配信済
  （`main.rs:2260`）なので API のみが対象。
- `custom-nodes` は**兄弟が既に全部 native** であった —— `comfyui_bridge.rs:698`
  の Discovery 節（`/api/diffusion-models`・`/api/text-encoders`・`/api/clip-types`・
  `/api/weight-dtypes`・`/api/controlnets`・`/api/embeddings`）に `FilterQuery { q }`
  の形が揃っており、これ 1 本だけが取り残されていた。ただし**兄弟と違い要素が
  `{name, category}` の object で絞り込みが 2 フィールドに跨る**ため、兄弟の実装を
  そのまま流用はできない。POST は Python 側が GET しか提供しないことを確認した上で
  転送のまま残した。
- `model-registry` は **POST/DELETE が既に native** で、保存層・builtin 保護・
  `load_user_registry` が揃っていた。GET だけが転送であった。`/object_info` の
  enum 読み出し原始関数（`:411`）を再利用し、`UNETLoader/unet_name`・
  `VAELoader/vae_name`・`CLIPLoader/clip_name` の 3 件を引く。
- **best-effort であることが本 route の要**。ComfyUI 不達時も **200 で registry を
  返し**、3 リストは空、`models_error` を添える。ここを 5xx に変えると
  **ComfyUI 未起動時に登録内容が読めなくなる**。試験
  `get_model_registry_keeps_registry_when_comfyui_fails` で固定した。

```
Rust standalone gap
  remaining work:  67 → 65
    no native path: 46 → 44
```

### Fixed

- 移植前の到達性確認で、**生きている route を死んでいると誤判定しかけた**。
  `comfyui-bridge/api/<name>` の完全パスで grep し 8 本中 6 本を「呼出 0 件」と
  読んだが、UI が URL を動的に組むためであった。素の endpoint 名で引き直すと
  全 8 本に 2〜12 件の呼出があった。**到達性の確認は、パスの組み立て方に依存
  しない引き方で行うこと。**

---

## [4.589.0] - 2026-08-07

### Added

- **`scripts/rust_standalone_gap.py`** —— Python へ転送する route を列挙し、
  移植の残作業を単一の数として出す。**移植完了時に 0 になる。**
  既存指標では残作業が読めなかったため新設した。
  `rust_migration_coverage.py` は自身の docstring で
  「**転送するだけの route も「カバー済み」と数える**」と警告しており、98.8% は
  route の存在確認であって動作の確認ではない。
- **`scripts/rust_proxy_keep.txt`** —— 意図的に転送のまま残す決定の registry。
  `mcp_parity_exceptions.txt` と同じ prefix 一致・`#` コメント形式。**各項に理由と
  決定文書の出典を必須とした** —— 根拠なき項は残作業を静かに消すため、書けない
  ものは載せない（載せなければ残作業として現れるのが正しい既定）。

```
Rust standalone gap
  total routes:            881
  forward to Python:       79
    deliberate proxy-keep: 12
    remaining work:        67
      no native path:      46
      native + fallback:   6
      unclassified:        15
```

- **転送を「native 経路が皆無」と「native + 条件付き fallback」に分けた。**
  分けない限り桁違いの作業が同列に並ぶ。例: `/api/thumbnail/{file_id}` は
  DB path が `!` を含む（アーカイブ内メンバー）ときのみ Python に落ち、通常
  ファイルは native。`/ext/hailo-genai/api/llm/generate` は native 経路が皆無。
  判定不能は推測せず `unclassified` として残す（自信のある誤分類より、点検可能な
  不明の方が価値が高い）。

### Documented

- **3 つの指標が別々の分母を持つことを明示した。** 混同が「どこが残っているか
  分からない」の主因である。
  - MCP 露出パス基準 505/511 = 98.8%（`rust_migration_coverage.py`）
  - Python route 登録基準 388/438 = 88.6%（`rust-migration-inventory.yaml`）
  - Rust 転送実測 814/881 = 92.4%（本増分）
- **`rust-migration-inventory.yaml` の `status` は手で維持され再生成時に保持
  されるため陳腐化する。** 実測により、`proxied` とされた 6 件のページ route
  （`/agent_memory`・`/crypto_tools`・`/lan_cowork`・`/llm_router`・
  `/mesh_inference`・`/sw.js`）は**すべて既に Rust native** であった
  （`main.rs:2223, 2251-2255` の `frontend::*`）。
- Hailo の現在地を実測で確定した。**推論は分離・Rust 化とも完了**しており
  （`eauesque/yu-hailo-infer` を git rev 固定で依存、`infer_client.rs` が
  `/v1/infer/*` を呼ぶ。`crates/yu-infer` は sidecar binary を同一 target へ
  出すためだけの shim）、**画面も Rust が配信済**（`frontend.rs:97-102` の
  `page!` が拡張側 Jinja テンプレートを minijinja で描画）。残るのは
  `/ext/hailo-genai` と `/ext/hailo-yolo` の API 26 route のみ。
  うち `vlm/generate` と `chat/send` は既に infer client を使い、画像添付・
  web_search・subprocess mode のときだけ Python へ落ちる。

---

## [4.588.3] - 2026-08-07

### Documented

- **第五の逆辺（UI 層）の決着を記録した。** `/ext/lan_cowork/fleet/ui` が core の
  Jinja テンプレート `_nav.html` を描画していた件（F4c 設計中に発見。それまでの
  4 系統は全てコード水準で、UI 層のものは見落とされていた）。当時挙げた 3 案
  （テンプレート複製・nav 無し配信・core が API で公開）のいずれも採らず、
  **S4b で認可に用いたのと同じ host trait 化**に帰着していた ——
  `LanCoworkHost::render_nav(&self, csp_nonce, active) -> String` の 1 メソッドで、
  `lan_cowork_fleet_ui.rs:37` がこれを `<!-- NAV_PLACEHOLDER -->` へ差し込む。
  **crate 側にテンプレート依存は残っていない。**
- 残るのは実行時契約なので、trait に doc コメントとして明記した。単独で審査
  される crate では、**空文字列が失敗なのか正常なのかがコードから読み取れない**
  ため。空文字列は正常（nav 無しで描画）であり、案(b)は「nav を持たない host の
  既定動作」として自動的に成立している。
- Rust/Python の乖離も doc に残した。Python は `dist_v` を jinja global に持つ
  （`runtime_app.py:81`）ため 2 キーしか渡さないが、Rust の `init_env` に global は
  無いので 3 キーが要る。`lan_cowork_host_impl.rs:118-122` は 3 つとも渡している。
  **この失敗は例外ではなく `?v=` という cache-busting の静かな破綻として現れる。**
- 記録先: `docs/superpowers/plans/2026-07-31-lan-cowork-core-decoupling-survey.md`
  §0-B'。同文書の §0-B は module 依存の表であり**テンプレート依存が入る欄が無い**
  ため、5 行目として足さず独立した項とした。

---

## [4.588.2] - 2026-08-07

### Fixed

- **import の部分失敗が成功として報告されていた。** peer が提示した N 件の一部が
  転送に失敗しても、session は `status="completed"` かつ
  `last_seen_rowid=max_rowid` と記録され、UI は完了時に件数を `done/done` へ
  書き換えていた。三つの症状が重なっていた。
  - `batch_zip` は末尾で無条件に `Ok(())` を返す
    （`lan_cowork_import_executor.rs:351`）。chunk の download 失敗は
    `individual_http` へ退避し、そこでの失敗も `tracing::warn!` を残して次へ
    進むだけで `import_file_id_map` へ登録されない。呼び出し側から成功と
    区別が付かなかった。
  - **cursor が未取得ファイルを飛び越していた。** diff mode の次回実行は
    `after_rowid=last_seen_rowid` を要求するため、失敗したファイルは二度と
    提示されない。ただし UI は毎回 session を新規作成し `create_session` は
    `last_seen_rowid=NULL` を入れる（`lan_cowork_import_state.rs:186`）ので、
    UI 経路では cursor は write-only であった。到達は `POST /execute` へ既存
    `session_id` を渡す API 直叩きに限られる。
  - **UI が失敗件数を消していた（実害あり）。** `import-panel.ts:97` が
    `` `${s.done_files} / ${s.done_files}` `` で `total_files` を捨てており、
    直前の poll が `40 / 100` と出していても完了時に **`40 / 40`** へ上書きし
    `Import completed` を出していた。省略ではなく**上書き**なので、利用者は
    失敗に気付く手掛かりを持たなかった。task #19 は本件を「潜在的欠陥」と
    記録していたが、それは cursor の症状のみを見た評価であり、この症状は
    通常の UI 経路で起きる。
- 是正は、転送後に `to_import` のうち `import_file_id_map` に無い件数を数え、
  **0 の時のみ `last_seen_rowid` を書く**。0 でなければ `status="completed"` だけを
  書き、cursor は据え置く。metadata が壊れて転送されなかった項目も未処理に
  数える（意図的）。
- **watermark（失敗した最小 rowid − 1 まで進める）は採らなかった。** `max_rowid` は
  snapshot の上界であって「remote file id → rowid」の写像はこのコードに存在せず、
  誤った watermark は静かにデータを失う。進めなければ再提示が重複するだけで
  済む —— **無駄は欠落に優る。**
- **status は `"completed"` のまま据え置いた。** `"failed"` にすると UI は進捗を
  隠してエラーを出す（`import-panel.ts:103-107`）ため、100 件中 99 件成功の実行に
  対して誤りとなる。新しい status 値も足していない —— `done_files` は `"done"` と
  `"skipped"` の双方で増える（`import_state.rs:320-326`）ので、`total_files` との差が
  **転送失敗件数と厳密に一致**しており、schema にも status 語彙にも手を入れずに
  部分失敗を判定できる。
- **Python も同一形の欠陥を持っていたので同時に直した**
  （`import_executor.py:159-164`）。両実装に共通する欠落であり、是正は挙動変更
  であるため（`/fleet/logs/stream` の先例に同じ）。
- UI は `done / total` を保ち、`done < total` では進捗バーを 100% にせず
  `lan_cowork.import.partial` を通知する。11 言語 22 ファイルに key を追加した。

---

## [4.588.1] - 2026-08-07

### Fixed

- **試験用継ぎ目 6 つを本番ビルドから除いた。** `lan-cowork` に `test-seams`
  feature を新設し、`TEST_ALLOW_LOOPBACK`・`TEST_DESCRIPTOR`・`TEST_LOCK`・
  `test_guard`・`reset_client_state`（`lan_cowork_descriptor.rs`）と、
  それを読む本番側の分岐 2 箇所（`is_reachable_peer_ip` の loopback 例外、
  `descriptor_for_handler` の差し替え判定）を
  `#[cfg(any(test, feature = "test-seams"))]` で囲んだ。crate は単独公開されるため、
  従来は**依存する任意の下流 crate が loopback ガードを無効化できた**。
  yu-server は `[dev-dependencies]` からのみ feature を有効化する
  （workspace は `resolver = "2"` なので非 test ビルドへ合流しない）。
- **是正作業中に同型の継ぎ目を 2 つ発見し、同じ gate を掛けた。**
  `PeerRegistry::insert_for_test`（`lan_cowork_registry.rs:97`）は任意の
  `PeerInfo` を DB も検証も経ずに信頼レジストリへ書き込むため、descriptor の
  2 つより重い（peer 同一性の偽造）。`sign_headers`
  （`auth/peer_transport.rs:539`）は seed を引数に取るので権限昇格ではなく
  公開表面積の問題。
- **`cargo tree` は証明にならないため sentinel で実証した。** `cargo tree` は
  `--no-dev-dependencies` を付けぬ限り dev 辺を必ず描画し、正しい状態と漏れて
  いる状態が同じに見える。`lib.rs` に
  `#[cfg(feature = "test-seams")] compile_error!` を一時的に置き、
  `cargo build -p yu-server` が成功し `cargo test -p yu-server` が当該
  compile_error で落ちることを確認した（除去後の build 成功も確認）。
  feature が本番へ漏れていれば build 側が落ちるので、「直ったように見えるだけ」を
  通さない。
- **`cargo clippy --all-targets -- -D warnings` を緑にした（31 件）。** 分離先
  repo の CI は初回 commit で**この step で落ちていた**（Format は通過、Test は
  未実行）。本体 repo はこの crate に clippy を一度も掛けておらず素通りしていた。
  実バグはゼロで、内訳は未使用 import・dead code・style。`#[allow]` は最小
  scope に限り、全てに理由コメントを付した。
- **`gpu_info` が `gpu_info_from` を呼ばず同じ選択ロジックを複製していた**
  （`lan_cowork_fleet_machine.rs`）。dead_code 警告はその複製の帰結であり、
  `#[cfg(test)]` で塞ぐと**試験が本番経路でなく複製を検証する状態が固定**される。
  委譲へ改めた。`gpu_windows_wmi` は probe 失敗時のみ呼ぶ必要があるため
  `impl FnOnce` で遅延評価を保持した（引数渡しにすると毎回 WMI が走る）。

### Changed

- 分離先 repo の同期スクリプトが `[features]` を比較するようにした。従来は
  依存名の集合のみを見ており、**feature の追加は検知されなかった** ——
  `src/` は逐語複写されるので、`#[cfg(feature = "x")]` が届いても mirror 側は
  黙って何も生成しない。加えて `docs/SECURITY_REVIEW.md`（親の
  `LAN_COWORK_SECURITY_REVIEW.md` の複製）は crate 外にあり複写対象から漏れて
  いたので追加した。
- 同スクリプトの節解析が壊れていたのを実測で発見して直した。awk は `-v` 値の
  エスケープを先に処理するため `'^\[features\]'` が文字クラス `'^[features]'`
  へ退化し、`[package]` の鍵まで拾っていた。**非ゼロ終了するので一見「正しく
  drift を検出」に見える**形の誤りである。完全一致比較へ改め、依存が 0 件と
  解析されたら parse 失敗として異常終了する検査を足した。

---

## [4.588.0] - 2026-08-07

### Changed

- **`lan-cowork` が parity 検証ベクタを自前で持つようにし、crate 単独で
  `cargo test` が通る状態にした。** 抽出の最後の障害であった。
  `tests/vectors/` の 8 ファイルを `crates/lan-cowork/tests/vectors/` へ移し、
  `include_str!` 9 箇所と生成器 7 本の出力先を揃えた。
- **`Cargo.toml` に現れない結合であった。** `crates/lan-cowork/{src,migrations}` を
  workspace の外へ写して測ったところ、`cargo build` は成功する一方
  `cargo test` が 9 errors で落ちた —— `include_str!` は**ソースファイル相対**で
  解決され、四階層上の repo 直下へ達していた。前増分で得た「path 依存ゼロ」は
  **独立性の証明ではなかった**。⟹ 切り出しの実証は実際に外でビルドする以外にない。
- **S4 設計 §3.10 決定(4)「ベクタは本体 repo に残す」を覆した。** 実装者が着手前に
  止めて報告し、design-advisor の裁定を経ている。根拠は類推でなく二つの実測 ——
  (a) 8 JSON を読むのは `crates/lan-cowork/src` の 9 箇所のみで、Python 試験・
  `parity_harness.py`・`verify_rust_compat`・`pre_push_check.py` いずれも読まず、
  **本体 repo 側の消費者はゼロ**、(b) live な parity 契約は `parity_harness.py`
  （受入条件の 281 PASS）であってベクタではなく、決定(4) の唯一の積極的論拠
  「ベクタは parity の契約そのもの」が事実に反していた。
  加えて (4) に従うと暗号内部が最大 15 項目 `pub` 化し、**同一文書の決定(2)**
  （試験専用 feature を「独立審査される crate の公開面を広げる」として却下）と
  矛盾する。元の決定文は消さず日付付き改訂節を追記し、(5) の三根拠のうち
  「未公開 private crate へ依存できない」は**転用不可**（JSON は複写できる）と
  明記した。
- 配置場所の安全性は `cargo metadata --no-deps` の前後比較で実測した。
  `lan-cowork` の target は前後とも `lib` 1 つのみで integration-test target は
  増えていない（仕様からの推論ではない）。

### Added

- 保安審査文書に **§3.7** を追加。`lan_cowork_descriptor.rs:145-164` の試験用
  継ぎ目 4 つのうち 2 つが `pub` ＋ `#[doc(hidden)]` のみで **`#[cfg(test)]` を
  欠く**。`#[doc(hidden)]` は rustdoc から隠すだけで可視性に作用しないため、
  **この crate に依存する任意のコードから呼べる**。
  `TEST_ALLOW_LOOPBACK` は本番 `is_reachable_peer_ip` の loopback ガードを
  無効化でき、`TEST_DESCRIPTOR` は本番 `descriptor_for_handler` の
  descriptor 解決を丸ごと差し替えられる（より広い迂回面）。
  同ブロックの `test_guard`・`reset_client_state` は同じ形だが性質を異にする
  （迂回の実行でなく解除側）。`pub` を要する消費者は workspace 全体で 1 箇所のみ。
  **本増分では直さず記録のみ** —— S4e で試験配置が決まれば `pub(crate)` へ絞れる。

検証: lan-cowork **509 passed / 0 failed**(移動前と同数)、
yu-server 989 passed / 12 failed(既知の基準)、
`cargo check --workspace --all-targets` 緑、
`grep 'include_str!("../../..'` 0 件、生成器の往復は byte 一致、pre_push exit 0。

## [4.587.0] - 2026-08-07

### Changed

- **`lan-cowork` の path 依存を除き、単独でビルド・試験できる状態にした。**
  唯一残っていた `tagdb-core = { path = "../tagdb-core" }` を除去し、
  `apply_lan_cowork_standalone_schema` と `086_lan_cowork_peer_family.sql` を
  `crates/lan-cowork/{src/schema.rs, migrations/}` へ移した。戻り型は
  `TagdbError` から `sqlx::Error` へ。tagdb-core 側の冪等性試験も併せて移送。
- **測定で決めた。** `cargo check -p lan-cowork`（lib のみ）は tagdb-core 無しで
  通り、`--all-targets` のみ 14 errors —— すなわち**試験専用依存**であった。
- **S4 設計 §3.10 決定(5)「schema は tagdb-core に残す」を覆した。**
  元の判断文は消さず、下に日付付きの改訂節を追記している。理由は三つ ——
  (a) (5) の論拠「migration 順序管理の二重化」は 086 が順序列に載っていない
  ため当たらない（列挙されるのは 084/085 形式の `Migration` エントリで、
  086 は standalone 関数からの 1 参照のみ）、(b) (5) 自身の ⚠「peer token と
  pairing request の表定義が分離後は別 repo にある。**保安審査の対象そのもの**」が、
  分離が現実になった今では移す理由に転じる、(c) tagdb-core は未公開 private repo
  ゆえ切り出し先から依存できず、残すと**写した先で試験が一件も走らない**。
- 保安審査文書に **§3.5「`8.8.8.8` は探索先であって通信先ではない」**を追加した。
  `UdpSocket::connect` は既定の宛先を設定するのみでパケットを送らず、目的は
  `local_addr()` による外向き経路の特定である。公開 repo の審査で誤指摘され
  やすいため先回りして記した（`TcpStream` へ変わっていれば実接続であり、
  その変更は指摘に値する旨も併記）。

### Fixed

- `.gitignore` の `!*.md`（「Keep documentation」節）が全 md の無視を解き、
  gitignore の**後勝ち**規則により冒頭の `.claude/agent-outputs/**` を黙って
  打ち消していた。`git add -A` が subagent 報告 69 件を巻き込む状態であった。
  否定の後に再宣言し、末尾に置く旨を註記した。

検証: lan-cowork **509 passed / 0 failed**(基準 508 + 移送 1)、
tagdb-core 51 passed、yu-server 989 passed / 12 failed(既知の基準と一致)、
`cargo check --workspace --all-targets` 緑、`path =` 0 件、pre_push exit 0。

## [4.586.1] - 2026-08-06

### Fixed

- **fleet 再起動の偽 FAILED を修正した。** Rust の peer は `execv` により初回 poll
  (3 秒後)より速く再起動し得るため、`saw_down && uptime < pre_uptime` の連言だけでは
  **成功した再起動を 60 秒後に `restart_timeout` と誤報**し、fleet 全体の再起動
  ループを招いていた。`uptime < elapsed_since_t0` を選言として追加した。
  `uptime` はプロセス生存時間(`state.start_time.elapsed()`)であり `execv` で 0 に
  戻るため、非再起動時は `uptime = pre_uptime + elapsed ≥ elapsed` となり条件は
  成立しない。**一方向であり真の FAILED を偽の SUCCESS に変えない。**
  Python 側は変更していない(自身の再起動が遅く `saw_down` が確実に成立するため)
  —— **意図的な parity 逸脱**であり `lan_cowork_fleet_dispatch.rs:810-877` に明記した。
- **実装過程で偽 SUCCESS 経路を一度作り込み、除去した。** 当初 2.0 秒の epsilon を
  置いたが、非再起動時は `pre_uptime + elapsed < elapsed + 2.0 ⟺ pre_uptime < 2` と
  `elapsed` が相殺され、**起動 2 秒未満の peer が恒久的に成功と報告される**状態だった。
  boot loop 中の node こそ `pre_uptime` が小さく、最も検出したい対象が漏れる。
  epsilon の根拠(truncation・網羅遅延)は共に報告値を小さくする方向で検出を
  容易にしており、買うものが無かった。`pre_uptime ∈ {0,1}` を軸とする回帰試験を
  追加し、epsilon 復活時に落ちることを実測で確認した。

### Added

- `docs/development/development_docs/LAN_COWORK_SECURITY_REVIEW.md` —— 独立 repo
  分離時点の保安審査ガイド。crate の外を読まないと分からないことのみを収めた
  (認可は宣言でなく route 本体で効く・`require_admin_scope` は fail-open・
  nonce も allowlist で fail-open・静的塩が安全なのは token が 256 bit だから、等)。

## [4.586.0] - 2026-08-06

### Fixed

- **`/ext/lan_cowork/fleet/logs/stream` に IP 毎の接続制限を設けた(Python・Rust 同時)。**
  これは Rust の退行ではなく**両実装に共通する欠落**であった —— Python は
  `iter_sse_events(log_ring, ...)` を直に流し、Rust は `local_log_response` が
  `register_connection` を呼んでいなかった。core 側の log SSE は双方とも制限を
  持つ(いずれも IP 毎 3)ため、片側のみ直すと parity が割れる。
  制限値 **3**、超過は **429** ＋ `{"error": "too_many_log_sse_connections"}`。
  解放は Rust が `Drop` guard、Python が `try/finally`。中継枝は局所資源を
  消費しないため意図的に制限していない。
- guard が当初**強い `Arc<dyn LanCoworkHost>`** を保持して `AppState` を延命し、
  `Arc` の drop で `RecvError::Closed` を観測する既存試験を壊していた。
  `Weak` ＋ `.upgrade()` に改めた。**資源を解放するための guard が別の資源を
  掴んで離さない形**であった。

## [4.585.0] - 2026-08-06

### Changed

- **LAN Cowork 全 35 モジュールの crate 移送が完了した。** `crates/lan-cowork` は
  31 route ＋ 4 auth を持ち、`yu-server` に依存せず独立にビルド・試験される。
  `yu-server` 側に残るのは `lan_cowork_host_impl.rs`(孤児則)と
  `lan_cowork_split_integration_tests.rs`(yu-server 専用試験)の 2 ファイルのみ。
- **試験の対応を crate 毎の増減で検証した。** lan-cowork 504 passed(基準 302、+202)・
  yu-server 989 passed(基準 1189、−200)。移送元から消えた試験が悉く移送先で走る。
  workspace 合計は他 crate の分で嵩上げされるため、**crate を跨ぐ移送では
  合計値を受入条件に使えない**。

## [4.584.0] - 2026-08-06

### Changed

- **LAN Cowork S4d の本番 crate 分割を実施。** `lan-cowork` workspace member を新設し、
  LAN Cowork 所有 33 module と `path_guard` を移した。`LanCoworkHost`・中立型・
  `LanCoworkState` は新 crate、`AppState` 実装・`LogEntry` 変換・state 組立関数は
  `yu-server` に残した。依存方向は `yu-server → lan-cowork → tagdb-core` の一方向である。
- `level_rank` を LAN Cowork 側へ複製し一致試験を `yu-server` に追加した。
  `LOG_OPEN_SEAM_HOOK` の駆動試験と `BYPASS_ROUTES` の source-scan 試験も
  `yu-server` 側へ移した。
- **S4e の legacy unit-test 移送は未完。** `yu-server` が binary-only crate であるため
  逆向き dev-dependency は作らず、新 crate の test harness を一時的に空にした。

## [4.583.0] - 2026-08-06

### Changed

- **S4d-2 —— crate ガ実体ヲ持テリ。16 ファイルノ核ヲ移セリ。**
  依存グラフノ強連結成分 13 ＋ 真ノ葉 3 ＝ **16 ファイルヲ原子単位トシテ**
  `crates/lan-cowork` ヘ。<br>
  **試験ハ一件モ失ハレヲラズ** —— 合計 **1632 passed / 13 failed**(基準 1491/13)、
  IDENTICAL failure set、`cfg(any())` ゼロ。<br>
  **前回ノ差戻シトノ違ヒハ「順序」ノミ** —— 初回ハ移送ヲ先ニ行ヒ
  `AppState` 依存ノ試験ガ悉ク壊レタルガ故ニ 26 ファイルヲ無効化シ 1491→968 デ
  「緑」トセリ(保安中核五件ヲ含ム)。今回ハ **`TestHost` ヲ先ニ作リ**然ル後ニ移セリ。<br>
  **依存グラフハ移送ノ前ニ取ルベシ。** Tarjan-SCC ニテ 13 モジュールガ分割不能ト
  判明セリ —— 之ガ初回ノ近道ノ構造的理由ナリ。拙者ノ見積リ「随伴ハ二ファイル程度」ハ
  **八倍外レヲリタリ**。

### Fixed

- **parity 台帳ノ検査ガ crate 移動ヲ追ヘザリキ**(pre_push ガ正シク止メタリ)。
  `extension_contract_sync.py` ノ `ROUTES_DIR` 単数ヲ `ROUTE_SEARCH_DIRS` ト成シ、
  yu-server ト lan-cowork ノ双方ヲ探ス形ヘ。台帳ハ crate ヲ符号化セヌガ故、
  モジュールガ crate 間ヲ移ツテモ台帳ハ揺レズ。<br>
  `lan-cowork/src/auth/` ハ**意図的ニ探索対象外** —— 三本ハ route ニ非ズ
  peer 認証ノ下回リニシテ、台帳ニ載セバ誤ツタ記述ト成ル。<br>
  **緩メテ通シタルニ非ズ** —— 両向キノ変異ニテ噛ムヲ確カメタリ(未登録 route ヲ植ヱレバ検知、
  存在セヌモジュールヲ指セバ検知)。

- **新設試験ノ SQL ニ `+` ガ二箇所混入シヲリタリ。** テーブル作成ガ構文誤リデ落チ、
  **見出シハ「pairing nonce ノ試験ガ二件失敗」ニシテ分割ガ認証ヲ壊セシ如ク読メタルモ、
  実体ハ一文字ノ混入**ナリキ。一箇所ヲ直シテ再走セバ別ノ箇所デ落チタルガ故、
  全数走査ニ切リ替ヘタリ。当該試験ハ実質的ナリ —— `peek_entry` ニテ nonce ノ保持、
  並行 pairing ニテ request_id ノ相異、**`check_static_bypass` ガ bypass 表ヲ
  正シク引クコト**ヲ crate 境界ヲ跨イデ確カム。

## [4.582.0] - 2026-08-06

### Changed

- **S4c —— core → LAN Cowork ノ循環辺ヲ、crate ヲ一ツモ作ラズニ閉ヂタリ。**
  `resolve_non_strict`(ト私有ノ随伴物 `enum PathPart`・`path_parts`・`prepend_parts`)ヲ
  `lan_cowork_sync.rs` ヨリ `path_guard.rs:80` ヘ移セリ。白箱試験モ同居サセタリ。
  **`path_guard.rs` ノ `lan_cowork` 参照ハ零**ト成レリ。<br>
  呼出ハ悉ク付ケ替ヘタリ —— `path_guard.rs:90`(循環ノ元)・`lan_cowork_sync.rs` 内 4 箇所・
  `import_transfer.rs:135,138`・`local_import.rs:555,562`。<br>
  **之ハ審査ガ出セシ第三案ナリ。** 拙案ハ二ツトモ「分割ト同時ニ決ムル」形ニシテ、
  分割前ニ環ヲ閉ヂ得ルヲ見テヲラザリキ。`resolve_non_strict` ハ LAN Cowork 固有ニ非ズ
  **汎用ノ非厳密 canonicalize** ニシテ本体ハ std ノミニ依ル。<br>
  保安境界(resolve→compare)ハ**同一モジュール内ニ留マレリ**。
  `path_is_within` ノ doc 自身ガ「之ハ比較ノ半分ニシテ、解決ヲ先ニ行ハネバ
  containment 検査ハ無言デ破ル」ト述ブルガ故、crate ノ縫ヒ目デ分断シテハナラヌ。
  `arch-constraints.yaml:182` ハ更新不要(共有述語ノ所在ト意味ガ不変ナルガ故)。<br>
  全件 1491 passed / 13 failed ニテ既存ト同一集合。

### Fixed

- **逆辺ノ表ヲ増分毎ニ取リ直スベキコトヲ記セリ** —— 実装者ガ
  **拙者自身ノ作リタル辺二本ヲ表ニ載セ忘レヲルヲ見出セリ**:
  `security.rs:8 → FleetUiNonce`(S4a)・`auth/middleware.rs:84 → PeerSourceIp`(S4b)。
  §1.3 ハ v4.579.0 時点ノ計測ニシテ、其ノ後ノ二増分ガ辺ヲ増ヤシヲリタリ。<br>
  **向キハ意図ドホリ** —— 分割後、両型ハ中立型トシテ LAN Cowork crate 側ヘ行キ、
  yu-server ガ import ス(yu-server → LAN Cowork。許容サルル向キ)。
  **然レドモ crate 境界越シニ `pub` ト成ル**ガ故、独立 repo ノ保安審査対象面ガ広ガル。
  §6.7 ノ公開面一覧ニ載スベシ。設計書 §1.3.1 ニ記セリ。

## [4.581.0] - 2026-08-06

### Changed

- **S4b —— 認可ヲ host trait ノ背後ヘ移セリ。分割ノ内デ最モ危キ段ナリ。**
  LAN Cowork 本番ヨリ `crate::auth::scope::{require_session, AuthContext}` ト
  `crate::auth::client_ip::ClientIp` ノ参照ヲ悉ク絶テリ(残零)。<br>
  `async fn require_session(&self, session: Option<&Session>) -> Option<Response>`。
  **保ツベキ五性質ノ悉ク保タレタリ** —— (一)async (二)`pin_auth_enabled == false` ノ
  許可経路 (三)`Option<&Session>` ノ非縮約 (四)401 ＋ 固定本体
  (五)**`AuthContext.reason` ヲ読マヌコト**。<br>
  (五)ハ審査ガ見出セシモノニシテ設計書 rev1 ニハ無カリキ ——
  認証連鎖ハ API key ヲ session ヨリ先ニ評価スルガ故、`reason` ニテ判ズレバ
  **有効ナ session ト無関係ナ API key ヲ同時ニ提示セシ要求ヲ誤ツテ拒否ス**。
  `AuthContext` ガ本増分ノ視野ニ在ルガ故ニ**構造的ナ誘惑**トシテ存在シタリ。<br>
  実装ハ**再実装ニ非ズ薄キ委譲**ナリ。意味ノズルル余地ヲ残サズ。<br>
  `ClientIp` ハ `PeerSourceIp(pub String)` ヘ。**`IpAddr` ヘ射影セズ** ——
  `"unknown"` ガ rate limit ノ bucket 鍵・DB 列・request↔IP 束縛検査ニ用ヰラルルガ故、
  射影セバ孰レカガ壊ル。挿入ハ core 側(`auth/middleware.rs:84`)。<br>
  全件 1491 passed / 13 failed ニテ既存ト同一集合。

## [4.580.0] - 2026-08-06

### Changed

- **S4a —— crate ヲ作ラズニ本番ノ core 依存ヲ四種減ゼリ。**
  (一)`inbound_read` ノ局所ヘルパ `relayed_sse_event` ノ戻リ型ヲ中立ナ
  `RelayedSseEvent` ヘ差シ替ヘ、`crate::sse::SseEvent` ヲ落トセリ。
  (二)`agent_journal::record_action` ヲ trait メソッド
  `record_journal_action` ニテ包ミ、`lan_cowork.rs` ノ直接 import ヲ絶テリ。
  (三)`security::CspNonce` ヲ **LAN Cowork 所有ノ中立 newtype `FleetUiNonce`** ニ替ヘ、
  core ノ `security::layer` ガ挿入スル形トセリ。
  (四)`peer_pairing_crypto.rs:102` ノ intra-doc リンクヲ平文化セリ
  (crate 境界ヲ跨グト解決不能ト成ルガ故)。<br>
  **`CspNonce` ノ二案ノ内、中立 newtype ヲ選ビタル理由** —— 他案(LAN Cowork 側ニ
  extractor ヲ定義)ハ内部デ `crate::security::CspNonce` ヲ読ム要アリ、
  **参照ヲ別ファイルヘ移スノミ**ニシテ消エズ。中立 newtype ナラバ参照ハ core 側ニ留マリ、
  分割後ノ依存ノ向キ(core → LAN Cowork)トモ一致ス。<br>
  実測: 本番依存ハ **17 種 32 箇所 → 16 種 28 箇所**。
  `crate::sse` 残ル一件ハ `lan_cowork_host.rs` ノ impl 内ニテ実際ニ `SseEvent` ヲ組ム
  正当ナ残存、`agent_journal` 残ル一件モ同ジク trait impl ノ委譲ニシテ意図セシ継ギ目ナリ。<br>
  全件 1491 passed / 13 failed ニテ既存ト同一集合。

### Fixed

- **計測手法ノ第三ノ欠陥ヲ記録セリ** —— 走査スクリプトハ正規表現ニテ源ヲ読ムガ故、
  **doc コメント中ノ完全修飾パスヲ実参照ト同一ニ数フ**。S4a 実装中ニ実測 ——
  `RelayedSseEvent` ノ doc ニ `crate::sse::SseEvent` ト書キタルトコロ、
  import モ型モ既ニ消エヲルニ一件計上サレタリ。<br>
  既知ノ盲点ハ之ニテ三ツ —— (i)再エクスポート(経路名ニ `lan_cowork` ガ現レヌ)
  (ii)`crate::` 記法ニ非ザル結合(`include_str!`・外部 crate)
  (iii)コメントト実コードノ非区別。**設計書 §1.0 ニ明記セリ。**

## [4.579.0] - 2026-08-06

### Changed

- **S3z —— crate 分割ヲ妨ゲヲリタル最後ノ構造的依存ヲ消セリ。**
  `AppState` ヨリ `peer_registry`・`fleet_manager`・`lan_cowork_settings_lock` ノ
  三フィールドヲ削除セリ。**`state.rs` ノ `lan_cowork` 参照ハ零**ト成レリ。
  三ツハ `LanCoworkState` ニノミ存ス。`main.rs` ガ `Arc` ヲ生ミ
  `LanCoworkState::new` ヘ渡ス形トセリ。<br>
  **一見危フク見ユルモ構造的ニ安全ナリ** —— `main.rs:934` ノ
  `lc_state.peer_registry.set(registry)` ハ **`lc_state` 自身ノフィールド**ニ対シテ
  行ハルルガ故、router ノ見ルモノト同一ナルコトガ保タル。構築時ノローカルハ
  以後一切用ヰラレズ、**乖離シ得ル第二ノ経路ガ存セズ**。<br>
  実装者ハ「両変異ガ route 層ノ試験デハ捕マラズ identity 試験一本ノミガ掴ム。
  本番配線ノ退行ハ route 層ニ見エヌ」ト正直ニ申告セシガ、**実際ニハ乖離スル相手ガ
  存セヌ**ガ故、懸念ハ稍過大ナリキ。「掴メテヲラヌ」ト言ハルル時モ其ノ範囲ヲ
  自ラ確カムル価値アリ。<br>
  **識別性ヲ両方実証セリ** —— `new()` ガ受ケ取リタル `Arc` ヲ無視スル変異ニテ
  `peer_registry`・`settings_lock` 共ニ identity 試験ガ落ツ。<br>
  全件 1491 passed / 13 failed ニテ既存ト同一集合。<br>
  **⟹ S4(crate 分割)ノ前提ガ揃ヘリ。**

## [4.578.0] - 2026-08-06

### Changed

- **S3d-2 —— S3 完了。LAN Cowork ノ本番コードハ core ノ `SharedState` ヲ名指サズ。**
  `routes()` ヲ持ツ十ファイル(`lan_cowork`・`pairing`・`client`・`local_import`・
  `fleet_consent`・`fleet_allowlists`・`fleet_ops`・`import_meta`・`inbound_read`・`settings`)ヲ
  登録スル全ハンドラト共ニ `Router<LanCoworkState>` ヘ。`main.rs` ニテ **LAN Cowork ノ
  router 十一本惉ク `.with_state(lc_state.clone())` 経由デ merge** サル形トなレリ。<br>
  併セテ `auth/peer_transport.rs`(`require_peer_auth` 他)ト `routes/peer_identity.rs`
  (`local_peer_id`)モ変換 —— **両者ハファイル名 glob ノ外ニ居ル LAN Cowork 所有
  モジュール**ナリ(設計書 §1.2。rev3 マデ落トシヲリタル四度目ノ同型失敗)。
  繰延ベタル `sync_fleet_manager`/`start_fleet_manager_if_configured` モ
  `&LanCoworkState` ヘ。`fleet_ops.rs` ノ `LogRingBuffer` import ハ試験 mod 内ヘ移セリ。<br>
  **実測: 本番ノ非コメント `SharedState` 参照ハ一件ノミ**(31 モジュール中 30 ガ完全切離)。
  残ル一件ハ `lan_cowork_host.rs` ノ `from_shared()` ナリ —— **設計上ノ分割線**ニシテ
  `SharedState` ヲ名指スベキ唯一ノ場所。S4 ニテ此ノファイルガ trait/中立型(LAN Cowork 側)ト
  `impl`(yu-server 側)ニ分カル。<br>
  全件 1492 passed / 13 failed ニテ既存ト同一集合。<br>
  **残ル構造的障害ハ `state.rs:183/185`** —— core ガ LAN Cowork ノ型
  (`PeerRegistry`/`FleetManager`)ヲ名指ス逆向キノ依存ナリ。S3z ニテ消ユ。

## [4.577.0] - 2026-08-05

### Changed

- **S3d-1 —— `main.rs` 直付ケノ二群ヲ `Router<LanCoworkState>` ヘ抽出セリ。**
  `lan_cowork_fleet_peers.rs`(四 route、旧 `main.rs:2106-2121`)ト
  `lan_cowork_fleet_dispatch.rs`(三 route、旧 `:2135-2146`)。両者トモ `routes()` ヲ
  持タズ `main.rs` ノ単一 builder 鎖ニ直接 `.route()` サレヲリタルが故、
  **場デ変換スレバ鎖全体ノ state 型ヲ巻キ込ム**。S3a ノ `fleet_ui` ト同型ナリ。<br>
  **塊ノ大きさヲ事前ニ宣言セズ、rustc ニ閉包ヲ計算サセタリ**(設計書 §4.2)。
  結果、引キ込マレタルハ `lan_cowork_fleet_manager.rs` ト `main.rs` ノ二ノミ。
  **二反復(9 errors → 0)ニテ収束**セリ。<br>
  名前に依る静的解析ヲ三通リ試ミ三通リトモ外シタル後ノ措置ナリ —— `new` ハ九ファイル、
  `fleet` ハ三ファイルニ同名定義ヲ持ツが故、**名でハ原理的ニ解ケヌ**。<br>
  `FleetManager` ノ `start`/`refresh`/`poll_loop`/`fetch_peer`/`request_peer`/`fleet_timing` モ
  `LanCoworkState` ヘ。`sync_fleet_manager`/`start_fleet_manager_if_configured` ハ
  呼出元(`lan_cowork.rs:438`・`main.rs:916`)ガ次塊ナルが故意図的ニ繰延ベ、
  内部デ `LanCoworkState::from_shared(state)` ヲ組ム形トセリ。<br>
  変換三ファイルノ本番ニ `SharedState` 型ノハンドラ・ route・マネージャメソッドは皆無。
  (`fleet_peers`/`fleet_dispatch` ニ残ル一件ハ doc コメントナリ。)<br>
  全件 1492 passed / 13 failed ニテ既存ト同一集合。

## [4.576.0] - 2026-08-05

### Changed

- **S3c —— log 配信経路ヲ中立化セリ。** trait ニ `log_open(limit, level)` ヲ加ヘテ **十五メソッド**。
  LAN Cowork 所有ノ中立型 `LogLine`(seq/timestamp/level/target/message ノ五)ト
  `LogEvent { Line, Closed }` ヲ設ケ、core ノ `LogRingBuffer`/`LogEntry` ヲ
  `lan_cowork_fleet_ops.rs` ノ本番経路ヨリ退ケタリ。<br>
  **三ツノ罠ヲ避ケタリ**(孰レモ単独ニテ「試験ヲ通リタルママ挙動ダケ変ハル」ヲ起コシ得):<br>
  (一)**level ノ語彙** —— core ハ `WARN`、API ハ `WARNING`。正規化後ノ名ヲ
  `LogLine.level` ニ載セバ `TRACE` ノ rank ガ 0→1 ニ化ケ、`level=DEBUG` ノ要求ニテ
  **今日落ツ行ガ通ル**。逆ニ API 語彙ヲ `log_open` ヘ渡セバ `ring.recent` ガ未知語ヲ
  rank 0 ニ落トシ、**backlog ノ絞込ダケガ静カニ消ユ**。⇒ 入口・出口トモ core 語彙ニ固定シ、
  `WARNING→WARN` 写像ト live 絞込ハ LAN Cowork 側ニ残セリ。<br>
  (二)**`subscribe` ト `recent` ヲ二メソッドニ割ラズ** —— 順序ヲ逆ニ書クモ
  コンパイルモ試験モ通リ、稀ニログガ一行消ユルノミ。<br>
  (三)**`Lagged`/`Closed` ノ区別** —— `BoxStream<LogLine>` デハ消ユルが故ニ `LogEvent` 列挙。<br>
  **順序保証ガ試験ニ掴マレヲルコトヲ実証セリ** —— impl 内ノ `subscribe` ト `recent` ヲ
  入レ替ヘタル変異ニテ `log_sse_live_filter_seam_close_and_connection_budget_are_pinned`
  ガ落ツ。**落チ方モ正確ナリ** —— 逆順ナレバ注入セシ行ガ backlog ノスナップショット後・
  `subscribe` 前ニ発生スルが故、**backlog ニモ live ニモ現ハレズ**。
  `seam_hook` モ impl 側ヘ移設セリ(旧位置ニ残セバ到達不能ト成ル)。<br>
  全件 1492 passed / 13 failed ニテ既存ト同一集合。

## [4.575.0] - 2026-08-05

### Changed

- **S3b —— `PeerTransport` ヨリ core ノ `Arc<SseHub>` ヲ外セリ。**
  `sse_hub: Arc<SseHub>` ヲ `host: Arc<dyn LanCoworkHost>` ト成シ、`sse_send(...)` ヘ移セリ。
  自由関数 `invalidate_outbound_token` ノ引数モ `&dyn LanCoworkHost` ト成シ、
  `import_transfer.rs` → `import_executor.rs` → `local_import.rs` ノ連鎖ヲ追随セシメタリ。
  trait ニ `sse_receiver_count()` ヲ加ヘ **14 メソッド**(呼出側 `inbound_read.rs:556` ハ
  後続増分ニテ変換ス)。⟹ `lan_cowork_transport.rs`・`import_executor.rs`・
  `import_transfer.rs` ノ三本ハ `SseHub`/`SseEvent` ノ参照**皆無**ト成レリ。<br>
  **設計書ノ「試験ダブル新設」ハ不要ナリキ。** S3a ニテ `AppState` ガ trait ヲ実装セシ
  ガ故ニ、既存ノ `semantic_test_state(true)` ガ其ノママ `Arc<dyn LanCoworkHost>` ト成ル。
  試験 30 箇所超ノ `&SseHub::new()` ハ之ニ置換セリ。14 メソッドノ手書ダミー
  (`db() -> &SqlitePool` ヲ返ス以上、実 pool ヲ保持セネバナラヌ)ハ書カズニ済メリ。
  ⟹ **設計書ガ「最モ重キ増分」ト見積モリシハ、S3a 着地前ノ視界ニ依ル過大評価ナリキ。**<br>
  **失効ノ意味論ヲ保テリ** —— `invalidate_outbound_token` ハ定義一・呼出三
  (`transport.rs:194`・`import_transfer.rs:217,347`)ニテ増減無シ。
  `source` ノ三形態(`"lan_cowork"`／`"lan-cowork"`／`peer:{id}`)モ正規化セズ。<br>
  全件 1492 passed / 13 failed ニテ既存ト同一集合。

### Fixed

- **`wd_tagger` ノ試験ガ約半分ノ確率デ落ツル瑕疵ヲ是正セリ**(S3b 検証中ニ判明)。
  ```rust
  assert_eq!(elapsed * 100.0, (elapsed * 100.0).round());
  ```
  `elapsed` ハ**実測時間**ナルガ故ニ毎度異ナリ、二桁ニ正シク丸メタル値デモ落ツ ——
  `4.27 * 100.0 == 426.99999999999994`、`4.89 → 488.99999999999994`、
  `4.44 → 444.00000000000006`。単独六回ニテ **三通過／三失敗**ヲ実測セリ。<br>
  **之ハ増分ノ検証ソノモノヲ蝕ミヲリキ** —— 「既存 13 失敗ト同一集合」ノ判定ガ
  増分ノ内容ト無関係ニ揺レ、**退行ト偶然ヲ区別デキヌ**。実際 S3b ノ検証ニテ
  一度「S3b ガ壊セリ」ト疑ヒ、単独二回ノ失敗ヲ見テ確信シカケタリ。<br>
  epsilon 比較(`< 1e-6`)ニ改メ、**緩メ過ギヌコトヲ実証セリ** ——
  本番側ノ丸メヲ外セバ五回トモ発火ス(`got 4.798488` 等)。八回連続通過モ確認。
  同型ノ瑕疵ハ他ニ無シ(全 `.rs` ヲ走査)。

## [4.574.0] - 2026-08-05

### Changed

- **S3a —— LAN Cowork ハンドラヲ `SharedState` ヨリ切離ス第一歩。**
  `LanCoworkHost` ヨリ **`Clone` supertrait ヲ除キ**(`Clone: Sized` ガ trait object 化ヲ
  阻ミヲリキ。棄テタル generic 案ノ遺物ナリ)、実装ヲ `SharedState` ヨリ **`AppState` ヘ移設**。
  `LanCoworkState`(= `Arc<dyn LanCoworkHost>` ＋ LAN Cowork 所有ノ三 `Arc`)ヲ設ケ、
  `lan_cowork_fleet_ui.rs` ヲ変換シテ其ノ一 route ヲ `Router<LanCoworkState>` トシテ抽出セリ。
  `render_nav` ヲ trait ニ加ヘ **`minijinja` ノ型ヲ LAN Cowork ヨリ隠セリ**。
  `chief_enabled` ハ `&dyn LanCoworkHost` ヲ取ル。<br>
  **設計書ハ四度ノ差戻シヲ受ケ、計 19 件ノ must-fix ヲ実装前ニ潰セリ**
  (`docs/superpowers/plans/2026-08-05-lan-cowork-s3-handler-decoupling.md`)。
  中核主張「trait ハ object-safe」ハ**偽ナリキ** —— 挙ゲタル根拠(全メソッド同期・`&self`・
  `Self` 非返却)ハ悉ク真ナルモ、阻害要因ハ其ノ一行上ノ supertrait ニ在リ、
  **根拠ガ結論ヲ支ヘヲラザリキ**。<br>
  **`AppState` ノ三フィールドハ per-field `Arc` ト成シ、名ヲ変ヘズ**(既存 135 箇所ハ
  Deref ニテ通ル)。⚠ **複製ヲ作ラバ静カニ壊ル** —— 複製セシ `peer_registry` ノ
  `OnceLock` ハ `main.rs` ノ `set()` ヲ受ケズ **route ハ恒久的ニ 503**、複製セシ
  `settings_lock` ハ `config.json` ノ read-modify-write ヲ直列化スル mutex ヲ割リ、
  **allowlist 更新・consent 応答・peer 失効ヲ稀ニ失フ**。孰レモ**コンパイルモ試験モ通ル**。<br>
  **識別性ヲ実証セリ** —— 構築ヲ `LanCoworkState::from_shared()` 一本ニ集約シ
  (crate 内ノ構造体リテラル構築ハ其ノ中ノ一箇所ノミ)、其ノ中ヲ変異サセテ
  identity 試験ト `fleet_ui` 試験 5/9 ノ落ツルヲ確カメタリ。<br>
  **当初追加セシ `Arc::ptr_eq` 検査ハ何モ守リヲラザリキ** —— 試験ガ自ラ `Arc::clone` シテ
  構築シ其ノ恒等性ヲ主張スルガ故ニ、**防ガントスル当ノ瑕疵(`main.rs` ヲ `Arc::new` ニ
  変フルコト)ガ起コリテモ通リ続ケタリ**。⟹ 本番ト試験ガ同ジ継ギ目ヲ通ル形ヘ改メタリ。
  「変異サセタラ落チタ」ハ、**何ヲ変異サセタカヲ問ハズシテハ証明ト成ラズ**。<br>
  全件 1492 passed(+1 ハ新設ノ identity 試験)ニテ既存 13 失敗ト同一集合。<br>
  **計測ノ不備ヲ二度繰返セリ** —— `cargo test` ヲ二度走ラセ、要約(13)ト失敗一覧(14)ヲ
  **別々ノ実行**ヨリ取リタリ。差分ノ `cross_search::open_file_uses_db_record_path` ハ
  単独ニテ 3/3 通ル flaky ニシテ S3a ノ触レヌ領域ナリ。一実行ヨリ双方ヲ取ル形ニ改メタリ。<br>
  **残ル S3 ハ** S3b(`PeerTransport` 改修 ＋ 試験ダブル新設。最重)・S3c(`log_open`)・
  S3d(`routes()` 十本 ＋ `peer_*` 二本)・S3z(`AppState` ヨリ三フィールド削除)。

## [4.573.0] - 2026-08-05

### Added

- `LanCoworkHost` ニ `sse_send(source, kind, timestamp, payload)` ヲ加ヘタリ(S2b)。
  **加算ノミニシテ呼出六箇所ハ未変換**(S3 ニテ行フ)。<br>
  **署名ハ三往復ヲ経テ確定セリ。毎度実在ノ欠落フィールドガ出デタリ** ——
  当初ノ二引数 `(kind, payload)` ハ `source` ヲ落トス(`"lan_cowork"`／`"lan-cowork"`／
  `"peer:{peer_id}"` ノ三通リニ分カレ、**同ジ kind/payload ニテ source ノミ異ナル組ガ在ル**
  ガ故ニ復元不能)。三引数ハ `timestamp: f64` ヲ落トス(呼出側ガ明示的ニ渡ス)。
  四引数ニテ六箇所悉ク収マリ、第五ノ欠落無シ。<br>
  **SSE ノフィールド欠落ハ試験ノ失敗トシテ現レズ、UI ガ静カニ更新セヌ形デ出ヅ。**
  二引数ノママ書キ換ヘヲレバ、後カラ原因ヲ特定スルハ困難ナリキ。<br>
  **`"lan_cowork"` ト `"lan-cowork"` ノ揺レハ正規化セズ逐語ニテ保テリ** ——
  恐ラク意図セヌ不統一ナルモ、受ケ手ガ `source` ニテ分岐シヲレバ挙動ガ変ハル。
  整フルハ**挙動ヲ変フル別増分**トスベシ。<br>
  `subscribe` ト `log_push` ハ**依然トシテ欠ク** —— 本番ノ呼出元ガ零ナルガ故ナリ
  (三箇所・二箇所トモ `#[cfg(test)]` 内)。設計書ハ「log relay ガ `broadcast::Receiver` ヲ
  await スルガ故ニ stream 抽象ヲ要ス」ト記シヲリシガ**別ノ機構ト取違ヘヲリキ** ——
  `/fleet/logs/stream` ハ LAN Cowork 自身ノ `LogRingBuffer` 参照ヲ用ヰ core ノ `SseHub` ヲ
  購読セズ。⟹ **stream 抽象モ第三ノ crate モ不要ナリ。**<br>
  全件 1491 passed ニテ新規失敗ゼロ。

## [4.572.0] - 2026-08-05

### Added

- **repo 分離ノ第二歩** —— `LanCoworkHost` trait ヲ設ケ `SharedState` ニ実装セリ
  (`routes/lan_cowork_host.rs`)。**加算ノミニシテ既存ハンドラハ一ツモ変ヘズ。**<br>
  **依存ノ向キヲ一方向ニスル為ノ形ナリ** —— LAN Cowork ヲ別 crate ヘ抜クニハ
  trait ヲ LAN Cowork 側ニ定義シ yu-server ガ之ヲ実装セネバナラヌ。逆(LAN Cowork ガ
  `SharedState` ニ依ル)ハ循環ス。<br>
  **面ハ実測ニテ極メテ狭シ** —— `SharedState` 五十九フィールドノ内 LAN Cowork ノ触ルルハ十一、
  内三ツ(`fleet_manager`・`peer_registry`・`lan_cowork_settings_lock`)ハ LAN Cowork 自身ノ状態
  ニシテ分離時ニ移ル。外カラ要スルハ八ツ。且ツ `Config` ハ五十九フィールドノ内六ツ、
  `SseHub` ハ三操作、`LogRingBuffer` ハ一操作ノミ。<br>
  **SSE 三操作ト log 一操作ハ意図シテ欠キタリ** —— 呼出署名ガ core 所有ノ型
  (`SseEvent`・`PartialEntry`)ヲ**引数ニ**要スルガ故ニ、trait ガ之ヲ名指セバ**依存ガ逆転ス**。
  設計書ハ「操作ヲ trait メソッドニテ包メル」ト記シヲリシガ、**包ム先ノ引数型ガ core 由来ナラバ
  包メテヲラヌ**。実装者ノ指摘ニテ訂セリ。移動デモ解ケズ ——
  `SseEvent` ハ十一ファイル中 LAN Cowork ハ四、`PartialEntry` ハ四ファイル中一ニシテ、
  孰レモ core ノ共有型ナリ。<br>
  **⚠ 次ニ触ル者ハ core ノ型ヲ import シテ SSE/log ヲ足ス勿レ。** 本増分ノ存在意義タル
  循環依存ノ除去ガ無言デ巻キ戻ル。trait ノ doc ニ其ノ旨ヲ記セリ。
  残ル四メソッドハ引数ノ中立化(`sse_send(kind, payload)`)ト `subscribe` ノ stream 抽象ヲ
  経テカラ足ス。<br>
  検証ハ**全メソッドヲ呼ビテ直接フィールドアクセスト一致スルヲ主張ス**
  —— 欠ケテモ配線ヲ誤リテモ落ツ。全件 1491 passed ニテ新規失敗ゼロ。

## [4.571.0] - 2026-08-05

### Changed

- **repo 分離ノ第一歩** —— `auth/chain.rs` ノ LAN Cowork bypass 列挙(本番三十五箇所)ヲ
  `routes/lan_cowork_bypass.rs` ノ `BYPASS_ROUTES` ヘ移セリ。**`chain.rs` ノ本番部ニ
  `lan_cowork` ハ零個ト成レリ。** core ノ認証鎖ガ LAN Cowork ノ route ヲ名前デ知ラヌ状態ヘ
  至リ、別 crate ヘ抜ク前提ガ整フ。<br>
  **`check_static_bypass` ノ signature ハ不変**ナリ —— `run_chain`(`chain.rs:49`)ニテ
  **関数ポインタ配列ノ要素**ナルガ故ニ、引数ヲ足セバ同一型デ無ク成リ配列ガ壊ル。
  内部ヨリ `const` テーブルヲ参照ス。<br>
  **二十七本ハ三判定種ヨリ成ル** —— Exact 二十四・SingleSegment 一
  (`/fleet/consent/status/{id}`。空ニ非ズ且ツスラッシュヲ含マヌ)・Prefix 二
  (`/api/peer/import/{file,stream}/`。素ノ `starts_with`)。
  設計書ハ rev3 マデ「悉ク完全一致」ト誤リヲリ、其ノ前提ノ上ニ「型デ規範ヲ守レル」ト
  記シヲリキ。実測ニテ訂セリ。<br>
  **正味ノ安全性向上ナリ** —— 従来 `fleet_bypass_is_limited_to_the_fourteen_peer_routes` ハ
  十四本ヲ列挙スルノミニテ**本数ヲ固定セズ**、**二十八本目ヲ足シテモ落ツル試験ハ皆無**ナリキ。
  本増分ニテ総数二十七・群別(fleet 14／import 5／peer 8)・判定種(24／1／2)ヲ pin シ、
  reason 八種モ pin セリ(従来 LAN Cowork ノ reason ヲ主張スル試験ハ**ゼロ**)。<br>
  **且ツ「一箇所シカ無キ」コトヲ機械検査ス** —— `chain.rs` ノ本番部ニ `lan_cowork` ガ
  零個ナルヲ source 走査ニテ主張ス。之無クバ、テーブルヲ集メタル後ニ `chain.rs` ヘ直接
  書キ足セバ**無認証 route ガ一本増エテ何レノ試験モ落チヌ**。<br>
  併セテ `arch-constraints.yaml` ノ `rust_session_bypass` ノ登録先ヲ新設テーブルヘ改メタリ
  —— **規範文書ガ古キ場所ヲ指シ続ケバ、其ノ条項ニ従ヒタル開発者ガ穴ヲ作ル。**<br>
  判別力ヲ変異三対照ニテ実証セリ(`chain.rs` ヘノ書キ戻シ・reason 取違ヘ・二十八本目ノ追加)。
  **三対照全テガ落チタリ。** 全件 1490 passed ニテ新規失敗ゼロ。挙動ハ一ビットモ変ハラズ。

## [4.570.0] - 2026-08-05

### Added

- LAN Cowork fleet dispatch ノ route 三本(`/fleet/update/dispatch`・`/fleet/update/dispatch/status`・`/fleet/restart/dispatch`)ヲ Rust ヘ移シ auto_stubs ヲ置キ換ヘタリ。**之ニテ LAN Cowork ノ Rust 移植ハ完了ス**(fleet route 23 本 → my-permissions → F4a peer 管理 → F4c UI 配信 → F4b dispatch)。<br>**認可ノ body ニ `"ok"` ハ無シ** —— `require_local_chief` ハ `fleet_routes_update.py:43-48` ニテ `message="chief only"` ノミヲ受ケ `ok_key` ヲ取ラズ、三本悉クヘ同ジ getter ガ渡ル。503 ハ `{"error":"service_unavailable"}` ニシテ `message` ヲ持タズ(`/fleet/peers` ト違フ)。着地済ノ guard 二種ハ孰レモ形ガ違フガ故ニ再利用セズ新規ニ三段 guard ヲ書ケリ。<br>**検証ノ順序ガ意味ヲ持ツ** —— update ハ `peer_ids` → `consent_tokens` → `invalid_source` → `invalid_branch` → strip → `no_peers` → `cannot_dispatch_self`。故ニ `{"peer_ids":[], "source":123}` ハ **`invalid_source`** ニシテ `no_peers` ニ非ズ。設計書 rev4 マデ節順ガ実際ト逆ナリキ。自己 dispatch ノ判定ハ **strip 後**ノ値ニテ行フ。<br>**自己 dispatch ノ門ハ二重ナリ** —— route 側ハ固定文言 `"chief cannot dispatch to itself"`、runner 側ハ `str(exc)` ＝ `"cannot_dispatch_self"`。**片方ノミヲ移セバ二重 chief 構成ニテ自機ヲ落トシ得ル。** 判別力ノ実測ニテ **route 側ノ message ガ無検証ナル穴**ヲ見出ダシ、両門ノ body ヲ pin スル assertion ヲ加ヘタリ。<br>status ハ **in-memory ヲ先ニ引キ**(実行中ノ状態ガ見ユル為)、無ケレバ履歴ヲ走査シ、無ケレバ 404 `dispatch_not_found`。履歴 entry ハ**逐語**ニテ返ス。<br>parity ハ**空 `peer_ids`** ニテ登録セリ —— **非空ヲ入ルレバ flag-day 後ノ chief ニテ harness ガ実際ノ fleet 再起動ヲ飛バス**。<br>判別力ヲ変異三対照ニテ実証セリ(runner 側ノ門ヲ握リ潰ス・404 body ノ改変・route 側 message ノ潰シ)。基準 23 passed、全件 1484 passed ニテ新規失敗ゼロ、parity 281 PASS / 0 FAIL。

## [4.569.0] - 2026-08-05

### Added

- LAN Cowork fleet 管理移植ノ F4b-1 トシテ、chief 側ノ逐次 update dispatch runner・同時実行十件上限ノ並列 restart dispatch runner・process 内台帳・`data/fleet_dispatches.json` 履歴永続化ヲ Rust ヘ移セリ。通信四操作ヲ差替可能トシ、`tokio::time` ノ停止時計ニテ restart 成功条件 `saw_down && post_uptime < pre_uptime` ノ正一・負二対照及ビ update ノ逐次順序ヲ固定セリ。**運用上ノ既知 caveat**: Python parity ヲ保ツ為、三秒以内ニ再起動ヲ終ヘタル Rust peer ハ down ヲ観測シ得ズ、実際ハ成功シテモ六十秒後 `restart_timeout` ト報告サル。自動再試行ヲ為ス勿レ。route 三本ハ F4b-2 ニ残ス。

## [4.568.0] - 2026-08-05

### Added

- LAN Cowork fleet 管理移植ノ F4c トシテ `/fleet/ui` 及ビ `/fleet/static/<path>` ヲ Rust ヘ移セリ。UI handler ハ registry 無キ時及ビ非 chief 時ニ空 body ノ 404 ヲ返シ、欠落 `fleet.html` ノミ `Fleet UI not found` ヲ返ス。nav ハ `csp_nonce`・`dist_v`・`active` ノ三値ニテ直接描画シ、描画失敗ヲ空文字ニ倒ス。静的資産ハ `ServeDir` ニテ字句的 traversal ヲ拒ミ、auth middleware 内側ニ置キ未認証読取ヲ許サズ。判別力ヲ九変異対照ニテ実証シ、悉ク期待通リ落チタリ。

## [4.567.0] - 2026-08-05

### Added

- LAN Cowork fleet 管理移植ノ F4a-2 トシテ `/fleet/peers`・`peer-grant`・`peer-revoke`・`peer-allowlist-status` ノ四 route ヲ Rust ヘ移セリ。認可順序ハ manager → session → chief ヲ保チ、module 別ノ 401／403／503 body、全三外向経路ノ nonce・絶対署名 path・route 固有 `X-Requested-With`、`categories` ノ無型透過、token 無キ peer ノ 409、grant/revoke ト status ノ到達不能写像ノ非対称ヲ Python ト同ジクセリ。`/fleet/peers` ハ GET ノミトシ、`force_refresh` ハ `.lower() == "true"` 相当ノ大小文字無関係ナル判定ヲ為ス。全 route ハ static auth bypass ニ加ヘズ、quick lock ヲ保全ス。

## [4.566.0] - 2026-08-05

### Added

- LAN Cowork fleet 管理移植ノ F4a-1a トシテ Python `FleetManager` ヲ Rust ヘ移セリ。`AppState` 所有ノ再起動可能ナル manager ハ native registry ト永続 chief 設定ヲ明示 gate トシ、boot 後及ビ runtime OFF/ON ニテ起動・停止ス。poll ハ `build_peer_client` ト nonce 付 `build_peer_headers_at` ヲ用ヰ、`X-Requested-With: FleetManager` ヲ固定シ token 無キ peer ニモ送信ス。cache／連続失敗数ノ prune、soft-prune、5 秒 timeout、全体 10 peer semaphore、`PeerRegistry::update_telemetry` 書戻シヲ移植シ、cache lock ヲ await 越シニ保持セズ。<br>**nonce ハ落トセバ四機能悉ク無言デ 401 ト成ル** —— `/ext/lan_cowork/fleet/` ハ `NONCE_REQUIRED_PREFIXES` ニ含マレ、且ツ 401 ハ `http_401` ト成リテ snapshot ノ隠蔽条件ニ掛カルガ故ニ、「全 peer 401 ニテ一覧常ニ空」ガ誤リヲ一ツモ出サズ成立ス。故ニ `make_signature_headers`(`X-Peer-Ts` ト `X-Peer-Sig` シカ返サズ)ヲ用ヰズ `build_peer_headers_at` ヲ用フ。<br>**poll ニ token 検査ヲ足ス勿レ** —— Python ハ token 無キ peer ニモ送リ 401 ヲ得テ隠ス。検査ヲ足セバ `last_error` ガ `http_4` デ始マラズ隠蔽ガ**反転**シ、未ペアリング peer ノ名ガ Fleet 一覧ニ現ル。<br>判別力ヲ変異六対照ニテ実証セリ(nonce 除去・`X-Requested-With` 既定・隠蔽条件ノ `info` 外シ・refresh 時 prune 削除・semaphore 撤去・成功時カウンタ解除削除)。**六対照全テガ期待通リ落チタリ**(基準 11 passed)。<br>尚、実装ヲ委ネタル sandbox ハ loopback bind ヲ許サザル(`Operation not permitted`)ガ故ニ mock HTTP 試験ヲ実行シ得ズ、之ハ本セッションニテ別途実測セリ。**「実行不能」ヲ「試験ガ弱シ」ト誤診シテ緩ムル勿レ。**

## [4.565.0] - 2026-08-05

### Added

- LAN Cowork `my-permissions` ヲ Rust ヘ移植セリ(repo 分離ロードマップ第二段)。**認可ハ `session_guard` → `require_session` ノミヲ用フ** —— `require_admin_scope` ハ LAN Cowork ノ bypass route ニ対シ **fail-OPEN** ナリ(`auth/scope.rs:41` ガ `_ => return None`、`middleware.rs:195` ガ `reason = "lan_cowork_fleet_peer"` ヲ置ク)。之ヲ用フレバ **admin scope ノ API key 保持者ニ LAN 全 peer ノ権限一覧ガ開ク**。auth chain ハ API key ヲ session ヨリ先ニ評価スルガ故ニ、`AuthContext.reason` 典拠ノ判定ハ悉ク誤ル。`require_session` ハ `tower_sessions::Session` ヲ直ニ読ム。<br>**順序ハ fleet 系ト逆ナリ** —— session 検査ガ `peer_registry` 検査ニ先行シ、session 無シ ＋ LAN Cowork 無効ハ **401**(503 ニ非ズ)。<br>**送信ハ `build_peer_client` ヲ経ル**(公開 IP・link-local ヲ拒ミ解決済 IP ヲ pin シ、redirect ヲ許サズ)。**`PeerTransport::send` ハ用ヒズ**署名ヘッダ生成ノミヲ借ル —— `send` ハ 401 ニテ `invalidate_outbound_token` ヲ呼ブガ故ニ、**一度ノ 401 ニテペアリングガ自壊ス**。<br>キャッシュ TTL ハ monotonic(`Instant`)、token 失効判定ハ壁時計(`unix_now`)ナリ。二種ヲ取違フレバ期限判定ガ壊ル。同時実行 10 peer ノ semaphore ハ**プロセス全体ニ共有ス**(要求毎ニ作ル勿レ)。HTTP ハ常ニ 200 トシ、peer 個別ノ失敗ハ `peers[].error` ト四権限フィールドノ `null`(`false` ニ非ズ)ニ表ス。<br>判別力ヲ変異七対照ニテ実証セリ(session guard 常時失敗／常時成功、`require_admin_scope` 差替、self-filter 削除、外側 timeout 削除、キャッシュ無効化、409 写像ノ潰シ)。**七対照全テガ期待通リ落チタリ**。尚 `connection_failure_is_unreachable_not_timeout` ハ定数ノ pin ナルガ故ニ判別力ヲ持タズ、外側 timeout ノ真ノ grip ハ `slow_response_maps_to_timeout`(遅延四秒 < client 十秒)ニ在リ。

### Fixed

- **`batch_zip` ノ試験ガ旧契約ヲ主張シ main 上ニテ落チ続ケタル問題**ヲ直セリ。8dfcba132 ガ `inspect_zip` ヲ強化シ、**要求外ノ remote id ヲ含ム zip ハアーカイブ毎拒ム**(同ループノ他異常モ悉ク全体拒否ナリ)ヨウ改メタルニモ拘ラズ、試験ハ「要求外ノ entry ノミ読ミ飛バス」旧来ノ寛容ナル契約ヲ主張セシママナリキ。試験ヲ新契約ヘ改メ、999 ガ一度モ永続化サレヌコト・3 ガ individual_http ヘノフォールバック経由ニテ入ルコト・要求ガ zip → 個別ノ二本ナルコトヲ主張セシム。**`pre_push_check.py` ガ `cargo test` ヲ回サヌ**ガ故ニ見逃サレヲリキ(main ハ本増分適用後モ 13 件ガ赤。別途課題トセリ)。

## [4.564.0] - 2026-08-05

### Added

- LAN Cowork fleet 群移植の第六段(F3c2)。`/fleet/update` を Rust へ移植し、**fleet route 23 本の移植が完了**した。**本増分は fleet 中で最大かつ最も破壊的**(git pull でコードを書き換えてからプロセスを自己置換する)。設計は design-advisor の裁定を一度受け Must-fix 4 件を反映した。<br>**F3c1(`restart`)との差は一点のみ** —— `check_update_allowed(.., allow_consent=true, include_restart_allowlist=**false**)`。Python は当該引数を渡さない(既定 false)ため、**`allow_restart_from` にしか居ない peer は update できない**。F3c1 の呼び方を写すと認可が緩む。他(503 body・`fleet_peer_guard`・`peer_only` 直呼び禁止・`lan_cowork_fleet_security.rs` 差分ゼロ)は F3c1 と同一。<br>**同時実行はノード全体で 1 job**(peer 単位ではない)。`active_jobs` を peer で絞らず全走査し、検査と挿入を単一の critical section で行う。誤れば**異なる peer が同時に git pull ＋ 自己置換**を起こす。<br>**`local:` の allowlist 照合は入力検証ではない** —— 切離しタスクの中に在り、**不許可でも HTTP は 200 ＋ `job_id` を返す**。拒否は `/fleet/update/status`(F3a 移植済)経由で `status:"failed"` / `error:"local_path_not_allowed"` / `steps[0].output` として観測される。同期 400 で弾くと status code の parity が壊れ、409 の job slot も消費しなくなる。`canonicalize()` の `Err` は**入力側は即拒否・entry 側は非一致として走査継続**(entry 側で中止すると、許可パスを一つタイポしただけで `local:` 更新が全滅する)。<br>**失敗 job も disk に残す** —— `save_last_job` の呼び手は route 側にもあり成功・失敗の別なく走る。pre-restart 保存のみでは再起動後の status が 404 となり parity が壊れる。<br>再起動は F3c1 の seam、job 永続化は F3a の `save_last_job`、認可は F2 の `check_update_allowed` を**再利用し書き直していない**。

### Fixed

- **fleet テストが実 git を起動し得た問題を塞いだ**(F3a から存在)。`run_git` を `#[cfg(not(test))]` の本番実装と `#[cfg(test)]` の seam に分け、**seam に実 git への fallback を置かない**(未設定・queue 枯渇は即エラー)。F3a の `git_short_head` も同経路へ統合した。これにより `git_precheck` → `fetch` → `pull --ff-only` の**コマンド列と順序**を試験で固定できる。<br>併せて `git_test_commands().lock()` の `MutexGuard` を保持したまま同一 mutex を再取得する**自己デッドロック**を修正した(F2 の consent 試験と同型。症状も同じく libtest が「60 秒超」を報告しないため、**実 git のネットワーク待ちと誤診した**)。

## [4.563.0] - 2026-08-05

### Added

- LAN Cowork fleet 群移植の第五段(F3c1)。`/fleet/restart` を Rust へ移植。**本増分は破壊的操作**(プロセス自己置換)ゆえ、誤れば**リモートから任意のノードを再起動できる**。設計は design-advisor の裁定を二度要した(rev1 = NO-GO/Must-fix 9、rev2 = GO-with-conditions/Must-fix 3)。<br>**認可は既存資産の再利用のみ**で新規判定を書かない —— 503 `{"ok": false, "error": "LAN Cowork not enabled"}`(**`@auth_decorator` が本体の `require_manager()` より先に走るため。F3b の `service_unavailable` とは別物**)→ `fleet_peer_guard`(Python は in-memory registry 典拠 / Rust は DB `peers` 典拠ゆえ `peer_only` 直呼びでは Python=403 / Rust=200 になる)→ F2 移植済みの `check_update_allowed(.., allow_consent=true, include_restart_allowlist=true)`。**consent と allowlist は排他**(`allow_remote_update=false` なら consent のみ、`true` なら allowlist のみ。加算ではない)。<br>**プロセス自己置換は OS ごとに Python と同じ分岐を保つ** —— Linux `libc::execv`(PID 維持ゆえ systemd 互換。`Restart=on-failure` の下で exit 0 は再起動しない／`KillMode=control-group` ゆえ spawn した後継は殺される)、macOS `Command` + `pre_exec(libc::setsid)`、Windows `Command` + `CREATE_NEW_PROCESS_GROUP`。**argv の作り方は分岐ごとに違う** —— execv は `[current_exe, ..args_os().skip(1)]`、spawn は `Command::new(current_exe).args(args_os().skip(1))`。`.args(args_os())` と書けば `argv[0]` が重複し、`Cli` が long option のみで位置引数を持たぬため clap が `exit(2)` し **200 を返した直後にノードが停止する**。`current_exe()` の `" (deleted)"`(Linux の procfs 固有)を検出したら中止。`args_os()` を用いる(`args()` は非 UTF-8 で panic)。<br>再起動 seam は **「予約」に置く** —— `tokio::spawn` の呼出自体を seam とし `sleep(1500ms)` と exec を内側へ閉じる。`sleep` の後ろに置くと「認可失敗時に seam が呼ばれない」検証が**応答直後には常に真**となり判別力を失う。seam は `FnOnce` take 型を避け `AtomicUsize` とした(二重受理の検証が構造的に不可能になるため。Python も daemon thread 二本ゆえ絞らない)。

### Fixed

- **fleet テストの隔離不良を修正**(F3b から存在。F3c1 の実装中に露見)。全 fleet テストが作業ディレクトリ直下の**同一 `config.json`** を読み書きしており、別テストが書いた `allow_log_stream_from` が見えて認可を通過し、負経路が **500** まで進んでいた。落ちるテストが実行順で変わる形で、**単独実行では通る**ため F3b 着地時の検証(同一順序で一度ずつ)では検出できなかった。⟹ test state の `config_path` を各 `tempdir` へ隔離し、consent guard を module 共有化した。**以後は直列一回 ＋ 並列複数回を標準とする。**

## [4.562.0] - 2026-08-05

### Added

- LAN Cowork fleet 群移植の第四段(F3b)。`/fleet/logs/stream`(SSE ＋ リレー)を Rust へ移植。**fleet 五 route 中最も難しく、設計は design-advisor の裁定を四度要した**(rev1〜rev3 が NO-GO)。**認可は三分岐**で F3a の単一ガード共有型が使えない —— リレー(503 → **session 401** → chief 404 → 未知 peer 404)/ peer(503 → registry 在籍 403 → pubkey 403 → 署名 → nonce → Bearer → allowlist 403)/ ブラウザ(503 → **session 401 のみ**)。**分岐 3 に peer 認証を掛けるとブラウザが壊れ**(`X-Peer-Id` 不在で即 401)、**分岐 2 を先に評価すると遠隔 peer がリレーを踏める**。SSE 側は移植先 primitive の差が四点 —— `get_since` が Rust に存在せず live は broadcast、`recent` は三引数(Python は二引数)、**seq の起点が Rust=0 / Python=1** ゆえ `after_seq=Some(0)` は先頭一件を落とす、`level_rank` が `pub(super)` で routes から呼べない(**可視性のみ `pub(crate)` へ拡大**。rank の写し直しは禁止)。**`subscribe()` を `recent()` より先に呼ぶこと**が核心で、逆順だと隙間に到着したログが**恒久的に失われ無言で通る**(Python が同じ罠をコメントで明記している)。両関数とも同期で間に await 点が無いため `#[cfg(test)]` seam を切って順序を試験で固定した。payload は `target`→`source` / `WARN`→`WARNING` を**直列化時のみ**写像(`ring.rs` を書き換えると native ビューアと回帰試験が壊れる)。`level` クエリは**四語完全一致検証を先に**行い写像を後にする(逆順だとフィルタが黙って無効化)。`RecvError::Lagged` は**切断せず `tracing::warn!` も出さない**(warn が ring へ再投入され lag→warn→lag の帰還路が生じ得るため)。**リレーの接続前失敗は `event: close` のみ**とし `event: error` を出さない —— Python は `except Exception` で握り潰し `finally` で close のみを送る(`event: error` は「到達したが非 200」の場合だけ)。審査で「当該経路に試験が一件も無い」と指摘され、`event: error` の**不在**を assert する試験を追加した。判別力は**五 mutation を自動化して実証**(ガード常時失敗で正経路八件、session 常時失敗で四件、`subscribe`/`recent` の順を逆転させて seam 試験が落ちる)。

## [4.561.3] - 2026-08-04

### Fixed

- **`/ext/lan_cowork/fleet/logs/stream` が無認証でログ全文を配信し得た問題を修正**(Python 側)。F3b の移植調査中に発見。**LAN 上の誰でも、認証もペアリングも無しに `X-Peer-Id: <対象ノード自身の peer_id>` を送るだけで SSE でログ全文を継続閲覧できた。** 成立経路は四段: (1) `bypass_session=True` により `auth_chain_checks.py:45-47` が `AuthResult(passed=True, reason=declared.require)` を返し session gate を素通りする(**`require` は理由文字列にしかならない**)、(2) **fleet 5 route 中この route だけ `@auth_decorator` を持たず**署名・nonce・Bearer のいずれも検証されない、(3) `X-Peer-Id` を検証せず信用する、(4) `check_log_stream_allowed` の `requester_peer_id == local_peer_id → True` が allowlist を無条件に迂回させる(`local_peer_id` は無認証の `/ext/lan_cowork/api/peer/status` 一回で取得できる)。**QuickLock でも防げない** —— `auth_chain_runner.py:18` の `_STATIC_CHECKS` は `check_quick_lock` より前にあり、**PIN を掛けた構成ほど裏切られる**。且つ LAN Cowork は**既定 ON**(`extension.json` の `config.enabled: true`、`extensions_loader_manifest.py:174` の `get("enabled", True)`)。露出の実体は `routes/logs_api.py:101` が `_require_admin_scope()` で守るのと**同じ ring buffer の全文・継続閲覧**である。⟹ `require_peer_auth` の本体を `authenticate_peer_request()` へ括り出し(暗号検証を二重化しない)、**peer 経路の分岐にのみ**適用する。`@auth_decorator` の無条件付与は `X-Peer-Id` 不在で即 401 となりブラウザ経路とリレー経路を壊すため採れない。自己申告による allowlist 迂回は削除(不要になった `local_peer_id` 引数も除去)。**リレー元は既に署名・nonce・Bearer を付けており**(`fleet_peer_http.py:14-45`)、受け手が検証していなかっただけなので**正規経路は無変更**。

- **`acquire_device` の owner 衝突による CMA 枯渇の恐れを解消**(Python 側)。hailo 境界裁定の副産物として発見。`acquire_device(owner, hef_path)` の owner 文字列は**グローバル協調名前空間**だが、`"yolo"` を `builtin_hailo_yolo_detect`(利用者が設定で選択)と LAN Cowork の `yolo_engine.py`(固定順の先勝ち)が共有していた。model を `yolov11n` に設定しつつ `yolov8n.hef` が在れば**同 owner・別 HEF** となり「Model switch」経路で相互 evict する。LAN Cowork は推論毎に再 acquire する(release しない)ため 1 秒級 HEF ロードのスラッシングに加え、`backend_hailo.py:35-43` が事前確保した DMA マッピングが取り残される。**CMA 枯渇は `device_manager_infer.py:57-63` が「フルシステム再起動が必要」と明記する不可逆障害。**⟹ LAN Cowork 側の owner のみ `"lan-yolo"` へ改名(2 ファイル 2 行)。`builtin_hailo_yolo_detect` 側は既存 UI 表示を保つため変更しない。`"clip"` も共有されるが現行呼出では同一 HEF ゆえ Model switch は起きない(ただし `get_encoder(hef_dir)` は別ディレクトリを指定し得るため「常に同一」は厳密には成り立たない)。**CMA 枯渇そのものは実機を要するため試験で固定できない**旨を試験に注記した。

## [4.561.2] - 2026-08-01

### Fixed

- LAN Cowork inbound SSE で受信者不在時の dropped event ログを 60 秒単位に集約し、初回は即時記録してログの過剰出力を防止。

### Changed

- agent workflow と環境メタデータを現行運用へ更新。

## [4.561.1] - 2026-08-01

### Fixed

- Codex Security scan の供給網・更新・LAN・UI・アーカイブ・Tauri 境界を修正。release Actions と portable download/依存を不変識別子・SHA-256 hash lock へ固定、reviewer が単一読込した unsigned ZIP の payload を reviewed path と forbidden policy へ結合、LAN import を one-shot session・永続展開量 quota・ZIP bomb 制限で保護し、isolated Extension DB RPC を動的 capability・SQLite 実行量・reverse peer PID/nonce で制限した。

## [4.561.0] - 2026-08-01

### Added

- LAN Cowork fleet 群移植の第三段(F3a)。`/fleet/info` と `/fleet/update/status` の 2 route を Rust へ移植。**設計は design-advisor の裁定を二度受け、rev1 は NO-GO(Must-fix 9)であった** —— `/fleet/update/status` の `@auth_decorator`(`fleet_routes_update_job.py:137`)を見落とし「認証を一切強制していない」と誤断し、設計書が**認証の除去を指示していた**ため。実際は両 route とも `fleet_routes.py:84,97,110,144` で `require_peer_auth` に束縛された同一デコレータを通り、X-Peer-Id → registry 在籍(403) → pubkey → Ed25519 署名 → **単回 nonce** → Bearer token を強制する。⟹ 実装は共通の `fleet_peer_guard` を両 route が通す形とし、認可が分岐し得ない構造にした。LAN Cowork 無効時(`peer_registry` 未設定)は **auth より前に 503**(`peer_auth.py:92-95` と同順)。auto-heal は `git rev-parse --short HEAD` を用いる(`--short` を欠くと 40 桁と短縮形の比較となり**無言で永久に不発**)。`status` 値は Python と同じ**小文字**。job record の探索は二段で、① in-memory `active_jobs` は **heal せず**返し、② disk 経路でのみ heal する。`check_static_bypass` へは**厳密パス 2 件のみ**を追加(prefix は `/fleet/update` を露出させるため禁止)。

## [4.560.0] - 2026-08-01

### Added

- LAN Cowork fleet 群移植の第二段(F2)。**peer-facing 9 route + 認可機構**を Rust へ移植 —— consent 6 本(`request`/`respond`/`status/<id>`/`pending`/`relay/request`/`relay/status`)、allowlists 3 本(`grant`/`revoke`/`check`)、および consent トークンの一回性・60 秒周期 janitor・`fleet_route_security` の 4 分岐認可。**`@auth_route(require=...)` は宣言メタデータであり実行時強制をしない**(`core/web/auth_route_policy.py` は登録のみ)ため、強制は route 本体が個別に持つ。Python 実測に合わせ `session_only` / `peer_only` / `session_and_chief` の 3 ガードへ**型で分離**した(union を作れない形)。allowlist カテゴリは Python と同じ `log_stream` と `update` の 2 つのみ。`status()` は未決定かつ期限切れのエントリを読み取り時に検出して削除し `"expired"` を返す(janitor 待ちにしない)。`pending()` も同じ期限の連言を持つ。`require_peer_auth_with_nonce_store` を抽出したが**本番経路は `nonce_store()` を渡す従来どおり**で挙動は不変(テストが grace 0 の store を注入するための seam)。

## [4.559.0] - 2026-07-31

### Added

- LAN Cowork fleet 群移植の土台(F1)。`machine_info`(機体情報。CPU/RAM/disk/GPU/git/OS)と `get_fleet_timings`(8 キーの既定値 + config override)を Rust へ移植。route は生やさない純粋層。GPU probe は nvidia/rocm/macOS/Windows-WMI の 4 段 chain を移し、非 Linux では `ram`/`disk` を `0.0` へ縮退させつつ**キー集合は全 OS で同一**に保つ(`ui/fleet/*.js` と MCP ツールが固定キーを前提とするため)。

## [4.558.0] - 2026-07-31

### Fixed

- **大規模ライブラリの LAN Cowork full import が「完了」表示のまま 0 件で終わっていた問題を修正**(Rust/Python 両側)。zip 一括取得の ids を分割せず単一 URL に載せていたため、約 6,500〜9,500 件(id の桁幅による)で hyper の request-target 上限 65,534 バイトを超え 414 になり、`download_zip` が非 200 で空 map を返すため縮退もせず `completed` が記録されていた。ids を 500 件ずつに分割する。`BATCH_THRESHOLD`(100) より大きいため 100〜499 件の通常規模では要求回数は従来どおり 1 回。zip サイズ上限発火時の個別 HTTP への縮退も当該チャンクのみに限定した。

## [4.557.0] - 2026-07-31

### Added

- LAN Cowork import の受信バイト数に上限を追加(Rust/Python 両側)。`download_file` は 8 GiB、`download_zip` は 2 GiB。判定は書き込み前、絶対値のみで peer 由来の数値を使わない。zip の上限発火は失敗ではなく個別 HTTP への縮退とし、import が停止しないようにした。

## [4.556.0] - 2026-07-31

### Added

- LAN Cowork local import の index route を Rust native 化。書込先検証を daemon gate より前に置く順序、`mkdir` を行わない挙動、二点 gate(registry/seed のみ。自己登録を行わないため descriptor 非依存)、peer が返した index の逐語透過を移植。これで `local_import_api.py` の 5 route すべてが Rust へ移った。

## [4.555.0] - 2026-07-31

### Added

- LAN Cowork local import の execute route を Rust native 化。session 二重認証、session 404 を daemon gate 503 より前に置く順序、自己登録・meta 取得の 502、3 モードの meta URL、背景実行と失敗時 `status="failed"` を移植。

### Fixed

- `scripts/setup-ai-tools.ps1` が Windows PowerShell 5.1 で構文エラーとなり全く実行できなかった問題を修正。null 合体演算子 `??` は PowerShell 7 以降専用のため明示的な null 判定へ置換。併せて `$Bins`(11 件) と `$Repos`(8 件) の添字ずれにより repomix/aider/ctags が常に「remote check failed」と表示されていた点を修正。

## [4.554.0] - 2026-07-30

### Added

- LAN Cowork local import の session 一覧・詳細・作成 route を Rust native 化。session 二重認証、非 strict 解決済み書込先 guard、readonly/write DB pool 分離、JSON 4 段検証を追加。

## [4.553.0] - 2026-07-30

### Added

- standalone モードで LAN Cowork import の `import_session`、`import_file_id_map`、`import_collection_id_map` schema を作成。Python 不在時のみ Rust が所有し、既存 hybrid 経路は変更しない。

## [4.552.0] - 2026-07-29

### Added

- LAN Cowork import orchestration を Rust へ移植。session の standalone 更新・個別/ZIP 転送の選択・処理済台帳の連携を dead code として追加。

## [4.551.0] - 2026-07-29

### Added

- LAN Cowork import transfer の `download_zip` を Rust へ移植。署名済み percent-encoded query をそのまま wire に載せ、300秒 read timeout、401 の outbound token 無効化、逐次 ZIP 展開と部分ファイル削除を実装。ZIP entry は crate が報告する名前を検証し、`ZipArchive::extract` 系を使わず symlink 作成を防止。

## [4.550.0] - 2026-07-29

### Added

- LAN Cowork import transfer の `download_file` を Rust へ移植。共有 peer client の IP pinning・redirect 拒否を保ち、60秒 read timeout、401 の outbound token 無効化、部分ファイル削除を実装。

## [4.549.0] - 2026-07-29

### Added

- **LAN Cowork import 転送層ノヘルパヲ Rust ヘ移植（Increment L3b-1）**: `unique_dest` / `validate_zip_entry_name` / `verify_within` ヲ `routes/lan_cowork_import_transfer.rs` ヘ収ム。route ハ未ダ生ヤサズ dead code トシテ着地ス。**zip-slip 対策ノ中核**ナリ —— R2b（v4.544.0）ニて `arcname` ヲ送信側デ消毒セズト決メタル根拠ガ「受信側ガ二重ニ守ル」コトナルが故、本増分ガ其ノ受ケ側ナリ。**`verify_within` ハ解決シテカラ比較ス** —— `path_guard::path_is_within` ハ `\\?\` ノ**文字列剥離ノミ**デ `canonicalize` ヲ呼バズ、「比較」ノ述語ニしテ「正規化」ノ述語ニ非ズ（既存 2 呼出元ハ何レモ canonicalize 済ノ値ヲ渡ス）。同述語ノみデ書ケバ外向キ symlink モ**素ノ `..`** モ素通リシ、traversal 防御ガ実質無効化ス。依ツテ S1 ノ `resolve_non_strict`（逐次 realpath）ヲ `pub(crate)` 化シテ再利用シ、両辺ヲ解決シテカラ比較ス。`validate_zip_entry_name` ハ **`\` → `/` ノ正規化ヲ全判定ノ先**ニ行フ（R2b デ挙ゲタル `12/..\..\x.txt` ガ此处デ `..` 検出ニ掛カル）。拒否理由ハ enum デ返シエントリ名ヲ log セズ。`unique_dest` ハ改名先ガ `folder`（`dest.parent` ニ非ズ）、且ツ **`Path.stem`/`suffix` ノ末尾ドット挿作**（実測: `Path("a.").stem == "a."` / `.suffix == ""`）ニ合ハセル。テスト 5 件。設計: `docs/superpowers/plans/2026-07-29-lan-cowork-import-transfer-l3b1.md`

## [4.548.0] - 2026-07-29

### Added

- **LAN Cowork import ノ DB 永続化層ヲ Rust ヘ移植（Increment L3a）**: `import_executor_db.py`（181 行）ノ `insert_file`/`write_metadata`/`persist_downloaded_file` ヲ `routes/lan_cowork_import_persist.rs` ヘ収ム。route ハ未ダ生ヤサズ dead code トシテ着地ス。**影響境界ハ実質 10 表** —— 直接書ク 6 表（`files`・`tags`・`file_tags`・`file_ratings`・`file_annotations`・`favorites`）ニ加ヘ、`files` INSERT ガ `search_stats` ト **FTS5 索引**ヲ、`file_tags` INSERT ガ `search_stats` ト `file_tag_counts` ヲトリガ経由デ更新ス。依ツテテスト DDL ハ本番スキーマヨリ**制約・トリガ込ミ**デ写ス（既存ノ読取用 DDL ヲ流用セバ `CHECK(rating)`・`value BLOB NOT NULL`・`path UNIQUE` ガ悉く素通リシ、`collections` ノ id=1 ヲ seed セネバ Favorites skip ノ検証ガ AUTOINCREMENT ノ偶然デ通ル）。`insert_file` ハ **`last_insert_rowid()` ヲ用ヰズ**常ニ path デ引ク（v4.547.1 デ Python 側ヲ是正セシ同ジバグヲ避ク為）。`resolve_collection_id` ノコールバックハ Rust デ二重借用ト成リ**実装不能**ナルガ故直接呼出ヘ確定。注釈値ノ復号ハ **R1 ノ符号化ノ受ケ側**ナリ（R1 ガ zstd ヲ展開シテハナラザリシ理由ガ此处ニ在ル —— 受信側ハ base64 ヲ復号シテ verbatim ニ INSERT スル）。**`dict.get(k, default)` ハキー不在時ノミ既定ヲ返ス**ガ故 `null` ヲ静カニ吸収セズ区別ス。`ann_rows` ガ文字列ノトキノ包ミ直シ（落トセバ注釈データガ黙ツテ消ユル）モ実装。テスト 51 件。設計: `docs/superpowers/plans/2026-07-29-lan-cowork-import-persist-l3a.md`

## [4.547.1] - 2026-07-29

### Fixed

- **import ノメタデータガ別ノファイルヘ書キ込マレ得タル件（データ破損）**: `import_executor_db.py` ノ `insert_file` ガ `INSERT OR IGNORE` ノ後ニ `cur.lastrowid` ヲ信ジ居タリ。**無視サレタ INSERT デハ `lastrowid` ハ `None` ニモ 0 ニモ非ズ、同ジ接続デ直前ニ成功セシ別 INSERT ノ id ヲ返ス**（実測: Python 3.13.13 / SQLite 3.50.4 ニて、id 1 ノ行ヲ再挿入シタル際 `lastrowid = 2`）。⇒ `insert_file` ガ誤ツタ file id ヲ返シ、`persist_downloaded_file` ガ其ノ id デ `write_metadata` ヲ呼ブガ故、**タグ・評価・注釈・コレクションガ別ノファイルヘ書キ込マルル**。共有 write 接続デバッチ import スルが故、**二件目以降ニて宛先パスガ既存行ト衝突セシファイル**デ発火ス（`ImportPlanner` ハ hash デ skip スレド hash ヲ持タヌファイルハ常ニ `to_import` ニ入ル）。一件目ハ既存ノ SELECT フォールバックヘ落チ正シキ id ヲ返スガ故、**二件目以降ノミ壊ルル所ガ気附キ難サナリ**。`lastrowid` ヘノ依存ヲやめ、常ニ `SELECT id FROM files WHERE path=?` デ引ク（同ジ SELECT ハ既ニ在リタレド `if cur.lastrowid:` ノ分岐ガ到達サセ居ラザリキ）。LAN Cowork の Rust 移植（L3a）着手時ニ発見シ実測ニて確認。回帰テストヲ加フ（是正前ハ `assert 2 == 1` ニて落ツルヲ確認済ミ）。

## [4.547.0] - 2026-07-29

### Added

- **LAN Cowork import 台帳ノ書込面ヲ Rust ヘ移植（Increment L2b）**: `create`/`update`/`register_file`/`get_or_create_collection` ヲ収ム。route ハ未ダ生ヤサズ dead code トシテ着地ス。**トランザクション規律ガ主題** —— API ハ `&mut SqliteConnection` ニ一本化（`Executor` ハ値デ消費サルルガ故二文以上ヲ発行スル関数ヲ汎用ニ書ケズ、`impl Acquire` モ `&SqlitePool` ヲ渡サレレバ毎回別接続ヲ取リ共有トランザクションノ目的ヲ破ル）、core ハ `BEGIN`/`COMMIT`/`ROLLBACK` ヲ発行セズ、ラッパハ `BEGIN IMMEDIATE` ト**全エラー経路デノ ROLLBACK**（`COMMIT` 自体ノ失敗時ヲ含ム。落トセバ接続ガトランザクション中ノ儀 pool ヘ戻リ以後其ノ接続ノ全処理ガ壊ルル）。**`register_file` ノ二文ハ同一トランザクション内**ナルベシ —— 裸ノ接続デ呼ベバ autocommit デ分離シ map ヘノ INSERT ダケ commit サレ、`done_files` ノ加算ガ落チテ進捗ガ恒久的ニ過少ト成ル。`get_or_create_collection` ハ中核表 `collections` ヘ INSERT シ、`LOWER(TRIM(name))` 照合ヲ **SQL 側デ**行フ（`'école'` ト `'ÉCOLE'` ハ別 collection）、**複数一致時ニ名ヲ log セズ件数ノミ**（peer 由来ナルガ故。Python ハ名ヲ出ス）、曖昧一致ノ選択ヲ `ORDER BY id` デ**決定化**ス（Python ハ ORDER BY 無シノ `existing[0][0]` ニて本来非決定的）。`update` ハ allowlist 5 列（`options` ヲ含マズ）・許可外ハ黙殺・**dirty check ニ依リ UPDATE 自体ガ発行サレズ `updated_at` モ動カズ**。テスト 43 件。設計: `docs/superpowers/plans/2026-07-29-lan-cowork-import-state-l2b.md`

## [4.546.0] - 2026-07-29

### Added

- **LAN Cowork import ノ計画層ト台帳読取面ヲ Rust ヘ移植（Increment L2a）**: `ImportPlanner.plan` ト `ImportSession` ノ `get`/`list_all`/`is_file_processed`/`get_local_file_id` ヲ `routes/lan_cowork_import_state.rs` ヘ収ム。書込面（`create`/`update`/`register_file`/`get_or_create_collection`）ハ **L2b** ヘ分ツ —— 見積リ約 945 行ガ自ラ置キタル上限ヲ超ヘ、且ツ書込面ニ論点ガ集中スル為。route ハ未ダ生ヤサズ dead code トシテ着地ス。DB 表 3 ツハ既ニ定義済ミナレド **Rust 側カラノ参照ハゼロ**ナリキ。**悉ク `Result` ヲ返ス**（握リ潰セバ `plan` ガ全件 `to_import` ヲ返シライブラリ全体ヲ再ダウンロードスル）。**peer 由来ノ `id` 欠落ハ fail-closed**（当初実装ハ `unwrap_or(Value::Null)` ニて不正ナ peer データデ静カニ `null` ガ入ル fail-open ナリキ。Python ハ `f["id"]` デ KeyError）。R1 ノ chunk/dedup helper ヲ**型引数ノミ** generic 化シテ再利用シ、`IN_CHUNK_SIZE` モ共有。`options` ハ parse シテ返シ、parse 失敗モ `Err`。テスト用 DDL ハ本番スキーマヨリ列単位デ写ス。テスト 38 件（R1 ノ 25 件ヲ含ム）。設計: `docs/superpowers/plans/2026-07-29-lan-cowork-import-state-l2.md`

## [4.545.0] - 2026-07-29

### Added

- **LAN Cowork ノ署名付 outbound peer transport ヲ Rust ヘ移植（Increment L1）**: Python ノ `PeerTransport`（`core_impl/transport.py`、169 行）ニ相当スル配線ヲ `routes/lan_cowork_transport.rs` ヘ収ム（署名ノ素ト outbound ノ土台ハ既ニ在リタレド `make_signature_headers` ハ本番呼出元ガゼロナリキ）。local_import ノ 5 route ハ悉ク outbound クライアントナルガ故、本 transport ガ全テノ前提ト成ル。route ハ未ダ生ヤサズ dead code トシテ着地ス。**401 ノ token 無効化デ方向ヲ取リ違ヘテハナラヌ** —— `revoke_token` ハ `peer_tokens.revoked_at`（**こちらが相手に発行した** inbound token）マデ失効サスルガ故、流用セバ相手カラノ受信ガ 401 ト成リ、`renew_if_not_revoked` ガ再発行モ拒ムガ故**再ペアリングマデ復旧セズ**。正シクハ `PeerRegistry::upsert` デ `peers` ノ token 3 列（**こちらが相手に提示する** outbound 資格情報）ノミヲ空ニス。**署名ノ invariant ハ「署名シタバイト列ヲ其ノ儀送ル」** —— `json.dumps` ト `serde_json` ハキー順・非 ASCII 表現・float デ一致セヌが、署名対象ハ自分ガ送ルバイト列ナルガ故 wire 互換ニ影響セズ。`reqwest` ノ `.json()` ハ再シリアライズスルガ故禁ジ、`.body(bytes)` ヲ用ヰル。他ニ ts 注入ノ seam（nonce 分岐モ本関数越シニ pin）、`X-Requested-With: PeerTransport` ヘの上書キ、応答 body 上限ノ引数化（JSON 取得の既定 64 MiB。既存 64 KiB デハ `/import/meta?mode=full` ガ必ズ当タル）、timeout 5 秒、署名 path/query ト実 URL ノ一致 guard、401 デ event 2 ツ。**応答 body ヲ log セズ**（Python ハ丸ゴト WARN ニ書クが、既知ノ漏洩経路ナルが故複製セズ）。テスト 8 件。設計: `docs/superpowers/plans/2026-07-28-lan-cowork-outbound-transport-l1.md`

## [4.544.1] - 2026-07-28

### Fixed

- **`register-path` ガ scan root 外・許可外拡張子ヲ受理シ居タリ件**: Rust ノ `register_path` ハ Python ノ `register_path_payload`（`services_drop_upload.py:234-277`）ガ持ツ検査ヲ**二ツ欠キ**、admin scope ダケデ**任意ノ既存パスヲ `files` ヘ登録シ得タり（scan root 封ジ込メ無シ・拡張子 allowlist 無シ・`is_file()` 無シ）。v4.544.0 ノ remote import R2b ガ **DB ニ載ルパスノファイル本体ヲ peer ヘ配信スル面**ヲ新設セシ為、「**admin ガ登録セシ任意ファイル → ペア済 peer ガ取得**」ナル **Python ニ存在セヌ連鎖**ガ成立スルニ至レリ（R2b ノ deny-list ハシステム領域シカ塔ガヌ為、`~/Documents/*.pdf` ノ如キ利用者ノ私物ハ素通リ）。連鎖ノ**起点**ヲ Python ト同ジ強サニ戻ス。受理条件ヲ狭ムルガ壊ルル経路ハ無シ（UI ノ再スキャンハ `files.path` ノ UNIQUE ニて**現状既ニ 409 デ失敗**、MCP ト利用者向文書ハ既ニ scan root 内ヲ要求）。設定ハ `app_config`（起動時スナップショット）デハなく **要求毎ニ `read_config_json`**で読ム（誤ラバ「UI ニ root ガ在ルニ register-path ダケ全拒否」ナル診断不能ナ停止ト成ル）。併セテ比較述語ヲ `crates/yu-server/src/path_guard.rs` ヘ集約シ、R2b ノ deny-list ト本増分ノ allow-list ノ双方カラ用ヰル（正規化子ノミ共有セバ **Windows 利用者ハ scan root 内デモ登録デキヌ** —— case-fold ガ呼出側ニ在リタル為）。INSERT スル値ハ変ヘズ（正規化スレバ 200 ガ 409 ニ転ジル）。`arch-constraints.yaml` ノ `windows:` 節ヘ恒久ルールヲ加フ。テスト `tools_ops` 27 / `path_guard` 2 / `lan_cowork_import` 25。設計: `docs/superpowers/plans/2026-07-28-register-path-scan-root-guard.md`

## [4.544.0] - 2026-07-28

### Added

- **LAN Cowork remote import ノファイル配信面ヲ Rust ヘ移植（Increment R2b）**: `/file/{id}`・`/zip`・`/stream/{id}` ヲ生ヤシ、`remote_import_api.py`（291 行）ヲ Rust 側デ完結セシム。**R2a トノ決定的ナ差ハファイル本体ヲ配ル面ノ新設**（R2a ハ basename ノミ、symlink モ追ハズ）。`main.rs:3189` ニ proxy fallback 無キが故、従前ハ 404 ナリキ。**読出側 deny-list ヲ本増分デ入ル** —— 書込側ニハ拒否リストガ在ルニ読出側ニ対応物無カリキ。allow-list（scan root 内）ハ scan roots ガ可変 config ニシテ `files` 行ガ長生キスル為採レズ、deny-list ナラバ**応答表ヲ一行モ変ヘズ**入レ得 symlink 経路モ塔ガル。**Windows verbatim 接頭辞（`\\?\`）ノ罠**ニ注意 —— 片方ノミ canonicalize シテ `starts_with` セバ Windows デ一度モ一致セズ deny-list ガ丸ゴト無効化サル（POSIX デハ起キヌ為 Linux 開発デハ気附カズ）。**極性ニ依リ結論ガ変ハル**: allow-list 形ハ fail-closed、deny-list 形ハ **fail-open**。棚卸シハ `docs/development/development_docs/WINDOWS_VERBATIM_PATH_PITFALL.md`。他ニ `check_static_bypass` ヘ 3 経路登録（`/import/` ナル広キ prefix ハ禁）、Semaphore ノ permit ヲ `acquire_owned()` デ closure ヘ move（`spawn_blocking` ハキャンセル不能）、`{file_id}`（符号無シ・404）ト `ids`（`i64`・`-1` ハ 404 `no files`）ノパース規則分離、`is_file()` 使用（`exists()` ハ **FIFO デ永久ハング**）、ZIP ハ常ニ `large_file(true)`、`arcname` 無消毒、エントリ読出失敗ハ伝播（500）。テスト 25 件 ＋ `auth::chain` 30 件。設計: `docs/superpowers/plans/2026-07-28-lan-cowork-remote-import-r2b-files.md`

## [4.543.1] - 2026-07-28

### Fixed

- **remote import ノ `meta`/`diff` ガセッションゲートノ内側ニ在リ peer ガ到達デキザリシ件**: `auth/chain.rs` ノ `check_static_bypass` ハ LAN Cowork ノ peer 経路ヲ**一本ヅツ厳密パスデ列挙**スルが（同 L144 ニ「exact paths, never a prefix」ト明記）、R2a（v4.543.0）デ生ヤシた 2 route ヲ載セ忘レタリ。Python 側ハ `auth_route(..., bypass_session=True, require="peer")` ニて**宣言的ニ** bypass ヲ得ルが故、Rust 側ノ手書キ列挙ニ漏レガ生ジタり。R2a ノテストハ Router ヲ直接 oneshot スルが故 **middleware ヲ通ラズ**検出セズ。修正ニ伴ヒ、`check_static_bypass` ヲ直接呼ブ回帰テストヲ置キ、許可 2 経路ト**`local_import_api` ノ session 系 5 経路ガ bypass サレヌ事**ノ双方ヲ pin ス（prefix 化ノ再発防止 —— 同一 prefix ヲ session 認証ノルートガ共有スル為）。`native_daemon` 既定オフにて**本番影響ハ現時点ゼロ**、失敗方向モ fail-closed（401）ナリシが、出荷セシコードガ機能セヌ状態ナルが故 R2b ニ先立チテ単独デ是正ス。

## [4.543.0] - 2026-07-28

### Added

- **LAN Cowork remote import ノ `meta`/`diff` ヲ Rust デ配信ス（Increment R2a）**: R1 ノ DB 問合セ・整形層ニ HTTP 面ヲ被セ、`/api/peer/import/meta` ト `/diff` ノ 2 route ヲ生ヤス。`file`/`zip`/`stream` ハ **R2b** ヘ分ツ —— R1 トノ決定的ナ差ハ「**Rust ノードニ存在セザリシ面ヲ新設スル**」点ニ在リ（`main.rs:3189` ニ proxy fallback 無ク、現在ハ 404）、ファイル配信ヲ含ム増分ハ独立審査トスル為ナリ。R2a ハ**ファイルニ一切触レズ**。**`native_daemon` gate ヲ必ズ掛ク**（`inbound_routes(native_daemon)` ト同形ニシテ flag off デ空 Router ⟹ 404）。**nonce ハ両側トモ不要**ナリ —— 当初「双方ノ `NONCE_REQUIRED_PREFIXES` ニ登録済ミ故 nonce 必須ノ扱ヒガ一致ス」ト解セシハ**誤リ**ニシテ、`path_requires_nonce` ハ行頭一致、実 path ハ `/ext/lan_cowork/...` ニ始マルガ故 prefix ニ一致セズ。Python クライアントハ `X-Peer-Nonce` ヲ送ラヌ為、「nonce 無シ署名ガ 200」ノ回帰テストヲ置ク（prefix ヲ剥グ「改善」ヲ入レタル瞬間ニ全 import ガ 401 ト成ル）。DB 呼出ニ `spawn_blocking` ヲ掛ケズ（R1 ノ関数ハ `async fn` ニシテ中デ `.await` 能ハズ）、署名ハ**生 query** ニ対シテ行フ（実 URL ハ `ids=1%2C2%2C3`）。`/meta` ハ `after_rowid` ヲ無視シ、`/diff` ハ常ニ `mode="full"` ニテ パース失敗ヲ 0 ニ倒ス。DB 失敗ハ `std::mem::discriminant` ノミ log（SQL 文モ値モパスモ出サズ）。parity harness ニハ登録セズ（`ENDPOINTS` ハ peer 署名機構ヲ持タズ live parity ガ FAIL スル為）。テスト 14 件。設計: `docs/superpowers/plans/2026-07-28-lan-cowork-remote-import-r2-routes.md`

## [4.542.0] - 2026-07-28

### Added

- **LAN Cowork remote import ノ DB 問合セ・整形層ヲ Rust ヘ移植（Increment R1）**: `routes/remote_import_api.py:18-203` ヲ `routes/lan_cowork_import_meta.rs` ヘ収ム。5 route ノ登録・streaming・ZIP 生成ハ R2 ヘ。route ハ未ダ生ヤサズ dead code トシテ着地ス。**着手前ニ到達可能性ヲ検ム**（直前ノ sync 系ガ何レノ設定デモ起動セヌと判明シ移植ヲ中止セシ経緯ニ鑑ミ）—— UI（`lan-cowork-page/api.ts`・`import-panel.ts`）・実行体（`import_transfer.py:130,190`）・署名対象（`request_signer.py:33`）ノ三者デ稼働ヲ確カメタリ。但シ `/api/peer/import/stream/{id}` ハ**呼出元ゼロ**ナリ。移植上ノ肝ハ三つ —— (1) `routes/annotations.rs:71-86` ノ既存 `decode_annotation_value` ヲ**再利用セズ**（NULLヲ空文字ト成シ、UTF-8 妥当ナ BLOB ヲ TEXT 扱ヒト成シ、**zstd ヲ展開シ**、lossy 変換スル四点デ parity ヲ破ル。zstd 圧縮値ハ実在シ受信側 `import_executor_db.py:103-125` ガ base64 ヲ復号シテ verbatim INSERT スルガ故、展開シテ送レバ相手ノ DB 内容ガ変ハル）、(2) `try_get_raw` ＋ `TypeInfo::name()` デ NULL/INTEGER/REAL/TEXT/BLOB ヲ分ツ汎用ヘルパニて**型ヲ保ツ**（`Option<f64>` 固定デハ `confidence = 1` ガ `1.0` ト成リ wire ガ変ハル。尚 `<String as Decode<Sqlite>>::decode` ハ UTF-8 妥当ナ BLOB デモ成功スルガ故「decode 成功 ⇒ TEXT」ハ偽）、(3) `redact_file_path` ヲ `Path::file_name()` ニ依ラセ、`/` ト `\` 双方デ分割スル自前実装ヲ避ク（POSIX ハファイル名ニ `\` ヲ含メ得）。テスト 7 件。設計: `docs/superpowers/plans/2026-07-28-lan-cowork-remote-import-r1-meta.md`

## [4.541.1] - 2026-07-28

### Fixed

- **sync root ノ外ヘ解決サルル symlink ヲ同期対象カラ除ク**: `wc_root` ノ中カラ外ヲ指スファイル symlink ガ、送出側 3 経路ヨリ外ヘ出居タリ。`build_manifest` ハ hash/mtime/size 付キデ manifest ニ載セ（`/api/peer/sync/manifest` ガ其ノ儀返スガ故**其レ自体ガ漏洩**）、`_push_file` ハ無検証ノ `read_bytes()` ニテ**本文ヲ peer ヘ送信**シ、`notify_local_change` ハ hash/size/mtime ヲ relay ヘ出シタリ。受入側 4 経路ハ既ニ検証済ミナルガ故、**送出側ノミ守ラレ居ラザル非対称**ガ実体ナリキ。`build_manifest` ハ root 外ヘ解決サルル成分ヲ除キ、`_push_file`/`notify_local_change` ハ `_validate_sync_path` ノ**戻り値**ニ対シテ操作ス（再構成ヲ禁ズ —— 検証ト読取ノ間ノ symlink 差シ替ヘ窓ヲ残サヌ為）。**併セテ受入側ノ耐性モ同一増分ニて是正ス** —— `to_fetch` ループガ `_write_synced_file` ノ `ValueError` ヲ捕ヘズ、`sync_with_all` ノ `return_exceptions=True` ガ log ゼロデ握リ潰スガ故、manifest 除外ノみデハ**起動時同期ガ無言デ打チ切ラル**（push 済ミ環境デハ適用直後ニ確実ニ発火）。log ハ path ノ provenance デ分ツ（peer 由来ハ件数ノミ、ローカル由来ハ `logger.debug` ニ rel_path）。**Rust 側ノ runtime 影響ハゼロ**（`/api/peer/sync/*` ノ route ガ 1 本モ無ク outbound モ無キ為、混在 fleet デ片側ノミ直リタル状態ニハ成ラズ）。本 gate ハ symlink 経由ノ脱出ノミヲ塞グモノニシテ、bind mount 等ノ物理的包含ヲ保証セズ。設計: `docs/superpowers/plans/2026-07-28-lan-cowork-sync-s1b-symlink-leak.md`

## [4.541.0] - 2026-07-28

### Added

- **LAN Cowork sync ノ純粋層ヲ Rust ヘ移植（Increment S1）**: sync 系 4 エンドポイントノ土台タル `file_hash` / `build_manifest` / `diff_manifests` / `validate_sync_path` / `backup_file` / `write_synced_file` ヲ `routes/lan_cowork_sync.rs` ヘ収ム。route ハ未ダ生ヤサズ dead code トシテ着地ス。**path 解決ハ `posixpath.realpath(strict=False)` ト同ジ逐次解決トス** —— 当初案ノ「最深既存祖先ヲ canonicalize シ残余ヲ字句結合」ハ Python 非等価ニシテ、`root/nope/../link`（`nope` 不在・`link` ハ root 外ヘノ symlink）ヲ通シテ了フ（実測: Python ハ `/etc/hostname` ヘ解決シテ拒否ス）。symlink 展開上限到達時モ早期 `return` セズ残余成分ヲ保持ス（失ヘバ root 内ノ意図セヌ場所ヘ書ク）。Python ニ揃ヘタルハ root 不在時ノ空 manifest・`rglob` ノ symlink 意味論（ディレクトリ symlink ヘ降リズ、ファイル symlink ハ追従）・`.bak` ノ mtime 保存・解決済 path ヘノ書キ込ミ。意図的差異ハ `diff_manifests` ノ出力順ノ決定化ト、絶対 `rel_path` ノ fail-closed 拒否ト、manifest key ヲ `Component` 連結デ作ル事（`to_string_lossy().replace()` ハ Linux ノ正当ナ `a\b.txt` ヲ壊ス）。新規依存無シ。テスト 14 件。設計: `docs/superpowers/plans/2026-07-28-lan-cowork-sync-s1-manifest.md`

## [4.540.2] - 2026-07-25

### Fixed

- **Python 側: loopback 待受ケ時ノ register リトライヲ止ム（成功シ得ヌ要求ト其ノ WARN ノ除去）**: `heartbeat.py` ハ heartbeat 失敗ノ都度 `/api/peer/register` ヘ再登録ヲ試ミ居タリ。loopback ノミデ待受クルノードデハ**必ズ失敗ス**（相手ガ広告サレタ LAN IP ヘ probe シ 502「peer not reachable」— `routes/peer_api.py:115-117`）。其ノ応答 body ハ `core_impl/transport.py:140-143` ニテ丸ゴト WARNING ニ書カルルガ故、heartbeat 失敗中ノ peer 毎ニ 10 秒周期デログガ膨ラミタリ。`core/web/runtime_runner.py` ニ `app.config["HOST"]` ヲ追加シ（`config["server"]["host"]` ヘノ back-fill ハ禁ズ — 同一 dict ガ `init_app_state` 経由デ共有サレ `resolve_public_host` ノ答ヲ変ヘル為）、純関数 `is_loopback_listener(host: str) -> bool`（分類不能ハ False ＝従来動作）ニテ bool ヲ導キ、register リトライノミヲ skip ス。

### Changed

- **「bind アドレスニ基ヅク広告」（Rust v4.539.0）ノ Python 移植ハ「実施セズ」ト決着ス**: design-advisor NO-GO。実コードニテ確メタル理由三点 — ①**機構ガ目的ヲ達セズ**: HELLO broadcast ハ HTTP bind ト独立シ（`discovery.py:131` ガ `("", 19850)` ヲ bind）、受信側ハ広告値ニ非ズ **UDP 送信元**デ登録ス（`discovery.py:240` → `manager.py:208,216`）。`api_host` ヲ空ニシテモ他ノードハ LAN IP デ登録シ続ク。②**防ガントセシ害ハ既ニ発生セズ**: `/api/peer/register` ハ既ニ fail-closed ニシテ 非 IP/非 private/**loopback** ヲ 400 ニ、到達不能ヲ 502 ニ弾ク（`peer_api.py:104-117`）。③**唯一ノ実効差分ガ重大ナ回帰**: pairing ノミ IP 検証モ probe モ持タズ（`pair_api.py:73,89`）、`require_peer_auth` ニ送信元 IP 照合モ無シ。⟹ **loopback ノードノ pairing ハ現ニ成功シ居リ**、其レガデスクトップ UI ノ主経路ナリ（`api.ts:119-120` → `client_api.py:20-41` → `peer_auth_client.py:54-82`）。Tauri ハ Python ヲ `--host 127.0.0.1` 固定デ起動スル（`flask_start.rs:122-123`）ガ故、移植セバ**全デスクトップ利用者ノペアリングガ恒久的ニ失敗セリ**。「利用者ノ大半ガ loopback」ハ実施ノ理由ニ非ズ**変ヘテハナラヌ理由**ナリキ。依ツテ `api_host`・pairing・discovery・LAN 待受ケノードノ挙動ハ一切変ヘズ。Rust 側 v4.539.0 ハ据置キ（Rust デハ広告値ガ其ノ儘接続先ト成ル為 有効）。

## [4.540.1] - 2026-07-25

### Security

- **Python 側: `event_type` ノ長サヲ有界化シ、拒否 WARN ヲ throttle ス（ログ氾濫ノ遮断）**: `inject_remote_event`（`core_impl/peer_event_relay.py`）ハ拒否セシ event 毎ニ**攻撃者制御ノ `event_type` ヲ丸ゴト** WARNING ヘ書キ throttle 無カリキ。加ヘテ `PeerEventRequest.event_type`（`routes/request_models.py:73`）ハ `min_length=1` ノミニシテ**上限無シ**ナリキ。⟹ ペアリング済 peer ガ、巨大ナ型名一発デモ短キ型名ノ連投デモ、ローカルノログヲ膨ラマセ得タリ。
  **是正ハ二段。入レ場所ヲ分カツ**: (i) model ニ `max_length=128` ヲ加ヘ、超過分ハ **relay ニ到達セズ** 400 ト成ス。`validate_json_model`（`core/infra_core/api_request.py:25-38`）ハ本文ヲ `err["loc"]`・`err["msg"]` ノミヨリ組ミ `err["input"]` ヲ含メヌガ故ニ、攻撃者ノ文字列ハ**応答ニモ現レズ**（相手ノ transport ガ応答 body ヲ逐語 WARN ニ書ク為 此ノ性質ガ要ル）。(ii) WARN ヲ出シ居ル relay 側ニ throttle ヲ置ク（route 側デ抑ヘテモ relay 内ノログハ止マラヌ）。窓ノ算術ハ純関数 `note_rejected_event` ニ切リ出シ、状態ハ **`PeerEventRelay` ノインスタンス**ニ持タス（Rust ガ process-global ヲ用ヰタルハ自然ナ実体ガ無カリシ故。Python ハクラスヲ持チ、テスト間ノ汚染モ避ケ得ル）。意味論ハ Rust ノ `note_relayed_event` ト同一（初回即可視化・窓内抑止・窓経過ニテ累計 flush）ニシテ、時刻ハ `time.monotonic()` ヲ用ヰ壁時計ノ跳ビニ依ラズ。log スルハ抑止件数・認証済 `source_peer`・`event_type` ノ 64 字切リ詰メノミ（`event_data` ハ非 log）。件数ヲ載スルガ故ニ氾濫ヲ止メツツ件数ハ失ハレズ。
  **Rust ヘハ持チ込マズ**: Rust ハ allowlist 拒否時ニ log セズ（`lan_cowork_inbound_read.rs:511-514` ハ `api_err` ノミ）、且ツ body 上限ニテ `event_type` モ有界ナルガ故、本氾濫経路ハ Python 固有ナリ。副作用トシテ 128 字超ノ型名ハ Python ガ 400・Rust ガ 403 ト status ヲ異ニスルガ、何レモ拒否ニシテ実害無シ。

## [4.540.0] - 2026-07-25

### Security

- **Python 側: relay サレタ event ノ出所ヲ認証済 identity ニ改ム（脆弱性ノ是正）**: `peer_event`（`routes/peer_api.py`）ハ event ノ出所ヲ**リクエストボディ**ノ `source_peer`（`request_models.py:75`、`StrictStr = ""` ノ素ノ文字列ニシテ攻撃者ノ完全制御下）カラ採リ、`inject_remote_event` ガ之ヲ `data["peer_id"]` トシテローカル event bus ヘ emit セリ（`peer_event_relay.py:87-89`）。⟹ **ペアリング済ミノ peer ガ他ノ任意ノ peer ヲ騙リテ event ヲ注入シ得タリ。** `@_auth`（`require_peer_auth`）ハ既ニ Ed25519 署名ト Bearer トークンヲ `X-Peer-Id` ノ peer ニ対シ検証済ミナルニ其ノ identity ヲ捨テ居タリ。之ヲ改メ `request.headers.get("X-Peer-Id", "").strip()` ヲ用フ。**kwargs ハ用ヰズ** — `peer_id` ナル kwarg ハ `peer_delete(peer_id: str)` ノ path 変数ト衝突シ削除対象ガ自機ニ化ケ得ル。ヘッダ再読ナレバデコレータ不変ニシテ其ノ他 24 箇所ヘ波及セズ。wire 互換ノ為 `source_peer` フィールドハ受理シ続ク（値ヲ信用セヌノミ）。Rust 側ハ v4.537.0 ニテ同ジ是正ヲ既ニ入レ居リ、本変更ハ其ノ **Python 側 parity**ナリ。**Python ハ実行時既定「オン」ニシテ現ニ動作スル経路**ナルガ故、Rust ノ dead-code 修正トハ blast radius ガ桁違ヒナル点ヲ勘案シ単独ノ最小差分トシテ切リ出セリ。

### Fixed

- **`/peer/event` ノ body 上限ヲ型別ニ改ム（Python + Rust）— v4.537.0 ノ一律 64 KiB ハ欠陥ナリキ**: `generation.submit` ハ relay allowlist ニ在リ、NAI bridge ガ `params` ヲ丸ゴト載セ（`nai_api_generate.py:257-261`）、其ノ `params` ニハ img2img ノ base64 画像ガ入ル（同 L96/L99）。`_relay_to_peers` ハ `event.data` ヲ無加工転送スルガ故ニ body ハ MB 級ト成ル。一方 他 6 型ハ構造上小サシ（GEN_COMPLETE ハ `images_count` ト `elapsed_ms` ノミヲ emit シ画像ヲ含メズ）。⟹ **一律 64 KiB ハ正当ナ `generation.submit` ヲ 413 デ弾ク**（`native_daemon` 既定オフゆゑ実害未発ナレド、有効化セシ瞬間ニ img2img relay ガ壊レタリ）。是正シテ **`generation.submit` ノミ 8 MiB、他 6 型ハ 64 KiB** トス。Python ハ純関数 `peer_event_body_limit` / `peer_event_body_too_large` ヲ置キ parse 後・`inject_remote_event` 前ニ検ス（従前ハ endpoint 固有ノ上限無ク全体 `MAX_CONTENT_LENGTH = 100 MB` ノミ）。Rust ハ **判定ヲ parse 後ヘ移シ**（型ヲ知ラネバ型別上限ヲ適用シ得ヌ為）、axum ノ暗黙上限 2 MiB ガ 8 MiB ヲ下回ルガ故ニ `/ext/lan_cowork/api/peer/event` ノ route ニノミ `DefaultBodyLimit::max(8 MiB)` ヲ付ス（他 route・全体設定ハ不変）。両側トモ「拒否時ハ SSE / event bus ヘ流サヌ」性質ヲ test デ pin ス。
- **413 応答ハ event 由来ノ内容ヲ一切含マヌ静的文言トス**: 相手ノ transport ガ応答 body ヲ逐語 WARN ニ書ク（`core_impl/transport.py:140-143` ノ `body=%s`）ガ故ニ、応答ニ載セタ内容ハ呼出側ノログヘ流ル。

### Changed

- Python 側 parity 移植ノ設計判断ヲ記録ス: **bind アドレスニ基ヅク広告（Rust v4.539.0）ハ Python ヘ持チ込マズ**、別途 再設計トス。理由: (a) Python ノ受信側ハ広告値ヲ用ヰズ UDP 送信元アドレスヲ採ル（`discovery.py:240` → `manager.py:208,216`）ガ故ニ目的ヲ達セズ、(b) Tauri ハ Python ヲ `--host 127.0.0.1` 固定デ起動シ（`src-tauri/src/flask_start.rs:122-123`）loopback ハ既定値デモアル為、`api_host` ヲ空化スレバ相手側 `min_length=1`（`request_models.py:44`）ニテ pairing 開始ガ 400 ト成リ **outbound ガ壊ル**、(c) `effective_host` ハ生文字列ニシテ Rust ノ `SocketAddr` ト非等価。Rust 側 v4.539.0 ハ据置キ（Rust デハ広告値ガ其ノ儘接続先ト成ル為 有効）。

## [4.539.0] - 2026-07-25

### Fixed

- **loopback 待受ノードガ到達不能ナ LAN IP ヲ広告シ得タルヲ是正**: `local_descriptor`（`lan_cowork_descriptor.rs`）ハ `resolve_lan_ip()`（既定経路ノ出口 IP ヲ UDP socket 経由デ得ル実装）ヲ其ノ儘広告シ、**HTTP ノ bind アドレスヲ一切参照セザリキ**。故ニ `127.0.0.1` ノミデ待受クルノード（**デスクトップ版ハ `--host 127.0.0.1` 固定ナルガ故ニ此ニ該当**、`src-tauri/src/yu_server.rs:76-84`）ガ、待受ケヌ LAN IP ヲ告知シ得タリ — 相手カラハ発見デキルモ接続デキヌ状態ナリ。`build_descriptor` ハ `is_reachable_peer_ip` ニテ loopback ヲ弾ク検証ヲ持テドモ、渡サルル値ガ bind ト無関係ナルガ故ニ此ノ場合ニ発火セザリキ。
  **是正**: bind 済 `SocketAddr` ヲ記録シ（`set_bound_port` → `set_bound_addr`、`main.rs` ハ既ニ取得済ノ `listener.local_addr()` ヲ渡ス。OnceLock ハ一本ノ儘）、純関数 `advertise_host(Option<SocketAddr>) -> Option<String>` ニ分岐ヲ集約ス: 未 bind ⟹ `None`／`is_unspecified()`（`--lan` ノ `0.0.0.0`）⟹ 従来通リ `resolve_lan_ip()`／**loopback ⟹ `None`（告知セズ）**／其ノ他ノ具体 IP ⟹ 其ノ IP。四分岐全テヲ unit test デ pin ス。`--lan` 経路ノ挙動ハ不変（`is_reachable_peer_ip` ガ `0.0.0.0` ヲ弾ク為、unspecified 分岐ヲ欠ケバ LAN bind ノード悉ク告知ヲ止メタリ — 回帰防止トシテ明示的ニ試ス）。`--host <LAN IP>` 指定時ハ**広告値ガ bind 値ト一致スル様改善サル**（従前ハ multi-homed ホストデ default route 出口 IP ト食ヒ違ヒ得タリ）。
  併セテ **loopback 専用時ハ起動後一度ダケ WARN ヲ出ス**（`note_loopback_only` 純関数 + tick call site、`note_recv_error` ト同型）: `LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan`。未 bind（起動直後ノ一過性）ニハ警告セズ（tick ハ先ニ sleep スルガ故ニ自然ニ解消ス）。

### Changed

- **公開文書 11 言語ヲ本挙動変更ニ追随更新**: 「PIN ヤ待受ケアドレスト無関係ニ告知スル」トノ記述ハ**PIN ノミト無関係**ニ改メ、`### loopback だけで待ち受けている場合（v4.539.0 以降）` 節ヲ新設シテ「告知セヌ事」「WARN 文言（逐語）」「LAN デ使フニハ LAN アドレス bind 又ハ `--lan`」「v4.539.0 以前ハ広告シ得タ経緯」ヲ記ス。runbook 冒頭ノ loopback 注記モ同期。構造検証（コードブロック 3 件ノバイト一致・見出シ 10 件・表行 29 件・技術トークン 16 種）ヲ全 10 言語デ通過。
- 前版デ新設セシ開示文書 `docs/ja/lan-cowork/network-behavior.md` ヲ 10 言語ヘ展開シ、各言語 README ヨリ相対リンクヲ張ル（`270364bbb`）。併セテ TODO ノ lan_cowork discovery daemon（Increment B+D）ヲ done(v4.538.0) トシテ閉ヅ。

## [4.538.0] - 2026-07-25

### Changed

- **LAN Cowork native daemon ヲ設定キー経由デ有効化スル様改ム（B-g1）**: 従前ハ `--native-daemon` フラグ（又ハ `YU_LAN_COWORK_NATIVE_DAEMON=1`）ノミガ有効化手段ニシテ、**文書化サレタ設定キーヲ Rust ハ一切読マザリキ**。之ヲ改メ、`config.json` ノ `extensions."builtin-lan-cowork".enabled` ヲ主経路トス。優先順位ハ **CLI > config > env > 既定**（`db` 解決ノ既存様式ニ倣フ）。純関数 `resolve_native_daemon(standalone, cli_on, cli_off, config, env)` ニ真理値表ヲ集約シ、全行ヲ unit test デ pin ス。解決点ハ **profile merge 直後**ヘ移ス（merge 前ノ config ヲ読ムト同一プロセス内デ `configured_peer_name` ト答ガ食ヒ違フ為。`server_cfg` 由来ノ host/port/lan/pin ハ merge 前ノ儘トイフ非対称ハ意図的ニシテ注釈ヲ残ス）。opt-out トシテ `--no-native-daemon` ヲ新設。起動時ニ `native daemon resolved`（決定値ト決定源）ノ INFO 一行ヲ出ス。plan: `docs/superpowers/plans/2026-07-25-lan-cowork-daemon-b-g1-flag-day-cutover.md`。

### Fixed

- **公開文書ノ LAN Cowork 設定名前空間ガ全面的ニ誤リナリシヲ是正（11 言語 36 ファイル）**: 文書ハ最上位 `{"lan_cowork": {...}}` ヲ案内セシガ、**Python モ Rust モ其ノ位置ヲ読マズ**（正ハ `config["extensions"]["builtin-lan-cowork"]`、`extensions_admin.py:100-104`）。`enabled` ノミナラズ `fleet` ノ許可リスト（`allow_remote_update` / `allow_update_from` / `allow_log_stream_from`、`settings_api.py:63`）モ同断ニシテ、文書通リ設定シタ利用者ハ「設定シタ積リデ効イテ居ナイ」状態ニ在リキ。尚 `fleet` ノ既定ハ `False` / `[]`（`fleet_routes_allowlists.py:83-85`）ナルガ故ニ**過剰許可ニハ非ズ**、fail-closed ニ機能セザル不具合ナリ。内部ノ設計 spec ハ当時ノ記録ニツキ改メズ。

### Added

- **利用者向 開示文書 `docs/ja/lan-cowork/network-behavior.md` ヲ新設**: 有効化後ニ LAN 上デ何ガ起ルカ（UDP 19850 待受・10 秒毎ノ署名付 HELLO broadcast・TOFU 登録・inbound 受付・SSE 配信・掃除）、セッション不要デ開ク 5 経路ノ意味、200/405/503 ノ読ミ分ケ、設定ノ優先順位ヲ一枚ニ纏ム。

### Security

- **既定ハ「無効」（fail-closed）— Python 実行時既定（有効）カラノ意図的逸脱**: Python ハ `extension.json:11-14` ノ `"config": {"enabled": true}` ヲ既定トシ、`config.json` ニ項目無キ時ハ**有効**トシテ振舞フ（`lan_cowork_ext.py:78` ハ無効化判定ニ非ズ、L84 ノ `default=True` ヘ落ツ）。Rust standalone ハ之ニ倣ハズ、**明示的ニ有効化セヌ限リ無効**トス。standalone/Tauri ノ Rust ノードハ現在 LAN 上デ何モセヌ故、更新ノミデ露出ガ増ユル事故ヲ構造的ニ防グ為ナリ。逸脱ノ事実ハ本項・コード注釈・公開文書ノ三所ニ記ス。
- **`config` ガ `false` ノ時 env デハ覆ラズ**: config ハ WebUI トグルガ書ク値、env ハ dotenv 経由デ混入シ得ル（`main.rs` `load_dotenv_files`）ガ故ニ、古キ dotenv ガ UI ノ無効化ヲ無言デ覆スヲ防グ。
- **hybrid ノ挙動ハ無変更**: hybrid（`--standalone` 無シ）デハ config ヲ**一切参照セズ**、`enabled:true` デモ Rust 側 daemon ハ起動セズ error ニモ非ズ（之ヲ error トセバ LAN Cowork ヲ用フル hybrid ノード悉ク起動不能ト成ル）。**CLI/env ニヨル明示 opt-in ノ起動時 fail-fast ハ従来通リ保持**（error 文言ハ env 起因ノ場合ヲ含ム様改メタリ）。smoke ノ新規 leg `4b hybrid safety` ガ、exit 1 セヌ事ト daemon ガ起動セヌ事ノ両方向ヲ pin ス。
- **開示: PIN ハ discovery ヲ止メズ**: `--lan`（0.0.0.0 bind）ハ PIN 必須ナレド（`main.rs:623-626`）、`--host <LAN IP>` ハ此ノ検査ヲ通ラズ、且ツ PIN 未設定時ハ `pin_auth_enabled=false` ニテセッションゲートガ**開ク**。加ヘテ UDP discovery ハ PIN ニモ HTTP bind ニモ非依存（`bind_discovery_socket` ハ `0.0.0.0:19850` 固定）。故ニ「PIN 未設定ナラ実質無効」ハ成立セズ、**既定無効ガ唯一ノ構造的防壁**ナリ。
- **開示（v4.539.0 デ是正済）: Tauri ハ loopback 待受ノ儘 LAN IP ヲ広告シ得**（`src-tauri/src/yu_server.rs:76-84` ハ `--host 127.0.0.1`、`resolve_lan_ip()` ハ bind ト無関係）。**開示: 破壊的 prune ハ有効化後ノ初回起動時ニ走ル**（hard 7 日 / soft 1 時間、`lan_cowork_registry.rs:235,243`）。**開示: 拡張一覧ハ `extension.json` 由来デ「有効」ト表示シ得ルガ daemon ノ実態トハ別**（`auto_stubs.rs:322-325`）— 起動ログノ `native daemon resolved` 行デ判別スベシ。

## [4.537.0] - 2026-07-25

### Added

- **LAN Cowork native daemon B-f2（受理 peer event ヲ local SSE hub ヘ relay ス・SF-1 Option B）**: b-5 ニテ採リシ Option A（log + drop）ヲ解消シ、allowlist ヲ通過セシ peer event ヲ `AppState.sse_hub` 経由デ `/api/events/stream`（session gate 配下）ノ購読者ヘ配信ス。b-5 当時ノ「Rust ニ event bus 無シ」ナル前提ハ既ニ崩レ（`pair_verify` ガ `peer.paired` ヲ実送出セリ）、本増分ハ其ノ変化ヲ承ケテ consumer ヲ配線スルモノ。移植元ハ Python `peer_event_relay.py::inject_remote_event`。`event_data`（object）ニ `_peer_relayed = true` ト `peer_id` ヲ**無条件上書キ**シ、`source = "peer:<peer_id>"` ヲ添ヘテ送出ス。純関数 `relayed_sse_event` ニ payload 整形ヲ抽出シ単体テストデ形ヲ pin ス。`native_daemon` 既定 false ハ据置キ、route 未 merge + registry slot 空ノ二重 gate ニヨリ flag=false デ本番挙動不変。plan: `docs/superpowers/plans/2026-07-25-lan-cowork-daemon-b-f2-event-sse-consumer.md`。

### Changed

- **SF-1 throttle ノ語彙ヲ `dropped` → `relayed` ニ改ム**: consumer ガ付キシ以上「dropped」ハ虚偽ナルガ故。機構（≤1 INFO/60s-window・first-event-visible・logging 中ニ lock ヲ握ラズ）ハ B-e5 ノ儘不変ニシテ、型名 `EventRelayedWindow`・定数 `EVENT_RELAYED_LOG_WINDOW_SEC`・純関数 `note_relayed_event`・static `EVENT_RELAYED_THROTTLE`・message・field ヲ一貫改称ス。flood 対策ノ必要性ハ不変（`generation.progress` ハ毎秒数 tick）。log スル field ハ `relayed` count・`event_type`・認証済 `source_peer` ノミ（`event_data` ハ従前通リ非 log）。runbook ノ §3/§5/§8/§10/§11 ト smoke harness ノ期待文字列モ追随更新ス。
- **smoke harness ノ throttle leg ヲ `relayed=<n>` 解析ヘ改メ、証跡ヲ v4.537.0 デ取リ直ス**: release ビルドニテ全 leg PASS（exit 0）、`10 throttle PASS relayed 1 then 50`。

### Security

- **peer_id 詐称ノ遮断（Python カラノ意図的乖離）**: Python ハ body 由来ノ `source_peer`（`PeerEventRequest.source_peer: StrictStr = ""`、既定空文字）ヲ用ヰルガ故ニ、paired peer ガ任意ノ `peer_id` ヲ騙リ得タリ。Rust ハ `require_peer_auth` ノ返ス**認証済 peer_id ノミ**ヲ用ヰ、`data["peer_id"]` ト `source` ノ双方ヲ之ニ拠ラシム。送信者ガ `event_data` ニ仕込ミシ `_peer_relayed` / `peer_id` ハ `Map::insert` ニテ無条件上書キサレ、其ノ事ヲ単体テスト（偽装 payload → 認証済 ID ヲ assert）ト統合テストデ pin ス。**キー名・形ハ Python ト逐語一致サセ、値ノ出所ノミ乖離セシム。** Python 側ノ詐称可能性ハ本増分ノ範囲外ノ残余トシテ TODO ニ記録ス。
- **body size guard 64 KiB（新設）**: `/ext/lan_cowork/api/peer/event` ニハ per-route `DefaultBodyLimit` ガ一ツモ掛カラズ（`main.rs` ノ 3 箇所ハ何レモ別 route ノ `MethodRouter` layer）、実効上限ハ axum 既定 2 MiB ナリキ。加ヘテ `/peer/event` ニ rate limit ハ無ク、broadcast ハ購読者 1 デモ 4096 slot ニ `Arc<SseEvent>` ヲ常駐セシメ得ル。故ニ**認証後・parse 前**ニ body 長ヲ検シ 64 KiB（既存 log route ノ `DefaultBodyLimit::max(65_536)` ニ揃フ）超過ヲ 413 ニテ拒ミ、SSE ヘ流サズ。拒否経路デモ `event_data` ヲ log セズ。境界テスト（丁度 64 KiB ハ通過・+1 ハ 413 且ツ SSE 非送出）ヲ加フ。
- **追加ノ sanitize ハ不要ト確認**: `sse/stream.rs` ガ `SseEvent` 全体ヲ `serde_json::to_string` シテカラ frame ニ載スルガ故ニ SSE frame injection ハ構造的ニ不可能。event 名モ RELAY_TYPES 7 型ニ限定サル。rate 制御ハ parity 優先デ不採用（lag ハ producer ヲ阻害セズ当該 client ノ切断ニ限局シ、Python ニモ無シ）。効ク lever ハ rate ニ非ズ size ナリ。
- **panic 経路ノ排除**: object 検証ヲ let-else ニ collapse シ、`expect`/`unwrap` ヲ remote 入力経路ニ残サズ。検証順序ハ 認証 → size guard → parse → event_type → **SF1 object** → allowlist → SSE 送出 ニシテ、非 object ハ allowlist 以前ニ 400（Python parity）。
- **flag=false デ本番不変**: 本 path ハ route 未 merge + registry slot 空ノ二重 gate 配下ニ在リ、`native_daemon=false` 時ハ到達不能。既定値ノ flip ハ含マズ。

## [4.536.0] - 2026-07-25

### Added

- **LAN Cowork native daemon B-f1（flag-day cutover ノ Must-fix 2・3）**: cutover 前提タル live smoke ト runbook ヲ納ム。`crates/` 配下ハ一切触レズ、`native_daemon` ノ既定 false モ据置ク（flip ハ別途明示 go-ahead ヲ要ス）。`scripts/lan_cowork_native_daemon_smoke.py`: 実 `yu-server` ヲ 2〜3 個起動シ実 HTTP 面ヲ駆動スル運用者向 harness。scratch DB ハ既存 `hailo_realhw_smoke.py::build_plain_scratch_db` ノ手順ヲ再利用シ（0 バイト SQLite ハ `schema_version` 不在ニテ起動不能ナルガ故ニ Python init/migrate 経路ガ base schema ヲ作ル）、Python 経路ガ SQLCipher 鍵付キデ作ル `vectors.db` ヲ削除シテ Rust ニ作ラシム。署名ハ repo 実関数（`core.crypto_identity.request_signer.build_canonical_message` / `keypair.sign`）ヲ再利用シスキームヲ再実装セズ。検証 leg ハ 起動 → discovery skip warn 検出（platform 分岐）→ フラグ ON ノ `/peer/status` 200 → フラグ無シ対照 → session（A・B 双方）→ 相互 discovery → register（既知 peer 更新・token 保全）→ pairing 四手順（request/requests/**approve**/verify）→ 署名付 inbound（heartbeat / event allowlist / allowlist 外 403 / token-renew）→ B-e5 throttle 二段。`docs/development/development_docs/LAN_COWORK_NATIVE_DAEMON_CUTOVER_RUNBOOK.md`: フラグガ有効化スル三者・有効化方法・flip 前チェックリスト・既知ノ限界・flip 手順・2-host 検証・監視信号・rollback ヲ記ス。**実行証跡（release ビルド・全 leg PASS・exit 0）ヲ runbook ニ収ム**（`4 flag off=405`・`6 discovery=mutual TOFU`・`8 pairing=0.7s`・`10 throttle=dropped 1 then 50`）。是ニテ cutover Must-fix 2・3 ヲ充足シ、残ル cutover 作業ハ flip 其ノ物ノミ。plan: `docs/superpowers/plans/2026-07-25-lan-cowork-daemon-b-f1-cutover-smoke-runbook.md`。

### Changed

- **文書化サレタ実測知見三件（何レモ live 実行ニテ判明シ、単体試験デハ露見セザリシモノ）**: (1) **フラグ off ノ観測値ハ 405 ニシテ 404 ニ非ズ** — `inbound_routes(false)` ハ空 Router ヲ返スガ、`/ext/lan_cowork/api/peer/{peer_id}` ノ DELETE（`lan_cowork.rs`）ガ無条件登録サレテ同 path ヲ shadow スルガ故。単体試験ノ 404 ハ孤立 router ヲ mount セシ場合ノ値ナリ。加ヘテ 503 ハ「フラグ on ナレド registry slot 空」ノ別信号ニシテ、此ノ三値ヲ運用者ガ読ミ分ケ得ル様 runbook ニ表ヲ置ク。(2) **debug ビルドデハ pairing ガ構造的ニ完了セズ** — initiator ノ outbound client ハ 10 秒固定 timeout ナルニ対シ responder ノ `pair_verify` ハ PIN KDF ニ scrypt log_n=17（release 実測 0.7 秒）ヲ用ヰ、debug デハ 10 秒ヲ超ユ。harness 側 timeout ヲ延バシテモ解決セズ（上限ハサーバ内部ニ在リ）。故ニ harness ハ release バイナリヲ優先シ、debug 実行時ハ「此ノ証跡ハ cutover ニ用ヰ得ズ」旨ヲ結果表先頭行ト banner ニ自己申告ス。(3) **rollback ハ data-safe ニ非ズ** — `PeerRegistry::load_all` ガ起動時ニ破壊的 DELETE ヲ走ラセ（hard prune `HARD_PRUNE_SEC=604800`）、7 日以上到達無キ peer 行ハ token 有無ニ関ハラズ消ユ。identity（`ed25519_seed`）ハ `INSERT OR IGNORE` ノミナルガ故ニ保全サル。故ニ rollback 手順ハ事前 DB バックアップト対ニ記ス。
- **B-d5e plan ノ誤決議ニ訂正注記ヲ残ス**: 「単一 bind ゆゑ同居不可」ハ TCP ニハ正シケレド **UDP/Linux ニハ誤リ**。`bind_discovery_socket` ハ `set_reuse_address(true)` ヲ設定シ、Linux デハ同一 UDP port ヘノ重複 bind ガ許サルル（実測: 同一ホスト 2 インスタンスガ共ニ bind 成功シ、broadcast ニテ相互発見ス）。macOS ハ許サヌ旨ノ既存記録（`changelog-2026-04.md`, v4.85.8）ト併セ、platform 分岐トシテ harness・runbook 双方ニ反映ス。

### Security

- **秘密非漏洩**: harness ハ ed25519 seed・平文 pairing PIN・**peer token（本増分デ扱ヒ始メタ資格情報）**・`event_data` ヲ、成功時モ例外・traceback 経路モ一切 print / log / 永続化セズ。PIN ハ使用直後ニ置換シ、例外ハ型名ト安全ナ status code ノミヲ記ス。code-reviewer 二周ニテ漏洩経路ゼロヲ確認。
- **監視信号ノ可視性（運用上ノ落トシ穴ヲ文書化）**: SF-1 ノ throttled INFO ハ「peer event ガ届キ drop サレツツ在ル」コトヲ示ス**唯一ノ実行時信号**ナレド、**既定デハ出力セズ**。実測ニテ `RUST_LOG` 未設定時ハ INFO 行ゼロ（`EnvFilter::try_from_default_env().unwrap_or_else(|_| "yu_server=info")` ハ**パースエラー時ニノミ**フォールバックシ、変数不在時ニハ効カズ）、`RUST_LOG=warn` 時モ当然抑止。故ニ flip 時ハ `RUST_LOG=yu_server=info` ヲ明示スベキ旨ヲ runbook ニ明記シ、harness ハ同ジ理由ニテ子プロセスノ `RUST_LOG` ヲ既定デ強制ス（`--rust-log` ニテ上書キ可）。
- **LAN 露出ノ明示**: smoke ハ loopback デハ動カズ（`is_reachable_peer_ip` ガ loopback ヲ拒ミ、`/peer/status` ハ `resolve_lan_ip()` ノ私設 IP ヲ広告スルガ故）、実行中ハ PIN 認証付 `yu-server` 二台ヲ私設 IP ニ一時露出ス。此ヲ runbook 冒頭ニ警告トシテ置キ、矮小化セズ。
- **本番挙動不変**: 本増分ハ script 一本ト doc 一本ノ追加ニシテ `crates/` 配下ゼロ変更、route・auth・依存ニ差分ナシ。`native_daemon` 既定ハ false ノ儘。

## [4.535.0] - 2026-07-24

### Changed

- **LAN Cowork native daemon B-e5（b-5 受理 event drop log ノ flood gate・SF-1）**: B-e1 ニテ受理済 peer event ノ drop log ヲ `tracing::debug!`→`tracing::info!` ニ昇格セシガ、M9 allowlist ハ `generation.progress`（毎秒数回 tick）ヲ admit スルガ故ニ、flag-day（`native_daemon=true`）以後ハ受理 event 毎ニ INFO 一行ヲ吐キ log ヲ flood シ得タリキ。之ヲ cutover 前提（SF-1 flood gate）トシテ、drop log ヲ ≤1 INFO/60s-window（window ノ drop count 携行）ニ throttle ス。窓判定ハ純関数 `note_dropped_event(&mut EventDropWindow, now: f64) -> Option<u64>` ニ抽出ス：`dropped` ヲ無条件 increment シ、`now - window_start >= 60.0`（定数 `EVENT_DROP_LOG_WINDOW_SEC`）ナレバ累計ヲ flush（reset）シテ `Some(count)`、然ラズンバ `None`（累積・抑止）ヲ返ス。`window_start` ハ `f64::NEG_INFINITY` 初期化ニテ初回 event ヲ即可視化ス（first-event-visible）。call site ハ process-global `static EVENT_DROP_THROTTLE: OnceLock<Mutex<EventDropWindow>>`（前例: `auth/apikey.rs:40` RATE_LIMITER）ヲ保持シ、`now_secs_f64()` ヲ `.lock()` 外デ読ミ、guard ハ内側ブロックニ scope シテ `tracing::info!` 前ニ解放ス（logging 中ニ lock ヲ握ラズ）。log スル field ハ `dropped` count・`event_type`・認証済 `source_peer` ノミニシテ、`event_data`・seed・平文 PIN ハ従前通リ一切 log セズ。純関数 unit-test 一本ヲ既存 `mod tests` ニ加ヘ（serial_test 不使用・process-global static ヲ介サズ）、first-event-visible→窓内抑止→境界 flush→新窓ノ遷移ヲ検ス。新規依存ナシ（`Mutex`/`OnceLock` ハ std）・route/`auth/chain.rs` 変更ナシ・`native_daemon` 既定 flip ナシ。此ノ path ハ本番デ二重ニ到達不能（native_daemon=false 時ハ route 未 merge ＋ registry slot 空ノ 503-gate ガ throttle static 初期化以前ニ短絡）ニツキ flag=false デ本番挙動不変。plan: `docs/superpowers/plans/2026-07-24-lan-cowork-daemon-b-e5-event-drop-throttle.md`。

### Security

- **秘密非漏洩不変**: throttled summary ハ `dropped`（件数）・`event_type`・認証済 `source_peer` ノミヲ log シ、`event_data`・ed25519 seed・平文 PIN ハ一切 log セズ。drop-count 完全性ハ clock 非依存（`dropped += 1` ハ時刻検査以前ニ走ル）ニシテ、wall-clock ノ後方 NTP step ハ高々一窓ノ summary ヲ遅延／拡大スルノミ、件数漏レ・crash ヲ生ゼズ。新規 logged field ハ `dropped` ノ一件ノミ。
- **可用性不変（log-flood 面ノ改善ニシテ攻撃面不増）**: 旧 unconditional INFO ハ `generation.progress` ノ高頻度 tick ヲ以テ log ヲ flood シ得タリ。throttle ハ此ノ per-event INFO ヲ ≤1/60s-window ニ律シ、且ツ純関数化ニテ lock ヲ logging 中ニ跨ガズ。新規 route・auth 変更・依存ナシ（GPL/LGPL/AGPL 禁・serial_test 不使用）。
- **flag=false デ本番不変**: 本 log 点ハ `native_daemon=true` 時ノミ到達可能ナル registry slot 配下ニ生キ、native_daemon=false 時ハ 503-gate ガ throttle static 初期化以前ニ短絡スルゆゑ本 path 全体ガ dead-code。本増分ハ gate 裏ノ log 律速ノミヲ改メ、本番挙動ニ差分ナシ。

## [4.534.0] - 2026-07-24

### Changed

- **LAN Cowork native daemon B-e3（b-5 recv_loop ノ continue-with-backoff・NH-1）**: discovery daemon ノ UDP 受信 task `recv_loop`（fire-and-forget・supervisor 不在）ハ従前 recv error ニテ `break` シ、一過性ノ recv error（例: ICMP port-unreachable 誘発ノ ECONNRESET）一発デ discovery 受信ヲ**永久ニ停止**シ得タリキ。之ヲ、error arm ヲ固定 500ms back-off（`RECV_ERROR_BACKOFF`）後ノ retry ニ改メ、持続 error 下デモ busy-spin セズ（≤2 Hz ニ律ス）discovery ヲ継続セシム。此ハ asyncio `DatagramProtocol` primary path（transport ハ recv error ヲ生キ延ブ）ニ整合シ、Windows `_listen_thread` fallback ノ `break`（此ハ `_running` flag ＋ socket timeout ト対ニ成ルガ、此ノ loop ハ其レラヲ意図的ニ欠ク）ニハ非整合ノ偽 parity ヲ避ク。warn ハ error run 毎ニ一度ノミ（成功 recv デ `recv_error_warned` reset）、log スルハ `std::io::Error`（`%error`）ノミニシテ datagram payload・`event_data`・`peer_id`・seed・PIN ハ一切混入セズ。warn 判定ト back-off 幅ハ純関数 `note_recv_error(&mut bool) -> (bool, Duration)` ニ抽出シ log 副作用ナシデ unit-test 化（warn-once-until-reset 遷移ヲ検ス）。fire-and-forget lifecycle 不変（JoinHandle/shutdown channel ナシ・`_running` machine 非移植）・新規依存ナシ（`Duration` ハ既 import）・route/`auth/chain.rs` 変更ナシ。此ノ path ハ本番デ二重ニ到達不能（native_daemon=false 時ハ daemon 未 spawn）ニツキ flag=false デ本番挙動不変。plan: `docs/superpowers/plans/2026-07-24-lan-cowork-daemon-b-e3-recv-loop-backoff.md`。

### Security

- **秘密非漏洩不変**: recv-error warn ハ `std::io::Error`（`%error`）ノミヲ log シ、datagram payload・`event_data`・認証前 `peer_id`・ed25519 seed・平文 PIN ハ一切 log セズ。`note_recv_error` ハ純関数（log 副作用ナシ）ニテ秘密ニ触レズ。新規 logged field 無シ。
- **可用性不変（DoS 耐性ノ改善ニシテ攻撃面不増）**: 旧 `break` ハ一過性 recv error 一発デ discovery 受信ヲ恒久停止セシメ、遠隔ノ port-unreachable 誘発（ECONNRESET）ヲ以テ受信 task ヲ黙殺サセ得タリ。back-off-retry ハ此ノ single-error kill ヲ塞ギ、且ツ ≤2 Hz ノ固定 back-off ニテ持続 error 下ノ busy-spin（CPU 消尽）ヲモ防グ。新規 route・auth 変更・依存ナシ。
- **flag=false デ本番不変**: recv_loop ハ `start_discovery_daemon`（native_daemon gate 下 spawn）ノ配下ニノミ生キ、native_daemon=false 時ハ daemon 未 spawn ゆゑ本 path 全体ガ到達不能。本増分ハ gate 裏ノ dead-code ノ error handling ノミヲ改メ、本番挙動ニ差分ナシ。

## [4.533.0] - 2026-07-24

### Added

- **LAN Cowork native daemon B-e2（b-4 renew mint 経路ノ E2E テスト・SF-D）**: token-renew handler ノ **glue**（auth 成功→`renew_if_not_revoked`→応答写像 `200 {ok,token,expires_at}` / `403 revoked` / `503 token_error`）ハ従前 component テストノミデ、handler ガ boot-grace ノ process-global `nonce_store()` ヲ直書キスルガ故ニ router テストデハ grace 窓内 503 ニ阻マレ到達不能ナリキ。之ヲ MF-3（boot-pinned nonce store）ヲ逆転セズ本番挙動モ触レズニ塞グ為、handler ヲ薄キ公開 wrapper `peer_token_renew`（slot-check ＋ `nonce_store()` 引渡シヲ保持）ト store 引数化サレシ内側 `peer_token_renew_inner(state, method, path, query, headers, body, nonces: &PeerNonceStore)` ニ分割ス。**CONTRACT INVARIANT**: `_inner` ハ slot-agnostic ニ留メ（slot-check ハ wrapper ノミ）、auth+renew+map ノミ行フ。新規 `#[tokio::test]` 二本ガ `PeerNonceStore::with_grace(0)` ヲ注入シ seed 済 active peer ＋正当署名リクエストデ `_inner` ヲ直呼ビシ、(1)mint 成功→200・非空 `token`・`expires_at` 存在、(2)revoked peer→403 `revoked` ヲ検ス。署名ヘルパ `sign_headers` ハ `peer_transport.rs` ノ private `mod tests` カラ module scope（`#[cfg(test)] pub(crate)`）ヘ hoist シ跨モジュール参照ヲ可能化ス（重複ナシ）。Option A（nonce store ヲ SharedState field 化）ハ MF-3 部分逆転＋10 constructor site ノ波及ゆゑ constraint-barred トシテ却下。新規依存・route・`auth/chain.rs` 変更ナシ。flag=false デ本番挙動不変（route 未 merge ＋ registry slot 空ノ二層 gate 不変）。plan: `docs/superpowers/plans/2026-07-24-lan-cowork-daemon-b-e2-renew-e2e-nonce-seam.md`。

### Security

- **本番不変（二層独立 gate）**: `peer_token_renew` wrapper ハ従前通リ slot-check シ `nonce_store()`（boot-pinned・MF-3 保持）ヲ渡ス。`_inner` 抽出ハ private ニシテ route/`auth/chain.rs`/依存ニ触レズ、native_daemon=false 時ハ route 未 merge（handler 404）＋ registry slot 空（内側 503）ノ二重ニ renew mint 経路ハ本番到達不能ナリ。
- **秘密非漏洩不変**: renew ハ自ラノ 200 body デ minted token ヲ返スガ（其ノ本旨）、ed25519 seed・平文 PIN・`event_data` ハ一切 log・返却・エラー混入セズ。新規 logged field 無シ。テスト署名ヘルパ hoist ハ `#[cfg(test)]` 限定ニシテ本番バイナリニ露出セズ。
- **攻撃面不増**: `_inner` ハ module private `async fn`、store 引数ハ `require_peer_renew_auth` ガ既ニ受容スル同型 `&PeerNonceStore`。新規 route・auth 変更・依存ナシ（GPL/LGPL/AGPL 禁・serial_test 不使用）。

## [4.532.0] - 2026-07-24

### Changed

- **LAN Cowork native daemon B-e1（b-5 event drop ノ可視化・NH1）**: b-5 event handler ニテ M9 allowlist ヲ通過シタ受理済 peer event ハ Rust ニ event bus 不在ゆゑ **Option A**（log+drop）ニテ落トサルルガ、其ノ log ガ `tracing::debug!` ナルガ故ニ既定 INFO 準位デハ不可視ナリキ。之ヲ `tracing::info!` ニ昇格シ、flag-day（`native_daemon=true`）以後ニ「event ハ到達スレド未ダ consumer 無シ」ノ運用信号ヲ operator ニ与フ。message・field（`event_type` ＋認証済 `source_peer` ノミ）ハ逐語不変ニシテ、**`event_data` ハ従前通リ一切 log セズ**。分岐（503/400/403/200）・`api_ok` 応答・allowlist（M9）ハ不変ニシテ level ノミノ差分ナリ。此ノ log 点ハ本番デ **二重ニ到達不能**（native_daemon=false 時ハ route 未 merge ゆゑ handler ハ 404、且ツ registry slot 空ゆゑ内側 503 guard）ニツキ flag=false デ本番挙動不変。full event_bus/SSE consumer（Option A ノ逆転）ト bare AtomicU64 counter（in-process reader 不在ゆゑ write-only）ハ孰レモ却下シ、最小 NH1 closure ニ留ム。plan: `docs/superpowers/plans/2026-07-24-lan-cowork-daemon-b-e1-event-consumer.md`。

## [4.531.0] - 2026-07-24

### Added

- **LAN Cowork native daemon B-d5g（独立 pairing sweeper 配線）**: 既ニ移植済ミナルモ dead-code タリシ pairing-PIN sweeper `sweep_expired` ヲ `native_daemon` gate 下ノ独立定期 task トシテ配線ス。`start_pairing_sweeper(state)`（`pub(crate)`・fire-and-forget）ハ `PAIRING_SWEEP_INTERVAL_SECS=60` 毎ニ sleep-first デ `sweep_expired` ヲ呼ビ、期限切レ pending/approved 行ヲ `status='expired'`・`pin_hash=NULL` ニ標シ、`drop_pin`+`untrack_pending` ニテ平文 PIN ヲ memory カラ排シ、長期終端行（`CLEANUP_AFTER_SECONDS`）ヲ削除ス。`main.rs` ハ registry ブロックノ兄弟トシテ `if native_daemon` 下ニ spawn ス（identity/registry 非依存ゆゑ registry ブロック内ニ nest セズ）。`sweep_expired` 本体ハ不変、新規依存・route・`auth/chain.rs` 変更ナシ。flag=false デ本番挙動不変。plan: `docs/superpowers/plans/2026-07-24-lan-cowork-daemon-b-d5g-pairing-sweeper.md`。

### Security

- **平文 PIN 滞留ノ有界化**: Python（`pairing_service.sweep_expired`）ハ write 契機ノ lazy cleanup ナルガ、traffic ゼロ時ニ期限切レ平文 PIN ガ無期限ニ滞留スル。Rust ハ traffic 非依存ノ独立周期 sweeper ヲ択ビ、滞留時間ヲ ≤ `PIN_TTL_SECONDS`(300)+interval(60)=360s ニ律ス（意図的逸脱・parity gap ニ非ズ）。此ハ hygiene bound ニシテ auth 窓ニ非ズ（`pair_verify` ハ `take_pin` 以前ニ期限切レ PIN ヲ拒ム）。sweeper ハ秘密ヲ *除去* スルノミデ PIN/seed ヲ log・返却・エラー混入セズ、新規 tracing モ加ヘズ。
- **safe_mode 非抑止**: `scheduler::start_scheduler` 前例（`standalone` gate ノミ・内部 safe_mode 検査ナシ）ニ倣ヒ sweeper ヲ safe_mode デ抑止セズ。抑止ハ期限切レ PIN ノ滞留ヲ却テ延バシ safe_mode ノ保護意図ニ反スル（`BG_TASKS` ヘハ登録セズ）。
- **既存 TOCTOU（fail-closed・本体不変）**: sweeper 化ニテ既存 `sweep_expired` 本体ノ pre-UPDATE SELECT snapshot→in-memory PIN eviction ノ窓ガ到達可能ト成ル。late-approve ガ sub-ms 窓ヲ競レバ DB 行ハ `approved`＋有効 hash ノママ平文 PIN ノミ排サレ得ル（fail-closed＝秘密ハ落チ、漏レズ、pairing ハ再試行可）。本体ハ不変トシ、RETURNING 単文修正ハ将来増分ニ繰延ブ。
- **flag-day 迄ハ本番ニ pairing cleanup 皆無**: 本増分後モ flag=false ノ間ハ production ニ lazy・periodic 何レノ pairing cleanup モ存在セズ（"lazy ヲ periodic ニ" ノ framing ハ flag 裏ニ残ル gap ヲ過小評価スルガ故、此ヲ明記ス）。

## [4.530.0] - 2026-07-24

### Added

- **LAN Cowork native daemon B-d5e**: native_daemon gate 下ノ既存 dead-code 部品(`recv_loop`・`tick_loop`・`bind_discovery_socket`・`check_timeouts`)ヲ起動時ニ配線シ、生キタ discovery daemon トシテ spawn ス。`start_discovery_daemon`(state, registry)ハ 19850 番ニ単一 `Arc<UdpSocket>` ヲ bind シ、recv_loop・tick_loop・timeout-sweep ノ三 task ヲ fire-and-forget デ起ス。`recv_loop` 第一引数ヲ `UdpSocket → Arc<UdpSocket>` ニ改メ recv/tick デ一 socket ヲ共有ス。bind 失敗(EADDRINUSE 含ム全種)ハ純関数 `discovery_socket_or_skip` ニテ warn+skip シ、決シテ panic/exit セズ「LAN discovery 無シ」ニ degrade ス。sweep ハ `check_timeouts` ヲ 10 秒毎ニ呼ビ in-memory ニテ online→offline ヲ標ス(DB 永続化無シ・event emit 無シ)。main.rs ハ既存 `if let Some(registry)` 内デ Arc ヲ複製シテ daemon ヘ渡シ其ノ後 OnceLock ヘ set ス。fire-and-forget(`scheduler::start_scheduler` 前例)ニツキ JoinHandle/shutdown channel ハ持タズ、プロセス終了時ニ OS ガ task 及ビ :19850 ヲ回収ス。純関数 2 本(graceful-skip・safe_mode 抑止)ヲ socket/runtime 無シデ unit test 化。依存追加ナシ。flag=false デ本番挙動不変。

### Security

- **safe_mode 抑止**: `start_discovery_daemon` 冒頭ニテ `should_start_discovery(safe_mode)` ガ偽ナラ即 return シ discovery task ノミヲ抑止ス。inbound registry/HTTP ハ不変(gate ヲ束ネザル方針)。standalone ハ `native_daemon ⊂ standalone` fail-fast ニヨリ spawn 点デ含意サレ明示 conjunct 不要。
- **seed 秘匿**: ed25519 seed ハ本増分デ触レズ。sweep ノ log ハ offline peer_id ノミ、bind 失敗 warn ハ io::Error ノミデ seed 由来値ヲ含マズ。
- **攻撃面不増**: 新規依存・route 登録・auth/chain.rs・recv/TOFU 経路ノ変更無シ。AF_INET 限定・SO_REUSEPORT 不使用。flag=false デ本番挙動不変。

## [4.529.0] - 2026-07-24

### Added

- **LAN Cowork native daemon B-d5d**: UDP discovery ノ HELLO 送信部 + heartbeat tick loop ヲ native_daemon gate 下ノ dead-code トシテ加フ。`send_hello_tick`(`build_hello_packet` ニテ署名済 HELLO ヲ組ミ seed カラ pubkey/x25519_pk ヲ導出シ、全 broadcast target ヘ `send_to` シ送信数ヲ返ス)、`broadcast_targets`(limited broadcast `255.255.255.255:19850` ノミ・per-interface directed broadcast ハ新規依存ヲ要ス故ニ不採用)、`hello_info_from_peer`(広告 7 フィールドノミ複写シ `pubkey`/`x25519_pk` ハ None デ seed 由来)、`load_identity_seed`(`lan_cowork_identity` カラ seed 読取)、`tick_loop`(local peer/seed 不在時ハ sleep+continue デ graceful degrade スル thin sleep-loop)、`HELLO_TICK_SECS=10` ヲ実装ス。spawn/lifecycle 配線(EADDRINUSE graceful ヲ含ム)ハ **B-d5e ヘ意図的ニ繰延ブ**。`generating`/`queue_depth` ハ HTTP-heartbeat フィールドニシテ UDP-HELLO ニハ載ラザル旨ヲ module doc ニ明記ス。依存追加ナシ。UDP socketpair デテスト可能(discovery テスト 19 件全通過)。flag=false デ本番挙動不変。

### Security

- **seed 秘匿**: `load_identity_seed` ハ seed ヲ **log セズ・返サズ・エラー/フォーマット文字列ニ含メザル** 旨ヲ doc ニ明記ス。送信失敗時ノ `tracing::warn!` ハ target アドレスノミヲ出シ、パケットバイト列ヤ seed ニハ触レズ。生 seed ハ wire ニ載ラズ(`build_hello_packet` 内デ pubkey/x25519_pk ヲ導出)、HELLO payload ハ広告 7 フィールドノミトス。

## [4.528.0] - 2026-07-24

### Added

- **LAN Cowork native daemon B-d5c**: UDP discovery recv-loop の受信専用部を native_daemon gate 下の dead-code として追加。`bind_discovery_socket`(port 19850・**AF_INET 専用**・SO_REUSEADDR before bind + SO_BROADCAST・非ブロッキング・0.0.0.0 bind)、`process_datagram`(parse→自己除外→api_port 範囲→replay→`handle_hello`)、`recv_loop`(recv_from ループ)、`ReplayGuard`、`unix_now` を実装。dual-stack V6 は ULA 到達性ゲートを壊す故に AF_INET を強制。spawn/lifecycle(EADDRINUSE graceful 含む)は **B-d5e へ意図的に繰延**。依存 `socket2 = "0.6"`(MIT OR Apache-2.0、tokio 経由で既に lock 済)を追加。UDP socketpair でテスト可能(discovery テスト 13 件全通過)。plan: `docs/superpowers/plans/2026-07-24-lan-cowork-daemon-b-d5c-udp-recv-loop.md`、rank1 GO。

### Security

- **SF-5(replay 防御)**: `ReplayGuard` が `(peer_id, timestamp)` を 60 秒窓で dedup し、窓を過ぎた記録は `retain` で剪定。同一パケットの再送を `handle_hello` 到達前に遮断。
- **SF-6(api_port 範囲検証)**: HELLO の `api_port` が `1..=65535` 外なら datagram を破棄。
- **自己除外**: `peer_id == local_peer_id` の HELLO を登録前に破棄(自パケット反射防止)。
- **TOFU 非バイパス**: recv-loop は verify/upsert を自前実装せず `handle_hello` の TOFU 経路へ委譲。検証済 host のみが registry へ保存される不変条件を維持。

## [4.527.0] - 2026-07-24

### Added

- **lan_cowork の自 identity(ed25519_seed)を standalone 起動時に生成・永続(Increment B-daemon / B-d5f)**: Rust には seed を生成する production コードが無く(全 INSERT が `#[cfg(test)]`)、fresh standalone ノードは自 identity を組めず seed 読取の全経路(pairing の `local_identity`・`local_peer_id`・`build_peer_registry` → B-d5b の全 inbound handler)が None/503 になっていた。`crates/yu-server/src/routes/peer_identity.rs` に `ensure_local_identity` を追加し、`main.rs` の既存 `if standalone` ブロック内(peers-family schema 適用直後)で 1 度だけ呼ぶ。Python `load_or_create_identity_from_con` に逐語準拠: read-first → 不在時のみ 32 byte を OS CSPRNG(`openssl::rand::rand_bytes`)で生成 → `INSERT OR IGNORE` → **re-fetch**(並行 writer の seed が先着で勝ち双方が同一 identity に収束) → 導出 sanity。**これは dead-code ではなく standalone で実際に identity を生成**し、今日壊れている standalone の pairing/discovery を修復して B-d5b inbound 全面を unblock する。hybrid(既定)は gate 外で Python が identity を単独所有し続けるため無変更。

### Security

- **長期秘密鍵の取扱い**: seed(ed25519 秘密鍵)は 32 byte 固定配列で OS CSPRNG から生成し、**log しない・返さない・エラー文字列に含めない**(破損時の error log も静的文言 + 復旧 SQL のみで鍵バイトを出さない)。書込は `INSERT OR IGNORE` 1 本のみで `UPDATE`/`DELETE`/`INSERT OR REPLACE` を一切持たず、`key TEXT PRIMARY KEY` と併せて**上書き経路が構造的に存在しない**(rotation は peer_id と両 pubkey を変え全 pairing を無効化するため)。失敗分類: 基盤障害(DB・CSPRNG・insert 後の行欠落)は起動時 fatal、seed 破損は復旧 SQL 付きの error log + 継続で LAN Cowork のみ degraded とし、自動再生成はしない。security-review + code-reviewer + rank1 の3独立レビューで確認(escalation なし)。

## [4.526.0] - 2026-07-23

### Added

- **lan_cowork heartbeat handler を活性化(Increment B-daemon / B-d5b/b-3、B-d5b inbound handler 系列の最終増分)**: `POST /ext/lan_cowork/api/peer/heartbeat`(Bearer+署名認証)を Rust へ移植。**既存 require_peer_auth を無改変で再利用**(heartbeat は nonce 非該当ゆえ Bearer+署名のみ・`uri.path()` の M4 完全 path・raw body 署名検証ゆえ parse 前に auth)。`peer_heartbeat` は slot 503→auth→`PeerHeartbeatRequest`(B-d3 dead-code 既存)parse→**M6 存在判定**→`update_runtime`→200。`chain.rs` に `/heartbeat` の exact-path bypass。`native_daemon=false` で route 未 merge(404)・slot 空(503)ゆえ**本番挙動ゼロ変更**。plan: `docs/superpowers/plans/2026-07-23-lan-cowork-daemon-b-d5b-b3-heartbeat.md`、rank1 GO(must-fix 0)。**これにより B-d5b inbound handler 系列(b-0→b-1→b-1b→b-2→b-4→b-5→b-6→b-3)が完結**(flag-day 前の残作業は identity bootstrap・UDP/tick/lifecycle・sweeper 等)。

### Security

- **M6(load-bearing な存在判定)**: Rust `update_runtime` は `()` を返し不在 peer を signal できない(silent no-op)。require_peer_auth は pubkey を **DB** から読む(U-B5-2)ため registry 不在 peer は auth を素通りする。ゆえに handler が auth 後・update_runtime 前に独立して `registry.get(peer_id)` で存在判定し不在なら 403 する — naive 移植が no-op peer に 200 を返す罠を回避し Python(`update_runtime→None`→403)と一致。認証済 peer_id のみを update_runtime に渡す(body/header 由来でなく peer 混同なし)。runtime telemetry は自 registry entry のみで危険 sink なし・秘匿値を log しない・署名は path 束縛で cross-route replay 不可。受容済 parity edge(U-B5-2): DB 在・registry 不在 peer の不正署名時のみ Rust 401 vs Python 403(敵対的・両者拒否)。security-review + code-reviewer + rank1 の3独立レビューで確認。

## [4.525.0] - 2026-07-23

### Added

- **lan_cowork pair_verify → registry hydration(Increment B-daemon / B-d5b/b-6、U-B5-2/M2 解)**: 既存 production の responder `pair_verify` handler の `tx.commit()` 直後に slot-gated な in-memory registry hydration を純加算。新規 pair 完了 peer を即座に `PeerRegistry` へ反映し、b-3 heartbeat の registry 存在判定(M6)を unblock する。`native_daemon=false`(slot 空)で完全 no-op ゆえ**本番挙動ゼロ変更**(既存 pairing テスト全 unchanged 通過で証明)。追加 DB read なし・commit 後 hydration error は非 fatal(log のみ)・panic-safe key 変換。plan: `docs/superpowers/plans/2026-07-23-lan-cowork-daemon-b-d5b-b6-pair-registry.md`。

### Fixed / Security

- **get-then-merge で既存 token/telemetry を保全(code-review 由来)**: `PeerRegistry::upsert` は token*/runtime を非 COALESCE で全置換ゆえ、既知 peer_id の再 pair・双方向 pairing で実 outbound token(`peers.token`、initiator flow 由来)を null 化し live telemetry を破壊し得た。sibling `handle_hole` 同様 `registry.get(peer_id)`→merge に修正: 既知 peer は **identity(api_host/api_port/pubkey/x25519)を refresh・liveness(status/last_seen)を live 接触として refresh・runtime telemetry と token* を preserve**。新規 peer は fresh default(token* None、plaintext token を registry に置かない)。field-refresh taxonomy を formalize。回帰テストで token/telemetry の survive と liveness refresh を pin。security-review + code-reviewer(2周)+ rank1 で確認。

## [4.524.0] - 2026-07-23

### Added

- **lan_cowork event handler を活性化(Increment B-daemon / B-d5b/b-5)**: `POST /ext/lan_cowork/api/peer/event`(Bearer+署名認証)を Rust へ移植。`lan_cowork_peer_api.rs` に `PeerEventRequest`(event_type/event_data[default `{}`・非 object は 400]/source_peer)・`RELAY_TYPES`(**7型**、decomposition の「8型」は誤り)・`event_type_allowed` を net-new 追加。`peer_event` handler は slot 503→**既存 `require_peer_auth` 再利用**(event は nonce 非該当ゆえ Bearer+署名のみ・raw body 署名検証ゆえ parse 前に auth)→空 event_type 400→非 object event_data 400→非 allowlist 403(M9)→**Option A**(event_type+認証済 peer_id のみ debug log・event_data は drop)→200。`chain.rs` に `/event` の exact-path bypass。`native_daemon=false` で route 未 merge(404)・slot 空(503)ゆえ**本番挙動ゼロ変更**。plan: `docs/superpowers/plans/2026-07-23-lan-cowork-daemon-b-d5b-b5-event.md`、rank1 GO(must-fix 0)。

### Security

- **M9 allowlist が durable な security 境界**: 7型(generation.submit/progress/complete/error/cancel・sync.file_changed・peer.status_update)厳密一致(case-fold/prefix なし)で非該当は 403。event_data は free-form JSON だが `.is_object()` 検査一箇所のみで sink ゼロ(log/実行/deserialize/SQL/SSE いずれにも渡らず drop)ゆえ悪意 payload は不活性。秘匿値(Bearer/署名/event_data)を一切 log しない。署名は uri path 束縛ゆえ他 route からの replay 不可。**local 伝播先の decide は Option A(Rust event bus 未実装・SSE は UI broadcast で意味論が異なり誤 surface risk ゆえ log+drop、local consumer は将来増分へ明示前送り)**。security-review + code-reviewer + rank1 の3独立レビューで確認(escalation なし=既存 require_peer_auth を無改変再利用)。

## [4.523.0] - 2026-07-23

### Added

- **lan_cowork token renew handler を活性化(Increment B-daemon / B-d5b/b-4)**: `POST /ext/lan_cowork/api/peer/token/renew`(署名+nonce 認証・**Bearer なし**)を Rust へ移植。`crates/yu-server/src/auth/peer_transport.rs` に net-new で `renew_if_not_revoked`(生 `BEGIN IMMEDIATE` 原子 tx で `revoked_at` 判定→失効なら拒否・未失効/未存在なら `source='renew'` の fresh token を upsert、`COMMIT` 失敗時も `ROLLBACK`)、`require_peer_renew_auth`(Bearer 不要・nonce 強制・unknown row→404・not-paired[pubkey NULL]→403、`&PeerNonceStore` 引数で D5 テスト seam)、`generate_raw_token`(openssl `rand_bytes(32)`→`URL_SAFE_NO_PAD` ≡ Python `secrets.token_urlsafe(32)`)を追加。scrypt `hash_token` は `spawn_blocking` offload。`lan_cowork_inbound_read.rs` の `peer_token_renew` は slot 503→auth→renew→`Ok(Some)`200`{token,expires_at}`/`Ok(None)`403/`Err`503。`chain.rs` に `/token/renew` の exact-path bypass。`native_daemon=false` で route 未 merge(404)・slot 空(503)ゆえ**本番挙動ゼロ変更**。plan: `docs/superpowers/plans/2026-07-23-lan-cowork-daemon-b-d5b-b4-token-renew.md`、rank1 GO-with-conditions(must-fix 1=not-paired 403 是正)。

### Security

- **M5(期限切れ peer の renew 権)**: renew は旧 token(Bearer)を要求せず ed25519 署名+nonce のみで認証する。これは意図的で安全 — 署名が鍵所持を証明し、`require_peer_auth` 流用だと期限切れ(但し未失効)peer が永久ロックアウトされる欠陥を回避する。token は 256bit CSPRNG・応答に 1 回だけ返し log しない(stored は scrypt hash のみ)。失効 token の再発行は `BEGIN IMMEDIATE` の RESERVED lock で並行 revoke を取りこぼさない。unknown→404 は Python 同等の登録状態 oracle(受容残余)。security-review + code-reviewer + rank1 の3独立レビューで確認。

## [4.522.0] - 2026-07-23

### Added

- **lan_cowork 未認証 register handler を活性化(Increment B-daemon / B-d5b/b-2)**: `POST /ext/lan_cowork/api/peer/register` を Rust へ移植。`crates/yu-server/src/routes/lan_cowork_peer_api.rs` に panic-safe な `peer_from_public_dict`(peer_id 必須・**base64** 鍵 `key32_from_b64`・配列の非文字列要素 skip、攻撃者影響下の /status 応答で一切 panic せず)を net-new 追加(test-only `key_from_hex` は hex+unwrap ゆえ不使用)。`lan_cowork_inbound_read.rs` の `peer_register` は CT 検査→`PeerRegisterRequest`→SSRF gate `validate_register_host`(B-d3・RFC1918v4+ULAv6 のみ・Python より厳格)→`build_peer_client`→`GET {base}/ext/lan_cowork/api/peer/status`→64KB cap read→パース→`api_host` を検証済 IP で上書き→M7 token 復元(`registry.get`→非 COALESCE upsert 前)→`to_public_dict`(token strip)応答。`chain.rs` に register の exact-path(`==`)bypass を追加、route は `inbound_routes(native_daemon)` gate 下。`native_daemon=false` で route 未 merge(404)・slot 空(503)・bypass は未 merge path 一致ゆえ**本番挙動ゼロ変更**。plan: `docs/superpowers/plans/2026-07-23-lan-cowork-daemon-b-d5b-b2-register.md`、rank1 GO-with-conditions(must-fix 1=base64 codec 是正)。

### Security

- **未認証 register の防御実装**: 攻撃者制御下の /status 応答パーサは panic-safe(remote-triggerable crash なし)。SSRF gate は outbound の前・IP literal のみ(DNS rebinding 無し)・`build_peer_client` で resolved IP を再検証しループバック/公開/メタデータへ steer 不能。既存 peer の token は M7 で保持され上書き不能、応答は token strip。registry の `PeerInfo.token` は inbound 認証情報ではない(inbound auth は別テーブル `peer_tokens` の scrypt 検証で register は書かない)ため self-registered token は認証を与えない。攻撃者が任意 peer_id の metadata を upsert し得る面は Python 同等の受容残余で B-d5d へ前送り。security-review + code-reviewer + rank1 の3独立レビューで確認。

## [4.521.0] - 2026-07-23

### Added

- **lan_cowork inbound read(discover/status)を条件配線で活性化(Increment B-daemon / B-d5b/b-1b)**: b-1 の dead-code handler を本番ルーティングへ接続。`crates/yu-server/src/routes/lan_cowork_inbound_read.rs` に `inbound_routes(native_daemon)`(flag gate: 空 `Router::new()` merge は matchit no-op)と `build_peer_registry(state, native_daemon)`(seed 無し/schema 無し/`load_all` Err で `None`→slot 空→503 の fail-safe、never unwrap、write pool で `load_all(now-604800, now-3600, now)` の M8 絶対 epoch cutoff)を追加。`crates/yu-server/src/auth/chain.rs` に discover/status の exact-path(`==`)bypass を pairing ブロック直後へ(session gate のみ解除、handler の `session_ok` が token 濃淡を再 gate ゆえ非認証 caller は public dict のみ=Python `auth_route(bypass_session=True)` と二段一致)。`main.rs` は `inbound_routes(native_daemon)` を merge し `shared` 構築後(standalone schema 適用後/`set_bound_port` 前)に registry slot を set。prune/offline 定数(`HARD_PRUNE_SEC`/`SOFT_PRUNE_SEC`/`OFFLINE_TIMEOUT_SEC=30`[Python default 準拠])を registry に追加。`native_daemon=false` で gate 空 router(404)・slot 空(503)・bypass は未 merge route に一致ゆえ**本番挙動ゼロ変更**。identity bootstrap(seed 生成、`manager_bootstrap.py` 相当)は Rust 未移植ゆえ fresh standalone は seed 無し→503(B-d5e/専用増分へ前送り、seed 無し→503 経路もテストで pin)。plan: `docs/superpowers/plans/2026-07-23-lan-cowork-daemon-b-d5b-b1b-wiring.md`、rank1: design-advisor GO-with-conditions(must-fix 0)。

### Security

- **discover/status の auth bypass は exact-path(`==`)厳守**: `/ext/lan_cowork/api/peer/discover`・`/status` のみ session gate を解除し、`/peer/tokens`・`/peer/admin/{id}`・operator ルートへ広がらない(退行防止テスト付き)。bypass 後も `session_ok` が token/session_id/roles の濃淡を再 gate し、pin_auth 有効時の非認証 caller は token-stripped public dict のみ受ける(新規露出なし)。security-review + code-reviewer + rank1 の3独立レビューで確認。

## [4.520.0] - 2026-07-22

### Added

- **lan_cowork inbound read(discover/status)の handler ロジックを Rust へ移植(Increment B-daemon / B-d5b/b-1)**: `crates/yu-server/src/routes/lan_cowork_inbound_read.rs`。自 peer identity 組立(seed→ed25519/x25519 導出 + local_descriptor)・discover/status async handler(session_ok で dict 濃淡・has_inbound_token preload・discover は list_all・registry 無しは 503)・`routes()`(**main.rs 未 merge**)・`PeerRegistry::local_peer_id()` getter。route 未登録・auth chain 未変更・registry 未構築の dead-code ゆえ本番挙動ゼロ変更(実配線は b-1b)。設計: `docs/superpowers/specs/2026-07-22-lan-cowork-daemon-b-d5b-decomposition.md`。

## [4.519.0] - 2026-07-22

### Fixed

- **standalone で LAN Cowork peer-family テーブルが作られない潜在バグを修正(Increment B-daemon / B-d5b/b-0)**: peers(13列)/peer_tokens(7列)/peer_pairing_requests(15列)/lan_cowork_identity を、Python(migration 59→83 で所有)不在の standalone デプロイでは Rust が作成するようにした(`crates/tagdb-core/src/migrations/086_lan_cowork_peer_family.sql` + `apply_lan_cowork_standalone_schema`、standalone 時のみ適用)。これまで standalone では pairing 等の DB アクセスが表不在で失敗していた。schema_sql_integrations.py と byte/列一致・idempotent(`CREATE TABLE IF NOT EXISTS`)。**hybrid では Python が schema_version を単独所有・migration するため Rust は触れない**(静的 MIGRATIONS 非登録、二重所有/version desync 回避)。B-d5b の registry/daemon の DB 前提を満たす land-first 分割。

## [4.518.0] - 2026-07-22

### Added

- **lan_cowork native daemon の起動フラグ + registry slot 足場(Increment B-daemon / B-d5a)**: `--native-daemon` CLI フラグ(既定 false、`env_truthy("YU_LAN_COWORK_NATIVE_DAEMON")` 併用)と、`native_daemon && !standalone` を拒否する起動時 coherence 検査(`native_daemon_startup_check`、純関数でユニットテスト)を追加。フラグは startup 配線でのみ用いる main.rs ローカルとし Config field 化しない(request 時の daemon 稼働信号は `AppState.peer_registry` slot の set/unset)。`AppState` に `peer_registry: OnceLock<Arc<PeerRegistry>>` slot を新設(既定空、registry 構築は B-d5b)。フラグ既定 false・slot 既定空ゆえ本番挙動は不変。分割: `docs/superpowers/specs/2026-07-22-lan-cowork-daemon-b-d5-decomposition.md`。

## [4.517.0] - 2026-07-22

### Added

- **lan_cowork UDP discovery TOFU を Rust へ移植(Increment B-daemon / B-d4)**: `crates/yu-server/src/routes/lan_cowork_discovery.rs` の `handle_hello`。受信 HELLO を検証し registry へ upsert する `_on_peer_found` 相当。route 未登録の dead-code(UDP socket recv-loop は B-d5)ゆえ本番挙動ゼロ変更。設計: spec §7 B-d4 / MF-11。

### Security

- **MF-11(TOFU 検証の非対称 + 強化)**: 既知 peer は **保存 pubkey** で `verify_hello`(packet 同梱鍵で検証せず成りすまし防御)、未知 peer は Python の無検証から逸脱し **同梱鍵での self-signature + ±60s timestamp を検証**して unsigned/replayed HELLO 汚染を防止。addr は B-d3 `validate_register_host` を再利用し link-local/cloud-metadata の planting を単一 gate で拒否(MF-11 literal の private/link-local 許可からの安全側逸脱、design-advisor B-d3 諮問 SF-3 反映)。

## [4.515.0] - 2026-07-22

### Added

- **lan_cowork inbound read handler ロジックを Rust へ移植(Increment B-daemon / B-d2)**: `crates/yu-server/src/routes/lan_cowork_peer_api.rs`。`PeerInfo` の `to_dict`/`to_public_dict` serialization(base64 STANDARD 鍵・None→null・float last_seen・public は token/session_id/roles 除外)、session 分岐込みの `serialize_peer`(has_inbound_token 注入)、`discover_response`(self 除外・per-peer has_inbound_token)、`status_response`(top-level pubkey/x25519_pk base64)を Python(`peer_api.py`/`models.py`)から byte/意味論厳密移植。DB(has_inbound_token)・session 判定・局所 peer 構築は呼出側(B-d5)の責務とし純関数化。route 未登録の dead-code ゆえ本番挙動ゼロ変更。設計: `docs/superpowers/specs/2026-07-21-lan-cowork-daemon-architecture.md` §7。
- **serialization parity を Python 生成 golden ベクタで固定**: `scripts/gen_peer_read_vectors.py` → `tests/vectors/peer_read_vectors.json`(to_dict/to_public_dict/serialize_peer/discover/status)。

## [4.514.0] - 2026-07-21

### Added

- **lan_cowork native PeerRegistry を Rust へ移植(Increment B-daemon / B-d1)**: `PeerRegistry`/`PeerInfo`(`crates/yu-server/src/routes/lan_cowork_registry.rs`)。upsert(ON CONFLICT+COALESCE、DB/memory 両側で鍵保持)・update_runtime・list_online・check_timeouts(30s)・load_all(hydrate + hard/soft dual-prune、self 除去)・remove・fleet 専用 update_telemetry を Python(`registry.py`/`peer_registry_service.py`)から byte/意味論厳密移植。内部 `std::sync::Mutex<Inner>` + `&self` + guard drop 後 sqlx 直発行で await を lock 越しに握らない。SharedState 非搭載の dead-code(B-d5 で配線)ゆえ本番挙動ゼロ変更。設計: `docs/superpowers/specs/2026-07-21-lan-cowork-daemon-architecture.md`。
- **DB parity を Python 生成 golden ベクタで固定**: `scripts/gen_registry_vectors.py` → `tests/vectors/registry_vectors.json`(upsert/load_all/remove/telemetry)。13列スキーマ・COALESCE 保持・created_at 不変・prune 述語境界を temp sqlite で照合。

## [4.513.0] - 2026-07-21

### Added

- **lan_cowork HELLO wire codec を Rust へ移植(Increment B-codec)**: `core/crypto_identity/hello_packet.py`(VERSION=2 HELLO パケットの build/parse/verify)を Rust 純関数 `crates/yu-server/src/auth/peer_hello.rs` として byte 厳密移植。discovery daemon(Increment B+D)の中で flag-day リスクを負わずに先行実装できる wire 層のみを切り出したもの。socket/daemon/registry/inbound handler/flag-day cutover は後続 B-daemon(スコープ外)。実装契約: `docs/superpowers/specs/2026-07-21-lan-cowork-hello-codec-design.md`。
- **byte 互換を Python 生成 golden ベクタで固定**: `scripts/gen_hello_packet_vectors.py` → `tests/vectors/hello_packet_vectors.json`(build 7 / verify 5 / reject 6 ケース)。非ASCII(U+007F・BMP・補助面 emoji)・control/quote/backslash・hostile packet ts(now±・u64::MAX)・意味的 reject(peer_id 不一致・低次数 x25519・非object/壊れ JSON・pubkey 欠落・base64 不正)を網羅。Ed25519 sign は `peer_transport::sign_canonical`、低次数点は `peer_pairing_crypto::is_low_order_x25519`、peer_id 束縛は `routes::peer_identity::derive_peer_id` を再利用(新規依存ゼロ)。

### Security

- **敵対的入力の堅牢性**: `parse_hello_packet` は全スライスを境界検査(`get()`)し `json_end`/`ts_end`/`sig_end` を `checked_add` で計算、攻撃者制御の u32 `json_len` でも panic せず `None`。`verify_hello` は `now.abs_diff(timestamp)` で未来/敵対的 timestamp の u64 underflow を回避(素の減算は debug で panic)。`ensure_ascii` 相当のカスタム Formatter で非 ASCII を `\uXXXX` 化し wire を Python とバイト一致させる。

## [4.512.0] - 2026-07-21

### Added

- **lan_cowork pairing Increment E3(initiator 2ルート)をRustへ移植**: `POST /ext/lan_cowork/api/client/pair/{request,verify}`。Rust standaloneノードが自機から他機へpairingを開始できるようになった(従来は「pairされる」ことしかできなかった)。新規`routes/lan_cowork_client.rs`(ハンドラ・nonce/予約枠state・pin付きoutboundクライアント)と`routes/lan_cowork_descriptor.rs`(到達可能アドレス述語・自機descriptor)。実装契約: `docs/superpowers/specs/2026-07-20-lan-cowork-pairing-e3-initiator-design.md`。
- **並行pairingの欠陥を是正**: nonceを`(peer_id, request_id)`キーの`[u8; 32]`とし、単一fieldのPython実装が複数peerへの並行pairingで先発を上書きしていた不具合を解消。
- **失敗状態の分類とUI提示**: 失敗応答に`state`(failed/unknown/retryable)・`code`・`attempts_remaining`を載せ、pairing modalが再pairing手順・残り試行回数を提示する(i18n 11言語)。verify不成立時に「responder側が完了しているかもしれない不明状態」と「確定的失敗」を区別し、410で詰まる不可逆状態への誤誘導を防ぐ。

### Security

- **outbound SSRF対策**: 宛先を private/非loopback/非link-local に限定(全DNS解決結果を検証しIPをpin、`redirect(none)`、scheme固定`http://`)。responderが返す`server_pubkey`の指紋を`derive_peer_id`で検証し、peer_idと不一致の鍵をpeersテーブルへ植えられないようにした。
- **認可の退行防止**: E3の2ルートは操作者向けsession保護ルートであり、`check_static_bypass`へ追加しない(追加すると未認証の権限昇格になる)。middlewareスタック経由の401を統合テストで固定。

### Notes

- 策定過程で**TODO.md L10の記述に権限昇格を招く誤りを発見し撤回**した(「E2と同じく`check_static_bypass`への追加が要る」)。
- **E3単体ではend-to-end検証ができない**(standaloneにdiscoveryが無く`peers`行の供給源が無いため)。新規peerへの能動的pairingのE2EはB+D完了後(BD-1)。単体・統合テスト計45件+ignore付き実測/timeout検証で担保。

## [4.511.0] - 2026-07-20

### Changed

- **推論クレートの参照先をpublicリポジトリへ切り替え、認証設定を撤去**: git依存をa private repository(private)から`eauesque/yu-hailo-infer`(public)へ向け直し、`crates/.cargo/config.toml`の`[net] git-fetch-with-cli = true`を削除した。**資格情報のない新規クローンやCIでもそのままビルドできる**ことを、当該設定を外した状態でのビルド成功により確認済み。
- **公開ミラーの更新方式を確立**: 初回取り込みのみ`git filter-branch`で内部ファイルを全履歴から除去し、**以降の更新はcherry-pickで積む**。毎回フィルタを掛け直すとSHAが変わりforce-pushが必要になる上、固定したrevも無効化されるため行わない。上流修正の取り込み手順(private修正→publicへcherry-pick→rev更新)を`HAILO_DEV_GUIDE.md`へ記載した。

### Notes

- **crates.io公開は当面見送る**(ユーザー判断)。GitHub公開が可逆であるのに対しcrates.ioはyankしても削除不可・版番号も名前も永久確定という非対称なリスクを負い、主成果物がHTTPサービスバイナリでライブラリとして依存される動機が薄く、対象もHailo-10H実機保有者に限られるため。publish手順自体は検証済み(前2クレートのdry-run通過、各クレートへのLICENSE同梱・メタデータ整備完了)で、実需が出た時点で3コマンドで実施できる。TODOに理由ごと記録した。
- 上流側の公開準備として、各クレートへLICENSE本文を同梱し(cargoはパッケージディレクトリ配下しか含めないため、従来は公開物にライセンス本文が入らなかった)、READMEの「Rust 1.88+(要確認)」という未検証のMSRV記述を「1.96.0で確認済み・MSRV未確定」へ改めた。MSRV確定はTODOへ登録。
- READMEに`hailort-sys`との関係を明記した(あちらはHailoRTのC API生バインディングでHailo-8/AI HAT+向け、本プロジェクトはHailo-10H向けサービス本体でC++ `InferModel` APIを独自シム経由で使用)。

## [4.510.0] - 2026-07-20

### Notes

- **hailo-infer分離が全フェーズ完了**: `eauesque/yu-hailo-infer`(public)として公開した。公開版は内部ファイル(`.claude/`・`.yu/`・`CLAUDE.md`・`TODO.md`・`docs/superpowers/`・`.github/`)を**全コミットから除去した履歴保持型のミラー**(13コミット)であり、除外規準は公開済み`eauesque/yu_ai_manager`の実例に合わせた(`.githooks/`と`docs/NAME_ORIGIN/`は公開側に含める)。公開前監査で、全履歴の秘密情報ゼロ・HailoRT SDK非同梱(システムヘッダ参照のみ)・MIT/GPL系依存ゼロを確認済み。
- **開発用と公開用でSHAが一致しない点に注意**: 本リポジトリのgit依存は引き続きa private repository(private)を指す。公開側は履歴を書き換えているため開発側のrevを参照できず、`git-fetch-with-cli`と認証設定は当面必要である。crates.io公開後に版指定へ置換し、認証設定ごと削除する予定(TODO登録済み)。
- 実機Hailo-10Hスモークテストはユーザーにより完了し、フェーズ2の残課題は解消した。

## [4.509.0] - 2026-07-20

### Changed

- **上流クレートの`yu-hailo-*`改名に追随**: a private repositoryはa private repositoryへ改名され、crates.io公開に向けクレート名も`auth-core`→`yu-hailo-auth`、`infer-core`→`yu-hailo-infer-core`、`yu-infer`→`yu-hailo-infer`へ改められた(crates.ioは名前空間がフラットかつ永久であるため、`auth-core`のような一般名の占有を避ける。また無印の`hailo-*`はHailo社公式と誤読される)。本リポジトリ側は`package = "..."`による依存リネームで従来のキー名を維持したため、**`infer_core::`・`yu_infer::`というソース中の参照およびshimのバイナリ名`yu-infer`は無変更**であり、`yu-server`のsidecar spawn契約も従来通り機能する。

### Notes

- 実機Hailo-10Hスモークテストはユーザーにより完了。フェーズ2の残課題は解消した。
- フェーズ3(公開)進行中。内部ファイル(`.claude/`・`.yu/`・`CLAUDE.md`・`TODO.md`・`docs/superpowers/`・`.github/`)を**全コミットから除去した履歴保持型のリリースブランチ**を構築済み(12コミット、除外パスの混入ゼロを検証)。除外規準は公開済みの`eauesque/yu_ai_manager`の実例に合わせ、`.githooks/`と`docs/NAME_ORIGIN/`は公開側に含める。

## [4.508.0] - 2026-07-20

### Changed

- **hailo-infer分離フェーズ2: `infer-core`・`yu-infer`をgit依存へ切替**: 両クレートをa private repository(private)からrev固定のgit依存として取得するようにし、yu_ai_manager側のソースを削除した。`[workspace.dependencies]`で**両者を同一revに固定**する(revが割れると`ort`/ONNX Runtimeが二重ビルドされ、feature unificationも壊れる)。`cuda`/`rocm`/`directml`/`coreml`/`openvino`のfeature転送は維持し、5種すべてが`ort`まで到達することをresolve graphで検証した(単一`image` 0.25.10・単一`ort` 2.0.0-rc.12に統一されることも確認)。
- **`crates/yu-infer`を`yu-infer-shim`へ置換**: `yu-server`はsidecarを`current_exe().parent().join("yu-infer")`で解決するため、バイナリが本workspaceのtarget dirから出る必要がある。cargoのgit依存は依存先のバイナリを生成しないため、上流の`yu-infer`を`[lib]`+バイナリshim構成へ分割し(hailo-infer側 `38e6997`)、yu_ai_manager側には`yu_infer::run()`を呼ぶだけのshimを残した。**`yu-server`のspawn経路と`scripts/hailo_realhw_smoke.py`は無変更**で通る。
- **sidecar起動失敗時のログを実態に合わせて修正**: 従来の「falling back to in-process inference」はWD-Taggerにしか当てはまらず、一様に安全へ劣化したと誤読させていた。実際にはWD-Taggerのみin-process ONNXへ降格して結果を返し続け、hailort proxyは503、hailo-genaiはPython backendへfallthrough、CLIP検索は`hailo_available=false`となる。この内訳を構造化ログとして明示する(可視化のみ。fail-fast化は行わない)。

### Added

- **private repo認証の手順を記録**: `crates/.cargo/config.toml`へ`[net] git-fetch-with-cli = true`を追加した(cargo内蔵のgitクライアントは`gh`のcredential helperを利用できない)。ビルドには当該repoへのread権限と`gh auth login`相当の設定が要る旨を`HAILO_DEV_GUIDE.md`へ記載。

### Notes

- **実機Hailo-10Hスモークテストは未実行**(実施環境に`/dev/h1x-0`が無いため)。Hailo-10H搭載機での`scripts/hailo_realhw_smoke.py`実行をTODOへ登録した。
- 設計判断はdesign-advisorのGO-with-conditions(must-fix 7件)に基づく: `.claude/agent-outputs/design-advisor/2026-07-18-hailo-infer-repo-extraction-phase2-rev1.md`。当初設計書の「git依存への切替はビルド設定の変更のみ」という記述は誤りであったため、設計書側も改訂した。

## [4.507.0] - 2026-07-20

### Removed

- **`crates/gateway-core`・`crates/gateway-server`(計2,918行)を削除**: 両クレートは Anthropic API プロキシゲートウェイ(上流 `ANTHROPIC_API_URL`、`~/.yu/gateway.sqlite`、集計・export・圧縮)であり、既に別リポジトリ `yu-gateway`(`yu-gateway-core`・`yu-gateway-server`、44,370行)へ独立して以降そちらで開発が継続している。yu_ai_manager 側に残っていたのは置き換え済みの旧実装で、`crates/Cargo.toml` の workspace member 登録以外に本体コードからの参照は存在しなかった(通信は HTTP 経由のみ)。`memory-core`/`memory-server` が v4.476.2 で同 repo へ移管された際に見送られていた後始末に相当する。経緯は `yu-gateway/docs/memory-server-origin.md`。

### Changed

- **リポジトリ分離ロードマップを実態へ同期**: `docs/development/development_docs/REPOSITORY_SPLIT_ROADMAP.md` に「分離済み」表(Anthropic APIプロキシgateway / memory-server / yu)を新設した。**削除した`crates/gateway-*`はロードマップが言う「LLM gateway」とは別物**である(前者は coding agent 向け開発者プロキシ、後者は `routes/gateway_*.py`+`routes/llm_*.py` のアプリ内バックエンド統合層)ため、混同を防ぐ注記を追加し、「LLM gateway」は未着手のまま先行分離に残した。分散推論と Hailo についても現在の移植進捗を追記。`RUST_SERVER_MIGRATION_PLAN.md` の関連ファイル表から削除済みクレートへの参照を除去し、`yu-gateway` 側を指すよう差し替えた。

## [4.506.0] - 2026-07-19

### Added

- **builtin_lan_cowork pairing の responder 側 5ルートを Rust ネイティブ化(Increment E2)**: `crates/yu-server/src/routes/lan_cowork_pairing.rs` を新設し、`POST /ext/lan_cowork/api/peer/pair/{request,approve,reject,verify}` と `GET .../pair/requests` を移植。**5ルートは原子的一括移植が必須**である(approve が生成する平文 PIN はプロセスメモリにのみ存在し DB には scrypt ハッシュしか無いため、approve と verify が別プロセスに分かれた瞬間に全 pairing が失敗する)。状態機械(pending→approved→completed / rejected / expired)、限界値(request 10回/分/IP・pending 同時3件/IP・verify 30回/分/IP・試行上限5・PIN TTL 300s・pending TTL 600s・削除 86400s)を Python と 1:1 で再現。`peer_id` が提示 pubkey の指紋(`sha256(pubkey)[:16]`)であることを強制し、x25519 は長さ + low-order deny-list で検証する。PIN は approve の応答で**認証済み運用者にのみ**返し、要求元 peer へは返さない。SSE `peer.pairing_request` / `peer.paired` を発火。

### Fixed

- **pairing ハンドシェイクが PIN 認証有効時に 401 で機能しない問題を解消**: `/pair/request` と `/pair/verify` は未ペアリング peer(セッションもトークンも持たない)が到達できねばならないが、グローバル `auth_middleware` がルータ全体を包むため `pin_auth_enabled=true` では両者が API 認証対象と判定され 401 になっていた。`auth/chain.rs::check_static_bypass` へ**厳密なフルパス一致**で 2 件を追加(Python の `auth_route(bypass_session=True)` 相当)。`approve`/`reject`/`requests` は session gate に残す。両者は無防備ではなく、request は IP 単位の rate limit と pending cap、verify は運用者承認 PIN + source_ip 束縛 + 5回で失効に守られる。
- **pairing verify の source_ip 束縛を復元**: request_id は SAS と共に LAN を流れるため、束縛が無いと第三者が別アドレスから検証を試みられた。誤 origin では試行カウンタも進めない。
- **pairing reject が完了済/期限切れの要求を上書きできた問題を修正**: `status IN ('pending','approved')` に限定(token 発行済の要求の監査証跡が壊れるのを防ぐ)。
- **pairing sweep が平文 PIN をメモリに残す問題を修正**: TTL 超過で失効した要求の平文 PIN が常駐し続け無制限に増えていた。sweep 対象を収集して破棄する。
- **同一 peer の再要求で pairing 行が累積する問題を修正**: 先行する pending/approved を失効させる(Python `_expire_prior_for_peer` 相当)。再試行が自分の残骸で pending 枠を塞がれなくなる。
- **pairing 完了時に「token は有効だが peer 未登録」となる窓を解消**: Python 版は token 発行と pairing status 更新を 1 トランザクションで commit した後、`peers` 行の書込を**別処理**で行うため、その間に届いた peer リクエストが `require_peer_auth` で `peers.pubkey` を見つけられず 403「peer not paired」になる窓があった。Rust 版は **peer_tokens 発行 / status='completed' / peers upsert の 3 つを単一トランザクション**に纏めて解消(wire 契約に影響なし)。設計: `docs/superpowers/specs/2026-07-19-lan-cowork-pairing-e2-responder-design.md`。

## [4.505.0] - 2026-07-19

### Added

- **builtin_lan_cowork pairing の暗号素体を Rust 実装(Increment E1)**: `crates/yu-server/src/auth/peer_pairing_crypto.rs` を新設し、X25519 seed 導出(HKDF-SHA256)・low-order point deny-list・PIN hash・PIN→AES 鍵導出・commit(96B/64B)・SAS(v2/legacy)・AES-256-GCM bundle の暗号化/復号/commit 検証を移植。**ルート・DB・状態機械は一切含まない純粋素体のみ**で、E の byte 互換リスクを先に潰す位置づけ。**新規依存ゼロ**を達成(HKDF は salt 空・L=HashLen ゆえ expand 1 ラウンドで既存 `hmac`+`sha2` により自作、X25519/AES-GCM は openssl、KDF は既存 `scrypt`。第二 crypto stack を避け security-boundary code の audit 面積を不変に保つ)。全出力を Python 実コード生成ベクタ(`tests/vectors/peer_pairing_vectors.json`、`scripts/gen_peer_pairing_vectors.py`)で byte 固定。**実測により scrypt が 3 用途で出力長を違えることを確定**(token hash 64B / PIN hash 64B / PIN→AES 鍵 32B。inventory は PIN hash を「64 hex」と 2 度目の誤記。均一と仮定すれば PIN 経路が破綻した)。**AES-GCM は Python が tag を暗号文へ連結し openssl は独立引数に取るため、固定 IV ベクタで暗号文+tag の byte 一致を assert**(復号一致より厳密に強い)。加えて実 `encrypt_pairing_bundle` 出力の復号も検証。deny-list は生成器が Python 定数から機械生成し集合一致を assert するため、片側変更で即座に test が落ちる。PIN KDF(n=2^17・128 MiB・~1秒)は `spawn_blocking` + `Semaphore(2)` の非同期経路を用意し、E2 が inline 呼出しないための forcing function とした。設計: `docs/superpowers/specs/2026-07-19-lan-cowork-pairing-e1-crypto-design.md`。

## [4.504.2] - 2026-07-19

### Fixed

- **X25519 low-order point deny-list の実効欠陥を修正(security hardening)**: `core/crypto_identity/hello_packet.py` の `_X25519_LOW_ORDER_POINTS` のうち 2 要素(`d9…`/`da…`)が末尾に余分な `7f` を持ち **33 バイト**になっていた。`probe_x25519_low_order` は 32 バイトに長さ検証済みの鍵に対する集合包含判定のため、これらは**決して一致しないデッドエントリ**であった。さらに `db`(2p+1)変種が丸ごと欠落しており、正準 12 点に対し**実効カバレッジは 9 点**だった。末尾 `7f` は直上の `p-1`/`p`/`p+1` 族からの誤複製と判断し、2p 族を正しい `d9`/`da`/`db` + `ff`×31 へ是正し `db` を追加(実効 12/12)。ECDH は pairing flow へ未統合(Phase 3+ stub)のため即時の実害は無いが、Rust 側 pairing 移植(Increment E1)が本定数を機械複製する前に是正した。全要素 32 バイトであること・2p 族が拒否されることを固定する回帰テストを追加。Increment E Phase 0 諮問(F-2)で検出。

## [4.504.1] - 2026-07-19

### Fixed

- **peer transport 認証の scrypt 検証が tokio ワーカーをブロックしていた問題を修正**: `auth/peer_transport.rs::require_peer_auth` が async 文脈から `hash_token`(scrypt n=2^14 = 16 MiB・数十 ms)を `spawn_blocking` なしで同期呼出しており、**認証を要する全 peer リクエストで非同期ランタイムを停滞**させていた。Python 側は `pair_api.py` で `asyncio.to_thread` へ offload しており非対称だった。トークン hash 比較を `tokio::task::spawn_blocking` へ移して解消。Increment E(pairing)の PIN KDF は n=2^17(128 MiB・~1秒)と桁違いのため、同モジュールの方針として先に是正した。Increment E Phase 0 諮問(`.claude/agent-outputs/design-advisor/2026-07-19-lan-cowork-pairing-incrementE-phase0.md` F-9)で検出。

## [4.504.0] - 2026-07-19

### Added

- **リポジトリ分離ロードマップを記録**: LLM gateway・分散推論・Hailoを先行分離する方針に加え、MCP server、Tauri desktop、外部Extension群の後続候補・前提条件・非推奨の即時分離対象を開発文書とTODOへ明記。

## [4.503.0] - 2026-07-19

### Added

- **ボスモード（目隠しログイン/ロック画面）のRustネイティブ移植**: `pin_boss_login_ui` 有効時、PIN認証ゲートと QuickLock 画面を、プレーンなPIN/ロック画面の代わりに WSJ 風クリーム紙面のカモフラージュ（偽の金融新聞）で描画する。Python版 `core/web/pages_boss_render.py` と WSJ スキン `core/web/boss_skins/wsj.py` の単一スキン移植（残り3スキン bloomberg/ft/nikkei は未移植）。edition ランダム化プール（見出し/記事/銘柄/セクション等）を `crates/yu-server/src/pages_boss.rs` へ移植し、RSS 実ヘッドライン取得は camouflage には不要のため省略。相場欄は `market_quotes` のキャッシュを非ブロッキング（`try_lock`・TTL 無視）で再利用しゲート描画を即時化。PIN モードは `/_pin_check` へのフォーム POST で no-JS でも動作、ロックモードはインライン JS で `/api/lock/unlock` を叩く。インライン `<script>` は `security::layer` の per-request CSP nonce（`strict-dynamic`）を付与して実行を担保。全補間値を `html_escape` でエスケープ。CSP ヘッダ nonce と `<script nonce>` 一致を検証する統合試験を追加。

## [4.502.0] - 2026-07-19

### Added

- **builtin_lan_cowork peer transport の outbound 署名を Rust 実装(discovery/transport Increment C)**: Python `make_signature_headers` / `make_nonce_header` 相当を `crates/yu-server/src/auth/peer_transport.rs` へ追加(`sign_canonical` / `make_signature_headers` / `make_nonce`)。Increment A の `build_canonical_message` を verify 側と**共有**し、署名側と検証側の canonical 構築が乖離し得ない構造とする(設計 SF-2)。**Ed25519 の決定性(RFC 8032)を利用し、Python 生成ベクタの署名を base64 まで含めてバイト単位で再現することを検証**(`sign_reproduces_python_vector_signature`)— outbound が既存 Python peer と wire 互換であることの最も強い証明。素体は openssl(新規依存なし)、nonce は uuid v4。本増分は primitive 追加のみで実運用 caller は無く(`#[allow(dead_code)]` 明示)、最初の consumer は Increment D(heartbeat)で入る。

## [4.501.0] - 2026-07-19

### Added

- **builtin_lan_cowork peer transport 認証の Rustネイティブ化(discovery/transport サブブロック Increment A)**: Python `require_peer_auth`(Ed25519 リクエスト署名 + nonce replay 保護 + scrypt Bearer トークン検証)を Rust へ移植(`crates/yu-server/src/auth/peer_transport.rs`)。Rust が唯一の HTTP front として DB 権威(`peers.pubkey` + `peer_tokens`)から検証するためモード非依存(hybrid/standalone 双方動作)。素体は openssl(Ed25519)、KDF は RustCrypto `scrypt`(新規依存、MIT/Apache)、hash 比較は openssl 定数時間 memcmp。canonical 署名文字列・scrypt パラメタ・nonce 分類は Python 実コード生成のテストベクタ(`tests/vectors/peer_transport_vectors.json`、`scripts/gen_peer_transport_vectors.py`)で byte 一致を pin。**inventory が誤記していた token hash 長を実測で是正(64 hex ではなく 128 hex = 64 bytes。誤れば peer 認証全滅)**。これを用いる最初の peer route として peer 自己削除 `DELETE /ext/lan_cowork/api/peer/{peer_id}` を追加(署名検証済 `X-Peer-Id` == path 強制で自分のみ削除可、削除本体は registry 増分のモード分岐ヘルパーを共有)。`discover`/`status` の実行時状態・pairing・discovery daemon(UDP :19850)は後続増分(C/E/B+D)。設計: `docs/superpowers/specs/2026-07-19-lan-cowork-transport-verify-incrementA-design.md`。

## [4.500.0] - 2026-07-19

### Added

- **builtin_lan_cowork「Peer基盤 registry」Rustネイティブ移植(増分1)**: session認可の peer 削除 `DELETE /ext/lan_cowork/api/peer/admin/{peer_id}` を Rust native化。Python版と異なり fleet allowlist 除去(config.json)を peers 行/registry 退避より**先に永続化**し、部分失敗時に「削除済だが権限残置」窓を作らないよう是正。standalone は Rust が直接 `peers` 行を DELETE、hybrid は `/_internal/lan_cowork/registry-peer-changed`(action=`removed`)経由で Python `registry.remove` へ委譲し discovery daemon による行復活を回避、evict 不達時のみ 502。自己削除は共有化した `local_peer_id`(`sha256(ed25519_pubkey)[:16]`、Python `derive_peer_id` とバイト一致)で拒否、identity 不在時は削除許可、不在 peer は冪等 200。加えて token revoke 後に同 notify(action=`token_cleared`)で in-memory registry の token 鮮度を fire-and-forget 同期(DB 権威は既に有効なため失敗しても revoke は成功)。`discover`/`status` の実行時状態読み取りと peer 自己削除は discovery/heartbeat・transport-crypto の native化を前提とするため先送り。設計: `docs/superpowers/specs/2026-07-19-lan-cowork-registry-native-increment1-design.md`。

## [4.499.1] - 2026-07-19

### Fixed

- **comfyui-bridge 設定保存が`default_scheduler must not be empty`で失敗する不具合を修正**: `loadConfig()`が保存済みの`default_scheduler`/`default_sampler`を`<select>`へ代入する際、その値が現在の選択肢一覧に無い場合(ComfyUIオフラインでライブ一覧を取得できない、または静的fallback一覧に無いscheduler/sampler)、ブラウザ仕様でselectが暗黙に空文字へリセットされ、保存時に空値が送られてバックエンドの必須チェックで弾かれていた。`_script_loaders.html`が既に持つ「一覧外の値はoptionを注入して保持」する挙動を`loadConfig()`にも適用し、設定値が常にround-tripするよう修正(`cfbEnsureOption`)。

## [4.499.0] - 2026-07-19

### Added

- **WD-Tagger standalone retag and opt-in import auto-tagging**: `retag/single` now runs native inference for compatible image profiles, preserving Python fallback only when native processing is unavailable. Retag writes support non-overwriting inserts, atomic active-model updates, and stats-cache invalidation. Bridge imports can opt into `extensions.builtin-wd-tagger.auto_tag_on_import`; work is bounded and duplicate file requests are suppressed. Enabling it may embed XMP metadata into imported images.

## [4.498.0] - 2026-07-19

### Added

- **WD-Tagger XMP native writeにJPEG/WebP対応を追加**: 新設`xmp-core`クレート(namespace registry + PNG/JPEG/WebP embedded-XMP read/write + 単一merge API)を導入し、従来PNG限定だった`write_wd_xmp_to_png`を`write_wd_xmp`として全形式対応に統合。WebPはsimple→extended自動昇格・VP8/VP8L寸法抽出・alpha伝播・アニメーション検出を含む。`tag_file`のXMP書込ゲートをPNG限定から`png/jpg/jpeg/webp`へ拡張。既存のsweep用PNG専用XMP経路(`sweep_common.rs`)・yu-infer nativeルーティングは変更なし(別途進行中の未マージbranchに存在するyu-serverモジュール化・auto-tag-on-import等とは独立)。

## [4.497.0] - 2026-07-18

### Added

- **hailo-infer分離フェーズ0: YOLO後処理をinfer-core/yu-inferへ移植**: `crates/yu-server/src/routes/hailo_yolo_postprocess.rs`の量子化解除・グリッド/ストライド相対デコード・HEF内蔵NMS出力パース・NMS等の純粋アルゴリズムを`infer-core`(`yolo_postprocess.rs`/`yolo_labels.rs`)へ移設。`yu-infer`の`POST /v1/infer/yolo/detect`は移植後ロジックを内部で呼び出し、生の量子化テンソルではなく最終検出結果(`{detections:[...]}`)を直接返すよう変更。`yu-server`側はDB永続化(`write_detections`)・ジョブ管理のみを残し、重複コードを解消。アルゴリズムは一切変更せず、既存回帰テストに加え移植前後の数値一致を検証する移行整合性テストを追加。標準リポジトリ分離計画(`docs/superpowers/specs/2026-07-18-hailo-infer-repo-extraction-design.md`)のフェーズ0のみを対象とし、新規リポジトリ作成・push・依存切替(フェーズ1以降)は本変更に含まない。

## [4.496.3] - 2026-07-18
### Fixed
- **Python ProxyFixのloopback XFF偽装によるtrusted-peer認証bypassを修正**: 信頼済み外部プロキシが`X-Forwarded-For: 127.0.0.1`または`::1`を転送した場合、外部TCP peerをloopbackとして採用せず元のpeer IPへ戻すよう変更。右端の非信頼候補と全hop信頼済み時の左端候補の双方を保護し、`/ext/<name>/v1/*`がロック中に`trusted_peer_loopback`として無認証通過する経路を遮断。正規の外部client IP転送とローカル自己リクエストは従来どおり維持する。

## [4.496.2] - 2026-07-18
### Fixed
- **WindowsでのCLIP usearch再構築失敗を防止**: mmap中の固定`index.usearch`/`ids.bin`を置換する方式を、世代付き不変ファイルと`current.json`ポインタへ変更。新世代の保存完了後にポインタだけをatomic renameし、旧世代の削除は切替後・起動時にベストエフォートで行うため、Windowsの共有違反で再構築やclearが失敗しない。複数回再構築時の世代切替と旧ファイル掃除を回帰テストで確認。

## [4.496.1] - 2026-07-18

### Fixed

- **Hailo semantic search のusearchインデックス常駐メモリを削減**: 検索用の永続インデックスを`Index::restore`によるフルRAMロードから`Index::restore_view`による読み取り専用mmapへ切り替えた。再構築後も保存したファイルをmmapで開き直してからアクティブ化し、旧インデックスをmmapで検索継続できるため、再構築ピークを旧mmapビュー＋新規フルRAMインデックス1個分に抑える。保存後のmmap再ロードでも検索できる回帰テストを追加。

---

## v4.496.0 (2026-07-18)

### Added

- Hailo semantic search Rustネイティブ移植 Phase 3A/3B を追加。`/ext/hailo-semantic/api/{search,runtime,status,backends,index/*,model/*}` を `yu-infer` CLIP sidecar・カーソル型`vectors.db`書込・永続usearch indexへ接続した。全routeにadmin scopeを適用し、画像indexingはscan_roots外をfail-closedで拒否、動画キーフレームを除外、数値入力を範囲検証する。テキストモデルdownloadは固定HTTPS・サイズ上限・SHA-256監査ログ・一時ファイル+atomic rename・プロセス内排他を用いる。caption routeは意図的にPython forwardのままとする。

---

## v4.495.0 (2026-07-18)

### Added

- Hailo semantic search のRustネイティブ移植 Phase 1A/1B/1C を追加。`yu-infer` にBearer認証付きCLIP画像・テキストembedding APIを実装した。画像側は既存の汎用HailoRT HEF shimを再利用し、VLMと同等の画像入力上限でJPEG/PNG/WebPをdecode+resize、HEF量子化情報を用いてuint8出力をdequantizeして512次元L2正規化ベクトルを返す。テキスト側はCPU ONNX RuntimeとApache-2.0の`tokenizers` BPEを用い、CLIPの77 token契約とモデル別lazy cacheを実装。Phase 2以降のvector storage/searchは別タスクとして残す。

- Hailo semantic search のRustネイティブ移植 Phase 2A/2B を追加。`yu-server` にtags.dbと同じSQLCipher鍵・WAL・busy timeout規約で同居する`vectors.db`のread/write poolを追加し、float16 BLOB CRUDとカーソル限定のusearch構築を実装した。Apache-2.0のusearch永続化はPython FAISSと別領域に置き、行数と`MAX(created_at)`でdriftを検出し、再構築成功後にメモリ上の検索indexをatomically差し替える。

---

## v4.493.3 (2026-07-18)

### Added

- ローカルモデルのコードレビュー前に過去の却下台帳を必読とし、同じ指摘の再掲を抑止する手順を追加。却下済み finding は path・claim・実行経路で照合し、再検討条件と新証拠がある場合のみ再掲する。既存 triage と今回の精査結果12件を `docs/development/review/rejected-findings.yaml` へ収録。

---

## v4.493.2 (2026-07-18)

### Fixed

- ローカル画像解析モデルが説明用 JSON の後に実際の JSON 応答を返した場合、複数オブジェクトを外側から一括抽出して解析失敗していた問題を修正。完全な JSON 候補を列挙し、画像解析・傾向分析それぞれの期待キーを持つ応答を選択する。

---

## v4.477.2 (2026-07-10)

### Fixed

- **Dedup（重複タグ削除）が全ブリッジ・全プロンプト欄で常に「dedup: error」になり一度も動作していなかった**: 共通モジュール `src/ts/bridge/dedup.ts` が `/api/tags/dedup` のレスポンスを `json.data?.string` として読んでいたが、実際のレスポンス（`api_result()`）は `data` を `null` のまま payload をトップレベルへ展開する形式のため、常に `null` が返り無条件でエラー扱いになっていた。`json.string` を直接読むよう修正し、Positive/Negative/キャラクタープロンプトいずれの Dedup も正しく動作するようにした。
- **NAI Bridge のキャラクタープロンプトカードに Dedup ボタンがなかった**: 既存の Sed ボタン/バーと対になる Dedup ボタン/バーを各キャラクターカードへ追加（フォーカス中のポジティブ/ネガティブ欄いずれにも適用）。
- **SD WebUI Bridge / ComfyUI Bridge の Sed・Dedup がネガティブプロンプトにフォーカスしていても常にポジティブプロンプトへ適用されていた**: NAI Bridge 同様、フォーカス中のテキストエリアを追跡する `_sdwbActiveGetSet` / `_cfbActiveGetSet` を導入し、Sed・Dedup がアクティブなプロンプト欄（ポジティブ/ネガティブ）へ正しく適用されるよう修正。
- 上記回帰を検知する単体テスト `tests/ts/bridge/dedup.test.ts` を追加（旧実装で red になることを確認済み）。

---

## v4.477.1 (2026-07-10)

### Fixed

- **NAI Bridge / SD WebUI Bridge の Vibe Transfer・img2img・Inpainting ドロップゾーンがクリックで反応しない**: `nabClickVibeFile` / `nabClickImg2ImgFile` / `nabClickInpaintFile` / `sdwbClickImg2ImgFile` が `data-action` から参照されているにもかかわらず定義されておらず、クリックしても隠しファイル入力が開かなかった（ドラッグ&ドロップのみ機能していた）。加えて、イベント委譲（`data-action-this="1"`）は各 `nabSet*File` ハンドラへ `<input>` 要素自身を渡すが、各ハンドラは `File` オブジェクトを前提としていたため、クリック経由でファイルを選んでも `file.type.startsWith("image/")` が偽になり画像が読み込まれない二重の不具合だった。イベント委譲（`event-delegation.ts`）は未定義関数の参照や早期returnを静かに無視するため、コンソールエラーも出ず気付きにくかった。各セクションのスクリプトに `input.click()` を呼ぶハンドラを追加し、各 `nabSet*File`/`sdwbSetImg2ImgFile` の先頭で要素から `File` を取り出す正規化を追加して修正。

---

## v4.477.0 (2026-07-10)

### Added

- **NAI Bridge Vibe Transfer ダウンロード機能**: エンコード済み Vibe（Vibe Transfer 単一スロット＋精密参照最大4件）を `.naiv4vibe`（1件）または `.naiv4vibeBundle`（2件以上）としてダウンロードできるボタンを Vibe Transfer / Reference Images 両セクションに追加。既にアップロード機能はあったがダウンロードがなく、Anlas を消費して一度エンコードした Vibe を後日再利用できなかった問題を解消。ダウンロードしたファイルは同じアップロード欄に再投入すれば `nai_vibe_cache` のキャッシュヒットにより Anlas 消費なしで同一エンコードを再利用できる。`nai_vibe_file.build_naiv4vibe()` / `build_naiv4vibebundle()` / `POST /api/vibe/download`

---

## v4.470.7 (2026-07-03)

### Fixed

- **rust-migration TODO実態乖離の是正（L25/L27/L132/L134/L136/L138）**: `arch-constraints.yaml` の `server_mode.python_forwarder` 記述を `call_python_bridge` 削除済み・`dispatch.rs` 置換済みの実態に更新（`agent_session_scopes` スコープ強制は未実装のまま明記）。L25「WD-tagger推論のauto_import統合」は `bridge_import.py`/`scan_core` 全文調査の結果、移植元となる正実装が存在しないためrust-migration完結の判定対象から除外し、新規feat提案として整理。L132/134/136/138のスタンドアロン除外スコープ4件について独立仕様書 `RUST_MIGRATION_STANDALONE_EXCLUSION_SCOPE_DESIGN.md` を新設し、特にL136「WD-Tagger/ONNX推論」は `crates/infer-core`（`ort` crate）+ `crates/yu-infer`（`/v1/infer/wd`）で既にRustネイティブ実装・稼働済みであることが判明したため、旧「onnxruntime Pythonバインディング依存のため対象外」という記述を誤りと訂正しGO判定へ変更。

---

## v4.470.6 (2026-07-03)

### Fixed

- **tagdb-core prompt parser parity**: `tests/compat_goldens/prompt_parse/` に Python 正実装生成の合成 golden fixture 18件を追加し、BUG-33〜67 の代表ヒューリスティクスを Rust conformance harness で実検証するようにした。`cargo test -p tagdb-core --test prompt_parse_conformance` PASS 確認後、`CURRENT_PARSER_VERSION` を Python 版と同じ 6 に昇格。

---

## v4.469.2 (2026-07-02)

### Fixed

- **parity harness: Pythonサーバーstdout/stderrパイプデッドロック**: `scripts/parity_harness.py` の `_start_python_server` が子プロセスのstdout/stderrを `subprocess.PIPE` に割り当てながら一度も読み取っていなかった。Hypercornのアクセスログが約64KBのOSパイプバッファを埋めると、子プロセスの `write()` が永久にブロックし、常に一定の位置でハーネス全体が固まっていた。`pre_push_check.py` の rust↔python native route parity チェックが `/api/maintenance/db-stats` 付近で一貫して `httpx.ReadTimeout` を起こしていた根本原因。ログファイルへのリダイレクトに変更（既存のRustサーバー側パターンに合わせた）。修正後、単体再現テストで242 PASS / 0 FAIL / 0 ERROR。

---

## v4.469.1 (2026-07-02)

### Fixed

- **yu-server graceful shutdown が SIGTERM に対応**: Axum graceful shutdown が `tokio::select!` で SIGINT / SIGTERM のどちらも待つようになり、systemd や process manager からの終了でも Ctrl-C と同じ `yu-infer` 子プロセス cleanup path を実行するよう修正。

---

## v4.468.0 (2026-07-02)

Added

- **yu-infer WD 推論エンドポイント**: 認証付き `POST /v1/infer/wd` を追加。scan_root 包含検査、危険な `model_id` 拒否、モデルDL済み確認、`WdInferEngine` 実行に対応。起動時 stdin contract の auth/roots と `--wd-cache-dir` を router state に渡すよう更新。

---

# Changelog (ja)

Tag Database の主要変更を記録します。

> 旧月のエントリは docs/development/archives/changelog-ja-YYYY-MM.md に格納済み。

## v4.460.17 (2026-06-30)
### Fixed
- **Hailo ツール可用性判定**: Mac/Windows/WSL で ONNX（または CoreML）バックエンドが使えるとき、セマンティック検索・YOLO 物体検出が `available=true` を返すよう修正。チェック項目を `onnx_ok` / `hailo_npu` に変更し、ONNX フォールバック動作中の reason テキストを赤ではなく中立色で表示。

---

## v4.460.16 (2026-06-30)
### Fixed
- **bridge Rust wildcards**: Rust native ComfyUI / SD WebUI / NAI bridge の `expand_wildcards` で prompt simulator の filesystem `wildcard_dirs` を読み、`client_wildcards` を上書きマージして prompt / negative prompt を backend 送信前に展開するよう修正。filesystem wildcard 読み込みと client override 優先順位の Rust unit test を追加。

---

## v4.460.13 (2026-06-30)
### Fixed
- **bridge Rust parity**: Rust native ComfyUI / SD WebUI / NAI generate response に Python 互換の prompt/save metadata を追加し、生成画像下の prompt accordion 表示に必要な項目を返すよう修正。yu-server build 用に DirectML + dynamic ONNX Runtime load を暫定有効化。

---

## v4.458.0 (2026-06-28)

### Added

- **feat(rust): OCR Phase 1 — CRUD/IO ハンドラ実装**
  - `GET /api/ocr/engines` — admin scope gate 追加（旧スタブは無認証）
  - `GET /api/ocr/result/{file_id}` — admin scope + 3+1 分岐 DB クエリ（task/engine 指定・最新・全件）
  - `DELETE /api/ocr/result/{file_id}` — 無認証・2 段階削除（file_translations 先削除→file_ocr_results 削除）・0 件でも 200
  - `GET /api/ocr/translations/{file_id}` — admin scope + file_id 全 OCR 結果 JOIN クエリ（ocr_engine alias で列衝突回避）
  - parity エントリを Phase 1 対応値（501→200）に更新

## v4.457.0 (2026-06-28)

### Added

- **feat(rust): 501 スタブ群を Rust ネイティブ実装に置換**
  - `profiles` CRUD 11 エンドポイント — ファイルシステム JSON 読み書き（atomic write / sensitive field strip / name validation）
  - `scan_queue_list/clear/remove` — standalone モード向け空レスポンス
  - `scanned_roots_purge` — SQLite UPDATE + DELETE でパス LIKE 両スラッシュ対応
  - `llm_router_refresh/disable/enable` — standalone 向け OK レスポンス
  - `infer-core`: ONNX multi-EP 対応 — `--features cuda/rocm` で GPU EP 自動選択、未搭載時は CPU fallback

## v4.370.0 (2026-06-17)

### Added

- **yu-server Group L share+config Rust native 化** — `GET /api/share/{file_id}` （A1111 full parse・NAI V4 negative 再構築・SQLite 2 クエリ）と `GET /api/settings/config`（DEFAULT_CONFIG merge + _apply_redactions 相当）を Rust native 化。inventory 更新（Group J の /api/search・/api/search-count ステータス修正を含む）。

## v4.363.0 (2026-06-16)

### Added

- **yu-server Group D suggest endpoints** — `/api/suggest`・`/api/suggest/lora`・`/api/suggest/embedding`・`/api/tags/suggest` を Rust native 化。SQLite read と regex 抽出のみで実装し、admin scope、LIKE escape、重複除去、case-insensitive sort、Phase 3 parity inputs、migration inventory を更新。

## v4.331.0 (2026-06-13)

### Added

- **parity gate Phase 3** — POST / パラメータ付き route parity 用 inputs、共有 seed DB helper、入力変数解決、inventory allowlist 同期検査、harness/generator 結線、pre-push 登録、CI egress blocking を追加。

## v4.306.0 (2026-06-10)

### Added

- **ai_coreutils MCP 文脈ツール拡張** — `context_router` / `read_plan` / `safe_cat` / `diff` / `failure` / `known_failure_match` / `test_impact` / `minimal_test` / `budget_check` / `budget_explain` / `pack` / `review` を MCP に追加。`safe_cat` は repo-root 制約を維持しつつ MCP 既定を `1:200` range・8000 byte 上限に丸め、`pack` / `context_router` / `budget` 系には MCP 用の上限を設けた。`safe_cat` 抜粋と `failure` ログ代表行は共通 redaction を通し、`known_failure_match` は read-only match のみ公開して登録系は公開しない。

## v4.283.0 (2026-06-08)

### Added

- **ai_coreutils i18n 支援** — `i18n map|check|coverage|pack --target <lang> --missing` を追加。JSON locale の missing/stale/placeholder 検査、Markdown 対訳ファイルの浅い構造警告、言語別 coverage、欠落 key のみを含む AI 翻訳投入 pack を出力できるようにした。

## v4.282.0 (2026-06-08)

### Added

- **ai_coreutils 残バックログ完了** — `docs map|brief|drift|update-plan|acceptance|changelog` を追加し、docs 向け入口を統一。`db --backend postgres|mysql --url-env ... --connect` と `db redact-sample` の安全ガード、`workflow run --execute` / `verify --run` の controlled execution contract、`release-check --project`、`bench --auto`、`clean --apply` を追加した。

## v4.281.0 (2026-06-08)

### Added

- **ai_coreutils DB diagnostics** — `db discover|summary|schema|migrations|locks|integrity|query-plan` を追加。SQLite/DuckDB file は repo containment を強制し、table/schema/migration/sidecar/integrity/query-plan を row dump なしで要約する。PostgreSQL/MySQL など接続系は discover で redacted candidate として扱い、credential と row value は出力しない。

## v4.280.1 (2026-06-08)

### Security

- **ai_coreutils AI 出力境界の強化** — `safe-cat` / `schema-check` の repo 外 path 読取を拒否し、`env-diff --baseline` の state 書込を `tmp/ai-coreutils/` 配下へ限定。`todo-scan` / `route-map` の AI 向け出力に共通 redaction を通し、token / secret / password / API key / Authorization / DB DSN の値をマスクするようにした。

### Fixed

- **ai_coreutils lockfile-summary changed 判定修正** — 存在する lockfile を常に changed 扱いしていた問題を修正し、git status/diff に現れる lockfile のみ要約対象にした。追加/削除/version bump の概算も diff 由来に変更。

## v4.280.0 (2026-06-08)

### Added

- **ai_coreutils environment/drift diagnostics** — `env-diff`、`path-fix`、`lockfile-summary`、`generated-check`、`schema-check`、`route-map`、`todo-scan`、`drift` を追加。環境差分、PATH 解決、lockfile 本文省略、generated file 直接編集疑い、schema 軽量検査、CLI/API entrypoint map、TODO risk、help/spec/test drift を 1 コマンドで要約する。

## v4.279.0 (2026-06-08)

### Added

- **ai_coreutils diagnostics closure** — `deps`、`ports`、`health`、`conflicts`、`branch`、`flake`、`artifacts`、`explain-run` を追加。依存変更、port/service health、merge conflict、branch hygiene、flaky test plan、AI作業成果物、直近 run 説明を 1 コマンドで要約し、raw process table / lockfile / log body の直接投入を避ける。

## v4.278.0 (2026-06-08)

### Added

- **ai_coreutils workflow/bench/policy closure** — `workflow list|show|run`、`bench`、`clean`、`export-openai`、`policy lint` を追加。定型 workflow の実行計画、削減率の単発測定表示、stale artifact cleanup 候補、OpenAI/Codex 向け説明資料、policy/config/help/spec drift 検査を 1 コマンド化した。

## v4.277.0 (2026-06-08)

### Added

- **ai_coreutils init/config bootstrap** — `init` と `config show|doctor|sync` を追加。repo shape から `ai-coreutils.toml` / `.aiignore` の初期案を dry-run 既定で生成し、`--write` 時のみ作成する。設定 path の存在検査、`AGENTS.md` / `CLAUDE.md` の byte 同期検査、検出結果との差分候補、`scripts/pre_push_check.py` / docs sync 系 script の Rust 化候補 advisory も出力する。

## v4.276.0 (2026-06-08)

### Added

- **gateway-server compress 統合・error_kind 拡張** — `proxy.rs` の `handle_messages` に `gateway_core::compress_analyze` を組み込み、`raw_tokens_estimated`/`submitted_tokens_estimated`/`proxy_removed_tokens` を `insert_usage_event` へ実値で渡すようにした。`extract_model_and_usage` を 3-tuple（`has_error_field`）に拡張し、`parse_error`/`provider_error_json` を `api_error` と区別できるようにした。`ProxyState` に `diag_dir` フィールドを追加し `dispatch_diagnostic` fire-and-forget ヘルパを実装。
- **gateway-server `--diag-dir` と `doctor` subcommand** — CLI に `GATEWAY_DIAG_DIR` 環境変数対応の `--diag-dir` オプションを追加（未指定時は `export_dir/diagnostics` にフォールバック）。`gateway-server doctor [--json]` subcommand で API キー・DB・upstream TCP・export_dir・diag_dir の 5 項目をヘルスチェックし、`[PASS]/[FAIL]` または JSON 形式で結果を出力する。

## v4.275.0 (2026-06-08)

### Added

- **ai_coreutils standard workflow gates** — `docs-sync` / `contract-check` / `risk` / `pr-ready` / `regression` / `sweep` / `stale` / `checkpoint` / `resume` / `smoke` を追加。文書同期漏れ、CLI/help/schema 不一致、危険変更、PR前確認、回帰調査、作業場棚卸し、古い一時物、中断復帰、最小受入確認を機械化した。

## v4.274.0 (2026-06-08)

### Added

- **ai_coreutils workflow combinators** — `investigate` / `verify` / `handoff` / `impact` / `safe-cat` / `next` / `fix-cycle` / `find-owner` を追加。調査初動、日常検証計画、作業結果報告、影響範囲推定、AI-safe file excerpt、次手推薦、失敗修正ループ、topic/doc map を 1 コマンド化し、`aihelp` catalog と workflow にも反映。

## v4.273.0 (2026-06-08)

### Added

- **ai_coreutils AI-readable help** — `aihelp` サブコマンドと `--aihelp` alias を追加。`ai-coreutils --help` / subcommand `--help` から JSON schema へ誘導し、`aihelp command <name>` と `aihelp workflow coding|review|debug|release` で command safety・exit code・examples・workflow steps を機械可読に取得できるようにした。

## v4.272.0 (2026-06-08)

### Added

- **ai_coreutils coding-agent shortcuts** — `brief` / `changed-context` / `latest` / `failure` / `review` / `session` / `touched` / `apply-plan` / `prompt-cache` / `why-read` / `denylist check` を追加。初回投入、hunk 周辺抽出、失敗調査、AIレビュー、作業単位記録、実装計画、定型 prompt、安全 denylist 確認を 1 コマンド化した。`pack` / `brief` には `--explain-budget` を追加。

## v4.271.0 (2026-06-08)

### Added

- **ai_coreutils operational follow-ups** — `doctor`（gps + tools check + guard の軽量統合）、`postflight`（strict guard + digest summary）、`metrics append|report`（raw tokens と ai_coreutils 後 tokens の削減率記録）を追加。README と仕様書に実運用順序と削減率計測の導線を追記。

## v4.270.0 (2026-06-08)

### Added

- **ai_coreutils final phase** — `tools summarize semgrep|repomix` を追加し、既存ツールの raw output を AI 向けに要約・省略する経路を実装。`todo done --apply` と `changelog rollover --apply` は dry-run 既定のまま実変更処理に対応し、`release-check --run` は controlled output で `guard` / `tools check` / `cargo fmt --check` / `cargo test -p ai_coreutils` / `cargo clippy -p ai_coreutils` / `scripts/pre_push_check.py` を実行するようにした。`docs/development/specs/ai-coreutils-spec.md` に仕様を固定。
- **pnpm workspace manifest** — corepack pnpm 10 系で `pnpm-workspace.yaml` が `packages` 欠落により起動拒否されるため、root package を明示して pre-push の `tsc --noEmit` を通せるようにした。

## v4.269.0 (2026-06-08)

### Added

- **ai_coreutils polish phase** — `diff` に unified diff hunk 由来の `read_range` 抽出を追加。`start` / `delegate` が `.claude/agent-workflows.yaml` の `作業開始宣言` 節を短く抽出して出力するようにした。`json` は TOML/YAML shape 要約にも対応し、YAML コメント行をノイズとして省略。`release-check --run` は内部で `guard` / `tools check` を実行し、外部コマンドは未実行として明示する。

## v4.268.0 (2026-06-08)

### Added

- **gateway-core aggregator**: `aggregate_day` / `aggregate_day_by_model` の UPSERT に `compression_rate`・`raw_tokens_estimated_sum`・`submitted_tokens_estimated_sum` の 3 カラムを追加。GROUP BY 内で直接 SUM して ratio を計算。
- **ai_coreutils v0.2/v0.3 拡張** — `diff` に `git diff --numstat` ベースの変更地図・insertions/deletions・Do Not Send Full を追加し、`pack` はtoken budgetに基づき本文投入を省略制御するよう拡張。`delegate` に rg/fd/jq/yq/delta/rtk/repomix/semgrep 等の既存ツール利用方針を明記。`json` / `log` / `test` / `todo done` / `changelog rollover` / `release-check` の v0.3 CLI 表面を追加し、JSON shape・ログ・テスト出力をAI向けに要約可能にした。

## v4.267.0 (2026-06-08)

### Added

- **ai_coreutils MVP** — `crates/ai_coreutils` に `ai-coreutils` CLI を追加。`gps` / `tools check` / `start` / `guard` / `run` / `size` の v0.1 コマンドを実装し、`digest` / `diff` / `pack` / `delegate` は骨格を用意。`.aiignore` と README を追加し、AI 文脈削減・作業開始宣言・逸脱検知・rtk 経由実行の土台を整備。
- **setup-dev-tools: repomix / aider / ctags 追加** — `repomix`（pnpm）・`aider`（uv）・`universal-ctags`（apt/brew）の 3 ツールを `setup-dev-tools.sh` と `setup-ai-tools.ps1` に追加。

### Fixed

- **setup-dev-tools: sg を ast-grep-cli に置換** — `/usr/bin/sg`（newgrp）を誤検知していた旧実装を廃止し、`uv tool install ast-grep-cli` → `~/.local/bin/sg` を使う `check_sg()` に置き換え。
- **setup-dev-tools: lean-ctx aarch64 cargo ビルド対応** — Pi 5 カーネルの 16KB ページにより pnpm プリビルドバイナリが jemalloc クラッシュ。aarch64 Linux では `JEMALLOC_SYS_WITH_LG_PAGE=14 CARGO_BUILD_JOBS=1 cargo install lean-ctx` でソースビルドするよう更新。lean-ctx パッケージ名を `lean-ctx-bin` に修正。

## v4.266.0 (2026-06-08)

### Added

- **gateway-core compress.rs** — RTK-lite dry-run estimator を実装。`PatternHit`/`CompressResult` 型、`estimate_tokens`・`analyze` 公開 API、ANSI 除去・空行圧縮・末尾空白除去・重複行圧縮の 4 パターンを実装。10 テスト全 PASS。

## v4.261.0 (2026-06-07)

### Added

- **Headroom dashboard provider quota 表示** — headroom `/stats` が返す OpenAI/Codex などの provider quota / rate limit 情報を検出し、`/headroom` ダッシュボードに「プロバイダー利用量」として表示。

## v4.260.1 (2026-06-07)

### Fixed

- **gateway guide Codex OAuth 注記** — Codex の Plus/Pro/max plan OAuth 認証では `env_key = "OPENAI_API_KEY"` を削除する必要がある旨を `docs/ja/guides/gateway.md` に追記。

## v4.255.15 (2026-06-04)

### Fixed

- **Headroom ページ上部クリッピング修正** — `<main>` の `padding: 24px` が fixed navbar（高さ約 58px）を考慮していなかったため h1 ヘッダーが navbar 背後に隠れていた問題を修正。`padding-top: 70px` に変更。
- **Headroom WCAG コントラスト違反修正（atelier テーマ）** — `.headroom-card` の背景が `var(--card-bg, var(--bg-secondary, #f7fafc))` にフォールバックし、atelier-dark テーマのテキスト色（`#ede4d3`）と白（`#f7fafc`）の組み合わせでコントラスト比 1.20:1（WCAG AA 最低 4.5:1 を大幅違反）になっていた問題を修正。`var(--card)` を fallback チェーンに追加し atelier テーマのサーフェス色を使用。ラベル色も `var(--text-muted)` 優先に修正。

---

## v4.255.14 (2026-06-03)

### Added

- **Headroom ダッシュボード** (`/headroom`) — headroom proxy (port 8787) の `/health` と `/stats` を yu に統合。バージョン・稼働時間・バックエンド・チェック状態、トークン節約率・入出力トークン・リクエスト統計・モデル別内訳・圧縮エグゼキュータ状態を 5 秒ポーリングで表示。オフライン時はエラーバナーを表示。ナビ「その他」メニューに 🗜️ Headroom リンクを追加。

### Fixed

- **Navbar ブランドスタイル旧バージョン混在修正** — `settings.html` / `diagnostics.html` / `crypto_tools.html` が `atelier-index.css` を未ロードのため navbar ロゴが "YU AI Manager" 旧テキスト表示になっていた問題を修正。3テンプレートに `atelier-index.css?v=20260507` を追加、`settings.html` の atelier CSS バージョンを `4.251.0` → `20260507` に更新。

---

## v4.255.13 (2026-06-03)

### Fixed

- **macOS LAN ファイアウォール guard の実状態確認を追加** — `--lan` / `0.0.0.0` guard の cdhash stamp 高速パスで、`socketfilterfw --getappblocked` による実際の Application Firewall 許可状態も確認するようにした。Python cdhash が不変でも、ファイアウォール例外が手動削除・macOS 更新・別ツールで失効した場合に silent skip して到達不能のまま起動する問題を防止する。
- **依存関係セキュリティ整理: dev 依存から `headroom-ai[all]` を除去** — `headroom-ai[all]` が脆弱な推移依存（`litellm` の critical/high 指摘、`sqlitedict` の high 指摘）をプロジェクト環境へ引き込んでいたため、`pyproject.toml` / `uv.lock` から完全に除去した。Headroom MCP はプロジェクト外の `uvx` 隔離起動へ変更した。
- **依存関係セキュリティ整理: `zeroconf` を更新** — `zeroconf` を `0.148.0` から `>=0.149.16` へ引き上げ、DNS 圧縮ポインタ再帰・unbounded cache 挙動など LAN-local moderate DoS 指摘へ対応した。

## v4.255.12 (2026-06-03)

### Fixed

- **macOS LAN 起動時のファイアウォール事前確認を追加** — `--lan` / `0.0.0.0` 起動時に uv 管理 Python 実体の cdhash を確認し、署名変更または初回起動時は macOS Application Firewall 例外を再登録するようにした。許可を適用できない場合は別マシンから到達不能になるため LAN 起動を中止する。ローカル stamp `.uv_fw_cdhash` は git 管理外にした。

## v4.255.9 (2026-06-03)

### Fixed

5月24日以降（v4.226.0→v4.255.7, 661 commits / 実コード約24,500行）の一括コード/セキュリティレビュー（Codex 独立パス + Opus×2 + Sonnet×3 + design-advisor 設計判断）で検出した指摘の修正。

#### Batch A — LAN Cowork 暗号 / peer-auth セキュリティ中核

- **X25519 公開鍵を pairing 検証に束縛（HIGH）** — pairing commit/SAS/PIN bundle に X25519 公開鍵を束縛し、新 peer は 96B bundle（Ed25519 pubkey + X25519 pubkey + nonce）で検証するようにした。旧 client 互換として `x25519_pk` 欠如時のみ従来の 64B bundle/旧 commit/SAS へ明示 fallback する。`verify_pairing_bundle` は `expected_x25519_pk` 指定時に 64B へのダウングレードを拒否。pair/request 受領側には X25519 low-order point 拒否を追加。HELLO wire format は不変・既存 paired peer の再ペアリング不要。
- **peer-auth nonce 必須範囲の拡張（MEDIUM）** — `/api/peer/infer/*`（clip-encode/yolo-detect/tag/whisper-transcribe/llm-chat）を nonce 必須にし、30 秒窓 replay を封じた。client/server は同一 `path_requires_nonce()` を共有し自動同期。write メソッドで nonce 非要求のパスを warning で観測可能にした。
- fleet consent の static bypass を宣言型 bypass（`auth_route` 登録）に一本化。`lan_cowork_identity.value` fresh schema を BLOB に同期（migration 60 と一致）。migration 81/82 の `wd_tag_stats_cache` 存在 guard 追加。action journal `result_summary` に JSON-aware redaction（token/secret/password/api_token/Authorization/pin）を追加。

#### Batch B — 拡張機能 / バックエンド

- **YOLO detection callback の asyncio.run() 誤用修正（MEDIUM）** — worker thread から新規ループを生成していたのを、起動時 bind した main loop へ `run_coroutine_threadsafe(...).result(timeout=10s)` で投入する方式に変更。
- stream_persist の `load_sources`/`load_rules` を `_write_lock` 保持読込に変更（torn read 防止）。NAI token sentinel を `enc:` pass-through / 空文字 clear / `pst-` encrypt / マスク skip / 未知値 warning に明示分岐。hailo の DB 呼び出し・モデルロードを `run_long_blocking_sync` に置換（`asyncio.to_thread` 規約違反解消）。ComfyUI `source_url` を http/https scheme + host 必須に制限。MCP client の復号失敗時に connection id 付き WARNING を追加。SVG ラスタライズの `svg_path` を data/cache/profiles 配下へ realpath/commonpath で閉じ込め（symlink 脱出拒否）。hailo `download_hef` 失敗時に sanitized error detail を付与。

#### Batch C — フロントエンド

- **ComfyUI model registry の onclick XSS 修正（MEDIUM）** — サーバ応答 id を `JSON.stringify` で `innerHTML` 連結していたのを `data-*` 属性 + 後付けリスナー方式に変更。属性文脈用 `_escAttr()` を追加し title/option value/data-* に適用。
- 検索結果の `setScopeResultIds` 二重呼出を整理（ガード付き呼出のみ残置）。

#### Batch D — LOW / Nice-to-have

- ComfyUI JSON workflow validation の dead `str` 判定を除去（挙動不変）。external-ref 検証で loopback URL（127.0.0.1/localhost/::1）のみ許可。
- PIN policy の `pin_source="none"` 下限 bypass を一度だけ WARNING で可視化。
- `agent_status` の `processes` read 失敗を例外型付き WARNING にしてから空辞書 fallback。
- `future_encryption.compute_shared_secret`（未使用 stub）に all-zero shared secret 拒否を追加（将来有効化時の安全網）。
- hailo trusted-peer admin scope コメント訂正、`delete_conversation` の caller-commit 契約 docstring 明記、LLM cancel timeout 時の WARNING ログ追加。
- **残（別途）**: ~~`_approved_pins` 永続化~~ → fail-closed 設計として確定・close。~~`scan/runtime_prepare` chunked IN の perf 評価~~ → close（`idx_files_deleted_path` 複合インデックスで回帰なし確認）。~~i18n ハードコード日本語~~ → v4.255.9 で対応済み。~~checkpoint family 判定の実機検証~~ → close（unit test 31件 全 PASS、`⚠ BEST-EFFORT` コメント除去）。

## v4.255.7 (2026-06-02)

### Added

- **画像ビュワーに「鑑賞モード」コーナー・トグルボタン（🖼）を追加** — 画像コンテナ左上に常設のトグルを置き、既存の没入モード（UIを隠して画像だけ表示）をワンクリックで切り替え可能にした。ON 時は accent 色で点灯し `aria-pressed` も反映、V キー／画像ダブルクリック／既存ツールバー⛶ボタンとも状態同期する。ラベルは i18n キー `detail.modal.viewing_mode` を全11言語に追加（絵文字アイコン自体は言語非依存）。既存ツールバーの英語直書き "Immersive (V)" も同キーへ統一。

### Changed

- **没入（鑑賞）モードの自動非表示を即時化（3000ms → 0ms）** — `IMMERSIVE_IDLE_HIDE_MS=0`。マウスを止めた瞬間に全UI（ツールバー・コーナーボタン含む）が CSS フェード（0.5s）で消え、移動で即再表示。通常モードのツールバー idle（250ms, `controls-hover.ts`）は不変。※ TS/CSS 変更のため反映には dist 再ビルドが必要。

## v4.255.6 (2026-06-02)

### Changed

- **画像ビュワーのツールバー自動非表示をさらに短縮（500ms → 250ms）** — Komiflo 等の鑑賞 UI に近い「マウスを動かした瞬間に出て、止まったら少しの余韻で消える」感覚に寄せ、idle タイムアウト `TOOLBAR_IDLE_HIDE_MS` を 250ms へ。「余韻」のフェードは既存 CSS（`.toolbar-auto-hidden` の `opacity 0.35s ease`）が担うため CSS 変更は不要。※ TS 変更のため反映には dist 再ビルドが必要。

## v4.255.5 (2026-06-02)

### Changed

- **画像ビュワーのツールバー自動非表示を高速化（2500ms → 500ms）** — カーソルが静止してからツールバーが消えるまでの idle タイムアウト `TOOLBAR_IDLE_HIDE_MS`（`src/ts/detail-modal/runtime/controls-hover.ts`）を 2500ms から 500ms へ短縮し、画像鑑賞時に操作バーが素早く引っ込むようにした。ツールバーから外れたとき用の `TOOLBAR_LEAVE_HIDE_MS`（1000ms）は据え置き。※ TS 変更のため反映には dist 再ビルドが必要。

## v4.255.4 (2026-06-02)

### Fixed

- **狭幅(<=720px)で「お気に入り」FAB とグリッド制御ボタンが左下で重なる問題を修正** — collections sidebar が畳まれて出現する `.cs-mobile-fab`（`left:16px/bottom:16px`, z-index 900, 48px）が、同じ左下隅に来る floating grid controller `.fgc` を覆い隠していた。真因は `uxpatch-responsive.css` の `@media(max-width:720px) .fgc { left:6px; bottom:6px }` が import 順で後勝ちし FAB 直下へ重ねていたこと。これを `left:16px; bottom:72px`（FAB の上に縦積み）へ変更し、toast 表示時も `bottom:122px` でスタックを維持するルールを追加した。Playwright で 700px 幅にて非重なり（縦8px gap・左端16px揃い）を確認。

## v4.255.3 (2026-06-02)

### Fixed

- **PIN pairing modal contrast, Fleet Atelier navbar, and keyring orphan logging polish** — LAN Cowork の SAS code box を dark/Atelier theme の card/surface 配色へ揃え、PIN placeholder の dark contrast を WCAG AA 以上へ改善。Fleet の navbar は `atelier-index.css` 全体を読まず、index 専用 sidebar/grid/search rule の副作用を避けて nav rule のみ `atelier-fleet.css` へ移植。失われた keyring `key_id` による復号不能ログは graceful continuation に合わせて WARNING へ格下げし、API key/secret 再作成 guidance を追加。

## v4.255.2 (2026-06-02)

### Fixed

- **LAN Cowork pairing が再起動後に未ペアリング表示へ戻る問題を修正** — schema v83 で `peers.pubkey` / `peers.x25519_pk` を冪等 ADD し、fresh schema と migration の列定義を一致させた。`PeerRegistry` の DB upsert/load/snapshot で pubkey と X25519 公開鍵を永続化・復元し、再起動後も `_pubkey_index` が再構築されるようにした。加えて mDNS 再発見の new peer 経路で、同一 `peer_id` の既存 peer が token を持ち、既存 pubkey が空または同一 pubkey の場合だけ token 系フィールドを引き継ぎ、discovery 由来の token 空値で paired token を NULL 上書きしない防御を追加。

## v4.255.1 (2026-06-02)

### Fixed

- **migration 82 の冪等再開パスで file_wd_tags index と stats cache reset が漏れる問題を修正** — `confidence_milli` が既に存在する中断再開/double-apply 経路でも、v81 と同じく `idx_fwt_tag_id` / `idx_fwt_model_file` を `IF NOT EXISTS` で作成し、`wd_tag_stats_cache` を `{}` / `computed_at=0` にリセットしてから schema version 82 を stamp するようにした。post-v81/post-v82 VACUUM+ANALYZE retry 設定は label 文字列分岐をやめ、呼び出し側から `max_attempts` / `retry_base` を明示的に渡す形へ整理。v81 double-apply テストは 2 回目を registry の `apply_pending` 経路で検証する形に戻した。あわせて DB_PATH 未初期化の in-memory migration test で migration 55 が権限依存の `tempfile.mkdtemp()` fallback に落ちないよう、`core.paths` 初期化済みなら data dir の `vectors.db` を使う fallback を追加した。

## v4.255.0 (2026-06-02)

### Changed

- **`file_wd_tags.confidence` を milli-scale INTEGER 化（migration 82）** — migration 81 で辞書正規化済みの `file_wd_tags.confidence REAL` を `confidence_milli INTEGER NOT NULL CHECK(0..1000)` へ再構築し、保存サイズをさらに削減。外部 Python/API 契約は従来どおり 0..1 float の `confidence` とし、write 境界で `round(confidence * 1000)`、read 境界で `confidence_milli / 1000.0` へ変換する。SQL の降順ソートは `ORDER BY confidence_milli DESC`、LoRA caption summary の平均 confidence は milli 合計を 1000 で戻す形へ更新。migration 82 は v81 と同じ rebuild パターン（新テーブル作成、`OR IGNORE` 不使用、行数検証、DROP→RENAME、fresh schema と同一 index 再作成、単一 transaction）で実装し、v81/v82 の file_wd_tags rebuild precheck と post-v82 one-shot VACUUM+ANALYZE を追加。

## v4.254.2 (2026-06-02)

### Docs

- **開発知見集（落とし穴・教訓カタログ）を `docs/development/development_docs/DEVELOPMENT_PITFALLS_AND_LESSONS.md` に新設** — 複数セッションで AI memory に蓄積した技術的落とし穴と回復パターン（DB/migration・perf 調査・frontend・test 設計・build/uv・bridge/executor・Windows 固有・外部 API）をテーマ別に恒久化・横断索引化。`dev-docs-index.yaml` に `known_pitfalls` タグで登録（CLAUDE.md「既知ノ罠」ポインタから到達可能）。Windows CRLF 偽 drift を避けるため index は全再生成せず `standalone:` へ手動 1 entry 追加（sha は `read_bytes` 計算で `pre_push_check` の照合と一致）。

## v4.254.1 (2026-06-02)

### Fixed

- **post-v81 VACUUM+ANALYZE が gateway health probe の周期書き込みと競合して実空間回収に失敗する問題を修正** — v80→v81 migration 後の `post_v81_vacuum_analyze` 実行時、`gateway_status_transitions` へ 10 秒周期で INSERT する gateway health probe が `VACUUM` の排他ロック取得と競合し、`database is locked` で 11GB DB の free page 回収が次回起動へ先送りされていた。`routes.gateway_status.get_probe()` で startup background から probe を取得し、実行中の場合だけ `HealthProbe.stop()` → `db_vacuum()` → `db_analyze()` → `HealthProbe.start()` の順で一時停止・再開するよう変更。同期 startup thread から Quart event loop 上の async probe API を安全に呼ぶため、`HealthProbe` に event loop 参照・idempotent start・`is_running()` を追加。`database is locked` は最大 3 回の指数 backoff retry とし、最終失敗時は従来どおり warning のみで完了フラグを立てず次回起動で再試行する。

## v4.254.0 (2026-06-02)

### Changed

- **`file_wd_tags` 辞書正規化で tags.db を ~2GB 削減（migration 81・schema v81）** — tags.db の最大テーブル `file_wd_tags`（15.5M 行）の 4 つの低カーディナリティ TEXT 列（`tag_name`/`tag_name_normalized`/`category`/`model`）を 3 つの辞書テーブル（`wd_tag_dict`/`wd_model_dict`/`wd_category_dict`）＋ INT FK へ正規化し、`file_wd_tags` を全列 INT 化（`tag_name_normalized` の行レベル重複も辞書側 1 回保持で構造的に解消）。**実 DB 実走で 10.68GB→8.34GB（純増分 2.05GB・~22%）削減を確認**（VACUUM 単独では 0.28GB のみ＝構造正規化でしか得られない削減）。検索は query→`normalize_tag_for_search()` 全 variants→`wd_tag_dict.tag_name_normalized` で tag_id 集合解決→`tag_id IN(...)`（現行 recall をビット等価で維持・CJK 含む全 distinct tag で before/after の file 集合一致を recall パリティハーネスで固定）。write は辞書解決＋DELETE→INSERT。migration 81 は engine 単一トランザクション内で辞書 populate→新テーブル rebuild（`OR IGNORE` 不使用・行数検証）→DROP/RENAME→`set_schema_version`。起動前 precheck（空き容量・FK orphan）と専用例外で安全に中断。rebuild 後の free page は起動後 idle の one-shot VACUUM→ANALYZE（`post_v81_vacuum_analyze`・kv_state フラグで一回限り）で回収。spec/plan: `docs/superpowers/specs|plans/2026-06-02-file-wd-tags-dictionary-normalization.md`。Codex 実装＋Opus 監修（spec×2／code-quality×2 レビュー・`/security-review` no findings）。
  - **⚠ アップグレード時の注意**: v80→v81 の初回起動時に `file_wd_tags`（15.5M 行規模）を再構築するため、**大規模ライブラリでは起動に数分〜十数分かかる**（実測 ~10 分）。再構築中はプロセスを強制終了しないこと（中断時は安全に rollback し次回起動で最初から再試行）。空きディスクは現 DB の ~30%（最低 2GiB）必要。

## v4.253.0 (2026-06-02)

### Added

- **artist 絞り込みが anima/NovelAI v4 の `@` 形式（`@someone`）を作者指定として認識** — 従来 namespace 分割が `:` のみだったため `artist:someone` しか artist 絞り込み（`namespace='artist'`）で拾えず、anima 系プロンプトの `@someone`（先頭 `@` による作者画風指定）は namespace なしの素タグとして保存され絞り込みから漏れていた。**取込み側**: 2 つの `split_namespace`（`core/helpers_core/helpers_text_path.py`・`core/tagdb_prompt/utils.py`）に、コロン namespace が確定しなかった場合に先頭 `@` を artist namespace として扱う分岐を追加（`@someone` → `('artist','someone')`。コロン優先は維持、`@` 単体や `@_@` のような記号のみは英数字 word 文字判定 `[^\W_]` で除外）。**検索側**: `apply_artist_filter`（`core/query/filters_common_media.py`）を、入力先頭 `@` を除去した base 名に対し「`namespace='artist'` の tag」または「namespace NULL/空の素タグ `@base`」の両方へマッチするよう拡張（con あり=該当 tag_id を `IN (...)` で EXISTS、con なし=OR 条件）。素タグ側を namespace NULL/空に限定することで `character:@foo` 等の他 namespace タグが artist 検索へ混入する退行を防止（Codex レビュー指摘対応）。これにより artist フィールドに `someone` と入力すれば `artist:someone` と `@someone` の両方を拾い、**再スキャン前の既存 `@someone` 素タグ（旧 `split_namespace` が namespace=NULL で格納）も検索で拾える**。SQL は全て `?` バインドで注入リスクなし。Sonnet 実装＋Codex/Opus 監修（`split_namespace`/parse パイプライン/フィルタの新規 20 tests＋既存 `test_preprocess.py` green、Codex レビュー no findings、tests/basic 全 green）。**注**: 既存データを namespace=artist へ正規化するには再スキャンが必要（未実施でも検索側 OR マッチで拾える）。

## v4.252.1 (2026-06-02)

### Fixed

- **Atelier 横展開のコードレビュー指摘を修正** — Opus コードレビューの指摘を反映。①`settings.html` の `atelier-settings.css` link が Phase 3（v4.252.0）での同 CSS 編集後も `?v=4.251.0` のままで stale cache リスクがあったため `?v=4.252.0` へ更新（他 4 本は未変更につき据え置き）。②`tests/test_atelier_settings.py` の `test_settings_form_input_themed` が要素不在時に `bg=None` で無条件 pass する偽陽性を、番兵 `"NO_ELEMENT"` ＋ `wait_for_selector` で解消。③トグル/secondary ボタン色比較テストで querySelector が null の際 `getComputedStyle(null)` が JS TypeError（error≠fail）になる問題を、JS 側 null guard ＋ Python 側 `assert "error" not in colors` で堅牢化。④`tests/test_atelier_fleet.py` に atelier-dark（`theme-atelier-dark dark atelier-tool`）でのログ暗色維持テストを追加。全 12 tests green。Codex 実装＋Opus 監修。

## v4.252.0 (2026-06-02)

### Added

- **settings ページの Atelier テーマ対応（仕上げ + テスト）** — v4.251.0 のコア部に続き、`atelier-settings.css` にトグルスイッチ on 色（`.toggle-switch input:checked + .toggle-slider` を `--accent-tool`）と generic `.btn` 中和（`.btn:not(.btn-primary):not(.btn-save):not(.btn-danger)` を neutral）を追加。`.tsr-ok`/`.tsr-error` 等 semantic 色は再宣言せず維持。DOM レベル Playwright テスト `tests/test_atelier_settings.py` を追加（7 passed）。settings.html は Jinja include（`_content.html` 等）を含み静的読込では `#main-content` が未展開のため、`shared_test_server` fixture 経由の live `/settings` route で検証（`test_settings_static_template_needs_live_route` がその理由を明示）。アサートはトークン値直書きを避け「default 配色でない」「`font-family` に Fraunces 含む」「トグル on 色＝save ボタン色」「neutral btn≠save 色」等の頑健形。default 本体・partial は不変更。これで Fleet（v4.250.0）と settings の Atelier 横展開が完了。Codex 実装＋Opus 監修。

## v4.251.0 (2026-06-02)

### Added

- **settings ページの Atelier テーマ対応（コア部）** — settings ページは index 専用の `atelier-index.css` を誤読込しており、`atelier-tool` クラスも無く部分対応どまりだった。正規ツールチェーン（`atelier-tool-tokens.css` + `atelier-tool-components.css` + 新規 `atelier-settings.css`）へ差し替え、`atelier-index.css` を除去、`body class="atelier-tool"` を付与。`atelier-settings.css` は全セレクタを `body:is(.theme-atelier-light,.theme-atelier-dark).atelier-tool #main-content` 配下に限定し共有 `_nav.html` への漏れを防止。コア部としてタブ（`.tab-btn`/`.tab-btn.active`）・セクションカード（`.settings-section`/`.tsr-card`）・見出し Fraunces 化（`#main-content header h1`）・フォーム入力（背景/境界/`:focus-visible` で outline 維持）・save bar（`.btn-save`）を atelier トークン化。inline style の多くは `var(--x,fallback)` 形式で atelier-tokens のレガシー別名により自動再テーマ。semantic 色は再宣言せず維持、`!important` 不使用。default 本体 `pages/settings.css` および partial テンプレートは不変更。トグル・button neutralize・DOM テストは次版（仕上げ）で追加。Codex 実装＋Opus 監修。

## v4.250.0 (2026-06-02)

### Added

- **Fleet 管理 UI を Atelier テーマ（light/dark）へ対応** — Fleet 拡張 UI（`extensions/builtin_lan_cowork/ui/fleet/`）はこれまで default 配色のみで、テーマ切替時も atelier トークンが当たらなかった。加算的 override 方式で対応: `fleet.html` に atelier チェーン（tokens/components/tool-tokens/tool-components）＋新規 `atelier-fleet.css` を読込み `body class="atelier-tool"` を付与。`atelier-fleet.css` は全セレクタを `body:is(.theme-atelier-light,.theme-atelier-dark).atelier-tool` で閉じ非 atelier テーマへ無影響。変数駆動部分は atelier-tokens のレガシー別名（`--card/--muted/--accent`）再定義で自動再テーマ。明示対応は①atelier-light でのログビューア暗色維持（`#1e1e1e`、atelier-dark は runtime の `.dark` 併用で既に暗色）、②Fleet 見出しの Fraunces 化、③generic `.btn` 一括 primary 化の中和（`.btn:not(.btn-primary):not(.btn-danger)`、`.fleet-node-restart-btn` は非該当で強調維持）の 3 点。warning banner・update-step・status-dot・bar-fill 等 semantic 色は再宣言せず維持。default 本体 `fleet.css` は不変更。DOM レベル Playwright テスト `tests/test_atelier_fleet.py`（fleet.html 静的読込＋手動クラス付与・サーバ非依存で常時実行、4 passed）追加。spec/plan: `docs/superpowers/{specs,plans}/2026-06-02-fleet-and-settings-atelier.md`。Codex 実装＋Opus 監修。

## v4.249.1 (2026-06-02)

### Fixed

- **freeze-pullback の admin scope 認可漏れを修正（認可の非一貫性）** — `builtin_freeze_pullback` の API は設計精査前に作られたため、`require_admin_scope()` の適用がエンドポイントごとにバラバラだった。出力一覧 `GET /api/outputs` は admin scope 必須なのに、個別ダウンロード `GET /api/outputs/<filename>`・削除 `DELETE /api/outputs/<filename>`・ジョブキャンセル `POST /api/cancel`・ffmpeg 確認 `GET /api/check` は無防備で、**admin scope を持たない非 admin API キー**が本来 admin 専用のダウンロード・削除・キャンセルを実行できた（PIN セッションは元々 scope チェックを素通りするため影響なし、API キーのスコープ分離のみが破れていた）。上記4ハンドラ冒頭に既存ハンドラと同一パターンの `require_admin_scope()` を追加し、全エンドポイントで認可を統一。DB 操作は元から読み取りのみ（`get_readonly_db()`）で現基準に準拠、CSRF/PIN ゲートは `/ext/` プレフィックスで基盤側が一括適用しており問題なし。既存の `tests/basic/test_extension_media_admin_scope.py` が当該4エンドポイントの admin scope 要求を**元々期待**していた（実装漏れの裏付け）ため、本修正でテスト期待と実装が一致。Codex 実装＋Opus 監修（`/security-review` no findings、lint/mypy clean、関連 6 tests green）。

## v4.249.0 (2026-06-02)

### Changed

- **Hailo 3拡張の UI を legacy `/api/status` から新 `/api/runtime` へ分離（`/api/status` 廃止の前半）** — `builtin_hailo_genai` / `builtin_hailo_semantic_search` / `builtin_hailo_yolo_detect` の Tools ページが、health 情報を統合 health バッジ（`/api/extensions` の health フィールド ＋ `extensionHealthApi.renderInto`）に一本化済みであるにもかかわらず、各拡張の `_*_ui.html` 内 inline ステータス区画（"OK/N/A 理由" 表示）で `/api/status` の health フィールドを重複表示していた。各拡張に **非health データのみ**を返す `GET /api/runtime`（既存 payload builder を再利用、同じ admin scope `_require_admin_scope()`）を追加し、UI の `loadStatus()` を `/runtime` 参照へ切替。重複 health 表示区画を撤去（genai `#hgStatus` は完全撤去、semantic `#semanticStatus` / yolo `#yoloStatus` は indexed/detected カウント専用の 1 行に縮退）。context 使用率バー・モデルドロップダウン・カウント・config フォーム復元・backend dropdown 可用性ヒントは維持。`/api/runtime` の admin scope テストを追加（read scope→403・admin→200・非health フィールド存在・health フィールド非含有）。**`/api/status` ルート本体と既存テストは互換期間として温存**（2026-06-16 期限で後半セッションにて削除予定）。Codex 実装＋Opus 監修（`/security-review` no findings、関連 94 tests green）。

## v4.248.3 (2026-06-01)

### Security

- **update.zip 署名公開鍵を本番 Ed25519 鍵へ差し替え（リリース前必須）** — `security/update_signing_pubkey.pem` を dev 由来鍵（commit f3b566cae）から、オフライン生成した本番 Ed25519 公開鍵に差し替え。秘密鍵はリポジトリ外（`~/yu_ai_manager_release_keys/`、git tracked 外）に保管し commit しない。差し替え後に「公開鍵が Ed25519 で、オフライン秘密鍵と sign/verify 往復一致」を確認。検証パス（`core/repair/update_package/verify.py`）は `public_key_path` 注入対応済みで、テストは `tests/update/fixtures/` の専用 fixture 鍵を使うため bundled 鍵と分離されており影響なし（update/repair 66 tests green）。互換ウィンドウ不要（update.zip 未公開）のため `_previous.pem` 併走なし。rotation/失効手順は `UPDATE_SIGNING_KEY_OPS.md` 参照。

## v4.248.2 (2026-06-01)

### Changed

- **`file_wd_tags` の重複インデックス削除（無損失・migration 80）** — `file_wd_tags`（15.5M 行）に `tag_name` 列の同一インデックスが 2 本（旧名 `idx_fwt_tag`＝pre-v17 migration のみ作成、canonical `idx_file_wd_tags_tag_name`＝fresh schema＋migration 56）存在し、旧 migrated DB で冗長だった。migration 80 で `DROP INDEX IF EXISTS idx_fwt_tag`（canonical を残す）し旧 DB を fresh schema 形状に収束。`tag_name` クエリは canonical index が完全カバーするため無損失（`INDEXED BY idx_fwt_tag` 参照なしを確認）。`CURRENT_SCHEMA_VERSION` 79→80。fresh DB は元々 `idx_fwt_tag` 非保持のため no-op、drift テスト維持。**実ファイル縮小には別途 VACUUM 要**（11GB 暗号化 DB の VACUUM は重い・一時 2x ディスク）。`tests/test_schema_migrate_80.py` で drop/冪等/no-op を固定。

## v4.248.1 (2026-06-01)

### Fixed

- **`test_import_session_create_accepts_regular_media_folder` の Windows 偽失敗を解消** — pytest の `tmp_path` は Windows では `~/AppData/Local/Temp` 配下で、`_validate_import_folder` の `_sensitive_import_bases()`（`~/AppData` を正当に書込拒否）に引っかかり 400 を返していた（Linux CI は `/tmp` のため緑、Windows ローカルのみ赤）。検証ロジックは防御として正しいため弱めず、positive テスト側で `_sensitive_import_bases` を空に monkeypatch して「通常フォルダ受理＋作成」だけを検証するよう修正（AppData/system dir 拒否は専用 rejection テストが担保）。

## v4.248.0 (2026-06-01)

### Added

- **LAN Cowork スライス C を nightly CI へ接続（self-hosted runner）** — `lan-cowork-harness.yml` に nightly `schedule`（03:17 JST）と `slice-c-realnode` ジョブを追加。GitHub ホストランナーは LAN ノードに到達できないため `runs-on: [self-hosted, lan-cowork]`。host 上 runner が実 DB から credential を都度ダンプ（`--db` 絶対パス）し**メモリ内のみで消費**（seed/token はログ・artifact 非出力）、`LANCOWORK_C_HOST_PIN` で direct を PIN 認証して実走、結果 JSON を `slice-c-report` artifact 化。必須設定（secret `LANCOWORK_C_HOST_PIN` ＋ var `LANCOWORK_C_PEER_URL`/`LANCOWORK_C_DB`）未設定時は graceful skip（runner 未登録でもマージ安全）。anlas 節約のため runner に `LANCOWORK_C_LIMIT`（実走 corpus 件数上限、既定 0=全件）を追加し、nightly は既定 1 件（=NAI 2 生成）。README に runner 登録手順・secrets/vars 表・コスト注意を追記。

## v4.247.1 (2026-06-01)

### Fixed

- **LAN Cowork「接続ピア」の陳腐化 discovery 行増殖を解消** — peer が起動毎に新しい peer_id ＋エフェメラルポートで mDNS 広告すると `_on_peer_found` が peer_id ごとに新規行を作り、UI が dead な未ペアリング行で埋まっていた（本番で 18 行中 17 行がノイズ）。既存の 7 日 hard-prune では <7 日の行が滞留するため、`prune_unpaired_unreached_peers(cutoff)` を追加し「`token` 無し ＋ `last_reached_at` 無し（一度も到達成功なし）＋ 作成から既定 1h（`DEFAULT_SOFT_PRUNE_SEC`）超」の discovery ノイズ行を registry load 時に soft-prune する。ペアリング済（token 保持）・作成直後の行は常に保護。再発源の peer_id 不安定は migration 79（identity 永続化）で収束済み。`tests/extensions/lan_cowork/test_peer_prune_unpaired.py` で old削除/recent保護/paired保護/reached保護を固定。

## v4.247.0 (2026-06-01)

### Added

- **LAN Cowork スライス C 実機 runner に host PIN 認証を追加** — boss-mode PIN 有効の host に対して direct ルートを実走できるよう、`LANCOWORK_C_HOST_PIN` を任意 env として追加。runner は direct call と同じ `httpx.AsyncClient` で PIN ページの CSRF token を取得し、`/_pin_check` へ form login して `pin_token` cookie を保持してから direct/peer ケースを走らせる。peer ルートは従来通り署名認証のみで、host cookie は domain scope により peer node へ送られない。PIN 未設定時に direct が 200 空 body なら boss-lock の可能性を case hint に出す。`httpx.MockTransport` で PIN flow と cookie 伝播を回帰固定。

## v4.246.35 (2026-06-01)

### Fixed

- **テスト中断時に `launch-args.txt` が example デフォルトへ初期化される footgun を解消** — `tests/conftest.py` の共有サーバー fixture が開発者の `launch-args.txt` を `.pytest_bak` に rename→`finally` で復元する設計だったため、テストプロセスが強制終了（kill/中断）すると復元されず本体ファイルが消失し、次回 `start.bat` 起動時に `web_ui.py::_seed_example_files` が example デフォルトを seed していた（スキーマ migration 開発中＝テスト多発時に起こりやすい）。対策: (1) `runtime_runner.load_launch_args_file()` を切り出し `YU_SKIP_LAUNCH_ARGS_FILE=1` で読み飛ばし可能化、(2) conftest は実ファイルを一切 rename せず子サーバーに同 env を渡すだけに変更（中断しても無傷）＋起動時に孤児 `.pytest_bak` を回収、(3) `_seed_example_files` は example seed の前に `.pytest_bak` があれば実データを復元。`tests/test_launch_args_loading.py`・`tests/test_seed_example_files_recovery.py` で固定。

## v4.246.34 (2026-06-01)

### Added

- **LAN Cowork スライス C 実機 runner — credential ダンプヘルパー（test/tooling）** — 実走に要る `LANCOWORK_C_SEED_HEX` / `PEER_ID` / `TOKEN` を host ノードのプロジェクト DB から読み取り専用で取得する `tests/lan_cowork_harness/realnode/dump_credentials.py` を追加。`lan_cowork_identity` の `ed25519_seed` から seed_hex と local peer_id を導出（identity 生成はしない・無ければ明示エラー）、`peers` テーブルから `--peer`（peer_id/api_host/name 部分一致）で 1 件を選び token を充てる。実機検証で判明した実データ事情に対応: (1) standalone 実行用に `--db`（既定 `data/tags.db`）＋ runtime 自己 bootstrap を追加（`DB_PATH is not initialized` を解消）、(2) 同名/同 host の陳腐化 peer 行が多数あるとき token を持つ 1 件を優先選択（`disambiguated_by_token`）。bash/PowerShell 両形式の export ブロックを出力。in-memory sqlite の pytest で固定。

### Fixed

- **スライス C runner: direct ルートに CSRF ヘッダ欠落で 403** — 実機 2 ノード実走で `drive_direct_real` が `X-Requested-With` を送らず host に `CSRF header missing`（403）で弾かれていた。web UI と同じく `X-Requested-With: XMLHttpRequest` を付与し、MockTransport テストでヘッダ存在を回帰固定。in-process mock では露見しない実機固有の経路バグ（spec §354 の C 責務）。
- **ペアリング失敗 `table peer_pairing_requests has no column named pubkey`（スキーマドリフト修正・migration 79）** — `peer_pairing_requests` の crypto identity 列（`pubkey/x25519_pk/commit_hash/sas/source_ip`）は migration 60 でしか追加されないが、fresh schema 定義（`schema_sql_integrations.py`）に含まれていなかったため、fresh schema から schema_version>=60 で作られた DB は migration 60 を適用済み扱いのまま列を持たず、ペアリング INSERT が失敗していた。(1) fresh schema 定義に5列を追加（新規 DB を恒久修正）、(2) **冪等・非破壊**の repair migration 79 を追加し既存 DB に欠落列のみ ALTER（既存トークン/identity/pairing 行は削除しない＝migration 60 の clean-cut とは別）、(3) `CURRENT_SCHEMA_VERSION` 78→79。`tests/extensions/lan_cowork/test_pairing_schema_repair.py` で repair・冪等・非破壊・INSERT 成功を固定。`test_schema_drift.py` は引き続き green（fresh/migrated 整合維持）。実機 slice C 実走が炙り出した本番バグ。

## v4.246.33 (2026-06-01)

### Added

- **dev-overview.json の構造参照ドリフト検出を pre-push に追加** — 従来 `check_dev_overview_sync` は version 一致と html 同期のみ検査していたが、json が記述する構造的パス参照が実リポジトリと乖離していないかも機械検査するよう拡張。検査対象: `tests.categories`（`tests/<cat>` 存在）・`domain_api_map` の `core`/`routes` パス・`docs.key_files` のパス・主要 scalar フィールド（entry_point/mcp_server.entry/cli.entry/desktop.config/frontend.src）。glob(`*`)・散文（core_subsystems 等）は誤検出回避のため対象外。stale 参照があれば push をブロックし該当 field/path を列挙して json 修正を促す（リファクタでパスが移動/削除された際に json を確実に追従させる）。回帰テスト `tests/test_pre_push_dev_overview_sync.py` 追加。

## v4.246.32 (2026-06-01)

### Changed

- **`dev-overview.json` のテストツール記述を更新** — 今回追加した pytest モジュール（pytest-timeout / pytest-mock / pytest-httpx / responses / aioresponses / time-machine / hypothesis）を `tests.tools` に反映し、`development_docs/TEST_MOCKING_TOOLS.md` への参照を追記。

## v4.246.31 (2026-06-01)

### Fixed

- **CI(Windows)の Unicode 出力クラッシュを修正** — 復活した CI の Windows レグで「Pyright baseline diff」(pre_push_check) が `UnicodeEncodeError: 'charmap' codec`（既定 cp1252 コンソールが `→`/`✅`/日本語を出力できない既存バグ）で失敗していた。`static-checks.yml` の env に `PYTHONUTF8: "1"` / `PYTHONIOENCODING: "utf-8"` を追加し、Windows でも UTF-8 stdio を強制。

## v4.246.30 (2026-06-01)

### Added

- **`requirements.txt` ↔ `pyproject.toml` ドリフト検出を pre-push に追加** — uv 移行後 `requirements.txt` は普段使わないが CI(pip) が使うため、pyproject の `[project].dependencies` を追加して requirements.txt を更新し忘れると CI が落ちる（今回 piexif/filelock で発生）。`scripts/pre_push_check.py` に `check_requirements_pyproject_sync`（`--skip reqs-sync`）を追加し、pyproject 主依存が requirements.txt に揃っているか push 前・CI で機械検出する。

### Fixed

- **CI(Python 3.12)固有のテスト失敗を解消** — 復活した CI の高速ユニットゲートが検出した移植性問題2種を修正。`test_hitl_gate.py` の `asyncio.get_event_loop().run_until_complete()`（3.12 で no-loop エラー）を `asyncio.run()` に置換。`test_sign_update_zip.py`（`uv` バイナリのサブプロセスを要求）に `skipif(shutil.which("uv") is None)` を付与し pip ベース CI では skip・uv 環境では実行されるように。

## v4.246.29 (2026-06-01)

### Fixed

- **`requirements.txt` のドリフトを解消（CI collection 失敗の修復）** — CI 復活後に `pytest --collect-only` が `ModuleNotFoundError: piexif / filelock` で失敗。`requirements.txt`（手管理・CI が使用）が `pyproject.toml` の `[project].dependencies` からドリフトし、`piexif` `filelock` `faiss-cpu` `tokenizers` `urllib3` `idna` の6件を欠いていた。全て追記し pyproject 主依存を完全カバー。

### Fixed

- **CI の pnpm を 10 に揃え、死んでいた static-checks を復旧（systemic 対策の前提修復）** — `pnpm-workspace.yaml` が pnpm 10 構文（`allowBuilds`）かつ `packages:` 無しのため、`pnpm/action-setup version: 9`（pnpm 9）の CI では setup-node の `cache: 'pnpm'`（`pnpm store path`）が `ERROR packages field missing or empty` で失敗し、**static-checks の全ゲート（ruff/pyright/collect-only/pytest/tsc）が一度も実行されていなかった**。`static-checks.yml`・`release-portable.yml` の `pnpm/action-setup` を `version: 10`（ローカル 10.30.3 と整合）に変更し復旧。これにより前バージョンで追加した高速ユニットスイート gate も実際に走るようになる。

## v4.246.27 (2026-06-01)

### Changed

- **CI に高速ユニットスイート実行を追加（テスト腐敗の systemic 対策）** — `static-checks.yml` はこれまで pytest を `--collect-only` のみ実行しており、本番リファクタ/セキュリティ修正にテストが追随できず静かに腐敗していた（P3 で 16 failed + 11 errors を一掃した根本原因）。Linux レグに hard gate を追加: onnxruntime cpu を導入し `pytest -m "not integration and not fuzz and not slow and not playwright and not shared_server" --ignore=tests/fuzz --ignore=tests/integration`（約5千テスト・ローカル 5891 passed / 0 failed で検証）。playwright/shared_server/integration は環境感応・順序依存のため別途カバーとして除外。`timeout-minutes` を 15→25 に引き上げ。

## v4.246.26 (2026-06-01)

### Fixed

- **フルテスト残存失敗（16 failed + 11 errors）を解消** — CI が `pytest --collect-only` のみのため、本番のリファクタ/セキュリティ修正にテストが追随できず腐敗していた残存を一掃。トリアージの結果ほぼ全てがテスト側の問題（本番リファクタ追随漏れ・テスト分離不備・cwd/状態汚染依存・baseline 更新漏れ）で、本物のバグは schema drift 1件のみだった。
  - **schema drift 修復（本番）**: `BASE_SCHEMA_SQL`(schema_sql_integrations.py) に migration 76/77 のテーブル（`agent_circuit_breaker_state` / `agent_budget_usage` / `wd_tag_stats_cache`）を追加し fresh schema を整合（runtime 影響なしの不変条件修復）。
  - **テスト分離/状態汚染**: `sys.modules` 生代入の monkeypatch.setitem 化（hailo errors 11件）、service_registry policy の `.claude/worktrees` 誤走査除外＋allowlist 追加、wd_active_model/NAI/TaggerRegistry/core.paths の隔離、integration app fixture での process-global cache reset（test_multi_step 回帰）。
  - **本番リファクタ追随漏れ**: mesh worker 署名必須化、config_atomic の cwd 干渉、prompt-library route registrar の kwargs、ComfyUI width/height 抽出、NAI CSS 分割、sweep helper patch 対象、chatlog delete の commit、nightly_review run-dir 抽出。
  - **baseline**: line-count 許可リストに新規/肥大4ファイルを追加。
  - 検証: `uv run --extra cpu pytest` フル suite で 5996 passed / 0 failed / 0 errors。
## v4.246.25 (2026-06-01)

### Security

- **プロジェクト固有 uv バイナリの供給網ハードニング（pin ゲート＋ bootstrap checksum 検証）** — `./bin/uv` は gitignore 済（ノード毎）で従来 `bootstrap_uv.sh`/`.ps1` が公式リリースを checksum 検証なしで取得しており、すり替え時に `uv run` 経由で任意 Python 実行＝砂箱外権限を得る余地があった。対策: (1) 公式リリースの SHA-256 を pin した tracked マニフェスト `scripts/uv-checksums.txt`（再生成ツール `scripts/update_uv_checksums.sh`、対応 8 triple の archive/binary hash）を追加。(2) `bootstrap_uv.sh`/`.ps1` がダウンロードしたアーカイブを展開前にマニフェストと照合し、不一致／未登録版（`UV_ALLOW_UNVERIFIED=1` 除く）を拒否。(3) `pre_push_check.py` に `check_uv_binary_pinned` ゲートを追加し、`bin/uv`(x) の SHA-256 が pin リリースバイナリ集合に無ければ push を拒否（すり替え検知）。`tests/test_pre_push_uv_pin.py` で skip/一致/不一致を固定。

## v4.246.24 (2026-06-01)

### Added

- **LAN Cowork スライス C 実機 runner（test/tooling）** — 実機 2 ノードで「直接ルート vs ピア委譲ルートの passthrough 契約パリティ（前処理差含む）」と「config 非対称（旧 E）= ピア委譲時にピア側 save_folder 等が効くこと」を検証する real-HTTP runner を `tests/lan_cowork_harness/realnode/` に追加。`corpus`/`differ`/`normalize_response` を再利用。実ノード実行は `LANCOWORK_C_RUN=1` ＋ host/peer URL・bridge・署名 credential の env gate（未設定で skip＝CI 非汚染）、署名 path は実 `request.path` 一致則を遵守。runner ロジックは `httpx.MockTransport` の 2-node 模擬で in-process 検証（CI で回る）。`python -m tests.lan_cowork_harness.realnode.run_slice_c` で結果を JSON 出力（別マシン実行→結果持ち帰り可）。host/peer の選択と実走は別途ハードウェア準備後。

## v4.246.23 (2026-06-01)

### Fixed

- **検索クエリの NUL バイトによる HTTP 500 を解消（チョークポイント修正）** — `q` に NUL（`\x00`）が非空白文字に挟まれて含まれると（例 `"a\x00b"`）、SQLite FTS5 が `unterminated string` を送出し `/api/search`・`/api/search-grouped` 等が 500 を返していた。NUL は C 文字列を途中終端するため FTS escape では無害化できない既知境界。`core/infra_core/api_params.py::get_str_arg` で全 string query 引数から NUL を除去（int-overflow clamp と同じ防御層）。完全性レビューで全 FTS MATCH sink が get_str_arg 経由であることを確認。`tests/test_api_params_property.py` に高速回帰テスト、fuzz property（`tests/fuzz/test_api_property_reads.py`、`@example(q="a\x00b")` 固定）で no-500 をガード。

### Changed

- **`tests/fuzz` 手書き burn-in を Hypothesis 戦略へ移植** — `tests/fuzz/strategies.py` を新設し `generators.py` 相当の戦略（search query/prompt/negative/collection name/bridge config/garbage JSON/file id/granularity）を定義。`tests/fuzz/test_api_property_reads.py` で read 系 5 endpoint（search-grouped・suggest/lora・stats/timeline・favorites/check・favorites/list）の no-500 property を追加し shrink・決定的再現・`@example` 固定を獲得。burn-in ループ（soak 目的）は温存。opt-in `-m fuzz`。

## v4.246.22 (2026-06-01)

### Changed

- **LAN Cowork import-transfer テストを pytest-httpx / pytest-mock 化** — `download_file`/`download_zip` テスト（`test_import_transfer_auth.py` / `test_import_executor.py`）の手書き stream mock（client+stream 二重 AsyncMock）を `httpx_mock` fixture に置換し `_mock_stream_client` ヘルパを除去。401 invalidation・`aiter_bytes`/ZIP 展開・Bearer 優先順位のアサーションは保持し、`mgr=None` 経路は `side_effect=[mgr, None]` でヘッダ生成と 401 ブランチ双方を正しく実行（実ネットワーク接続を試みていた退行も解消）。`test_remote_import_api.py` の5層ネスト `with patch` を `mocker.patch` にフラット化。

### Added

- **`docs/development/development_docs/TEST_MOCKING_TOOLS.md` 新規** — テストモックツール（pytest-timeout/responses/pytest-httpx/aioresponses/time-machine/pytest-mock）の使い分け指針を明文化。動くテストの大量 retrofit は行わず本物の簡潔化が出る箇所のみ適用する方針を記載。

## v4.246.21 (2026-06-01)

### Fixed

- **Gateway/LLM-router 型混同 500→400 ＋ 数値型ガード DRY 集約** — `/v1/chat/completions` の非 string `model`、`/v1/messages` の不正 Anthropic shape、Hailo GenAI chat の `model`/`temperature`/`max_tokens` 型不正を、認証・スコープ確認後の境界検証で 400 に収束。数値判定 helper を `core/llm_router/type_guards.py` へ集約。OpenAI messages の `role` も必須化。
- **Gateway `/v1/router/*` meta の scope 強制（authz）** — `/v1/router/{health,estimate,capabilities,capabilities/<target>}` に `llm:models`、`/v1/router/refresh` に `node:status` を要求。`/v1/models`・`/v1/node/services` との認可不統一を解消（低権限 key での inventory 参照・probe 起動を防止）。
- **LLM stream 途中失敗の表面化** — backend の途中切断/timeout/malformed SSE/翻訳・直列化例外を、無音切れではなく OpenAI error chunk / Anthropic `event: error`+`message_stop` で終端。driver は全 choices の `finish_reason` を走査し、全不正・連続 malformed・marker 欠落 EOF を `LLMRouterError` 化。
- **LAN Cowork `import_folder` の書込み先制約** — peer 由来内容の任意ディレクトリ新規書込みを、機微ディレクトリ denylist（home dotfile・`/etc`・bin/lib・Windows `AppData`/`Program Files`/`Windows` 等）で認可後に 400 拒否。正規メディアフォルダ取り込みは不変。

### Notes

- Hailo `/ext/*/v1/chat/completions` の trusted-peer IP bypass は spec `2026-04-09-trusted-peer-auth-design.md` §8 の意図的設計（IP=peer identity）として受容。実効範囲を誤読しないようコメントを追記（挙動不変）。

## v4.246.20 (2026-06-01)

### Fixed

- **分散推論の `mode="single"` を実装（tracked gap 解消）** — `BatchInferenceStrategy.select_peers()` が `mode` を無視し、`single` でも capable な全 online peer を返していた問題を修正。eligibility 抽出（`_eligible_peers`）と mode 選択（`_apply_mode`）を分離し、`single` は先頭 1 peer のみ返す（router が local を先頭に渡すため local 実行を優先）。`DisableAwareStrategy` は `_eligible_peers` override に変更し、disabled フィルタ後に single 切り詰めが効く（disabled peer が選ばれて 0 件になる退行を回避）。strict xfail だった `test_single_mode_selects_only_one_worker_documented_gap` を通常テストへ戻し、disabled-first/parallel の回帰テストを追加。

## v4.246.19 (2026-06-01)

### Added

- **テスト基盤の依存追加** — スモーク（高速既定スイート）に `pytest-timeout` を導入し、`pytest.ini` で `timeout=120` を設定。ハングしたサーバ起動・SSE・外部 API 呼び出しが CI を止めず明示的に失敗するようにした。長時間 burn-in の opt-in テスト（`fuzz` / `slow` の 4 ファイル）は `pytest.mark.timeout(0)` で除外。フルスイート向けに `responses`・`pytest-httpx`・`aioresponses`（requests/httpx/aiohttp の外部 API モック）、`pytest-mock`、`time-machine` を追加。
- **`asyncio_mode = auto`** — `pytest.ini` に追加。`async def test_*` を per-test marker 無しで asyncio として実行（anyio/trio 不使用のため安全。既存の `@pytest.mark.asyncio` も無害に共存）。フル suite（5867 passed）で auto/strict の失敗集合が完全一致することを確認し、回帰ゼロを検証済み。

### Changed

- **`hypothesis` を `[dependency-groups] dev` へ移動** — 従来 `[project.optional-dependencies] dev` にあり素の `uv sync` で入らず property テストが collection error になっていたため、常時同期される dev グループへ移設（本番依存に含めない点は不変）。新規テスト依存は `requirements.txt`（CI 系統）にも追加し parity を確保。

## v4.246.18 (2026-06-01)

### Security

- **`/api/extract-from-zip`・`/api/svg/rasterize`・`/api/open-folder` に明示 admin-scope ガードを追加（defense-in-depth）** — 先の int-overflow 完全性レビューがこれらを「未認証」と指摘したが、調査の結果 false positive（グローバル `before_request` で未認証 `/api/*` は 401、API キーは `get_required_scope` の default-deny で admin 必須）。挙動ゼロ変化のまま `_require_admin_scope()` を明示追加し、`api_file_info` との不整合を解消。authz を回帰テストで固定。

## v4.246.17 (2026-06-01)

### Fixed

- **SQLite int overflow による 500 を app-wide で解消（systemic）** — ユーザー制御 int（`<int:...>` URL converter / query param / JSON body）が `>= 2**63` で SQLite bind を overflow し HTTP 500（"Python int too large to convert to SQLite INTEGER"）になる問題を、チョークポイントで一括修正。(path) `ClampedIntConverter` を `app.url_map.converters["int"]` に登録し全 ~89 `<int:>` route を clamp。(query) `get_int_arg`・`as_int_or_none`・`safe_int` が SQLite signed-64 範囲に clamp。(body) favorites・search-union・extract-from-zip・svg-rasterize の raw int() sink を clamp。共有 `clamp_sqlite_int` ＋ `SQLITE_MIN_INT/MAX_INT`（`core/infra_core/api_params.py`）。Hypothesis API fuzz で発見、2 段階の完全性レビューで known sink を網羅。

### Added

- **API fuzz の Hypothesis property test を拡張** — `tests/fuzz/test_api_property.py`（opt-in `-m fuzz`）に search-union/extract-from-zip/svg-rasterize/未認証 `<int>` route の no-500 property を追加（`@example` で `2**63` 固定）。`tests/test_sqlite_int_clamp.py` で converter/get_int_arg/clamp の高速回帰。

## v4.246.16 (2026-06-01)

### Changed

- **tauri 2.11.1 → 2.11.2 patch 追従** — `cargo update -p tauri --precise 2.11.2`（tauri/tauri-build/tauri-codegen/tauri-macros/tauri-runtime/tauri-runtime-wry/tauri-utils）。`cargo check` 通過。

### Security (tracked, upstream-blocked)

- **Dependabot moderate 3 件（Cargo GTK3/glib 0.18 スタック）は wry の GTK4 移行待ち** — `glib 0.18.5`/`gtk`/`gdk`/`atk 0.18.2`（RUSTSEC-2024-0429 ほか）は wry 0.55.1 / tao 0.35.x が `gtk ^0.18` を pin する transitive 依存で、本リポジトリから直接修正不可。GTK3 バインディングは EOL（0.18.2 で凍結）のため「gtk-rs 0.20」は出ず、解消条件は wry/tao の WebKitGTK 6 / GTK4 backend stable リリース（未到達）。tauri patch 追従では advisory は不変。詳細は TODO 参照。


### Security

- **meta-renderer の HTML 属性インジェクション（stored-XSS 相当）を修正** — `esc()` は実 DOM の `textContent→innerHTML` で `< > &` のみ escape し `"` を escape しないため、user 制御値（tag/model/seed/section title 等）を double-quote 属性へ直接埋める箇所で `"` 混入時に属性破壊→event handler 注入の余地があった。`src/ts/meta-renderer/utils.ts` に `escAttr()`（`esc()` ＋ `"`→`&quot;`）を新設し、`core.ts`/`sections-content.ts`/`sections-file.ts` の全 `data-action-arg`/`data-copy-label` 動的値を `escAttr` 経由へ統一（numeric な `data.id`/`fileId` も runtime defense-in-depth で `escAttr(String(...))`）。リテラル `'positive'/'negative'` と `_tr(...)` 開発者翻訳は対象外。`escAttr` ユニットテスト＋ tag breakout 回帰テスト（TDD red→green）を追加。99 tests green。


### Fixed

- **`.gitignore` コメントを英語化** — v4.246.13 で追加した `.pnpm-store/` の注釈が日本語だったため、リポジトリ規則（注釈・識別子ハ英語）に合わせ英語へ修正。

## v4.246.13 (2026-06-01)

### Added

- **TS テストの jsdom 環境導入** — devDependency に `jsdom` を追加。DOM 依存テスト（`json-download` / `json-schema-validator` / `meta-renderer/sections-content`）を手書き `document`/`window` モックから実 jsdom 環境（per-file `// @vitest-environment jsdom`）へ移行し、脆い自前モックを除去。`meta-renderer sections-content` の自前 `innerHTML` エスケープ（`"` を誤って `&quot;` 化）が実 DOM 挙動とズレていた問題も解消。
- **meta-renderer `utils` の回帰テスト** — `esc()` が HTML テキスト文脈のメタ文字 `< > &` のみエスケープし `"` はエスケープしない実 DOM 挙動を固定（属性文脈で `esc()` を使う呼び出し側が手動 `.replace(/"/g,'&quot;')` を要する契約を明文化）。`toB64` の UTF-8 round-trip、`sectionOpen`/`sectionClose` も検証。

### Fixed

- **`.gitignore`**: pnpm のローカル `.pnpm-store/`（グローバルストアが別 FS の際に生成される）を除外対象に追加。


## v4.246.12 (2026-06-01)

### Fixed

- **SQLite int overflow による検索/ファイル API の 500 を修正** — `/api/search` の int 系クエリ（offset/skip/collection_id/coll/min_rating/max_rating/min_width/max_width/min_height/max_height とその別名）および `/api/file/<int:fid>` で、`>= 2**63` の値が SQLite bind を overflow し 500（"Python int too large to convert to SQLite INTEGER"）になる問題を修正。parse helper（`as_int_or_none`/`safe_int`）と offset/collection_id の clamp、ファイルルートの `_clamp_file_id` で SQLite signed-64 範囲に丸める。Hypothesis API fuzz で発見。**注**: 同クラスが他 13+ endpoint（うち 3 件未認証）に残存（TODO 追跡、別途一括対応予定）。

### Added

- **API fuzz の Hypothesis property test** — `tests/fuzz/test_api_property.py`（opt-in `-m fuzz`）で search/suggest/file/favorites/collections の no-500 を property 検証（offset=2**63 を `@example` 固定）。`tests/test_search_params_clamp.py` で clamp の高速回帰。fuzz harness の fixture 破損（init_app_paths 未呼び出し）も修復。

## v4.246.11 (2026-06-01)

### Fixed

- **TaggerProfile.from_dict 入力堅牢化** — ユーザー drop-in profile JSON の型ミス入力（`files[]` 非 dict / `size_hint_mb` 非数値 / `supports_categories` 非 list・非 str 要素 / `tag_source`・`threshold_source` 非 dict / `tag_source.category_map` 非 dict・非 str 値）で、宣言例外でなく未捕捉の `AttributeError`/`TypeError` が送出され profile ロードがクラッシュしうる問題を修正。全て `ValueError` に収束。Hypothesis property test で発見。

### Added

- **crypto-identity 高速プリミティブの Hypothesis property test** — Ed25519 sign/verify round-trip・tamper/wrong-key 拒否・verifier の no-throw、canonical message 決定性、peer_id/fingerprint/SAS の format・決定性を property 化（反例なし＝堅牢確認）。
- **TaggerProfile robustness の property/回帰テスト** — `from_dict` は宣言例外のみ送出することを property 検証＋ hostile 型の回帰ケースを固定。

## v4.246.10 (2026-06-01)

### Fixed

- **分散推論 Whisper/Tagger の部分失敗表面化＋契約是正** — CLIP/YOLO に続き Whisper/Tagger の分散結果ハンドラを修正。Tagger: worker_client が `ok is True` と `tags` list を要求（`{"ok": false}` を確定保存しない）、保存失敗・不正 payload を `errors` 計上し保存成功時のみ `tagged` 加算。Whisper: クライアントを `{"ok": True}` 契約へ是正（peer endpoint と一致、legacy `status:"ok"` も後方互換許容）、`text:str`/`segments:list` 以外を保存せず `errors` 計上、`_run_distributed_batch` 呼び出しの `emit_progress` 引数欠落（実行時エラー）を修正。正規空（タグ無し・無音声）と失敗を厳密に区別。fake-worker ハーネスで回帰を固定。
- follow-up: Tagger の正規空を `empty` として会計・表示し、`tagged + empty + errors == done` を維持。Whisper client 側でも `text:str`/`segments:list` 検証を実施して peer 文脈ログを残すようにした。

## v4.246.9 (2026-06-01)

### Fixed

- **タグ正規化の冪等性バグ** — `normalize_tag` が NFKC を underscore->space の後に実行していたため、NFKC で ASCII underscore を生成する 6 コードポイント（U+FE33/FE34/FE4D/FE4E/FE4F/FF3F、全角アンダースコア系）で `normalize_tag("＿")=="_"` だが `normalize_tag("_")==""` となり非冪等。保存済み `tag_name_normalized` と検索クエリ再正規化形が食い違い検索ミスを生んでいた。パイプライン順序を NFKC→underscore->space に修正。既存 DB は migration 78（`CURRENT_SCHEMA_VERSION` 77→78）で該当 6 文字を含む行のみ限定再正規化。Hypothesis ベースの BMP 全走査で発見。

### Added

- **純粋関数スイートの Hypothesis property test** — escape round-trip / FTS5・LIKE helpers（実 trigram FTS5 で構文妥当性検証）/ normalize_tag 冪等性 / get_int_arg clamp / search cursor round-trip を property 化（Tier S 完了）。NUL 境界 2 件は `xfail(strict=True)` で文書化。

## v4.246.8 (2026-06-01)

### Fixed

- **Fleet 設定ローカルテーブルの ReferenceError** — `fleet-tabs-settings.js` の `renderSettingsLocalTable` 内にリモートステータステーブル描画から紛れ込んだ死にコード（`st`/`btnGrant`/`btnRevoke` 参照）が、peer を 1 件以上描画する際に `ReferenceError: st is not defined` を投げ Fleet 管理画面の初期描画をクラッシュさせていた問題を修正。ローカルテーブルは読み取り専用で全 checkbox を `disabled` 済みのため当該ブロックは機能上も不要であり削除。

## v4.246.7 (2026-06-01)

### Fixed

- **分散推論の部分失敗表面化** — CLIP/YOLO の result handler を単一の会計源とし、`processed + errors == total` を batch 単位で満たすよう修正。CLIP remote の `None`/不足 vector と誤次元 vector、保存失敗を `errors` に計上し、`output_dim` 不明時は 512 fallback ではなく次元検査をスキップ。YOLO remote の `None`/不足 detection は正規の空検出 `[]` と区別して保存せず、skip 理由を batch 終端ログに表面化。`batch_size<=0` は無音 no-op ではなく明示エラーに変更し、fake-worker ハーネスで回帰を固定。

## v4.246.6 (2026-06-01)

### Tests

- **LAN Cowork cancel-effect tracked gaps** — ComfyUI direct `/api/cancel` の `task_id` 経路が `task_registry.cancel_task()` 経由で status/error_message/cancel callback を反映すること、および NAI cancel handler が client-side-only marker を返して `GEN_CANCEL` を emit することを固定。

## v4.246.5 (2026-06-01)

### Fixed

- **LAN Cowork peer/Fleet trust-boundary input validation Batch 2** — `/api/peer/infer/clip-encode`、`/api/peer/infer/yolo-detect`、`/api/peer/infer/tag` の不正画像 bytes を decode 起因例外に限定して 400 (`invalid image data`) へ収束。session/local-chief gated Fleet 経路（peer grant/revoke、update/restart dispatch、consent request/respond/relay request）にも認可後 `require_json_dict` を追加し、非 dict JSON body による 500 を防止。

## v4.246.4 (2026-06-01)

### Fixed

- **LAN Cowork peer/Fleet trust-boundary input validation Batch 1** — peer 認証通過後の `/api/peer/sync/push`、`/api/peer/negotiate`、`/fleet/update`、`/fleet/allowlists/grant|revoke` に型ゲートを追加。既存認可チェックの後に配置し、sync/push の base64 と negotiate の `requirements` は Pydantic model validator/field に集約。Fleet update の `source`/`branch`、allowlist `categories` の非 dict body・非 string 要素を 400 に収束し、sink 到達前の 500 を防止。
## [4.679.2] - 2026-08-29

### Fixed

- `setup-ai-tools.ps1` は既存の `lean-ctx` バイナリ更新に失敗した場合、cargo ソースビルドへフォールバックするよう改めた。
