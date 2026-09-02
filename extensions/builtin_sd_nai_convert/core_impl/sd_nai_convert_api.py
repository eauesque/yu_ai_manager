"""Quart blueprint factory for SD<->NAI conversion APIs."""

from quart import Blueprint, jsonify, render_template, request

from .sd_nai_convert_handlers import handle_batch_convert, handle_nai_to_sd, handle_sd_to_nai


def create_sd_nai_convert_blueprint(import_name: str):
    bp = Blueprint("ext_sd_nai_convert", import_name, template_folder="templates")

    @bp.route("/")
    async def convert_ui():
        return await render_template("convert.html")

    @bp.route("/sd-to-nai", methods=["POST"])
    async def api_sd_to_nai():
        data = await request.get_json(silent=True) or {}
        payload, status = handle_sd_to_nai(data)
        return jsonify(payload), status

    @bp.route("/nai-to-sd", methods=["POST"])
    async def api_nai_to_sd():
        data = await request.get_json(silent=True) or {}
        payload, status = handle_nai_to_sd(data)
        return jsonify(payload), status

    @bp.route("/batch", methods=["POST"])
    async def api_batch_convert():
        data = await request.get_json(silent=True) or {}
        payload, status = handle_batch_convert(data)
        return jsonify(payload), status

    return bp
