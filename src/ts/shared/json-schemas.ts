import type { JsonSchema } from './json-schema-validator';

// ── Declaration order constraint ─────────────────────────────────────────────
// const has TDZ (Temporal Dead Zone) — SCHEMA_REGISTRY must be declared LAST.
// Order: CONFIG_SCHEMA → MCP_CONNECTIONS_SCHEMA → SCHEMA_REGISTRY

export const CONFIG_SCHEMA: JsonSchema = {
  allowUnknown: true, // Prevent false warnings for extension fields
  fields: {
    db:        { type: 'string' },
    api_key:   { type: 'string' },
    log_level: {
      type: 'string',
      enum: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const,
    },
    language: {
      type: 'string',
      enum: ['ja', 'en', 'zh-tw', 'zh-cn', 'ko'] as const,
    },
    // server / remote_fs nested objects are out of scope (spec §2)
  },
};

/** Shared field shape for mcpServers / mcp_servers / servers aliases */
const _serverMapField = {
  type: 'object' as const,
  valueSchema: {
    type: 'object' as const,
    properties: {
      command: { type: 'string' as const, required: true },
      args:    { type: 'array' as const },
      env:     { type: 'object' as const },
    },
  },
};

export const MCP_CONNECTIONS_SCHEMA: JsonSchema = {
  allowUnknown: false,
  // Format detection — keeps MCP key names out of json-editor-enhance.ts
  applies: (v) =>
    typeof v === 'object' &&
    v !== null &&
    ('mcpServers' in v || 'mcp_servers' in v || 'servers' in v),
  fields: {
    mcpServers:  _serverMapField, // Claude Desktop format
    mcp_servers: _serverMapField, // alias 1
    servers:     _serverMapField, // alias 2
  },
};

// SCHEMA_REGISTRY must be declared AFTER CONFIG_SCHEMA and MCP_CONNECTIONS_SCHEMA (TDZ)
export const SCHEMA_REGISTRY: Readonly<Record<string, JsonSchema>> = {
  config: CONFIG_SCHEMA,
  'mcp-connections': MCP_CONNECTIONS_SCHEMA,
} as const;
