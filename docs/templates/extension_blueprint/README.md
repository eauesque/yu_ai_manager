# Extension Blueprint Template

このテンプレートは `scripts/new_extension.py` で使用される雛形です。

## 使い方

```bash
uv run python scripts/new_extension.py <name>
uv run python scripts/new_extension.py <name> --type simple  # API のみ
uv run python scripts/new_extension.py <name> --dry-run      # 確認のみ
```

## Scope Gate ルール（必須）

`POST` / `PUT` / `DELETE` / `PATCH` メソッドを持つ全ルートは、
**request body 処理（`request.get_json()` / `await run_db_sync()` 等）より前に**
以下のいずれかを無条件で呼び出すこと:

- `require_admin_scope()` — API キーの admin スコープを検証
- `require_local()` — localhost からのアクセスのみ許可
- `require_pin()` — PIN 認証済みセッションを検証

### NG パターン（pre-push で FAIL になる）

```python
# NG: request body を読んでから guard
@bp.route("/api/foo", methods=["POST"])
async def handler():
    data = await request.get_json()  # ← 先に読んでいる
    auth_err = _require_admin_scope()  # ← 遅い
    ...

# NG: 条件分岐の中
@bp.route("/api/foo", methods=["POST"])
async def handler():
    if condition:
        auth_err = _require_admin_scope()  # ← 条件付き
    ...
```

### OK パターン

```python
# OK: guard が最初
@bp.route("/api/foo", methods=["POST"])
async def handler():
    auth_err = _require_admin_scope()  # ← 先頭
    if auth_err:
        return auth_err
    data = await request.get_json()
    ...
```

### 意図的に公開するエンドポイント

```python
# nosec: scope-gate — public webhook, HMAC verified downstream
@bp.route("/api/webhook", methods=["POST"])
async def handler():
    ...
```

`# nosec: scope-gate` はデコレータの直前行に記述すること。
