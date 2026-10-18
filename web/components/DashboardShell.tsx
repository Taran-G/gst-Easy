"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { getStoredToken } from "@/lib/api";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (!pathname.includes("/login")) {
      const token = getStoredToken();
      if (!token) {
        router.push("/login");
      }
    }
  }, [pathname, router]);

  if (!mounted) return null;

  if (pathname.includes("/login")) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        
        {/* Quiet Persistent Mock/Demo mode banner per SRS §7.3 */}
        <div className="bg-amber-50/70 border-b border-amber-200/50 px-8 py-1.5 text-xs text-amber-900/80 flex items-center justify-between">
          <span>Demo / Mock Mode · Deterministic Validation & FalkorDB Isolated Graphs Active</span>
          <span className="font-mono text-[11px] text-amber-800">Tenant: {typeof window !== "undefined" ? localStorage.getItem("lg_active_tenant") || "apex" : "apex"}</span>
        </div>

        <main className="flex-1 p-8 max-w-[1120px] w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
