import { useEffect, useRef } from 'react';
import { runProfileSync } from '../lib/profileSync';
import { getInitData } from '../lib/initData';

const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Фоновый sync профиля: каждые 4 сек пытается отправить профиль из localStorage на бэкенд.
 * Останавливается после 3 успешных sync подряд.
 */
export default function ProfileSyncManager() {
  const successCount = useRef(0);

  useEffect(() => {
    const claimReferral = async () => {
      const init = getInitData() || '';
      if (!init.trim()) return;
      try {
        await fetch(`${API_BASE}/api/payments/referral/claim`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: init }),
        });
      } catch {
        // ignore
      }
    };
    claimReferral();
    const t = setTimeout(claimReferral, 3000);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const trySync = async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      const ok = await runProfileSync();
      if (ok) {
        successCount.current += 1;
      } else {
        successCount.current = 0;
      }
    };

    trySync();
    const t1 = setTimeout(trySync, 2000);
    const t2 = setTimeout(trySync, 4000);
    const iv = setInterval(async () => {
      if (successCount.current >= 3) return;
      await trySync();
    }, 8000);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearInterval(iv);
    };
  }, []);

  return null;
}
