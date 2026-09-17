/** Escape a single CSV cell value.
 * Guards against formula injection (Excel/Sheets treats cells starting with
 * = + - @ \t \r as formulas) and wraps cells containing commas, quotes, or
 * newlines in double-quotes per RFC 4180.
 */
function _csvCell(value: unknown): string {
  let s = String(value ?? '');
  // Prefix dangerous leading characters with a single-quote to defuse formulas
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv(filename: string, rows: Array<Record<string, unknown>>): void {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const lines = [keys.join(',')];
  for (const row of rows) {
    lines.push(keys.map((key) => _csvCell(row[key])).join(','));
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function initCsvButtons(csvData: Record<string, Array<Record<string, unknown>>>): void {
  document.querySelectorAll<HTMLButtonElement>('[data-csv-chart]').forEach((btn) => {
    if (btn.dataset.actionBound === '1') return;
    btn.dataset.actionBound = '1';
    btn.addEventListener('click', () => {
      const key = btn.dataset.csvChart || '';
      const rows = csvData[key];
      if (rows && rows.length) downloadCsv(`stats_${key}.csv`, rows);
    });
  });
}
