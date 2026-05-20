import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { getInitData } from '../lib/initData';
import { postJson } from '../lib/apiClient';

const API_BASE = import.meta.env.VITE_API_URL || '';

const AuthContext = createContext(null);

// Соответствует TARIFF_V1 в app/services/limits.py
const defaultLimits = {
  tarot: { limit: null, used: 0, price_cents: 1000, welcome_by_spread: {} },
  vision: { limit: null, used: 0, price_cents: 1000 },
  dreams: { limit: null, used: 0, price_cents: 0 },
  balance_cents: 0,
  is_paid: false,
  subscription_days_remaining: null,
};

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState({
    user: null,
    status: 'free',
    limits: defaultLimits,
    profilesCount: 0,
  });
  const [authLoaded, setAuthLoaded] = useState(false);
  const inFlightRef = useRef(null);
  const lastFetchAtRef = useRef(0);
  const lastAppliedHashRef = useRef('');

  const applyAuthState = useCallback((data) => {
    const next = {
      user: data?.user ?? null,
      status: data?.status ?? 'free',
      limits: data?.limits ?? defaultLimits,
      profilesCount: data?.profiles_count ?? 0,
    };
    const hash = JSON.stringify(next);
    if (hash === lastAppliedHashRef.current) return;
    lastAppliedHashRef.current = hash;
    setAuth(next);
  }, []);

  const fetchAuth = useCallback(() => {
    const now = Date.now();
    if (inFlightRef.current) return inFlightRef.current;
    if (authLoaded && now - lastFetchAtRef.current < 1200) return Promise.resolve();
    const initData = getInitData();
    if (!initData) {
      setAuthLoaded(true);
      return Promise.resolve();
    }
    let profilePayload = {};
    try {
      const raw = typeof window !== 'undefined' && window.localStorage.getItem('astrov_profile');
      if (raw) {
        const data = JSON.parse(raw);
        const users = Array.isArray(data?.users) ? data.users : [];
        const u = users[0];
        if (u) {
          profilePayload = {
            profile_name: (u.name || '').trim(),
            profile_birth_date: (u.birthDate || '').trim(),
            profile_birth_time: (u.birthTime || '12:00').trim(),
            profile_birth_city: (u.birthCity || '').trim(),
            profile_gender: (u.gender || '').trim(),
          };
        }
      }
    } catch (_) {}
    const request = postJson(`${API_BASE}/api/user/auth`, { init_data: initData, ...profilePayload }, { dedupeKey: 'auth' })
      .then(({ ok, data }) => {
        if (!ok || !data) return;
        applyAuthState(data);
        lastFetchAtRef.current = Date.now();
      })
      .catch(() => {})
      .finally(() => {
        inFlightRef.current = null;
        setAuthLoaded(true);
      });
    inFlightRef.current = request;
    return request;
  }, [applyAuthState, authLoaded]);

  useEffect(() => {
    fetchAuth();
  }, [fetchAuth]);

  const value = { ...auth, authLoaded, refetchAuth: fetchAuth };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  return (
    ctx || {
      user: null,
      status: 'free',
      limits: defaultLimits,
      profilesCount: 0,
      authLoaded: true,
      refetchAuth: () => Promise.resolve(),
    }
  );
}
