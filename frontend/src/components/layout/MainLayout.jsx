import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { cn } from '../../lib/cn';
import { getInitData } from '../../lib/initData';
import { postJson } from '../../lib/apiClient';
import { runProfileSync as runProfileSyncTask } from '../../lib/profileSync';
import { markRouteRender } from '../../lib/perfTelemetry';
import { useProfile } from '../../context/ProfileContext';
import { useAuth } from '../../context/AuthContext';
import { useChromeLayout } from '../../context/ChromeLayoutContext';

const API_BASE = import.meta.env.VITE_API_URL || '';

export default function MainLayout() {
  const location = useLocation();
  const route = location.pathname;
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [keyboardFromViewport, setKeyboardFromViewport] = useState(false);
  const mainScrollRef = useRef(null);
  const profileSyncInFlightRef = useRef(false);
  const primaryProfileLoadStartedRef = useRef(false);
  const { activeUser, setUsers, setActiveUserId, users, loaded } = useProfile();
  const { refetchAuth } = useAuth();
  const { suppressBottomNav } = useChromeLayout();

  useEffect(() => {
    markRouteRender(route);
  }, [route]);

  const runProfileSync = useCallback(() => {
    const hasProfileData = (activeUser?.name || '').trim() || (activeUser?.birthDate || '').trim() || (activeUser?.birthCity || '').trim() || (activeUser?.relationshipStatus || '').trim() || (activeUser?.occupation || '').trim() || (Array.isArray(activeUser?.interests) && activeUser.interests.length > 0);
    if (!hasProfileData || profileSyncInFlightRef.current) return;
    profileSyncInFlightRef.current = true;
    runProfileSyncTask()
      .then(() => {})
      .finally(() => {
        profileSyncInFlightRef.current = false;
      });
  }, [activeUser?.id, activeUser?.name, activeUser?.birthDate, activeUser?.birthTime, activeUser?.birthCity, activeUser?.gender, activeUser?.relationshipStatus, activeUser?.occupation, activeUser?.interests, activeUser?.avatarUrl]);

  useEffect(() => {
    runProfileSync();
    const t = setTimeout(runProfileSync, 2500);
    return () => clearTimeout(t);
  }, [runProfileSync]);

  const fetchAndMergeProfile = useCallback(() => {
    const initData = getInitData();
    if (!initData || users.length === 0) return;
    const current = users[0];
    if (
      (current?.birthDate || '').trim()
      && (current?.birthCity || '').trim()
      && current?.birthCityLat != null
      && current?.birthCityLon != null
    ) {
      return;
    }
    postJson(`${API_BASE}/api/user/profile/primary`, { init_data: initData }, { dedupeKey: 'profile_primary', cacheTtlMs: 5000 })
      .then(({ ok, data }) => {
        if (!ok) return;
        if (!data?.id) return;
        const bd = data.birth_date || '';
        const city = data.birth_city || '';
        const serverAvatar = data.avatar_url || '';
        const needsMerge = (
          (bd && !(current?.birthDate || '').trim())
          || (city && !(current?.birthCity || '').trim())
          || (serverAvatar && String(serverAvatar) !== String(current?.avatarUrl || ''))
          || (city && (current?.birthCityLat == null || current?.birthCityLon == null) && data.birth_lat != null)
        );
        if (needsMerge) {
          setUsers([{
            ...current,
            name: current?.name || data.name || '',
            birthDate: (current?.birthDate || '').trim() || bd,
            birthCity: (current?.birthCity || '').trim() || city,
            birthTime: (current?.birthTime || '').trim() || (data.birth_time || '12:00'),
            gender: (current?.gender || '').trim() || data.gender || '',
            relationshipStatus: (current?.relationshipStatus || '').trim() || data.relationship_status || '',
            occupation: (current?.occupation || '').trim() || data.occupation || '',
            interests: Array.isArray(current?.interests) && current.interests.length > 0 ? current.interests : (Array.isArray(data.interests) ? data.interests : []),
            avatarUrl: serverAvatar || current?.avatarUrl || null,
            birthCityLat: current?.birthCityLat != null ? current.birthCityLat : (data.birth_lat != null ? data.birth_lat : null),
            birthCityLon: current?.birthCityLon != null ? current.birthCityLon : (data.birth_lon != null ? data.birth_lon : null),
          }]);
        }
      })
      .catch(() => {});
  }, [users, setUsers]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      runProfileSync();
      refetchAuth?.();
      fetchAndMergeProfile();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [runProfileSync, refetchAuth, fetchAndMergeProfile]);

  useEffect(() => {
    const initData = getInitData();
    if (!loaded || !initData) return;
    if (primaryProfileLoadStartedRef.current) return;
    primaryProfileLoadStartedRef.current = true;
    postJson(`${API_BASE}/api/user/profile/primary`, { init_data: initData }, { dedupeKey: 'profile_primary', cacheTtlMs: 5000 })
      .then(({ ok, data }) => {
        if (!ok) return;
        if (!data?.id) return;
        const bd = data.birth_date || '';
        const city = data.birth_city || '';
        if (users.length === 0) {
          setUsers([{
            id: String(data.id),
            name: data.name || '',
            gender: data.gender || '',
            birthDate: bd,
            birthTime: data.birth_time || '12:00',
            birthCity: city,
            birthCityLat: data.birth_lat != null ? data.birth_lat : null,
            birthCityLon: data.birth_lon != null ? data.birth_lon : null,
            relationshipStatus: data.relationship_status || '',
            occupation: data.occupation || '',
            interests: Array.isArray(data.interests) ? data.interests : [],
            avatarUrl: data.avatar_url || null,
            profileLocked: false,
          }]);
          setActiveUserId(String(data.id));
        } else {
          const current = users[0];
          const serverAvatar = data.avatar_url || '';
          const needsMerge = (
            (bd && !(current?.birthDate || '').trim())
            || (city && !(current?.birthCity || '').trim())
            || (serverAvatar && String(serverAvatar) !== String(current?.avatarUrl || ''))
            || (city && (current?.birthCityLat == null || current?.birthCityLon == null) && data.birth_lat != null)
          );
          if (needsMerge) {
            setUsers([{
              ...current,
              name: current?.name || data.name || '',
              birthDate: (current?.birthDate || '').trim() || bd,
              birthCity: (current?.birthCity || '').trim() || city,
              birthTime: (current?.birthTime || '').trim() || (data.birth_time || '12:00'),
              gender: (current?.gender || '').trim() || data.gender || '',
              relationshipStatus: (current?.relationshipStatus || '').trim() || data.relationship_status || '',
              occupation: (current?.occupation || '').trim() || data.occupation || '',
              interests: Array.isArray(current?.interests) && current.interests.length > 0 ? current.interests : (Array.isArray(data.interests) ? data.interests : []),
              avatarUrl: serverAvatar || current?.avatarUrl || null,
              birthCityLat: current?.birthCityLat != null ? current.birthCityLat : (data.birth_lat != null ? data.birth_lat : null),
              birthCityLon: current?.birthCityLon != null ? current.birthCityLon : (data.birth_lon != null ? data.birth_lon : null),
            }]);
          }
        }
      })
      .catch(() => {});
  }, [loaded, users, setUsers, setActiveUserId]);

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

  const TAROT_BG = '#0e090c';
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
