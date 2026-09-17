/**
 * mcp-tools-panel.ts — MCP tool list displayed as prefix-based accordion groups.
 */

interface McpTool {
  name: string;
  description?: string | undefined;
}

const PREFIX_GROUPS: Array<{ prefix: string | string[]; label: string }> = [
  { prefix: 'bsky_', label: 'Bluesky' },
  { prefix: 'github_', label: 'GitHub' },
  { prefix: 'sd_', label: 'Stable Diffusion' },
  { prefix: 'nai_', label: 'NovelAI' },
  { prefix: 'comfyui_', label: 'ComfyUI' },
  { prefix: ['hailo_', 'hailo-'], label: 'Hailo' },
  { prefix: 'mesh_', label: 'メッシュ推論' },
  { prefix: ['wd_', 'tagger_'], label: 'タガー' },
  { prefix: 'yolo_', label: 'YOLO' },
  { prefix: 'ocr_', label: 'OCR' },
  { prefix: 's2t_', label: '音声認識' },
  { prefix: 'agent_', label: 'エージェント' },
  { prefix: 'debug_', label: 'デバッグ' },
  { prefix: 'archive_', label: 'アーカイブ' },
];

function _matchPrefix(name: string, prefix: string | string[]): boolean {
  if (Array.isArray(prefix)) return prefix.some(p => name.startsWith(p));
  return name.startsWith(prefix);
}

function _groupTools(tools: McpTool[]): Map<string, McpTool[]> {
  const groups = new Map<string, McpTool[]>();
  const matched = new Set<string>();

  for (const g of PREFIX_GROUPS) {
    const group: McpTool[] = tools.filter(t => _matchPrefix(t.name, g.prefix));
    if (group.length > 0) {
      groups.set(g.label, group);
      group.forEach(t => matched.add(t.name));
    }
  }

  const other = tools.filter(t => !matched.has(t.name));
  if (other.length > 0) groups.set('汎用', other);
  return groups;
}

/** Escape HTML special characters to prevent XSS. */
function _esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _renderAccordion(groups: Map<string, McpTool[]>): string {
  let html = '';
  for (const [label, tools] of groups) {
    html +=
      `<details style="margin-bottom:6px;border:1px solid rgba(128,128,128,0.2);border-radius:6px;overflow:hidden;">` +
      `<summary style="padding:8px 12px;cursor:pointer;font-weight:600;font-size:12px;background:rgba(128,128,128,0.04);list-style:none;display:flex;justify-content:space-between;">` +
      `<span>${_esc(label)}</span><span style="color:var(--muted);font-weight:400;">${tools.length} ツール</span></summary>` +
      `<div style="padding:8px 12px;">` +
      tools
        .map(
          t =>
            `<div style="padding:3px 0;font-size:12px;"><code style="font-size:11px;color:var(--accent);">${_esc(t.name)}</code>` +
            (t.description
              ? `<span style="color:var(--muted);margin-left:8px;font-size:11px;">${_esc(t.description)}</span>`
              : '') +
            `</div>`,
        )
        .join('') +
      `</div></details>`;
  }
  return html;
}

export async function loadMcpToolsPanel(container: HTMLElement): Promise<void> {
  // All string interpolation below uses _esc() to prevent XSS
  container.innerHTML = '<div style="color:var(--muted);font-size:12px;">読み込み中...</div>';
  try {
    const resp = await fetch('/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 }),
    });
    const json = (await resp.json()) as { result?: { tools?: Array<{ name: string; description?: string }> } };
    const tools: McpTool[] = (json.result?.tools ?? []).map(t => ({
      name: t.name,
      description: t.description,
    }));

    if (tools.length === 0) {
      container.innerHTML =
        '<div style="color:var(--muted);font-size:12px;">MCP ツールが見つかりません</div>';
      return;
    }

    const groups = _groupTools(tools);
    const total = tools.length;
    container.innerHTML =
      `<div style="font-size:12px;color:var(--muted);margin-bottom:10px;">合計 ${total} ツール</div>` +
      _renderAccordion(groups);
  } catch {
    container.innerHTML =
      '<div style="color:var(--muted);font-size:12px;">MCP ツールリストを取得できませんでした</div>';
  }
}
