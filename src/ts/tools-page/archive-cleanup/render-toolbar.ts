export function renderPagination(
  page: number,
  totalPages: number,
): string {
  let html = `<div style="display:flex;gap:4px;align-items:center;margin-bottom:10px;font-size:12px;">`;
  html += `<button type="button" class="btn btn-secondary" data-action="toolsPageApi.acPage" data-action-arg="${page - 1}" ${page <= 1 ? 'disabled' : ''} style="font-size:11px;padding:3px 8px;">&#x25C0;</button>`;

  const start = Math.max(1, page - 3);
  const end = Math.min(totalPages, page + 3);
  if (start > 1) {
    html += `<button type="button" class="btn btn-secondary" data-action="toolsPageApi.acPage" data-action-arg="1" style="font-size:11px;padding:3px 8px;">1</button>`;
    if (start > 2) html += `<span style="color:#888;">...</span>`;
  }
  for (let i = start; i <= end; i++) {
    const active = i === page;
    html += `<button type="button" class="btn ${active ? 'btn-primary' : 'btn-secondary'}" data-action="toolsPageApi.acPage" data-action-arg="${i}" style="font-size:11px;padding:3px 8px;${active ? 'font-weight:600;' : ''}">${i}</button>`;
  }
  if (end < totalPages) {
    if (end < totalPages - 1) html += `<span style="color:#888;">...</span>`;
    html += `<button type="button" class="btn btn-secondary" data-action="toolsPageApi.acPage" data-action-arg="${totalPages}" style="font-size:11px;padding:3px 8px;">${totalPages}</button>`;
  }

  html += `<button type="button" class="btn btn-secondary" data-action="toolsPageApi.acPage" data-action-arg="${page + 1}" ${page >= totalPages ? 'disabled' : ''} style="font-size:11px;padding:3px 8px;">&#x25B6;</button>`;
  html += `</div>`;
  return html;
}

export function renderSortFilterBar(
  totalFiltered: number,
  totalAll: number,
  perfectCount: number,
  page: number,
  totalPages: number,
  t: (key: string, fallback: string) => string,
): string {
  return `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;align-items:center;">
    <label style="font-size:12px;">${t('tools.ac_sort', 'Sort')}:
      <select id="acSort" data-action="toolsPageApi.acSort" data-action-event="change" style="font-size:11px;padding:2px 6px;border-radius:4px;border:1px solid rgba(128,128,128,0.3);background:var(--card,#2a2a2a);color:var(--text,#eee);">
        <option value="rate_desc">${t('tools.ac_sort_rate_desc', 'Match % (high)')}</option>
        <option value="rate_asc">${t('tools.ac_sort_rate_asc', 'Match % (low)')}</option>
        <option value="name">${t('tools.ac_sort_name', 'Name')}</option>
        <option value="size">${t('tools.ac_sort_size', 'Size')}</option>
      </select>
    </label>
    <label style="font-size:12px;">${t('tools.ac_filter', 'Filter')}:
      <select id="acFilter" data-action="toolsPageApi.acFilter" data-action-event="change" style="font-size:11px;padding:2px 6px;border-radius:4px;border:1px solid rgba(128,128,128,0.3);background:var(--card,#2a2a2a);color:var(--text,#eee);">
        <option value="all">${t('tools.ac_filter_all', 'All')}</option>
        <option value="perfect">${t('tools.ac_filter_perfect', '100% only')}</option>
        <option value="imperfect">${t('tools.ac_filter_imperfect', '<100%')}</option>
      </select>
    </label>
    <span style="margin-left:auto;font-size:12px;color:#888;">${totalFiltered}${totalFiltered !== totalAll ? '/' + totalAll : ''} ${t('tools.ac_pairs_found', 'pairs found')}</span>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center;">
    <span style="font-size:13px;font-weight:600;">${t('tools.ac_bulk', 'Bulk:')}</span>
    <button type="button" class="btn btn-secondary" data-action="toolsPageApi.acSelectAll" data-action-arg="delete_archive" style="font-size:11px;padding:4px 10px;">
      ${t('tools.ac_all_del_archive', 'All: Delete Archive')}
    </button>
    <button type="button" class="btn btn-secondary" data-action="toolsPageApi.acSelectAll" data-action-arg="delete_folder" style="font-size:11px;padding:4px 10px;">
      ${t('tools.ac_all_del_folder', 'All: Delete Folder')}
    </button>
    <button type="button" class="btn btn-secondary" data-action="toolsPageApi.acSelectAll" data-action-arg="skip" style="font-size:11px;padding:4px 10px;">
      ${t('tools.ac_all_skip', 'All: Skip')}
    </button>
    ${perfectCount > 0 ? `
    <span style="border-left:1px solid rgba(128,128,128,0.3);height:20px;margin:0 4px;"></span>
    <button type="button" class="btn btn-secondary" data-action="toolsPageApi.acSelectAllPerfect" data-action-arg="delete_archive" style="font-size:11px;padding:4px 10px;color:#27ae60;">
      ${t('tools.ac_perfect_del_archive', '100%: Delete Archive')} (${perfectCount})
    </button>
    <button type="button" class="btn btn-secondary" data-action="toolsPageApi.acSelectAllPerfect" data-action-arg="delete_folder" style="font-size:11px;padding:4px 10px;color:#27ae60;">
      ${t('tools.ac_perfect_del_folder', '100%: Delete Folder')} (${perfectCount})
    </button>` : ''}
  </div>
  ${totalPages > 1 ? renderPagination(page, totalPages) : ''}`;
}
