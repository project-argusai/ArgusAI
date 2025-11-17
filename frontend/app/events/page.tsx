/**
 * Events Timeline page - Coming in Story 4.2
 * Placeholder page for navigation structure
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Calendar } from "lucide-react";

export const metadata = {
  title: "Events - Live Object AI Classifier",
  description: "View and search detected events",
};

export default function EventsPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Events Timeline</h1>
        <p className="text-muted-foreground mt-2">
          View all detected events with AI-generated descriptions
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center space-x-2">
            <Calendar className="h-5 w-5 text-blue-600" />
            <CardTitle>Coming Soon</CardTitle>
          </div>
          <CardDescription>
            Event timeline view with filtering will be available in Story 4.2
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This page will display:
          </p>
          <ul className="list-disc list-inside mt-2 space-y-1 text-sm text-muted-foreground">
            <li>Chronological timeline of detected events</li>
            <li>AI-generated descriptions with thumbnails</li>
            <li>Filtering by camera, date range, and object type</li>
            <li>Full-text search capabilities</li>
            <li>Event detail modal with actions</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
