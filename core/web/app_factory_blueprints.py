"""Blueprint registration helpers for Quart app factory."""

from quart import Quart


def register_blueprints(app: Quart) -> None:
    """Register all built-in route blueprints."""
    from core.lan_share.share_routes import bp as lan_share_bp
    from routes import (
        analysis,
        apikeys,
        collections,
        debug,
        diagnostics,
        events,
        extensions,
        favorites,
        files,
        hailo_tagger,
        inference_info,
        monthly_report,
        pages,
        profiles,
        ratings,
        scan,
        scan_roots,
        search,
        share,
        sns_share,
        stats,
        sweep_routes,
        tagger_servers,
        tags,
        tauri_shell,
        tools,
        trophies,
        update_package,
        video_analysis,
        wd_tagger,
        zip_files,
    )

    app.register_blueprint(pages.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(stats.bp)
    app.register_blueprint(files.bp)
    app.register_blueprint(scan.bp)
    app.register_blueprint(scan_roots.bp)
    app.register_blueprint(tauri_shell.bp)
    app.register_blueprint(tools.bp)
    app.register_blueprint(zip_files.bp)
    app.register_blueprint(sweep_routes.bp)
    app.register_blueprint(share.bp)
    app.register_blueprint(debug.bp)
    app.register_blueprint(diagnostics.bp)
    app.register_blueprint(update_package.bp)
    app.register_blueprint(analysis.bp)
    app.register_blueprint(extensions.bp)
    app.register_blueprint(favorites.bp)
    app.register_blueprint(ratings.bp)
    app.register_blueprint(collections.bp)
    app.register_blueprint(profiles.bp)
    app.register_blueprint(lan_share_bp)
    app.register_blueprint(tags.bp)
    app.register_blueprint(apikeys.bp)
    app.register_blueprint(wd_tagger.bp)
    app.register_blueprint(hailo_tagger.bp)
    app.register_blueprint(tagger_servers.bp)
    from routes import mesh_inference_api
    app.register_blueprint(mesh_inference_api.bp)
    app.register_blueprint(video_analysis.bp)
    app.register_blueprint(inference_info.bp)
    app.register_blueprint(monthly_report.bp)
    app.register_blueprint(trophies.bp)
    app.register_blueprint(sns_share.bp)

    from routes.help import bp as help_bp
    app.register_blueprint(help_bp)

    from routes.mcp_endpoint import bp as mcp_endpoint_bp
    app.register_blueprint(mcp_endpoint_bp)

    from core.infra_core.openapi_gen import bp as openapi_bp
    app.register_blueprint(openapi_bp)

    from routes.logs_api import bp as logs_api_bp
    app.register_blueprint(logs_api_bp)

    from routes.ocr_api import bp as ocr_bp
    app.register_blueprint(ocr_bp)

    from routes.ui_api import bp as ui_api_bp
    app.register_blueprint(ui_api_bp)

    from routes.settings_manage import bp as settings_manage_bp
    app.register_blueprint(settings_manage_bp)

    from routes.agent_api import bp as agent_api_bp
    app.register_blueprint(agent_api_bp)

    from routes.scheduler_api import bp as scheduler_bp
    app.register_blueprint(scheduler_bp)

    from routes.source_api import bp as source_api_bp
    app.register_blueprint(source_api_bp)

    from routes.svg_api import bp as svg_api_bp
    app.register_blueprint(svg_api_bp)

    from routes.update_api import bp as update_api_bp
    app.register_blueprint(update_api_bp)

    from routes.llm_endpoints import bp as llm_endpoints_bp
    app.register_blueprint(llm_endpoints_bp)

    from routes.llm_router import bp as llm_router_bp
    app.register_blueprint(llm_router_bp)

    from routes.llm_router_admin import bp as llm_router_admin_bp
    app.register_blueprint(llm_router_admin_bp)

    from routes.gateway_status import bp as gateway_status_bp
    app.register_blueprint(gateway_status_bp)

    from routes.gateway_admin import bp as gateway_admin_bp
    app.register_blueprint(gateway_admin_bp)

    from routes.gateway_admin_token import bp as gateway_admin_token_bp
    app.register_blueprint(gateway_admin_token_bp)

    from routes.gateway_sd import bp as gateway_sd_bp
    app.register_blueprint(gateway_sd_bp)

    from routes.gateway_comfy import bp as gateway_comfy_bp
    app.register_blueprint(gateway_comfy_bp)

    from routes.gateway_ollama import bp as gateway_ollama_bp
    app.register_blueprint(gateway_ollama_bp)

    from routes.gateway_gradio import bp as gateway_gradio_bp
    app.register_blueprint(gateway_gradio_bp)
    from routes.gateway_agentmemory import bp as gateway_agentmemory_bp
    app.register_blueprint(gateway_agentmemory_bp)
    from routes.gateway_agentmemory import bp_dash as agentmemory_dash_bp
    app.register_blueprint(agentmemory_dash_bp)
    from routes.gateway_agentmemory import bp_config as agentmemory_config_bp
    app.register_blueprint(agentmemory_config_bp)

    from routes.server_info import bp as server_info_bp
    app.register_blueprint(server_info_bp)

    from routes.mdns_identity import bp as mdns_identity_bp
    app.register_blueprint(mdns_identity_bp)

    from routes.maintenance import bp as maintenance_bp
    app.register_blueprint(maintenance_bp)

    from routes.recipe import bp as recipe_bp
    app.register_blueprint(recipe_bp)

    from routes.crypto_tools import bp as crypto_tools_bp
    app.register_blueprint(crypto_tools_bp)

    from routes.shutdown_api import bp as shutdown_api_bp
    app.register_blueprint(shutdown_api_bp)

    from routes.gateway_backends import bp as gateway_backends_bp
    app.register_blueprint(gateway_backends_bp)

    from routes.headroom_api import bp as headroom_api_bp
    app.register_blueprint(headroom_api_bp)
    from routes.headroom_api import bp_config as headroom_config_bp
    app.register_blueprint(headroom_config_bp)
    from routes.gateway_headroom_llm import bp as gateway_headroom_llm_bp
    app.register_blueprint(gateway_headroom_llm_bp)

    from routes.file_trace import bp as file_trace_bp
    app.register_blueprint(file_trace_bp)

    from routes.workflow_params import bp as workflow_params_bp
    app.register_blueprint(workflow_params_bp)

    from routes.ai_context import bp as ai_context_bp
    app.register_blueprint(ai_context_bp)

    app.register_blueprint(events.sse_bp)
    app.register_blueprint(events.webhooks_bp)
    app.register_blueprint(events.webhooks_inbound_bp)
