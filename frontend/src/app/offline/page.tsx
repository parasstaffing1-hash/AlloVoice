"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { WifiOff, RefreshCw, FolderSync, Home } from "lucide-react";

export default function OfflinePage() {
  const retry = () => {
    window.location.reload();
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4 text-foreground">
      <Card className="w-full max-w-md">
        <CardContent className="space-y-5 py-12 text-center">
          <div className="mx-auto w-fit rounded-full bg-primary/10 p-4">
            <WifiOff className="h-10 w-10 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">You&apos;re offline</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              No internet connection. Don&apos;t worry — your work is safe on this device.
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-card/50 p-4 text-left">
            <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <FolderSync className="h-4 w-4 text-primary" /> What still works
            </p>
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
              <li>Pages you have already visited stay available from cache.</li>
              <li>New jobs, notes and updates are queued on this device.</li>
              <li>Queued actions sync automatically when you reconnect.</li>
            </ul>
          </div>
          <div className="flex flex-col gap-2">
            <Button onClick={retry} className="gap-2">
              <RefreshCw className="h-4 w-4" /> Retry connection
            </Button>
            <Button variant="outline" asChild>
              <Link href="/" className="gap-2">
                <Home className="h-4 w-4" /> Back to home
              </Link>
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Tip: keep this tab open — pending work will sync when you&apos;re back online.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
