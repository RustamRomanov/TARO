import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { cn } from '../../lib/cn';
import { markRouteRender } from '../../lib/perfTelemetry';
import { useChromeLayout } from '../../context/ChromeLayoutContext';

const TAROT_BG = '#0e090c';

export default function MainLayout() {
  const location = useLocation();
  const route = location.pathname;
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [keyboardFromViewport, setKeyboardFromViewport] = useState(false);
  const mainScrollRef = useRef(null);
  const { suppressBottomNav } = useChromeLayout();

  useEffect(() => {
    markRouteRender(route);
  }, [route]);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let raf = 0;
    let lastKb = false;
    const SHOW_THRESHOLD = 28;
    const HIDE_THRESHOLD = 18;
    const flush = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        raf = 0;
        const delta = Math.max(0, Math.round((window.innerHeight || 0) - vv.height));
        const visible = delta > SHOW_THRESHOLD;
        const hidden = delta < HIDE_THRESHOLD;
        const next = lastKb ? !hidden : visible;
        if (next === lastKb) return;
        lastKb = next;
        setKeyboardFromViewport(next);
        if (!next) setKeyboardVisible(false);
      });
    };
    flush();
    vv.addEventListener('resize', flush, { passive: true });
    vv.addEventListener('scroll', flush, { passive: true });
    return () => {
      vv.removeEventListener('resize', flush);
      vv.removeEventListener('scroll', flush);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  useEffect(() => {
    const tg = window?.Telegram?.WebApp;
    const requestExpand = () => {
      if (!tg?.expand) return;
      try {
        tg.expand();
      } catch (_) {}
    };
    requestExpand();
    if (tg?.disableVerticalSwipes) {
      try {
        tg.disableVerticalSwipes();
      } catch (_) {}
    }
    try {
      if (screen?.orientation?.lock) {
        screen.orientation.lock('portrait').catch(() => {});
      }
    } catch (_) {}
    const onFocus = (e) => {
      const tag = e.target?.tagName?.toLowerCase();
      const isEditable = e.target?.getAttribute?.('contenteditable') === 'true';
      if (tag === 'input' || tag === 'textarea' || isEditable) setKeyboardVisible(true);
    };
    const onBlur = (e) => {
      const tag = e.target?.tagName?.toLowerCase();
      const isEditable = e.target?.getAttribute?.('contenteditable') === 'true';
      if (tag === 'input' || tag === 'textarea' || isEditable) setKeyboardVisible(false);
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') requestExpand();
    };
    const onWindowFocus = () => requestExpand();
    document.addEventListener('focusin', onFocus);
    document.addEventListener('focusout', onBlur);
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('focus', onWindowFocus);
    return () => {
      document.removeEventListener('focusin', onFocus);
      document.removeEventListener('focusout', onBlur);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('focus', onWindowFocus);
    };
  }, []);

  const keyboardOpen = keyboardVisible || keyboardFromViewport || suppressBottomNav;

  useLayoutEffect(() => {
    const el = mainScrollRef.current;
    if (el && typeof el.scrollTo === 'function') {
      el.scrollTo({ top: 0, behavior: 'auto' });
    } else if (el) {
      el.scrollTop = 0;
    }
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'auto' });
    }
  }, [route]);

  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    html.style.backgroundColor = TAROT_BG;
    html.style.paddingTop = '0';
    body.style.backgroundColor = TAROT_BG;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', TAROT_BG);
    const tg = window?.Telegram?.WebApp;
    if (tg) {
      try {
        if (typeof tg.setHeaderColor === 'function') tg.setHeaderColor(TAROT_BG);
        if (typeof tg.setBackgroundColor === 'function') tg.setBackgroundColor(TAROT_BG);
      } catch (_) {}
    }
    return () => {
      html.style.backgroundColor = '';
      html.style.paddingTop = '';
      body.style.backgroundColor = TAROT_BG;
    };
  }, []);

  return (
    <div className="min-h-screen text-white overflow-x-hidden bg-[#0e090c]">
      <motion.div
        className="fixed -z-10"
        style={{
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          minHeight: '100dvh',
          minWidth: '100vw',
          background: 'rgb(14, 9, 12)',
          pointerEvents: 'none',
        }}
        initial={false}
        animate={{ opacity: 1 }}
        aria-hidden
      />

      <main
        ref={mainScrollRef}
        className={cn(
          'relative z-10 min-h-[100dvh] w-full max-w-none mx-0 px-0 overflow-x-hidden overflow-y-visible bg-[rgb(14,9,12)] h-[100dvh] max-h-[100dvh] flex flex-col min-h-0',
        )}
        style={{
          paddingTop: 'calc(max(48px, env(safe-area-inset-top, 0px)) + 2px - 0.1rem)',
          paddingBottom: keyboardOpen
            ? 'max(env(safe-area-inset-bottom), constant(safe-area-inset-bottom))'
            : 'calc(5rem + max(env(safe-area-inset-bottom), constant(safe-area-inset-bottom)))',
        }}
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-visible">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
