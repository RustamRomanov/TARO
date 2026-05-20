import { createContext, useContext, useState, useEffect, useMemo, useRef } from 'react';

const STORAGE_KEY = 'astrov_profile';

function normalizeAvatarForStorage(rawUrl) {
  const url = typeof rawUrl === 'string' ? rawUrl.trim() : '';
  if (!url) return null;
  if (url.startsWith('blob:')) return null;
  if (url.startsWith('uploads/')) return `/${url}`;
  if (
    url.startsWith('/') ||
    url.startsWith('http://') ||
    url.startsWith('https://') ||
    url.startsWith('data:image/')
  ) {
    return url;
  }
  return null;
}

function loadProfile() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { users: [], activeUserId: null };
    const data = JSON.parse(raw);
    const rawUsers = Array.isArray(data?.users) ? data.users : [];
    if (rawUsers.length === 0) return { users: [], activeUserId: null };
    const user = {
      ...rawUsers[0],
      avatarUrl: normalizeAvatarForStorage(rawUsers[0]?.avatarUrl),
    };
    return { users: [user], activeUserId: user?.id ?? null };
  } catch {
    return { users: [], activeUserId: null };
  }
}

function saveProfile(users, activeUserId) {
  try {
    const single = Array.isArray(users) && users.length > 0 ? [users[0]] : [];
    const toSave = single.map((u) => ({
      ...u,
      avatarUrl: normalizeAvatarForStorage(u.avatarUrl),
    }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ users: toSave, activeUserId: toSave[0]?.id ?? null }));
  } catch {}
}

const ProfileContext = createContext(null);

export function ProfileProvider({ children }) {
  const [users, setUsers] = useState([]);
  const [activeUserId, setActiveUserId] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const lastSavedRawRef = useRef('');

  useEffect(() => {
    const { users: u, activeUserId: aid } = loadProfile();
    setUsers(u);
    setActiveUserId(aid);
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    try {
      const single = Array.isArray(users) && users.length > 0 ? [users[0]] : [];
      const toSave = single.map((u) => ({
        ...u,
        avatarUrl: normalizeAvatarForStorage(u.avatarUrl),
      }));
      const raw = JSON.stringify({ users: toSave, activeUserId: toSave[0]?.id ?? null });
      if (raw === lastSavedRawRef.current) return;
      lastSavedRawRef.current = raw;
      saveProfile(users, activeUserId);
    } catch {
      saveProfile(users, activeUserId);
    }
  }, [loaded, users, activeUserId]);

  const activeUser = useMemo(
    () => users.find((u) => u.id === activeUserId) || users[0] || null,
    [users, activeUserId]
  );

  const value = useMemo(
    () => ({
      users,
      setUsers,
      activeUserId,
      setActiveUserId,
      activeUser,
      loaded,
    }),
    [users, activeUserId, activeUser, loaded]
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfile must be used within ProfileProvider');
  return ctx;
}
