import { CONDITIONS, type ConditionDef, type PeriodPreset } from './config';
import { renderFieldByCondition } from './render-fields';
import { clearFormatExts, toggleFormatExt } from './render-fields-basic';
import { setPeriodPreset, setResolutionPreset, showCustomPeriod } from './actions';
import { updateConditionHintState } from './render-hint';
import { getAppApi, getConditionBuilderApi, getRuntimeInitApi } from '../shared/browser-apis';

function esc(value: unknown): string {
  return getAppApi().escapeHtml(value);
}

export interface RenderContext {
  activeConditions: Set<string>;
  CONDITIONS: Record<string, ConditionDef>;
  conditionLabel: (c: ConditionDef) => string;
  conditionPlaceholder: (c: ConditionDef) => string;
  PERIOD_PRESETS: PeriodPreset[];
}

export function renderActiveConditions(ctx: RenderContext): void {
  const { tr } = getAppApi();
  const runtimeInitApi = getRuntimeInitApi();
  const conditionBuilderApi = getConditionBuilderApi();
  const {
    activeConditions,
    CONDITIONS,
    conditionLabel,
    conditionPlaceholder,
    PERIOD_PRESETS
  } = ctx;

  const chipsContainer = document.getElementById('activeConditions');
  const fieldsContainer = document.getElementById('conditionFields');
  if (!chipsContainer || !fieldsContainer) return;
  let chipsHtml = '';
  let fieldsHtml = '';

  function chipValueText(cond: ConditionDef | undefined): string {
    if (!cond) return '';
    if (cond.type === 'select') {
      const el = document.getElementById(cond.target!) as HTMLSelectElement | null;
      if (!el || el.disabled) return '';
      const selected = el.selectedOptions?.[0];
      const value = (selected?.textContent || '').trim();
      const parts: string[] = [];
      if (value && value.toLowerCase() !== 'all' && el.value !== 'all') {
        parts.push(value);
      }
      if (cond.target === 'fileFormat') {
        const formatExts = String((document.getElementById('formatExts') as HTMLInputElement | null)?.value || '')
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        if (formatExts.length) {
          const joined = formatExts.slice(0, 3).map((s) => `.${s}`).join(',');
          const suffix = formatExts.length > 3 ? ',...' : '';
          parts.push(`${joined}${suffix}`);
        }
      }
      if (!parts.length) return '';
      return `: ${esc(parts.join(' | '))}`;
    }
    if (cond.type === 'text') {
      const el = document.getElementById(cond.target!) as HTMLInputElement | null;
      const raw = String(el?.value || '').trim();
      if (!raw) return '';
      const short = raw.length > 28 ? `${raw.slice(0, 28)}...` : raw;
      return `: ${esc(short)}`;
    }
    if (cond.type === 'toggle') {
      const el = document.getElementById(cond.target!) as HTMLInputElement | null;
      if (!el?.checked) return '';
      return `: ${esc(tr('common.enabled', 'ON'))}`;
    }
    if (cond.type === 'resolution') {
      const [mw, xw, mh, xh] = (cond.targets || []).map((id) => String((document.getElementById(id) as HTMLInputElement | null)?.value || '').trim());
      const summary: string[] = [];
      if (mw) summary.push(`W>=${mw}`);
      if (xw) summary.push(`W<=${xw}`);
      if (mh) summary.push(`H>=${mh}`);
      if (xh) summary.push(`H<=${xh}`);
      if (!summary.length) return '';
      return `: ${esc(summary.join(' '))}`;
    }
    if (cond.type === 'period') {
      const [fromId, toId] = cond.targets || ['fromDate', 'toDate'];
      const fromVal = String((document.getElementById(fromId) as HTMLInputElement | null)?.value || '').trim();
      const toVal = String((document.getElementById(toId) as HTMLInputElement | null)?.value || '').trim();
      if (!fromVal && !toVal) return '';
      if (fromVal && toVal) return `: ${esc(`${fromVal} ~ ${toVal}`)}`;
      return `: ${esc(fromVal || toVal)}`;
    }
    return '';
  }

  for (const key of activeConditions) {
    const cond = CONDITIONS[key];
    if (!cond) continue;

    if (key !== 'sort') {
      const removeBtn =
        `<button type="button" data-remove-key="${key}" style="background:none;border:none;color:#e74c3c;cursor:pointer;font-size:14px;padding:2px 4px;line-height:1;min-width:24px;min-height:24px;display:inline-flex;align-items:center;justify-content:center;" title="${esc(tr('conditions.remove'))}" aria-label="${esc(tr('conditions.remove'))}">×</button>`;
      chipsHtml += `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;background:rgba(102,126,234,0.15);border:1px solid rgba(102,126,234,0.3);border-radius:14px;font-size:12px;">
        ${esc(conditionLabel(cond))}${chipValueText(cond)}
        ${removeBtn}
      </span>`;
    }

    fieldsHtml += `<div class="condition-field" data-key="${key}" style="display:flex;align-items:center;gap:8px;margin:4px 0;flex-wrap:wrap;">`;
    fieldsHtml += `<span style="font-size:12px;color:var(--muted-accessible,#aab);min-width:100px;">${esc(conditionLabel(cond))}:</span>`;
    fieldsHtml += renderFieldByCondition(cond, { PERIOD_PRESETS, conditionPlaceholder, conditionLabel }) || '';
    fieldsHtml += '</div>';
  }

  chipsContainer.innerHTML = chipsHtml;
  fieldsContainer.innerHTML = fieldsHtml;

  // Bind remove buttons via addEventListener (avoid inline onclick XSS)
  chipsContainer.querySelectorAll<HTMLButtonElement>('[data-remove-key]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.removeKey;
      if (k) conditionBuilderApi.removeCondition?.(k);
    });
  });

  fieldsContainer.querySelectorAll<HTMLInputElement>('[data-condition-text-target]').forEach((el) => {
    el.addEventListener('input', () => {
      const targetId = el.dataset.conditionTextTarget;
      const target = targetId ? document.getElementById(targetId) as HTMLInputElement | null : null;
      if (!target) return;
      target.value = el.value;
      runtimeInitApi.saveSearchState();
    });
  });

  fieldsContainer.querySelectorAll<HTMLElement>('[data-condition-clear-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.conditionClearTarget;
      const target = targetId ? document.getElementById(targetId) as HTMLInputElement | null : null;
      const input = btn.previousElementSibling as HTMLInputElement | null;
      if (!target || !input) return;
      input.value = '';
      target.value = '';
      input.focus();
      runtimeInitApi.saveSearchState();
    });
  });

  fieldsContainer.querySelectorAll<HTMLSelectElement>('[data-condition-select-target]').forEach((el) => {
    el.addEventListener('change', () => {
      const targetId = el.dataset.conditionSelectTarget;
      const target = targetId ? document.getElementById(targetId) as HTMLSelectElement | null : null;
      if (!target) return;
      target.value = el.value;
      if (el.dataset.conditionSyncChip === '1') {
        conditionBuilderApi.renderActiveConditions();
      }
      runtimeInitApi.saveSearchState();
    });
  });

  fieldsContainer.querySelectorAll<HTMLElement>('[data-condition-reset-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.conditionResetTarget;
      const select = btn.previousElementSibling as HTMLSelectElement | null;
      const target = targetId ? document.getElementById(targetId) as HTMLSelectElement | null : null;
      if (!select || !target) return;
      select.value = select.options[0]?.value || '';
      target.value = select.value;
      if (btn.dataset.conditionResetFormatExts === '1') {
        clearFormatExts();
        return;
      }
      runtimeInitApi.saveSearchState();
    });
  });

  fieldsContainer.querySelectorAll<HTMLInputElement>('input[data-format-ext]').forEach((el) => {
    el.addEventListener('change', () => {
      const ext = el.dataset.formatExt;
      if (!ext) return;
      toggleFormatExt(ext, el.checked);
    });
  });

  fieldsContainer.querySelectorAll<HTMLElement>('[data-condition-clear-format-exts]').forEach((btn) => {
    btn.addEventListener('click', () => {
      btn.blur();
      clearFormatExts();
    });
  });

  fieldsContainer.querySelectorAll<HTMLInputElement>('[data-condition-toggle-target]').forEach((el) => {
    el.addEventListener('change', () => {
      const targetId = el.dataset.conditionToggleTarget;
      const target = targetId ? document.getElementById(targetId) as HTMLInputElement | null : null;
      if (!target) return;
      target.checked = el.checked;
      runtimeInitApi.saveSearchState();
    });
  });

  fieldsContainer.querySelectorAll<HTMLElement>('[data-condition-period-custom]').forEach((btn) => {
    btn.addEventListener('click', () => {
      showCustomPeriod();
    });
  });

  fieldsContainer.querySelectorAll<HTMLElement>('[data-condition-period-days]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const days = Number(btn.dataset.conditionPeriodDays || '0');
      const type = btn.dataset.conditionPeriodType || '';
      const hours = Number(btn.dataset.conditionPeriodHours || '0');
      setPeriodPreset(days, type, hours);
    });
  });

  fieldsContainer.querySelectorAll<HTMLInputElement>('[data-condition-period-target]').forEach((el) => {
    el.addEventListener('change', () => {
      const targetId = el.dataset.conditionPeriodTarget;
      const target = targetId ? document.getElementById(targetId) as HTMLInputElement | null : null;
      if (!target) return;
      target.value = el.value;
      runtimeInitApi.saveSearchState();
    });
  });

  fieldsContainer.querySelectorAll<HTMLElement>('[data-condition-resolution-min-w]').forEach((btn) => {
    btn.addEventListener('click', () => {
      setResolutionPreset(
        Number(btn.dataset.conditionResolutionMinW || '0'),
        Number(btn.dataset.conditionResolutionMaxW || '0'),
        Number(btn.dataset.conditionResolutionMinH || '0'),
        Number(btn.dataset.conditionResolutionMaxH || '0'),
      );
    });
  });

  fieldsContainer.querySelectorAll<HTMLInputElement>('[data-condition-resolution-target]').forEach((el) => {
    el.addEventListener('input', () => {
      const targetId = el.dataset.conditionResolutionTarget;
      const target = targetId ? document.getElementById(targetId) as HTMLInputElement | null : null;
      if (!target) return;
      target.value = el.value;
      runtimeInitApi.saveSearchState();
    });
  });

  updateConditionHintState(
    activeConditions.size,
    chipsContainer,
    activeConditions,
    CONDITIONS,
    conditionBuilderApi.clearAllConditions,
    tr,
    esc,
  );
}
