export interface DetailModalActionContext {
  action: string;
  arg?: string | undefined;
  element: HTMLElement;
  event: Event;
}

export type DetailModalActionHandler = (context: DetailModalActionContext) => void;

let initialized = false;
let actionRegistry: Record<string, DetailModalActionHandler> = {};

export function initDetailModalActionDispatch(registry: Record<string, DetailModalActionHandler>): void {
  actionRegistry = registry;
  if (initialized) return;
  initialized = true;

  document.addEventListener('click', (event) => {
    dispatchScopedAction(event, 'click');
  });

  document.addEventListener('change', (event) => {
    dispatchScopedAction(event, 'change');
  });

  document.addEventListener('input', (event) => {
    dispatchScopedAction(event, 'input');
  });

  document.addEventListener('keydown', (event) => {
    dispatchScopedAction(event, 'keydown');
  });

  // Tag suggestion input delegation (replaces inline oninput)
  document.addEventListener('input', (event) => {
    const target = event.target as HTMLElement | null;
    if (!target || !(target as HTMLInputElement).dataset?.tagSuggest) return;
    if (!target.closest('#modal')) return;
    const api = (window as unknown as Record<string, unknown>).tagEditApi as
      { fetchSuggestionsForTagInput?: (el: HTMLInputElement) => void } | undefined;
    if (api?.fetchSuggestionsForTagInput) api.fetchSuggestionsForTagInput(target as HTMLInputElement);
  });
}

function dispatchScopedAction(event: Event, expectedType: 'click' | 'change' | 'input' | 'keydown'): void {
  const target = event.target as HTMLElement | null;
  if (!target) return;
  const element = target.closest<HTMLElement>('[data-action][data-action-scope="detail-modal"]');
  if (!element) return;
  if (!element.closest('#modal')) return;

  const eventType = element.dataset.actionEvent || 'click';
  if (eventType !== expectedType) return;

  const action = element.dataset.action;
  if (!action) return;
  const handler = actionRegistry[action];
  if (!handler) return;

  handler({
    action,
    arg: element.dataset.actionArg,
    element,
    event,
  });
}
