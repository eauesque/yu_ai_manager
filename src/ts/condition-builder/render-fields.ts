import type { ConditionDef, PeriodPreset } from './config';
import { renderTextField, renderSelectField, renderToggleField } from './render-fields-basic';
import { renderPeriodField, renderResolutionField } from './render-fields-special';

export interface RenderFieldHelpers {
  PERIOD_PRESETS: PeriodPreset[];
  conditionPlaceholder: (c: ConditionDef) => string;
  conditionLabel: (c: ConditionDef) => string;
}

export function renderFieldByCondition(cond: ConditionDef, helpers: RenderFieldHelpers): string {
  if (cond.type === 'text') return renderTextField(cond, helpers.conditionPlaceholder);
  if (cond.type === 'select') return renderSelectField(cond, helpers.conditionLabel);
  if (cond.type === 'toggle') return renderToggleField(cond);
  if (cond.type === 'period') return renderPeriodField(helpers.PERIOD_PRESETS);
  if (cond.type === 'resolution') return renderResolutionField();
  return '';
}
