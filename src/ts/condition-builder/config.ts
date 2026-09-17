export interface ConditionDef {
  label: string;
  labelKey: string;
  icon: string;
  type: 'text' | 'select' | 'toggle' | 'period' | 'resolution';
  target?: string;
  targets?: string[];
  placeholder?: string;
  placeholderKey?: string;
  descKey?: string;
}

export interface PeriodPreset {
  label: string;
  labelKey: string;
  hours?: number;
  days?: number;
  type?: string;
}

export const CONDITIONS: Record<string, ConditionDef> = {
  artist:       { label: '🎨 Artist', labelKey: 'conditions.artist.label', icon: '🎨', type: 'text', target: 'artist', placeholder: 'artist name', placeholderKey: 'conditions.artist.placeholder', descKey: 'conditions.artist.desc' },
  orTags:       { label: '🔀 OR tags', labelKey: 'conditions.orTags.label', icon: '🔀', type: 'text', target: 'orTags', placeholder: 'contains any (comma-separated)', placeholderKey: 'conditions.orTags.placeholder', descKey: 'conditions.orTags.desc' },
  period:       { label: '📅 Period', labelKey: 'conditions.period.label', icon: '📅', type: 'period', targets: ['fromDate','toDate'], descKey: 'conditions.period.desc' },
  resolution:   { label: '📐 Resolution', labelKey: 'conditions.resolution.label', icon: '📐', type: 'resolution', targets: ['minWidth','maxWidth','minHeight','maxHeight'], descKey: 'conditions.resolution.desc' },
  inFolder:     { label: '📂 Folder', labelKey: 'conditions.inFolder.label', icon: '📂', type: 'text', target: 'inPath', placeholder: 'path part e.g. o:\\test', placeholderKey: 'conditions.inFolder.placeholder', descKey: 'conditions.inFolder.desc' },
  format:       { label: '📄 Format', labelKey: 'conditions.format.label', icon: '📄', type: 'select', target: 'fileFormat', descKey: 'conditions.format.desc' },
  model:        { label: '🤖 Model', labelKey: 'conditions.model.label', icon: '🤖', type: 'select', target: 'modelFilter', descKey: 'conditions.model.desc' },
  wdModel:      { label: '🖼️ WD Model', labelKey: 'conditions.wdModel.label', icon: '🖼️', type: 'select', target: 'wdModelFilter', descKey: 'conditions.wdModel.desc' },
  sort:         { label: '↕️ Sort', labelKey: 'conditions.sort.label', icon: '↕️', type: 'select', target: 'sortBy', descKey: 'conditions.sort.desc' },
inPrompt:     { label: '🔤 In Prompt', labelKey: 'conditions.inPrompt.label', icon: '🔤', type: 'text', target: 'inPrompt', placeholder: 'keyword in prompt', placeholderKey: 'conditions.inPrompt.placeholder', descKey: 'conditions.inPrompt.desc' },
  tagCase:      { label: 'Aa Case sensitive', labelKey: 'conditions.tagCase.label', icon: 'Aa', type: 'toggle', target: 'tagCaseSensitive', descKey: 'conditions.tagCase.desc' },
  checkpoint:   { label: '🎯 Checkpoint', labelKey: 'conditions.checkpoint.label', icon: '🎯', type: 'text', target: 'checkpointFilter', placeholder: 'e.g. animagine, pony', placeholderKey: 'conditions.checkpoint.placeholder', descKey: 'conditions.checkpoint.desc' },
  inNegative:   { label: '🚫 In Negative', labelKey: 'conditions.inNegative.label', icon: '🚫', type: 'text', target: 'inNegative', placeholder: 'keyword in negative', placeholderKey: 'conditions.inNegative.placeholder', descKey: 'conditions.inNegative.desc' },
  inCharPos:    { label: '✨ In Char Positive', labelKey: 'conditions.inCharPos.label', icon: '✨', type: 'text', target: 'inCharPositive', placeholder: 'character positive search', placeholderKey: 'conditions.inCharPos.placeholder', descKey: 'conditions.inCharPos.desc' },
  inCharNeg:    { label: '🚫 In Char Negative', labelKey: 'conditions.inCharNeg.label', icon: '🚫', type: 'text', target: 'inCharNegative', placeholder: 'character negative search', placeholderKey: 'conditions.inCharNeg.placeholder', descKey: 'conditions.inCharNeg.desc' },
  favOnly:      { label: '⭐ Favorites only', labelKey: 'conditions.favOnly.label', icon: '⭐', type: 'toggle', target: 'favOnly', descKey: 'conditions.favOnly.desc' },
  aiAnalyzed:   { label: '🧠 AI Analyzed', labelKey: 'conditions.aiAnalyzed.label', icon: '🧠', type: 'toggle', target: 'aiAnalyzed', descKey: 'conditions.aiAnalyzed.desc' },
  hasTags:      { label: '🏷️ Tagged', labelKey: 'conditions.hasTags.label', icon: '🏷️', type: 'toggle', target: 'hasTags', descKey: 'conditions.hasTags.desc' },
  hasAnnotation: { label: '📝 Has Note', labelKey: 'conditions.hasAnnotation.label', icon: '📝', type: 'toggle', target: 'hasAnnotation', descKey: 'conditions.hasAnnotation.desc' },
  hasSweep:     { label: '🧪 Sweep あり', labelKey: 'conditions.hasSweep.label', icon: '🧪', type: 'toggle', target: 'hasSweep', descKey: 'conditions.hasSweep.desc' },
  collection:   { label: '⭐ Collection', labelKey: 'conditions.collection.label', icon: '⭐', type: 'select', target: 'collectionFilter', descKey: 'conditions.collection.desc' },
};

export const PERIOD_PRESETS: PeriodPreset[] = [
  { label: '', labelKey: 'period.3h', hours: 3 },
  { label: '', labelKey: 'period.8h', hours: 8 },
  { label: '', labelKey: 'period.12h', hours: 12 },
  { label: '', labelKey: 'period.24h', hours: 24 },
  { label: '', labelKey: 'period.yesterday', type: 'yesterday' },
  { label: '', labelKey: 'period.days3', days: 3 },
  { label: '', labelKey: 'period.days5', days: 5 },
  { label: '', labelKey: 'period.week1', days: 7 },
  { label: '', labelKey: 'period.week2', days: 14 },
  { label: '', labelKey: 'period.month1', days: 30 },
  { label: '', labelKey: 'period.last_month', type: 'lastMonth' },
  { label: '', labelKey: 'period.month2', days: 60 },
  { label: '', labelKey: 'period.month3', days: 90 },
  { label: '', labelKey: 'period.half_year', days: 180 },
  { label: '', labelKey: 'period.month9', days: 270 },
  { label: '', labelKey: 'period.year1', days: 365 },
  { label: '', labelKey: 'period.custom', type: 'custom' },
];
