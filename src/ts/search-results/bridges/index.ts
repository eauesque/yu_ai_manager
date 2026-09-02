import { createSearchResultsSearchBridgeApi } from './search';
import { createSearchResultsRenderBridgeApi } from './results';
import { createSearchResultsGroupingBridgeApi } from './grouping';

export function createSearchResultsBridgeApi() {
  return {
    ...createSearchResultsSearchBridgeApi(),
    ...createSearchResultsRenderBridgeApi(),
    ...createSearchResultsGroupingBridgeApi(),
  };
}
