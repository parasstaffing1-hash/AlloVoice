"use client";

import { ScheduleOptimizer } from "@/components/schedule-optimizer";
import { Calendar } from "lucide-react";

export default function SchedulePage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Calendar className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Smart Scheduling</h1>
          <p className="text-muted-foreground">AI-powered job assignment and route optimization</p>
        </div>
      </div>
      <ScheduleOptimizer />
    </div>
  );
}
