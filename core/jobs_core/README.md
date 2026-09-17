# core/jobs_core

バックグラウンドジョブ管理の実装本体。

- `jobs.py`: 公開集約 (`job_manager`)
- `jobs_manager.py`: JobManager
- `jobs_model.py`: Jobモデル

依存方向: `core/jobs*.py` (compat) -> `core/jobs_core/*`
