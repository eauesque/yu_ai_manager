"""Standalone Python inference service — Phase 3 分離サービス.

yu-server (Rust) からのプロキシを受け付け、AI推論を実行するサブプロセスサービス。
ポート: 5001 (デフォルト)

起動例:
    uv run python deploy/inference_service.py --port 5001 --db data/tags.db
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from quart import Quart

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("inference_service")


def create_app(db_path: str) -> Quart:
    app = Quart(__name__)
    app.config["DB_PATH"] = db_path

    # 推論系ルートのみ登録
    from routes.mesh_inference_api import bp as mesh_inference_bp
    from routes.tagger_servers import bp as tagger_servers_bp
    from routes.wd_tagger import bp as wd_tagger_bp

    app.register_blueprint(tagger_servers_bp)
    app.register_blueprint(mesh_inference_bp)
    app.register_blueprint(wd_tagger_bp)

    try:
        from routes.hailo_tagger import bp as hailo_bp
        app.register_blueprint(hailo_bp)
    except ImportError:
        logger.info("hailo_tagger not available — skipping")

    try:
        from routes.inference_info import bp as inference_info_bp
        app.register_blueprint(inference_info_bp)
    except ImportError:
        logger.info("inference_info not available — skipping")

    @app.route("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "inference"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Yu AI Manager — Inference Service")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--db", default="data/tags.db", help="SQLite DB path")
    args = parser.parse_args()

    app = create_app(args.db)
    logger.info("inference_service starting on %s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
