/**
 * Dashboard home page with system overview
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CameraGrid } from "@/components/cameras/CameraGrid";
import { DashboardStats } from "@/components/dashboard/DashboardStats";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { SummaryCard } from "@/components/dashboard/SummaryCard";
import { PackageDeliveryWidget } from "@/components/dashboard/PackageDeliveryWidget";

export const metadata = {
  title: "Dashboard - ArgusAI",
  description: "AI-powered event detection and monitoring dashboard",
};

export default function DashboardPage() {
  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-2">
          System overview and statistics
        </p>
      </div>

      {/* Stats Grid - Real data */}
      <DashboardStats />

      {/* Activity Summary and Package Deliveries Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SummaryCard />
        </div>
        <div>
          <PackageDeliveryWidget />
        </div>
      </div>

      {/* Live Camera Preview Grid */}
      <CameraGrid />

      {/* Recent Activity - Real events */}
      <RecentActivity />

      {/* Quick Actions Info */}
      <Card>
        <CardHeader>
          <CardTitle>Getting Started</CardTitle>
          <CardDescription>
            Configure your system to start monitoring
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3 text-sm">
            <li className="flex items-start">
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-600 font-semibold text-xs mr-3 mt-0.5">1</span>
              <div>
                <p className="font-medium">Configure Cameras</p>
                <p className="text-muted-foreground">Add RTSP or USB cameras in the Cameras section</p>
              </div>
            </li>
            <li className="flex items-start">
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-600 font-semibold text-xs mr-3 mt-0.5">2</span>
              <div>
                <p className="font-medium">Set Up Alert Rules</p>
                <p className="text-muted-foreground">Create rules to get notifications when events occur</p>
              </div>
            </li>
            <li className="flex items-start">
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-600 font-semibold text-xs mr-3 mt-0.5">3</span>
              <div>
                <p className="font-medium">Monitor Events</p>
                <p className="text-muted-foreground">View AI-generated event descriptions on the Events page</p>
              </div>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
