/**
 * Setup Page
 * First-run setup wizard for configuring the application
 * FF-008: Installation Script & Setup Wizard
 */

'use client';

import { useRouter } from 'next/navigation';
import { SetupWizard } from '@/components/setup/SetupWizard';

export default function SetupPage() {
  const router = useRouter();

  const handleComplete = () => {
    // Mark setup as complete in localStorage
    if (typeof window !== 'undefined') {
      localStorage.setItem('setup_complete', 'true');
    }
    // Redirect to dashboard
    router.push('/');
  };

  return <SetupWizard onComplete={handleComplete} />;
}
