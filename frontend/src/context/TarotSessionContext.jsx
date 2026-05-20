import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const STORAGE_KEY = 'astrov_tarot_session_v1';

const TarotSessionContext = createContext(null);

function getStorage() {
  if (typeof window === 'undefined') return null;
  return window.sessionStorage;
}

function loadSession() {
  try {
    const storage = getStorage();
    if (!storage) return { inProgress: false, snapshot: null };
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return { inProgress: false, snapshot: null };
    const parsed = JSON.parse(raw);
    return {
      inProgress: Boolean(parsed?.inProgress),
      snapshot: parsed?.snapshot && typeof parsed.snapshot === 'object' ? parsed.snapshot : null,
    };
  } catch {
    return { inProgress: false, snapshot: null };
  }
}

export function TarotSessionProvider({ children }) {
  const [session, setSession] = useState(() => loadSession());

  useEffect(() => {
    const id = setTimeout(() => {
      try {
        const storage = getStorage();
        if (!storage) return;
        storage.setItem(STORAGE_KEY, JSON.stringify(session));
      } catch {}
    }, 150);
    return () => clearTimeout(id);
  }, [session]);

  const startSession = useCallback((snapshot = {}) => {
    setSession({
      inProgress: true,
      snapshot: { ...(snapshot || {}), updatedAt: Date.now() },
    });
  }, []);

  const updateSession = useCallback((patch = {}) => {
    setSession((prev) => ({
      inProgress: typeof patch.inProgress === 'boolean' ? patch.inProgress : prev.inProgress,
      snapshot: {
        ...(prev.snapshot || {}),
        ...(patch || {}),
        updatedAt: Date.now(),
      },
    }));
  }, []);

  const finishSession = useCallback((patch = {}) => {
    setSession((prev) => ({
      inProgress: false,
      snapshot: {
        ...(prev.snapshot || {}),
        ...(patch || {}),
        updatedAt: Date.now(),
      },
    }));
  }, []);

  const clearSession = useCallback(() => {
    setSession({ inProgress: false, snapshot: null });
    try {
      const storage = getStorage();
      if (!storage) return;
      storage.removeItem(STORAGE_KEY);
    } catch {}
  }, []);

  const value = useMemo(
    () => ({ session, startSession, updateSession, finishSession, clearSession }),
    [session, startSession, updateSession, finishSession, clearSession]
  );

  return <TarotSessionContext.Provider value={value}>{children}</TarotSessionContext.Provider>;
}

export function useTarotSession() {
  const ctx = useContext(TarotSessionContext);
  if (!ctx) throw new Error('useTarotSession must be used within TarotSessionProvider');
  return ctx;
}
