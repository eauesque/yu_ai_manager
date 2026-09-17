"""MCP interceptor: Kill Switch + Circuit Breaker + Budget + Scope + HITL Gate."""

import contextlib
import json as _json_mod
import time as _time

from mcp.types import CallToolResult, TextContent

from .facade import unwrap_facade
from .interceptor import (
    _summarize_result,
    capture_undo_before,
    check_hitl_gate,
    pre_check,
    record_error,
    record_success,
)


def _blocked_result(msg: str) -> CallToolResult:
    """Return a blocked response as CallToolResult.

    The lowlevel server returns CallToolResult as-is,
    bypassing outputSchema validation.
    """
    return CallToolResult(
        content=[TextContent(type="text", text=msg)],
        isError=True,
    )


def install_interceptor(mcp) -> None:
    """Hook safety checks and Action Journal recording into MCP tool calls."""
    _original_call_tool = mcp._tool_manager.call_tool

    async def _intercepted_call_tool(name: str, arguments: dict, **kwargs):
        # A facade call arrives as {"action": ..., "args": {...}}. Every check
        # below keys on the tool name AND on the argument keys, so both must be
        # recovered first — otherwise the scope fence's fnmatch patterns and
        # classify_tool's prefix table stop matching (they fail OPEN, not shut),
        # and params.get("items"/"file_ids") readers see the envelope instead of
        # the real arguments, silently zeroing batch-size anomaly detection and
        # undo capture. See docs/development/development_docs/spec-mcp-tool-facade.md §4.
        eff_name, eff_args = unwrap_facade(name, arguments)
        # The facade's own name stays deny-able: a scope rule written against
        # yu_tagger must still stop the whole domain.
        facade_name = name if eff_name != name else None

        # Sync checks: Kill Switch -> Circuit Breaker -> Budget -> Scope Fence
        block_msg = pre_check(eff_name, facade_name=facade_name)
        if block_msg:
            return _blocked_result(block_msg)

        # Async check: HITL Gate (Level 2 waits for approval)
        hitl_msg = await check_hitl_gate(eff_name, eff_args)
        if hitl_msg:
            return _blocked_result(hitl_msg)

        # Undo: capture pre-state
        undo_before = capture_undo_before(eff_name, eff_args)

        start = _time.monotonic()
        try:
            result = await _original_call_tool(name, arguments, **kwargs)
            duration_ms = int((_time.monotonic() - start) * 1000)
            # Extract result text and summarize
            summary = ""
            result_data = None
            # When convert_result=True, -> str tools return a tuple
            content_items = result
            if isinstance(result, tuple) and len(result) == 2:
                content_items = result[0]  # unstructured part
            if isinstance(content_items, list):
                for item in content_items:
                    if hasattr(item, "text"):
                        summary = _summarize_result(item.text)
                        # Parse JSON response as result_data
                        with contextlib.suppress(Exception):
                            result_data = _json_mod.loads(item.text)
                        break
            record_success(
                eff_name, eff_args, duration_ms, summary,
                undo_before=undo_before, result_data=result_data,
            )
            return result
        except Exception as exc:
            duration_ms = int((_time.monotonic() - start) * 1000)
            record_error(eff_name, eff_args, duration_ms, str(exc))
            raise

    mcp._tool_manager.call_tool = _intercepted_call_tool
