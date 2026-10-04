/**
 * Whole seconds left until `deadline` (epoch ms), re-rendering a few times a second; null without a deadline.
 */
import {useEffect, useState} from 'react';

export function useCountdown(deadline: number | null): number | null {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (deadline === null) {
      return;
    }
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [deadline]);
  return deadline === null ? null : Math.max(0, Math.ceil((deadline - now) / 1000));
}
