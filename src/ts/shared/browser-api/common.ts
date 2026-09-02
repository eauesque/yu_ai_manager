export type Fn = (...args: any[]) => any;

export function pickFunction<T extends Fn>(
  namespaced: unknown,
  legacy: unknown,
  fallback: T,
): T {
  if (typeof namespaced === 'function') return namespaced as T;
  if (typeof legacy === 'function') return legacy as T;
  return fallback;
}
