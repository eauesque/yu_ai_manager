/**
 * api.ts -- Shared API helper for tools page scripts.
 *
 * Tools page now reuses the main apiFetch so partial failures flow into
 * the global error reporter as well.
 */

export { apiFetch } from '../main/api-utils';
