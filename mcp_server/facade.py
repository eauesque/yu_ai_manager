"""Collapse a hub's tools into a single action-dispatch tool.

Each hub's ``register_*`` takes the FastMCP server as an argument and decorates
its functions with ``@mcp.tool()``. Passing a collector that quacks like FastMCP
captures those functions instead of registering them, so a hub's 27 tools become
one ``yu_<domain>`` tool with an ``action`` argument — without touching a single
hub function.

Argument validation is NOT reimplemented here: each collected function is wrapped
in FastMCP's own ``Tool``, so ``Tool.run()`` applies the same pydantic model,
coercion and async handling it would have applied to a directly registered tool.

Safety: the interceptor keys every check on the tool name and arguments, so a
facade call must be unwrapped before those checks run. See ``unwrap_facade`` and
``mcp_server/server_interceptor.py``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools.base import Tool

ENV_VAR = "YU_MCP_FACADE"

#: Max characters of summary text published per action (spec §3 D-1).
ACTION_SUMMARY_BUDGET = 100


@dataclass(frozen=True)
class FacadeSpec:
    """One facade tool and the hubs whose tools it absorbs."""

    name: str
    title: str
    hubs: tuple[str, ...]


#: Stage 1 (spec §7). Hub names match ``server_registration_manifest`` entries.
#:
#: Never listed here, by design (spec §2.1 / §9):
#:   server_tools      - the most-used surface; an extra round trip costs most
#:   wait_tools        - takes a Context, which a facade cannot carry
#:   diagnostics_tools - returns dict, i.e. publishes an output schema
#: ``_reject_if_unfacadeable`` enforces the last two mechanically.
FACADE_SPECS: tuple[FacadeSpec, ...] = (
    # --- stage 1 -----------------------------------------------------------
    FacadeSpec("yu_agent", "Agent safety", ("agent_safety_tools",)),
    FacadeSpec("yu_tagger", "WD Tagger", ("wd_tagger_tools",)),
    FacadeSpec("yu_github", "GitHub", ("github_tools",)),
    FacadeSpec("yu_comfyui", "ComfyUI bridge", ("comfyui_bridge_tools",)),
    FacadeSpec(
        "yu_hailo",
        "Hailo",
        ("hailo_chat_tools", "hailo_genai_tools", "hailo_tagger_tools"),
    ),
    FacadeSpec("yu_sd", "Stable Diffusion and NovelAI bridges",
               ("sd_bridge_tools", "sd_nai_convert_tools", "nai_bridge_tools")),
    FacadeSpec("yu_yolo", "YOLO", ("yolo_detect_tools", "yolo_stream_tools")),
    # --- stage 2 -----------------------------------------------------------
    FacadeSpec("yu_misc", "Assorted file, media and server", ("misc_tools",)),
    FacadeSpec("yu_analysis", "Image analysis and tagger servers",
               ("analysis_tools", "tagger_servers_tools")),
    FacadeSpec("yu_extension", "Extensions", ("extension_tools",)),
    FacadeSpec("yu_prompt", "Prompt library",
               ("prompt_library_tools", "prompt_sim_tools", "prompt_syntax_tools")),
    FacadeSpec("yu_scan", "Scan roots and duplicates",
               ("scan_roots_tools", "auto_scan_tools", "duplicate_tools")),
    FacadeSpec("yu_settings", "Settings, profiles and UI",
               ("settings_tools", "profiles_tools", "ui_tools", "dnd_tools")),
    FacadeSpec("yu_chatlog", "Chat logs", ("chatlog_tools",)),
    FacadeSpec("yu_ocr", "OCR and speech-to-text", ("ocr_tools", "s2t_tools")),
    FacadeSpec("yu_lora", "LoRA dataset", ("lora_dataset_tools",)),
    FacadeSpec("yu_share", "SNS share and markdown viewer",
               ("sns_share_tools", "md_viewer_tools")),
    FacadeSpec("yu_llm", "LLM endpoints and router", ("llm_tools",)),
    FacadeSpec("yu_search", "Semantic and cross search",
               ("semantic_tools", "cross_search_tools")),
    FacadeSpec("yu_automation", "Webhooks, scheduler, MCP clients and boss mode",
               ("webhook_tools", "scheduler_tools", "mcp_client_tools", "boss_mode_tools")),
    FacadeSpec("yu_debug", "Debug and validation", ("debug_tools",)),
    FacadeSpec("yu_fleet", "Fleet, mesh, gateway and LAN share",
               ("fleet_tools", "freeze_pullback_tools", "mesh_inference_tools",
                "mesh_inference_toggle_tools", "lan_share_tools", "gateway_tools")),
    FacadeSpec("yu_maintenance", "Backup, archive, update and reports",
               ("backup_tools", "archive_cleanup_tools", "update_tools", "stats_tools",
                "monthly_report_tools", "download_tools", "svg_tools", "source_tools",
                "tag_dict_tools", "favorites_tools", "trophy_tools", "help_tools")),
)

#: Hubs deliberately left registered directly. Every hub must be either absorbed
#: by a FACADE_SPEC or listed here; ``test_every_hub_is_accounted_for`` fails
#: otherwise, so a newly added hub cannot sit unabsorbed by accident (which is
#: exactly how nai_bridge_tools was missed while writing stage 2).
KEEP_DIRECT: frozenset[str] = frozenset(
    {
        # The most-used surface: an extra round trip costs most here.
        "server_tools",
        # Takes a Context. FastMCP injects it from the REGISTERED function's
        # signature, so inside a facade it arrives as None and the progress
        # notifications are swallowed by contextlib.suppress.
        "wait_tools",
        # Returns dict and publishes no output schema; a facade would have to
        # re-serialise it, changing the text a client sees.
        "diagnostics_tools",
    }
)

#: facade name -> action name -> Tool. Populated at registration.
_REGISTRY: dict[str, dict[str, Tool]] = {}



def facade_enabled() -> bool:
    """``YU_MCP_FACADE=0`` falls back to registering every tool directly."""
    return os.environ.get(ENV_VAR, "1").strip().lower() not in {"0", "false", "off", "no"}


def hubs_absorbed_by_facades() -> frozenset[str]:
    return frozenset(hub for spec in FACADE_SPECS for hub in spec.hubs)


def facade_names() -> frozenset[str]:
    return frozenset(_REGISTRY)


def registered_actions(facade_name: str) -> frozenset[str]:
    return frozenset(_REGISTRY.get(facade_name, ()))


def all_actions() -> dict[str, str]:
    """action name -> facade name, across every registered facade."""
    return {action: facade for facade, tools in _REGISTRY.items() for action in tools}


def resolve(facade_name: str, action: str) -> Tool | None:
    return _REGISTRY.get(facade_name, {}).get(action)


def unwrap_facade(name: str, arguments: dict | None) -> tuple[str, dict]:
    """Recover the effective tool name and arguments from a facade call.

    Only a *known* action of that facade is unwrapped. An unknown action keeps
    the facade's own name, so a caller cannot push an arbitrary string into the
    scope fence's fnmatch patterns or into ``classify_tool``'s prefix table by
    inventing an action (spec §4 S-2).
    """
    arguments = arguments or {}
    if name not in _REGISTRY:
        return name, arguments
    action = arguments.get("action")
    if not isinstance(action, str) or action not in _REGISTRY[name]:
        return name, arguments
    args = arguments.get("args")
    return action, dict(args) if isinstance(args, dict) else {}


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _summary(tool: Tool) -> str:
    line = _first_line(tool.description)
    if len(line) > ACTION_SUMMARY_BUDGET:
        line = line[: ACTION_SUMMARY_BUDGET - 1].rstrip() + "…"
    return line


#: How many optional arguments to name inline before eliding the rest.
#: Required arguments are always named in full — they are what a caller cannot
#: supply by guessing, and naming them is what removes the yu_help round trip.
#: Optional ones are capped because comfyui_generate alone has 19 of them and
#: printed a 310-character line.
OPTIONAL_ARGS_SHOWN = 4


def _signature(tool: Tool) -> str:
    """``(file_id, limit?, +3?)`` — required args in full, optional ones capped.

    Measured: without argument names, 302 of 607 actions named no required
    argument anywhere in their published line, so a caller had to spend a
    yu_help round trip or guess. See scripts/internal/measure_facade_roundtrips.py.
    """
    params = tool.parameters or {}
    props = list(params.get("properties") or {})
    required = [p for p in props if p in (params.get("required") or [])]
    optional = [p for p in props if p not in required]
    parts = list(required) + [f"{p}?" for p in optional[:OPTIONAL_ARGS_SHOWN]]
    if len(optional) > OPTIONAL_ARGS_SHOWN:
        parts.append(f"+{len(optional) - OPTIONAL_ARGS_SHOWN}?")
    return f"({', '.join(parts)})"


def build_description(spec: FacadeSpec, tools: dict[str, Tool]) -> str:
    table = "\n".join(
        f"- {name}{_signature(tools[name])}: {_summary(tools[name])}" for name in sorted(tools)
    )
    example = next(iter(sorted(tools)), "some_action")
    return (
        f"{spec.title} operations. Pass one of the actions below as `action`, "
        f"with that action's arguments as `args` "
        f'(e.g. {{"action": "{example}", "args": {{}}}}). '
        f"Arguments are listed per action; `?` marks an optional one and "
        f"`+N?` means N further optional arguments. "
        f"Call `yu_help` for an action's full description and every argument."
        f"\n\nActions:\n{table}"
    )


class UnfacadeableTool(RuntimeError):
    """A tool whose wire behaviour a facade cannot reproduce.

    Raised at registration, not at call time: a tool that loses its Context or
    its structured output fails *silently* (progress notifications are swallowed
    by contextlib.suppress; structuredContent simply stops being sent), so the
    only honest moment to notice is startup.
    """


def _is_plain_str_output(schema: dict) -> bool:
    """True when the schema is the one FastMCP derives from ``-> str``.

    Every ``-> str`` tool publishes ``{"result": {"type": "string"}}``; only the
    schema *title* differs per tool. A facade also returns str, so absorbing such
    a tool leaves the structuredContent shape unchanged. A tool returning dict
    (or anything else) publishes a different shape and must stay direct.
    """
    props = schema.get("properties") or {}
    return (
        schema.get("type") == "object"
        and set(props) == {"result"}
        and props["result"].get("type") == "string"
        and schema.get("required") == ["result"]
    )


def _reject_if_unfacadeable(tool: Tool, facade_name: str) -> None:
    if tool.context_kwarg is not None:
        raise UnfacadeableTool(
            f"{facade_name}: {tool.name} takes a Context ({tool.context_kwarg!r}). "
            "FastMCP injects Context from the REGISTERED function's signature, so "
            "inside a facade it would arrive as None and the tool's progress "
            "notifications would vanish without raising. Keep this hub direct."
        )
    schema = tool.output_schema
    if schema is not None and not _is_plain_str_output(schema):
        raise UnfacadeableTool(
            f"{facade_name}: {tool.name} publishes a non-str output schema "
            f"({sorted(schema.get('properties') or {})}). A facade returns str, "
            "so its structuredContent shape would change. Keep this hub direct."
        )


class ToolCollector:
    """Quacks like FastMCP for ``@mcp.tool`` / ``@mcp.resource``, but collects.

    Resources are passed through to the real server: there are only two and they
    are not tools, so they have nothing to do with the facade.
    """

    def __init__(self, real: FastMCP) -> None:
        self.tools: dict[str, Tool] = {}
        self._real = real

    def tool(self, *, name=None, description=None, **kwargs) -> Callable:
        def deco(fn):
            # description= is the only text some hubs have (debug_tools.py).
            tool = Tool.from_function(fn, name=name, description=description, **kwargs)
            self.tools[tool.name] = tool
            return fn

        return deco

    def resource(self, *args, **kwargs):
        return self._real.resource(*args, **kwargs)


def _unknown_action(facade_name: str, action: object) -> str:
    return json.dumps(
        {
            "error": f"unknown action {action!r} for {facade_name}",
            "available": sorted(_REGISTRY.get(facade_name, ())),
        },
        ensure_ascii=False,
    )


def register_facade(
    mcp: FastMCP,
    client,
    spec: FacadeSpec,
    registrars: Iterable[Callable],
) -> dict[str, Tool]:
    """Collect ``registrars``' tools and publish them as one facade tool."""
    collector = ToolCollector(mcp)
    for registrar in registrars:
        registrar(collector, client)
    tools = collector.tools
    if not tools:
        raise RuntimeError(f"facade {spec.name} collected no tools from {spec.hubs}")
    for tool in tools.values():
        _reject_if_unfacadeable(tool, spec.name)
    _REGISTRY[spec.name] = tools

    facade_name = spec.name

    async def dispatch(action: str, args: dict | None = None) -> str:
        tool = _REGISTRY[facade_name].get(action)
        if tool is None:
            return _unknown_action(facade_name, action)
        result = await tool.run(args or {})
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    dispatch.__name__ = facade_name
    mcp.tool(name=facade_name, description=build_description(spec, tools))(dispatch)
    return tools


def register_help_tool(mcp: FastMCP) -> None:
    """Publish the full description of an action that a facade only summarises."""

    def yu_help(action: str) -> str:
        """Show an action's full description and argument schema.

        Args:
            action: An action name listed by one of the yu_* facade tools.
        """
        for facade_name, tools in _REGISTRY.items():
            tool = tools.get(action)
            if tool is not None:
                return json.dumps(
                    {
                        "facade": facade_name,
                        "action": action,
                        "description": tool.description,
                        "arguments": tool.parameters,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
        return json.dumps(
            {"error": f"unknown action {action!r}", "facades": sorted(_REGISTRY)},
            ensure_ascii=False,
        )

    mcp.tool(name="yu_help")(yu_help)


def reset_for_tests() -> None:
    _REGISTRY.clear()


def snapshot_registry() -> dict[str, dict[str, Tool]]:
    """Copy the registry so a test can restore it.

    The registry is process-global: ``mcp_server.server`` fills it at import, and
    a test that builds its own facade must not leave the real one empty for every
    later test in the session.
    """
    return {facade_name: dict(tools) for facade_name, tools in _REGISTRY.items()}


def restore_registry(snapshot: dict[str, dict[str, Tool]]) -> None:
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)
