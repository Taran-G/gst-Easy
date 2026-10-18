"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { formatRupees, getActiveTenant, apiFetch } from "@/lib/api";
import {
  ArrowRight,
  AlertTriangle,
  Clock,
  Inbox,
  Users,
  Bot,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  FileCheck,
  Building2
} from "lucide-react";

interface StatusCounts {
  all?: number;
  needs_review?: number;
  ready?: number;
  blocked?: number;
  approved?: number;
}

interface ITCSummary {
  matched_itc: number;
  variance_itc: number;
  at_risk_itc: number;
  timing_gap_itc: number;
  total_claimable: number;
}

interface ReconResponse {
  counts: {
    matched: number;
    missing_in_2b: number;
    expected_timing_gap: number;
  };
  itc_summary: ITCSummary;
}

interface Rule37Alert {
  invoice_id: string;
  tax_at_stake: number;
}

interface VendorRisk {
  gstin: string;
  risk_level: string;
}

interface AutomationLog {
  id: string;
  timestamp: string;
  event: string;
  message: string;
  level: string;
  details?: Record<string, unknown>;
}

interface AutomationStatus {
  is_running: boolean;
  interval_seconds: number;
  cycle_count: number;
  last_run: string | null;
  invoices_processed_count: number;
  alerts_generated_count: number;
  email_mode: string;
  email_username: string;
  email_unread_count: number;
  logs: AutomationLog[];
}

