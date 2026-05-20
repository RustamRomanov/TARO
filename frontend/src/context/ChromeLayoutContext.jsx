import { createContext, useCallback, useContext, useMemo, useState } from 'react';

const ChromeLayoutContext = createContext(null);

export function ChromeLayoutProvider({ children }) {
  const [bottomNavSuppressionDepth, setBottomNavSuppressionDepth] = useState(0);
  const pushBottomNavSuppression = useCallback(() => {
    setBottomNavSuppressionDepth((d) => d + 1);
  }, []);
  const popBottomNavSuppression = useCallback(() => {
    setBottomNavSuppressionDepth((d) => Math.max(0, d - 1));
  }, []);
  const value = useMemo(
    () => ({
      suppressBottomNav: bottomNavSuppressionDepth > 0,
      pushBottomNavSuppression,
      popBottomNavSuppression,
    }),
    [bottomNavSuppressionDepth, pushBottomNavSuppression, popBottomNavSuppression],
  );
  return <ChromeLayoutContext.Provider value={value}>{children}</ChromeLayoutContext.Provider>;
}

/** Управление оболочкой (нижние вкладки): в Telegram WebView клавиатура часто не даёт стабильного visualViewport. */
export function useChromeLayout() {
  const ctx = useContext(ChromeLayoutContext);
  if (!ctx) {
    return {
      suppressBottomNav: false,
      pushBottomNavSuppression: () => {},
      popBottomNavSuppression: () => {},
    };
  }
  return ctx;
}
