/**
 * Alert Rules page - Coming in Story 5.2
 * Placeholder page for navigation structure
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Bell } from "lucide-react";

export const metadata = {
  title: "Alert Rules - Live Object AI Classifier",
  description: "Manage alert rules and notifications",
};

export default function RulesPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Alert Rules</h1>
        <p className="text-muted-foreground mt-2">
          Configure rules to receive notifications for specific events
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center space-x-2">
            <Bell className="h-5 w-5 text-yellow-600" />
            <CardTitle>Coming Soon</CardTitle>
          </div>
          <CardDescription>
            Alert rule configuration will be available in Epic 5
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This page will include:
          </p>
          <ul className="list-disc list-inside mt-2 space-y-1 text-sm text-muted-foreground">
            <li>Create and manage alert rules</li>
            <li>Configure conditions (object type, confidence, camera)</li>
            <li>Set up webhook integrations</li>
            <li>Test alert rules before deploying</li>
            <li>View alert history and logs</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
