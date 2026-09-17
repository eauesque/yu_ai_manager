// agent-memory-page/dom — table/text DOM helpers and the JSON fetch wrapper.
//
// Split out of index.ts to keep it under the 500-line policy
// (tests/basic/test_line_count_policy.py). Behaviour is unchanged.

export async function amFetch(path: string, opts: RequestInit = {}): Promise<Response> {
  const headers = { Accept: 'application/json', ...(opts.headers as Record<string, string> | undefined) };
  return fetch(path, { ...opts, headers });
}

export function makeCell(text: unknown): HTMLTableCellElement {
  const td = document.createElement('td');
  td.textContent = String(text ?? '—');
  return td;
}

export function makeRow(...cells: unknown[]): HTMLTableRowElement {
  const tr = document.createElement('tr');
  for (const text of cells) tr.appendChild(makeCell(text));
  return tr;
}

export function makeTable(headers: string[], rows: HTMLTableRowElement[]): HTMLTableElement {
  const table = document.createElement('table');
  table.className = 'am-table';
  const thead = table.createTHead();
  const hr = thead.insertRow();
  for (const h of headers) {
    const th = document.createElement('th');
    th.textContent = h;
    hr.appendChild(th);
  }
  const tbody = table.createTBody();
  for (const row of rows) tbody.appendChild(row);
  return table;
}

export function setText(id: string, value: unknown): void {
  const el = document.getElementById(id);
  if (el) el.textContent = String(value ?? '');
}
