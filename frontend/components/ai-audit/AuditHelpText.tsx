/**
 * #691 S5 (#733): plain-language notice for the local-first cloud audit.
 * No audit toggle exists in Settings yet (S4b/S7 add the env flag and kill
 * switch), so this is help text only.
 */
import { Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function AuditHelpText() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Info className="h-4 w-4" aria-hidden="true" />
          Local vs cloud AI audit
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground" data-testid="ai-audit-help">
        <p>
          When local AI is the primary provider, the audit sends more of your household images to the cloud than
          before. It sends a sample of key-event images (person, vehicle, package and doorbell ring), up to 200 a
          day, to cloud AI providers you have already enabled, so their descriptions can be compared with the
          local results.
        </p>
        <p>
          It never sends images to a provider you have not enabled. The paired descriptions are kept for 30 days
          and the numbers-only daily summaries for 365 days. Admins can review the pairs on the AI Audit tab.
        </p>
      </CardContent>
    </Card>
  );
}
