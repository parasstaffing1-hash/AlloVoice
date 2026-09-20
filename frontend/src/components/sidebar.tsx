"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Users, Briefcase, FileText, Receipt, Mic, Star,
  Settings, LogOut, Zap, Shield, Calendar, Package, Truck, BarChart3,
  BookOpen, Globe, CreditCard, PenTool, DollarSign, LayoutGrid, UsersRound,
  AlertTriangle, ClipboardCheck, FileCheck, Search as SearchIcon, Sparkles,
  Plug, Trophy, Warehouse, Clock, Siren, Palette, Wrench, PhoneCall, Headset,
} from "lucide-react";
import { useAuth } from "@/lib/store";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "AI Quote", href: "/quote", icon: Mic },
  { name: "Jobs", href: "/jobs", icon: Briefcase },
  { name: "Customers", href: "/customers", icon: Users },
  { name: "Quotes", href: "/quotes", icon: FileText },
  { name: "Invoices", href: "/invoices", icon: Receipt },
  { name: "Reviews", href: "/reviews", icon: Star },
];

const operations = [
  { name: "Contracts", href: "/contracts", icon: Calendar },
  { name: "Inventory", href: "/inventory", icon: Package },
  { name: "Warehouses", href: "/warehouses", icon: Warehouse },
  { name: "Fleet", href: "/fleet", icon: Truck },
  { name: "Calendar", href: "/calendar", icon: Calendar },
  { name: "Attendance", href: "/attendance", icon: Clock },
  { name: "Memberships", href: "/memberships", icon: UsersRound },
  { name: "Price Book", href: "/pricebook", icon: DollarSign },
  { name: "Schedule", href: "/schedule", icon: LayoutGrid },
  { name: "Voice Agent", href: "/voice-agent", icon: Mic },
  { name: "Live Talk", href: "/talk", icon: PhoneCall },
  { name: "Call Log", href: "/calls", icon: Headset },
  { name: "Fault Codes", href: "/fault-codes", icon: Wrench },
  { name: "RAMS", href: "/rams", icon: ClipboardCheck },
];

const business = [
  { name: "Reports", href: "/reports", icon: BarChart3 },
  { name: "Scorecards", href: "/scorecards", icon: Trophy },
  { name: "Knowledge Base", href: "/kb", icon: BookOpen },
  { name: "GDPR", href: "/gdpr", icon: Shield },
  { name: "Compliance", href: "/compliance", icon: ClipboardCheck },
  { name: "CIS Tax", href: "/cis", icon: FileCheck },
  { name: "AI Insights", href: "/ai-insights", icon: Sparkles },
  { name: "Integrations", href: "/integrations", icon: Plug },
  { name: "Safety", href: "/safety", icon: Siren },
  { name: "Branding", href: "/branding", icon: Palette },
  { name: "Billing", href: "/billing", icon: CreditCard },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-border bg-card/50 backdrop-blur-xl overflow-y-auto">
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-border px-6 py-5">
          <Zap className="h-6 w-6 text-primary" />
          <span className="text-xl font-bold gradient-text">VoiceField</span>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </Link>
            );
          })}

          <div className="pt-3 mt-3 border-t border-border">
            <p className="px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Operations</p>
            {operations.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  {item.name}
                </Link>
              );
            })}
          </div>

          <div className="pt-3 mt-3 border-t border-border">
            <p className="px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Business</p>
            {business.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  {item.name}
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="border-t border-border p-4">
          <div className="flex items-center gap-3 rounded-lg px-3 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-primary text-sm font-bold">
              {user?.full_name?.charAt(0) || "U"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.full_name}</p>
              <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
            </div>
            <button
              onClick={logout}
              className="text-muted-foreground hover:text-destructive transition-colors"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
