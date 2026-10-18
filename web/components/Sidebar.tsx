"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Inbox, FileCheck, Users, Settings, MessageSquare } from "lucide-react";
import { getStoredUser, UserProfile } from "@/lib/api";

const NAV_ITEMS = [
  { name: "Home", href: "/", icon: Home },
  { name: "Inbox", href: "/inbox", icon: Inbox },
  { name: "Reconcile", href: "/reconcile", icon: FileCheck },
  { name: "Suppliers", href: "/suppliers", icon: Users },
  { name: "WhatsApp", href: "/whatsapp", icon: MessageSquare },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [user, setUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    setUser(getStoredUser());
  }, []);

  const isClient = user?.role === "Client";

  return (
    <aside className="w-56 bg-surface border-r border-border flex flex-col justify-between shrink-0 h-screen sticky top-0">
      <div>
        {/* Brand / Logo */}
        <div className="h-16 flex items-center px-6 border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 bg-primary text-white font-semibold rounded flex items-center justify-center text-sm shadow-sm">
              LG
            </div>
            <span className="font-semibold text-ink tracking-tight text-lg">LedgerGraph</span>
          </div>
        </div>

        {/* Navigation list - clean 6 accountant items */}
        <nav className="p-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  isActive
                    ? "bg-primary text-white"
                    : "text-ink/80 hover:bg-background hover:text-ink"
                }`}
              >
                <Icon className={`w-4 h-4 mr-3 ${isActive ? "text-white" : "text-muted"}`} />
                {item.name}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Account info at bottom */}
      <div className="p-4 border-t border-border bg-background/50">
        <div className="text-xs font-semibold text-ink uppercase tracking-wider">
          {isClient ? "Client Portal" : "CA Practice"}
        </div>
        <div className="text-xs text-muted truncate">
          {user?.firm_name || (isClient ? user?.name : "Demo CA & Associates")}
        </div>
      </div>
    </aside>
  );
}
