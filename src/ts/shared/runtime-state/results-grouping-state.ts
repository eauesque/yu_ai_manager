export interface RuntimeResultsGroupingApi {
  applyToCurrentResults: () => number[];
  getOrderedGroups: () => Array<{ key: string; type: string; ids: number[]; label: string; groupPath: string }>;
  getAdjacentGroupIds: (currentIds: number[], delta: number) => number[] | null;
}

let runtimeResultsGrouping: RuntimeResultsGroupingApi | null = null;

export function setRuntimeResultsGrouping(api: RuntimeResultsGroupingApi | null): void {
  runtimeResultsGrouping = api;
}

export function getRuntimeResultsGrouping(): RuntimeResultsGroupingApi | null {
  return runtimeResultsGrouping;
}
