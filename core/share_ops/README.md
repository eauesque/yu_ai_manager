# share_ops

責務: Share API のペイロード生成ロジック。

## Files

- `data_ops.py`: 互換ファサード（公開関数の入口）
- `payload_build.py`: DB行から share payload を構築
- `prompt_extract.py`: raw prompt/meta から共通パラメータ抽出

## Dependency

- `routes/share.py -> routes/share_ops/data_ops.py`
- `data_ops.py -> payload_build.py -> prompt_extract.py`
- `prompt_extract.py -> core.prompt_parser`

## Notes

- 新規コードは `data_ops.py` ではなく `payload_build.py` へ追加する。
