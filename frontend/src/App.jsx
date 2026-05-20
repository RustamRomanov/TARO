import { lazy, Suspense, useEffect } from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import SplashIntro from './components/SplashIntro';
import AppShell from './components/layout/AppShell';
import { prewarmMagicBall3D } from './lib/magicBallPrewarm';
import { prewarmTarot } from './lib/tarotPrewarm';

const loadTarot = () => import('./pages/Tarot');
const Tarot = lazy(loadTarot);

function RouteLoadingFallback() {
  return (
    <div
      className="min-h-[40vh] text-white/60 flex items-center justify-center"
      style={{ minHeight: '40vh', color: 'rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      Загрузка...
    </div>
  );
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/tarot" replace /> },
      {
        path: 'tarot',
        element: (
          <Suspense fallback={<RouteLoadingFallback />}>
            <Tarot />
          </Suspense>
        ),
      },
      { path: '*', element: <Navigate to="/tarot" replace /> },
    ],
  },
]);

export default function App() {
  useEffect(() => {
    const tg = window?.Telegram?.WebApp;
    if (!tg) return;

    const requestMaximize = () => {
      try {
        tg.ready?.();
      } catch (_) {}
      try {
        tg.expand?.();
      } catch (_) {}
      try {
        tg.requestFullscreen?.();
      } catch (_) {}
    };

    requestMaximize();
    const retryTimers = [120, 350, 800, 1600].map((delayMs) =>
      window.setTimeout(() => requestMaximize(), delayMs)
    );

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') requestMaximize();
    };
    const onFocus = () => requestMaximize();
    const onViewportChanged = () => requestMaximize();

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('focus', onFocus);
    try {
      tg.onEvent?.('viewportChanged', onViewportChanged);
    } catch (_) {}

    return () => {
      retryTimers.forEach((timerId) => window.clearTimeout(timerId));
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('focus', onFocus);
      try {
        tg.offEvent?.('viewportChanged', onViewportChanged);
      } catch (_) {}
    };
  }, []);

  useEffect(() => {
    const preload = () => {
      loadTarot().catch(() => {});
      prewarmTarot().catch(() => {});
      prewarmMagicBall3D().catch(() => {});
    };

    if (typeof window === 'undefined') return undefined;
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(preload, { timeout: 2500 });
      return () => window.cancelIdleCallback?.(id);
    }
    const t = window.setTimeout(preload, 1200);
    return () => window.clearTimeout(t);
  }, []);

  return (
    <>
      <SplashIntro />
      <RouterProvider router={router} />
    </>
  );
}
