import ProfileSyncManager from '../ProfileSyncManager';
import { AuthProvider } from '../../context/AuthContext';
import { ProfileProvider } from '../../context/ProfileContext';
import { TarotSessionProvider } from '../../context/TarotSessionContext';
import { ChromeLayoutProvider } from '../../context/ChromeLayoutContext';
import MainLayout from './MainLayout';

export default function AppShell() {
  return (
    <AuthProvider>
      <ProfileProvider>
        <TarotSessionProvider>
          <ProfileSyncManager />
          <ChromeLayoutProvider>
            <MainLayout />
          </ChromeLayoutProvider>
        </TarotSessionProvider>
      </ProfileProvider>
    </AuthProvider>
  );
}
