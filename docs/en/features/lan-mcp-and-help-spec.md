# LAN MCP Access & Help Endpoint Specification

**Implementation version**: 3.1.0
**Related documentation**: `docs/en/features/mcp-integration-guide.md`
**Related files**: `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## Overview

1. **LAN MCP Access** — Allow MCP clients on the LAN to connect to the MCP endpoint by IP address when LAN sharing mode is enabled
2. **`/help` Endpoint** — Provide a built-in web manual for the application (also published as an MCP resource)

---

## 1. LAN MCP Access

### 1-1. Architecture

Over the LAN, MCP clients connect directly to the YU AI Manager `/mcp` endpoint using HTTP/SSE transport.

### 1-2. MCP SSE Endpoint

| Item | Details |
|------|------|
| Endpoint | `/mcp` (SSE + message posting) |
| Transport | HTTP + Server-Sent Events (SSE) |
| Authentication | Not required from localhost. API key required from LAN IPs |

### 1-3. API Key Authentication

The existing API key management mechanism (`/api/keys`) is reused.

### 1-4. Settings UI

A LAN MCP connection configuration snippet (HTTP version) is added to the Settings > API Keys tab.

---

## 2. `/help` Endpoint

### 2-1. Design Principles

- Fully offline
- Dual-purpose as an MCP resource
- No authentication required

### 2-2. Endpoints

| Endpoint | Content |
|----------------|------|
| `GET /help` | Manual top page |
| `GET /help/<section>` | Section-specific page |
| `GET /api/help/toc` | Table of contents JSON |
| `GET /api/help/content/<section>` | Section body JSON |

### 2-3. MCP Tools

- `help_search`: Keyword search
- `help_get_section`: Section retrieval
