/**
 * Чтение профиля из localStorage и вызов sync API.
 * Работает независимо от React, вызывается по таймеру.
 */
import { getInitData } from './initData';

const STORAGE_KEY = 'astrov_profile';
const API_BASE = import.meta.env.VITE_API_URL || '';
let inFlightPromise = null;
let lastPayloadKey = '';
let lastSuccessAt = 0;

function normalizeAvatarForBackend(rawUrl) {
  const url = typeof rawUrl === 'string' ? rawUrl.trim() : '';
  if (!url) return '';
  if (url.startsWith('uploads/')) return `/${url}`;
  if (url.startsWith('/') || url.startsWith('http://') || url.startsWith('https://')) return url;
  return '';
}

function getProfileFromStorage() {
  try {
    const raw = typeof window !== 'undefined' && window.localStorage?.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    const users = Array.isArray(data?.users) ? data.users : [];
    return users[0] || null;
  } catch {
    return null;
  }
}

export async function runProfileSync() {
  const initData = getInitData();
  const u = getProfileFromStorage();
  if (!initData || !u) return false;
  const hasData = (u.name || '').trim() || (u.birthDate || '').trim() || (u.birthCity || '').trim() || (u.avatarUrl || '').trim();
  if (!hasData) return false;
  const payload = {
    init_data: initData,
    name: (u.name || '').trim(),
    gender: (u.gender || '').trim(),
    birth_date: (u.birthDate || '').trim(),
    birth_time: (u.birthTime || '12:00').trim(),
    birth_city: (u.birthCity || '').trim(),
    avatar_url: normalizeAvatarForBackend(u.avatarUrl),
  };
  if (u.birthCityLat != null && u.birthCityLon != null) {
    payload.birth_lat = u.birthCityLat;
    payload.birth_lon = u.birthCityLon;
  }
  const payloadKey = JSON.stringify(payload);
  const now = Date.now();
  if (inFlightPromise) return inFlightPromise;
  if (payloadKey === lastPayloadKey && now - lastSuccessAt < 30_000) return true;
  try {
    inFlightPromise = fetch(`${API_BASE}/api/user/profile/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((res) => {
      if (res.ok) {
        lastPayloadKey = payloadKey;
        lastSuccessAt = Date.now();
      }
      return res.ok;
    }).finally(() => {
      inFlightPromise = null;
    });
    return await inFlightPromise;
  } catch {
    inFlightPromise = null;
    return false;
  }
}