export default function HomePage() {
  const [activeTenant, setActiveTenantState] = useState("apex");
  const [loading, setLoading] = useState(true);
  const [statusCounts, setStatusCounts] = useState<StatusCounts>({});
  const [reconData, setReconData] = useState<ReconResponse | null>(null);
  const [rule37Count, setRule37Count] = useState<number>(0);
  const [highRiskVendorsCount, setHighRiskVendorsCount] = useState<number>(0);

  // Autonomous Engine State
  const [autoStatus, setAutoStatus] = useState<AutomationStatus | null>(null);
  const [runningCycle, setRunningCycle] = useState(false);
  const [triggeringTest, setTriggeringTest] = useState(false);
  const [testSuccessMessage, setTestSuccessMessage] = useState<string | null>(null);

  const fetchDashboardData = () => {
    Promise.allSettled([
      apiFetch<{ status_counts?: StatusCounts }>("/invoices"),
      apiFetch<ReconResponse>("/reconcile/092026"),
      apiFetch<Rule37Alert[]>("/rules37/aging"),
      apiFetch<VendorRisk[]>("/risk/vendors"),
      apiFetch<AutomationStatus>("/automation/status"),
    ]).then(([invoicesRes, reconRes, rulesRes, vendorsRes, autoRes]) => {
      if (invoicesRes.status === "fulfilled" && invoicesRes.value.status_counts) {
        setStatusCounts(invoicesRes.value.status_counts);
      }
      if (reconRes.status === "fulfilled") {
        setReconData(reconRes.value);
      }
      if (rulesRes.status === "fulfilled" && Array.isArray(rulesRes.value)) {
        setRule37Count(rulesRes.value.length);
      }
      if (vendorsRes.status === "fulfilled" && Array.isArray(vendorsRes.value)) {
        const highRisk = vendorsRes.value.filter((v) => v.risk_level === "High" || v.risk_level === "Medium");
        setHighRiskVendorsCount(highRisk.length);
      }
      if (autoRes.status === "fulfilled") {
        setAutoStatus(autoRes.value);
      }
      setLoading(false);
    });
  };

  useEffect(() => {
    const tenant = getActiveTenant();
    setActiveTenantState(tenant);
    fetchDashboardData();

    // Periodic live feed refresh
    const interval = setInterval(() => {
      apiFetch<AutomationStatus>("/automation/status")
        .then((data) => setAutoStatus(data))
        .catch(() => {});
    }, 6000);

    return () => clearInterval(interval);
  }, []);

  const handleRunCycleNow = async () => {
    setRunningCycle(true);
    setTestSuccessMessage(null);
    try {
      await apiFetch("/automation/run-now", { method: "POST" });
      const updated = await apiFetch<AutomationStatus>("/automation/status");
      setAutoStatus(updated);
      fetchDashboardData();
    } catch (err: unknown) {
      console.error("Failed running autonomous cycle:", err);
    } finally {
      setRunningCycle(false);
    }
  };

  const handleTriggerTest = async (isGstr2b: boolean, companyName: string = "Tata Steel Ltd") => {
    setTriggeringTest(true);
    setTestSuccessMessage(null);
    try {
      if (isGstr2b) {
        await apiFetch("/automation/email/simulate-incoming", {
          method: "POST",
          body: JSON.stringify({
            is_gstr2b_notification: true,
            subject: "GST Portal: Intimation of auto-drafted ITC statement in Form GSTR-2B for period 092026",
            body: "Form GSTR-2B for the tax period September 2026 (092026) has been generated and is available for download on the GST Portal.",
          }),
        });
        setTestSuccessMessage("GSTR-2B filing notification delivered! AI Auto-Pilot triggered 2B reconciliation.");
      } else {
        await apiFetch("/automation/email/simulate-incoming", {
          method: "POST",
          body: JSON.stringify({
            is_gstr2b_notification: false,
            from_addr: `accounts@${companyName.toLowerCase().replace(/[^a-z0-9]/g, "")}.com`,
            subject: `Tax Invoice INV-2026-990 from ${companyName}`,
            body: `Dear Accounts Team, please find tax invoice from ${companyName} attached for material supplied.`,
            fixture_name: "clean_intrastate",
            company_name: companyName,
          }),
        });
        setTestSuccessMessage(`Tax invoice from '${companyName}' delivered! AI Auto-Pilot triggered GSTIN verification.`);
      }

      // Immediately run cycle to process it
      await apiFetch("/automation/run-now", { method: "POST" });
      const updated = await apiFetch<AutomationStatus>("/automation/status");
      setAutoStatus(updated);
      fetchDashboardData();
    } catch (err: unknown) {
      console.error("Failed triggering test notification:", err);
    } finally {
      setTriggeringTest(false);
    }
  };

  const tenantName = activeTenant === "apex" ? "Apex Auto Parts" : activeTenant;

  const totalBills = statusCounts.all || 0;
  const needsReview = statusCounts.needs_review || 0;
  const readyBills = statusCounts.ready || 0;
  const blockedBills = statusCounts.blocked || 0;

  const itc = reconData?.itc_summary || {
    matched_itc: 0,
    variance_itc: 0,
    at_risk_itc: 0,
    timing_gap_itc: 0,
    total_claimable: 0,
  };

  const totalItc = itc.total_claimable || (itc.matched_itc + itc.at_risk_itc + itc.timing_gap_itc) || 1;
  const matchedPct = Math.round((itc.matched_itc / totalItc) * 100);
  const timingPct = Math.round((itc.timing_gap_itc / totalItc) * 100);
  const atRiskPct = Math.min(100 - matchedPct - timingPct, Math.round((itc.at_risk_itc / totalItc) * 100));

  return (
    <div className={`space-y-8 transition-opacity duration-300 ${loading ? "opacity-60 pointer-events-none" : "opacity-100"}`}>
      {/* Calm Greeting with Real Data */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-ink tracking-tight">
            Dashboard · {tenantName}
          </h1>
          <p className="text-muted text-sm">
            {needsReview === 0
              ? `All purchase bills reviewed. ${formatRupees(itc.at_risk_itc)} tax credit continuously monitored.`
              : `${needsReview} ${needsReview === 1 ? "bill needs" : "bills need"} review. ${formatRupees(itc.at_risk_itc)} tax credit needs attention.`}
          </p>
        </div>

        {/* Live Channel Status Chip */}
        <div className="flex items-center space-x-2 px-3 py-1.5 bg-surface border border-border rounded-lg text-xs font-semibold text-ink shadow-sm">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-success"></span>
          </span>
          <span>AI Auto-Pilot Monitoring Active</span>
        </div>
      </div>

      {/* Real ITC Summary Bar */}
      <div className="bg-surface border border-border rounded-xl p-5 space-y-3 shadow-sm">
        <div className="flex justify-between items-center text-xs font-semibold uppercase tracking-wider text-muted">
          <span>Input Tax Credit (ITC) Breakdown · Sep 2026</span>
          <span className="text-ink font-semibold">
            Total Claimable: {formatRupees(itc.total_claimable || (itc.matched_itc + itc.at_risk_itc + itc.timing_gap_itc))}
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-3 w-full bg-border/40 rounded-full flex overflow-hidden">
          <div
            style={{ width: `${matchedPct}%` }}
            className="bg-success transition-all duration-300"
            title={`Matched in GSTR-2B (${matchedPct}%)`}
          />
          <div
            style={{ width: `${timingPct}%` }}
            className="bg-warning transition-all duration-300"
            title={`Pending GSTR-2B reflection (${timingPct}%)`}
          />
          <div
            style={{ width: `${atRiskPct}%` }}
            className="bg-danger transition-all duration-300"
            title={`At Risk (${atRiskPct}%)`}
          />
        </div>

        <div className="flex items-center space-x-6 text-xs pt-1">
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-success shrink-0" />
            <span className="text-ink font-medium">Matched 2B: {formatRupees(itc.matched_itc)}</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-warning shrink-0" />
            <span className="text-ink font-medium">Pending 2B: {formatRupees(itc.timing_gap_itc)}</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-danger shrink-0" />
            <span className="text-ink font-medium">At Risk: {formatRupees(itc.at_risk_itc)}</span>
          </div>
        </div>
      </div>

      {/* 4 Large Calm Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card 1: To Review */}
        <div className="bg-surface border border-border rounded-xl p-6 flex flex-col justify-between space-y-4 shadow-sm hover:border-primary/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Purchase Inbox</span>
              <div className="text-3xl font-bold text-ink">{totalBills} {totalBills === 1 ? "Bill" : "Bills"}</div>
              <p className="text-sm text-muted">
                {readyBills} ready for approval, {blockedBills} blocked with errors.
              </p>
            </div>
            <div className="p-3 bg-primary-light text-primary rounded-lg">
              <Inbox className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/inbox"
            className="inline-flex items-center justify-between w-full px-4 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover transition-colors"
          >
            <span>Review Bills in Queue</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Card 2: Tax Credit at Risk */}
        <div className="bg-surface border border-border rounded-xl p-6 flex flex-col justify-between space-y-4 shadow-sm hover:border-danger/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Tax Credit at Risk</span>
              <div className="text-3xl font-bold text-danger">{formatRupees(itc.at_risk_itc)}</div>
              <p className="text-sm text-muted">
                {reconData?.counts.missing_in_2b || 0} bills missing in GSTR-2B requiring payment hold.
              </p>
            </div>
            <div className="p-3 bg-danger-light text-danger rounded-lg">
              <AlertTriangle className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/reconcile"
            className="inline-flex items-center justify-between w-full px-4 py-2 bg-surface border border-border text-ink hover:bg-background text-sm font-semibold rounded-lg transition-colors"
          >
            <span>Inspect 2B Reconciliation</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Card 3: Deadlines Coming Up */}
        <div className="bg-surface border border-border rounded-xl p-6 flex flex-col justify-between space-y-4 shadow-sm hover:border-warning/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Statutory Deadlines</span>
              <div className="text-3xl font-bold text-ink">
                {rule37Count > 0 ? `${rule37Count} Aging Alerts` : "Rule 37 Compliant"}
              </div>
              <p className="text-sm text-muted">
                {rule37Count > 0
                  ? `${rule37Count} invoices approaching 180-day ITC reversal statutory cutoff.`
                  : "Zero bills currently exceeding the 150-day aging threshold."}
              </p>
            </div>
            <div className="p-3 bg-warning-light text-warning rounded-lg">
              <Clock className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/reconcile?tab=deadlines"
            className="inline-flex items-center justify-between w-full px-4 py-2 bg-surface border border-border text-ink hover:bg-background text-sm font-semibold rounded-lg transition-colors"
          >
            <span>Check Rule 37 & 37A Schedule</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Card 4: Suppliers to Follow Up */}
        <div className="bg-surface border border-border rounded-xl p-6 flex flex-col justify-between space-y-4 shadow-sm hover:border-primary/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Supplier Risk & Chases</span>
              <div className="text-3xl font-bold text-ink">
                {highRiskVendorsCount > 0 ? `${highRiskVendorsCount} High-Risk Vendors` : "Vendors Compliant"}
              </div>
              <p className="text-sm text-muted">
                {highRiskVendorsCount > 0
                  ? `${highRiskVendorsCount} suppliers flagged with suspended GSTIN or delayed GSTR-3B filings.`
                  : "All active suppliers in good standing with monthly tax filings."}
              </p>
            </div>
            <div className="p-3 bg-primary-light text-primary rounded-lg">
              <Users className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/suppliers"
            className="inline-flex items-center justify-between w-full px-4 py-2 bg-surface border border-border text-ink hover:bg-background text-sm font-semibold rounded-lg transition-colors"
          >
            <span>View Suppliers & Compliance Advice</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      {/* AUTONOMOUS AI AUTO-PILOT SECTION */}
      <div className="bg-surface border border-border rounded-xl p-6 space-y-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-border gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-primary text-white flex items-center justify-center shadow-sm">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-ink">Autonomous AI Auto-Pilot</h3>
                <span className="px-2 py-0.5 bg-success-light text-success rounded-full text-[11px] font-semibold">
                  Live Background Engine
                </span>
              </div>
              <p className="text-xs text-muted">
                Monitors real Gmail and WhatsApp notifications, verifies incoming bills, and triggers GSTR-2B sweeps automatically.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={handleRunCycleNow}
              disabled={runningCycle}
              className="px-3.5 py-1.5 bg-primary text-white text-xs font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-sm disabled:opacity-50 flex items-center space-x-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${runningCycle ? "animate-spin" : ""}`} />
              <span>{runningCycle ? "Scanning Channels..." : "Run Channel Scan Now"}</span>
            </button>

            <Link
              href="/settings"
              className="px-3 py-1.5 border border-border text-ink hover:bg-background text-xs font-semibold rounded-lg transition-colors"
            >
              Configure Gmail API
            </Link>
          </div>
        </div>

        {testSuccessMessage && (
          <div className="p-3 bg-success-light border border-success/20 text-success rounded-lg text-xs flex items-center space-x-2 animate-in fade-in-50">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{testSuccessMessage}</span>
          </div>
        )}

        {/* 4 Stats Chips */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="p-3.5 bg-background border border-border rounded-lg space-y-1">
            <div className="text-[11px] font-semibold text-muted uppercase">Ingested by AI</div>
            <div className="text-xl font-bold text-ink">{autoStatus?.invoices_processed_count || 0} Bills</div>
            <div className="text-[11px] text-muted">Auto-extracted & verified</div>
          </div>

          <div className="p-3.5 bg-background border border-border rounded-lg space-y-1">
            <div className="text-[11px] font-semibold text-muted uppercase">Monitored Channels</div>
            <div className="text-sm font-bold text-ink truncate">Gmail & WhatsApp</div>
            <div className="text-[11px] text-muted">IMAP SSL + Webhook Active</div>
          </div>

          <div className="p-3.5 bg-background border border-border rounded-lg space-y-1">
            <div className="text-[11px] font-semibold text-muted uppercase">GSTR-2B Trigger</div>
            <div className="text-sm font-bold text-success flex items-center space-x-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Auto-Sync Active</span>
            </div>
            <div className="text-[11px] text-muted">Triggers on return notice</div>
          </div>

          <div className="p-3.5 bg-background border border-border rounded-lg space-y-1">
            <div className="text-[11px] font-semibold text-muted uppercase">Rule 37 Radar</div>
            <div className="text-sm font-bold text-ink">150-Day Sweeper</div>
            <div className="text-[11px] text-muted">Runs every cycle</div>
          </div>
        </div>

        {/* Instant Autonomous Trigger Test Bar */}
        <div className="p-4 bg-primary-light/30 border border-primary/20 rounded-lg space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-xs font-semibold text-ink">
              <Sparkles className="w-4 h-4 text-primary" />
              <span>Simulate Real Autonomous Triggers:</span>
            </div>
            <span className="text-[11px] text-muted">Test how AI triggers on incoming company invoices or 2B notices</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              onClick={() => handleTriggerTest(false, "Tata Motors Ltd")}
              disabled={triggeringTest}
              className="px-3 py-1.5 bg-surface border border-border hover:border-primary text-ink text-xs font-medium rounded-md transition-colors shadow-sm disabled:opacity-50 flex items-center space-x-1.5"
            >
              <Building2 className="w-3.5 h-3.5 text-primary" />
              <span>Receive Invoice from &quot;Tata Motors Ltd&quot;</span>
            </button>

            <button
              onClick={() => handleTriggerTest(false, "Reliance Industries")}
              disabled={triggeringTest}
              className="px-3 py-1.5 bg-surface border border-border hover:border-primary text-ink text-xs font-medium rounded-md transition-colors shadow-sm disabled:opacity-50 flex items-center space-x-1.5"
            >
              <Building2 className="w-3.5 h-3.5 text-primary" />
              <span>Receive Invoice from &quot;Reliance Industries&quot;</span>
            </button>

            <button
              onClick={() => handleTriggerTest(true)}
              disabled={triggeringTest}
              className="px-3 py-1.5 bg-surface border border-success/40 hover:border-success text-ink text-xs font-medium rounded-md transition-colors shadow-sm disabled:opacity-50 flex items-center space-x-1.5"
            >
              <FileCheck className="w-3.5 h-3.5 text-success" />
              <span>Receive GSTR-2B Filing Notification Email</span>
            </button>
          </div>
        </div>

        {/* Live Autonomous Activity Feed */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted uppercase tracking-wider">
              Live Autonomous Activity Stream
            </span>
            <span className="text-[11px] text-muted">Auto-refreshes every 6 seconds</span>
          </div>

          <div className="border border-border rounded-lg divide-y divide-border bg-background/50 max-h-56 overflow-y-auto">
            {autoStatus?.logs && autoStatus.logs.length > 0 ? (
              autoStatus.logs.slice(0, 6).map((log) => {
                const isSuccess = log.level === "SUCCESS";
                const isWarning = log.level === "WARNING";
                const isError = log.level === "ERROR";

                return (
                  <div key={log.id} className="p-3 text-xs flex items-start justify-between space-x-3">
                    <div className="flex items-start space-x-2.5">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase shrink-0 mt-0.5 ${
                          isSuccess
                            ? "bg-success-light text-success"
                            : isWarning
                            ? "bg-warning-light text-warning"
                            : isError
                            ? "bg-danger-light text-danger"
                            : "bg-surface text-muted border border-border"
                        }`}
                      >
                        {log.event.replace(/_/g, " ")}
                      </span>
                      <span className="text-ink leading-relaxed font-medium">{log.message}</span>
                    </div>
                    <span className="text-[11px] text-muted font-mono shrink-0">
                      {new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </span>
                  </div>
                );
              })
            ) : (
              <div className="p-4 text-center text-xs text-muted">
                Background engine active. Waiting for incoming invoices on watched channels...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
