import { useEffect, useState } from 'react';

/**
 * Reactively tracks a CSS media query.
 *
 * @param query - A valid CSS media query string, e.g. "(max-width: 768px)"
 * @returns true when the media query matches
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);

    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

/**
 * Shorthand: true when viewport width <= 768px.
 */
export function useMobile(): boolean {
  return useMediaQuery('(max-width: 768px)');
}
