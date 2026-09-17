"""MCP API service layer.

JSON-RPC handler dispatch + auth (localhost / API key) for the /mcp HTTP
endpoint. Routes layer (``routes/mcp_endpoint.py``) registers the HTTP
blueprint and delegates here.
"""
