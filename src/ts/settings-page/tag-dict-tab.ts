/**
 * Settings Tag Dictionary tab — CSV import, stats, test search, and clear
 */

const CATEGORY_NAMES: Record<number, string> = {
  0: 'General', 1: 'Artist', 3: 'Copyright', 4: 'Character', 5: 'Meta',
};

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

export function initTagDictTab(): void {
  loadTagDictStats();
}

export function loadTagDictStats(): void {
  const el = document.getElementById('tagDictStats');
  if (!el) return;
  fetch('/api/tag-dict/stats')
    .then(r => r.json())
    .then((data: { total: number; categories: Record<string, number> }) => {
      if (data.total === 0) {
        el.innerHTML = '<span style="color:var(--muted)">No tags loaded. Import a CSV file below.</span>';
        return;
      }
      let html = '<div style="font-size:14px;margin-bottom:8px;font-weight:600;">'
        + data.total.toLocaleString() + ' tags</div>';
      html += '<div style="display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted)">';
      for (const [cat, count] of Object.entries(data.categories)) {
        const name = CATEGORY_NAMES[Number(cat)] || ('Cat ' + cat);
        html += '<span>' + name + ': ' + count.toLocaleString() + '</span>';
      }
      html += '</div>';
      el.innerHTML = html;
    })
    .catch(() => {
      el.textContent = 'Failed to load stats';
    });
}

export function importTagDictCsv(): void {
  const input = document.getElementById('tagDictFile') as HTMLInputElement | null;
  const status = document.getElementById('tagDictImportStatus');
  if (!input?.files?.length) {
    if (status) status.textContent = 'Please select a CSV file.';
    return;
  }
  const file = input.files[0];
  const form = new FormData();
  form.append('file', file);

  if (status) {
    status.style.display = '';
    status.style.color = 'var(--muted)';
    status.textContent = 'Importing...';
  }

  fetch('/api/tag-dict/import', {
    method: 'POST',
    headers: XHR_HEADERS,
    body: form,
  })
    .then(r => r.json())
    .then((data: { imported: number; skipped: number; total_time: number }) => {
      if (status) {
        status.style.color = '#22aa22';
        status.textContent = 'Imported ' + data.imported.toLocaleString()
          + ' tags (' + data.skipped + ' skipped) in ' + data.total_time + 's';
      }
      loadTagDictStats();
    })
    .catch(() => {
      if (status) {
        status.style.color = '#cc4444';
        status.textContent = 'Import failed.';
      }
    });
}

export function clearTagDict(): void {
  if (!confirm('Are you sure you want to delete all tags from the dictionary?')) return;
  fetch('/api/tag-dict/clear', {
    method: 'DELETE',
    headers: XHR_HEADERS,
  })
    .then(r => r.json())
    .then((data) => {
      const status = document.getElementById('tagDictImportStatus');
      if (status) {
        status.style.display = '';
        status.style.color = 'var(--muted)';
        status.textContent = 'Cleared ' + (data.data?.deleted || 0).toLocaleString() + ' tags.';
      }
      loadTagDictStats();
    })
    .catch(() => {});
}

let _searchTimer: ReturnType<typeof setTimeout> | null = null;

export function onTagDictSearchInput(): void {
  if (_searchTimer) clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => {
    const input = document.getElementById('tagDictSearch') as HTMLInputElement | null;
    const resultsEl = document.getElementById('tagDictSearchResults');
    if (!input || !resultsEl) return;
    const q = input.value.trim();
    if (q.length < 2) {
      resultsEl.innerHTML = '';
      return;
    }
    fetch('/api/tag-dict/search?q=' + encodeURIComponent(q) + '&limit=10&fuzzy=1')
      .then(r => r.json())
      .then((data: { results: Array<{ tag_name: string; category: number; post_count: number; match_type: string }> }) => {
        if (!data.results?.length) {
          resultsEl.innerHTML = '<span style="color:var(--muted)">No results</span>';
          return;
        }
        let html = '<table style="width:100%;font-size:12px;border-collapse:collapse;">';
        html += '<tr style="color:var(--muted);text-align:left;"><th style="padding:4px 8px;">Tag</th><th style="padding:4px 8px;">Category</th><th style="padding:4px 8px;">Posts</th><th style="padding:4px 8px;">Match</th></tr>';
        for (const r of data.results) {
          const cat = CATEGORY_NAMES[r.category] || String(r.category);
          html += '<tr style="border-top:1px solid var(--border,rgba(128,128,128,0.2));">';
          html += '<td style="padding:4px 8px;">' + escHtml(r.tag_name) + '</td>';
          html += '<td style="padding:4px 8px;">' + cat + '</td>';
          html += '<td style="padding:4px 8px;">' + r.post_count.toLocaleString() + '</td>';
          html += '<td style="padding:4px 8px;">' + r.match_type + '</td>';
          html += '</tr>';
        }
        html += '</table>';
        resultsEl.innerHTML = html;
      })
      .catch(() => {
        resultsEl.innerHTML = '<span style="color:#cc4444">Search failed</span>';
      });
  }, 300);
}

function escHtml(s: string): string {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(s));
  return d.innerHTML;
}
