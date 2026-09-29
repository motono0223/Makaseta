import { useEffect } from "react";

/** Call `tick` now and then every `ms` while `active`; stops when the component unmounts. */
export function usePolling(tick: () => void, ms: number, active = true) {
  useEffect(() => {
    if (!active) return;
    tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, ms);
    return () => window.clearInterval(id);
  }, [tick, ms, active]);
}
