/**
 * System Settings page - Coming in Story 4.4
 * Placeholder page for navigation structure
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Settings } from "lucide-react";

export const metadata = {
  title: "Settings - Live Object AI Classifier",
  description: "Configure system settings and preferences",
};

export default function SettingsPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">System Settings</h1>
        <p className="text-muted-foreground mt-2">
          Configure application settings and preferences
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center space-x-2">
            <Settings className="h-5 w-5 text-gray-600" />
            <CardTitle>Coming Soon</CardTitle>
          </div>
          <CardDescription>
            System settings page will be available in Story 4.4
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This page will provide:
          </p>
          <ul className="list-disc list-inside mt-2 space-y-1 text-sm text-muted-foreground">
            <li>Data retention policy configuration</li>
            <li>Storage monitoring and cleanup</li>
            <li>AI provider settings and API keys</li>
            <li>System health monitoring</li>
            <li>Export and backup options</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
