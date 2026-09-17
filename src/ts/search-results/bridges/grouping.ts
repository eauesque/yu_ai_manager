import type { RuntimeResultsGroupingApi } from '../../shared/runtime-state/results-grouping-state';

export function createSearchResultsGroupingBridgeApi(): { runtimeResultsGrouping: RuntimeResultsGroupingApi } {
  return {
    runtimeResultsGrouping: {
      applyToCurrentResults: (): number[] => [],
      getOrderedGroups: () => [],
      getAdjacentGroupIds: (_currentIds: number[], _delta: number): number[] | null => null,
    },
  };
}
