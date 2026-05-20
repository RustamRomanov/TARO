import ReferralClaim from '../ReferralClaim';
import { AuthProvider } from '../../context/AuthContext';
import { TarotSessionProvider } from '../../context/TarotSessionContext';
import { ChromeLayoutProvider } from '../../context/ChromeLayoutContext';
import MainLayout from './MainLayout';

export default function AppShell() {
  return (
    <AuthProvider>
      <TarotSessionProvider>
        <ReferralClaim />
        <ChromeLayoutProvider>
          <MainLayout />
        </ChromeLayoutProvider>
      </TarotSessionProvider>
    </AuthProvider>
  );
}
