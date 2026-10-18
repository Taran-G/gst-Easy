"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getActiveTenant, setActiveTenant, getStoredUser, clearAuth, apiFetch, UserProfile } from "@/lib/api";
import {
  Building2,
  Calendar,
  LogOut,
  ChevronDown,
  ShieldCheck,
  Plus,
  X,
  CheckCircle2,
  AlertCircle
} from "lucide-react";

interface Tenant {
  id: string;
  name: string;
  gstin: string;
  state_code: string;
  filing_freq?: string;
}

export function TopBar() {
  const router = useRouter();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [activeTenantId, setActiveTenantIdState] = useState<string>("apex");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [period, setPeriod] = useState<string>("092026"); // Sep 2026

  // Add Client Modal State (for Accountants)
  const [showAddModal, setShowAddModal] = useState(false);
  const [newClientName, setNewClientName] = useState("");
  const [newClientGstin, setNewClientGstin] = useState("");
  const [newClientFiling, setNewClientFiling] = useState("Monthly");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const fetchTenants = () => {
    apiFetch<Tenant[]>("/auth/tenants")
      .then((data: Tenant[]) => {
        if (data && data.length > 0) {
          setTenants(data);
          const current = getActiveTenant();
          if (!data.some((t) => t.id === current)) {
            setActiveTenant(data[0].id);
            setActiveTenantIdState(data[0].id);
          }
        }
      })
      .catch((err) => {
        console.warn("Failed fetching tenants:", err);
      });
  };

  useEffect(() => {
    setUser(getStoredUser());
    setActiveTenantIdState(getActiveTenant());
    fetchTenants();

    const handleTenantChange = () => {
      setActiveTenantIdState(getActiveTenant());
    };
    window.addEventListener("tenantChanged", handleTenantChange);
    return () => window.removeEventListener("tenantChanged", handleTenantChange);
  }, []);

  const handleSelectTenant = (tenantId: string) => {
    setActiveTenant(tenantId);
    setActiveTenantIdState(tenantId);
    window.location.reload();
  };

  const handleLogout = () => {
    clearAuth();
    router.push("/login");
  };

  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);

    const cleanGstin = newClientGstin.trim().toUpperCase();
    if (cleanGstin.length !== 15) {
      setModalError("GSTIN must be exactly 15 characters (e.g. 06AAACA1234A1Z5)");
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await apiFetch<Tenant>("/auth/tenants", {
        method: "POST",
        body: JSON.stringify({
          name: newClientName.trim(),
          gstin: cleanGstin,
          state_code: cleanGstin.substring(0, 2),
          filing_freq: newClientFiling,
        }),
      });

      setShowAddModal(false);
      setNewClientName("");
      setNewClientGstin("");
      setNewClientFiling("Monthly");

      // Switch to new client immediately
      setActiveTenant(created.id);
      setActiveTenantIdState(created.id);
      window.location.reload();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setModalError(err.message);
      } else {
        setModalError("Failed creating client dashboard");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const isClientRole = user?.role === "Client";
  const activeTenant = tenants.find((t) => t.id === activeTenantId);

  return (
    <>
      <header className="h-16 bg-surface border-b border-border px-6 sm:px-8 flex items-center justify-between shrink-0 sticky top-0 z-20">
        {/* Left: Client Switcher or Locked Client Badge */}
        <div className="flex items-center space-x-6">
          {isClientRole ? (
            /* CLIENT ROLE: Strictly Locked to their own dashboard */
            <div className="flex items-center space-x-2">
              <Building2 className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Business:</span>
              <div className="px-3 py-1 bg-background border border-border rounded-md text-ink font-semibold text-sm shadow-sm flex items-center space-x-1.5">
                <span>{activeTenant?.name || user?.name || "My Business"}</span>
                <span className="text-xs text-muted font-mono">
                  ({activeTenant?.gstin || "Client Account"})
                </span>
              </div>
            </div>
          ) : (
            /* ACCOUNTANT / CA ROLE: Multi-Client Switcher + Add Client button */
            <div className="flex items-center space-x-2">
              <Building2 className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Client:</span>
              <div className="relative">
                <select
                  value={activeTenantId}
                  onChange={(e) => handleSelectTenant(e.target.value)}
                  className="appearance-none bg-background border border-border text-ink font-semibold text-sm rounded-md px-3 py-1.5 pr-8 focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer shadow-sm"
                >
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.gstin.substring(0, 2)} - {t.gstin})
                    </option>
                  ))}
                  {tenants.length === 0 && (
                    <>
                      <option value="apex">Apex Auto Parts (06 - Haryana)</option>
                      <option value="greenleaf">Greenleaf Traders (24 - Gujarat)</option>
                    </>
                  )}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-muted absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>

              {/* + Add Client Button */}
              <button
                type="button"
                onClick={() => setShowAddModal(true)}
                className="inline-flex items-center space-x-1 px-2.5 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold rounded-md transition-colors"
                title="Create a new client dashboard"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Client</span>
              </button>
            </div>
          )}

          {/* Period Selector */}
          <div className="hidden sm:flex items-center space-x-2 pl-4 border-l border-border">
            <Calendar className="w-4 h-4 text-muted" />
            <span className="text-xs font-medium text-muted">Period:</span>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="bg-transparent text-sm font-medium text-ink focus:outline-none cursor-pointer"
            >
              <option value="092026">Sep 2026 (FY 2026-27)</option>
              <option value="082026">Aug 2026 (FY 2026-27)</option>
              <option value="072026">Jul 2026 (FY 2026-27)</option>
            </select>
          </div>
        </div>

        {/* Right: AI Shield badge, user profile & logout */}
        <div className="flex items-center space-x-5">
          <div className="hidden md:flex items-center space-x-1.5 px-2.5 py-1 bg-success-light text-success rounded-full text-xs font-semibold">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>AI Statutory Shield Active</span>
          </div>

          <div className="flex items-center space-x-3 text-sm">
            <div className="text-right">
              <div className="font-semibold text-ink leading-tight">
                {user?.name || (isClientRole ? "Client Portal" : "CA Rajesh Sharma")}
              </div>
              <div className="text-xs text-muted leading-tight">
                {user?.role || "Admin"} · {user?.firm_name || "Practice"}
              </div>
            </div>
            <button
              onClick={handleLogout}
              title="Log out"
              className="p-1.5 text-muted hover:text-danger hover:bg-danger-light rounded transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Add Client Modal (For Accountants) */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl shadow-xl max-w-md w-full p-6 space-y-5 animate-in fade-in-50 zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center space-x-2">
                <div className="w-8 h-8 rounded-lg bg-primary-light text-primary flex items-center justify-center font-bold">
                  <Building2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-ink">Add Client Dashboard</h3>
                  <p className="text-xs text-muted">Create an isolated statutory workspace for your client</p>
                </div>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="p-1 text-muted hover:text-ink rounded-md transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {modalError && (
              <div className="p-3 bg-danger-light border border-danger/20 text-danger rounded-lg text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleCreateClient} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
                  Client / Business Name
                </label>
                <input
                  type="text"
                  required
                  value={newClientName}
                  onChange={(e) => setNewClientName(e.target.value)}
                  placeholder="e.g. Tata Motors Dealership, Singhania Logistics"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
                  GSTIN (15 Alphanumeric)
                </label>
                <input
                  type="text"
                  required
                  maxLength={15}
                  value={newClientGstin}
                  onChange={(e) => setNewClientGstin(e.target.value.toUpperCase())}
                  placeholder="e.g. 06AAACA1234A1Z5"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm font-mono text-ink uppercase focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                />
                <p className="text-[11px] text-muted mt-1">
                  State Code: {newClientGstin.length >= 2 ? newClientGstin.substring(0, 2) : "Auto-extracted from first 2 digits"}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
                  GST Return Filing Frequency
                </label>
                <select
                  value={newClientFiling}
                  onChange={(e) => setNewClientFiling(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="Monthly">Monthly (Regular Taxpayer - GSTR-1 & 3B)</option>
                  <option value="Quarterly">Quarterly (QRMP Scheme)</option>
                </select>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border border-border text-ink hover:bg-background text-sm font-medium rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !newClientName || newClientGstin.length !== 15}
                  className="px-4 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-sm disabled:opacity-50 flex items-center space-x-1.5"
                >
                  <span>{isSubmitting ? "Creating..." : "Create Client Dashboard"}</span>
                  <CheckCircle2 className="w-4 h-4" />
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
