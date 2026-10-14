import { useEffect, useRef, useState } from "react";

/** Calls `callback` every `delay` ms; pass null to pause. Always uses the latest callback. */
export function useInterval(callback: () => void, delay: number | null) {
  const saved = useRef(callback);
  useEffect(() => {
    saved.current = callback;
  }, [callback]);
  useEffect(() => {
    if (delay === null) return;
    const id = setInterval(() => saved.current(), delay);
    return () => clearInterval(id);
  }, [delay]);
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Tweens a number toward `target` (ease-out), so a balance visibly counts down. */
export function useAnimatedNumber(target: number | null, duration = 1100): number | null {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);

  useEffect(() => {
    if (target === null) return;
    const from = fromRef.current;
    fromRef.current = target;
    // Hidden tabs pause requestAnimationFrame; jump so the number is never stale.
    if (from === null || from === target || prefersReducedMotion() || document.hidden) {
      setValue(target);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    // If the page isn't painting (rAF stalls), still land on the real value.
    const settle = setTimeout(() => setValue(target), duration + 150);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(settle);
    };
  }, [target, duration]);

  return value;
}

export function useLocalStorage(key: string, initial: string): [string, (v: string) => void] {
  const [value, setValue] = useState(() => localStorage.getItem(key) ?? initial);
  useEffect(() => {
    localStorage.setItem(key, value);
  }, [key, value]);
  return [value, setValue];
}
