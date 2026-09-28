export type SingleFlightState<T> = { current: Promise<T> | null };

export function runSingleFlight<T>(state: SingleFlightState<T>, operation: () => Promise<T>): Promise<T> {
  if (state.current) return state.current;
  const pending = Promise.resolve().then(operation);
  state.current = pending;
  const clear = () => {
    if (state.current === pending) state.current = null;
  };
  void pending.then(clear, clear);
  return pending;
}
