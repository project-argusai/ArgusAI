/**
 * Dashboard home page with system overview
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Activity, Camera, Calendar, Bell, TrendingUp } from "lucide-react";
import { CameraGrid } from "@/components/cameras/CameraGrid";

export const metadata = {
  title: "Dashboard - Live Object AI Classifier",
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

      {/* Stats Grid - Placeholder cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Events</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
            <p className="text-xs text-muted-foreground">
              Coming in Story 4.2
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Cameras</CardTitle>
            <Camera className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
            <p className="text-xs text-muted-foreground">
              See Cameras page
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Alert Rules</CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
            <p className="text-xs text-muted-foreground">
              Coming in Epic 5
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Today&apos;s Activity</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
            <p className="text-xs text-muted-foreground">
              Events detected today
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Live Camera Preview Grid */}
      <CameraGrid />

      {/* Recent Activity */}
      <Card>
        <CardHeader>
          <div className="flex items-center space-x-2">
            <Activity className="h-5 w-5 text-blue-600" />
            <CardTitle>Recent Activity</CardTitle>
          </div>
          <CardDescription>
            Latest events from all cameras
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-8">
            Event timeline will be available in Story 4.2
          </p>
        </CardContent>
      </Card>

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
                <p className="text-muted-foreground">Create rules to get notifications (Coming in Epic 5)</p>
              </div>
            </li>
            <li className="flex items-start">
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-600 font-semibold text-xs mr-3 mt-0.5">3</span>
              <div>
                <p className="font-medium">Monitor Events</p>
                <p className="text-muted-foreground">View AI-generated event descriptions (Coming in Story 4.2)</p>
              </div>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
