"""MCP tools for monthly report."""

import json


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_monthly_report_tools(mcp, client):
    @mcp.tool()
    def get_monthly_report(month: str = "") -> str:
        """Get monthly statistics report with rankings and trends.

        Args:
            month: Month in YYYY-MM format (default: current month)
        """
        params = {}
        if month:
            params["month"] = month
        return _json(client.get("/api/stats/monthly-report", params))
