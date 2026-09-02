import { createDetailModalControlActions } from './controls';
import { createDetailModalIntegrationActions } from './integration';
import { createDetailModalNavigationActions } from './navigation';
import type { DetailModalActionRegistry, DetailModalActionRegistryDeps } from './types';
import { createDetailModalViewerActions } from './viewer';

export function createDetailModalActionRegistry(
  deps: DetailModalActionRegistryDeps,
): DetailModalActionRegistry {
  return {
    ...createDetailModalNavigationActions(deps),
    ...createDetailModalViewerActions(deps),
    ...createDetailModalControlActions(deps),
    ...createDetailModalIntegrationActions(deps),
  };
}
