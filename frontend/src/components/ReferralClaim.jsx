import { useEffect } from 'react';
import { getInitData } from '../lib/initData';

const API_BASE = import.meta.env.VITE_API_URL || '';

/** Реферальный бонус при старте (код оплаты сохранён, UI скрыт). */
export default function ReferralClaim() {
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

  return null;
}
