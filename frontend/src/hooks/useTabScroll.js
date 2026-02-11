import { useEffect, useRef } from 'react';

// Persist and restore scroll position for a scrollable container per tab key
// Usage: const ref = useTabScroll('pipeline'); attach ref to the scrollable div
export function useTabScroll(key) {
  const containerRef = useRef(null);
  const storageKey = `scroll:${key}`;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Restore
    const saved = sessionStorage.getItem(storageKey);
    if (saved) {
      const top = parseInt(saved, 10) || 0;
      try { el.scrollTo({ top }); } catch { el.scrollTop = top; }
    }
    const onScroll = () => {
      sessionStorage.setItem(storageKey, String(el.scrollTop || 0));
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, [storageKey]);

  return containerRef;
}
