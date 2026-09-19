import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MapPin } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardContent className="py-12 text-center space-y-4">
          <div className="p-4 bg-primary/10 rounded-full w-fit mx-auto">
            <MapPin className="h-10 w-10 text-primary" />
          </div>
          <h1 className="text-5xl font-bold">404</h1>
          <p className="text-muted-foreground">
            This page drove off somewhere else.
          </p>
          <Button asChild>
            <Link href="/dashboard">Back to dashboard</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
