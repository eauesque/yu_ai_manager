# core/models_core

DB CRUD モデル補助の実装本体。

- `models.py`: 公開集約（files/tags/templates）
- `models_files.py`: files テーブル
- `models_tags.py`: tags/file_tags テーブル
- `models_templates.py`: templates 集約
- `models_template_model_info.py`: model名/hash 抽出
- `models_template_write.py`: templates/token 書き込み

依存方向: `core/models*.py` (compat) -> `core/models_core/*`
