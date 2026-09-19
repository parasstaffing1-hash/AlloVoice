"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import CommandPalette from "@/components/command-palette";
import { useAuth } from "@/lib/store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { token, user, loadUser } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!token) {
      router.push("/login");
      return;
    }
    if (!user) {
      loadUser();
    }
  }, [token, user, loadUser, router]);

  if (!token) return null;

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="ml-64 p-8">{children}</main>
      <CommandPalette />
    </div>
  );
}
