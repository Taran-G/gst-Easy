"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { formatRupees, getActiveTenant, apiFetch, downloadBlob, getBusinessWhatsAppPhone } from "@/lib/api";
import {
  ArrowRight,
  AlertTriangle,
  Clock,
  Inbox,
  MessageSquare,
  CheckCircle2,
  FileCheck,
  Upload,
  Download,
  FileSpreadsheet
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

interface WhatsAppStats {
  total: number;
  inbound: number;
  outbound: number;
  invoices_ingested: number;
}

export default function HomePage() {
  const [activeTenant, setActiveTenantState] = useState("apex");
  const [loading, setLoading] = useState(true);
  const [statusCounts, setStatusCounts] = useState<StatusCounts>({});
  const [reconData, setReconData] = useState<ReconResponse | null>(null);
  const [rule37Count, setRule37Count] = useState<number>(0);
  const [highRiskVendorsCount, setHighRiskVendorsCount] = useState<number>(0);
  const [waStats, setWaStats] = useState<WhatsAppStats | null>(null);
  const [businessPhone, setBusinessPhone] = useState("+91 98765 43210");

  // Upload & Export State
  const [uploadingBill, setUploadingBill] = useState(false);
  const [uploading2B, setUploading2B] = useState(false);
  const [exportingTally, setExportingTally] = useState(false);
  const [exportingRecon, setExportingRecon] = useState(false);
  const [bannerMessage, setBannerMessage] = useState<{ title: string; desc: string; type: "success" | "warning" } | null>(null);

  const billInputRef = useRef<HTMLInputElement>(null);
  const gstr2bInputRef = useRef<HTMLInputElement>(null);

  const fetchDashboardData = () => {
    Promise.allSettled([
      apiFetch<{ status_counts?: StatusCounts }>("/invoices"),
      apiFetch<ReconResponse>("/reconcile/092026"),
      apiFetch<Rule37Alert[]>("/rules37/aging"),
      apiFetch<VendorRisk[]>("/risk/vendors"),
      apiFetch<{ stats?: WhatsAppStats }>("/whatsapp/messages?limit=1"),
    ]).then(([invoicesRes, reconRes, rulesRes, vendorsRes, waRes]) => {
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
      if (waRes.status === "fulfilled" && waRes.value.stats) {
        setWaStats(waRes.value.stats);
      }
      setLoading(false);
    });
  };

  useEffect(() => {
    const tenant = getActiveTenant();
    setActiveTenantState(tenant);
    fetchDashboardData();
    setBusinessPhone(getBusinessWhatsAppPhone());

    const handlePhoneChange = () => setBusinessPhone(getBusinessWhatsAppPhone());
    window.addEventListener("whatsAppPhoneChanged", handlePhoneChange);
    return () => window.removeEventListener("whatsAppPhoneChanged", handlePhoneChange);
  }, []);

  // Quick Manual Bill Upload Handler
  const handleUploadBill = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingBill(true);
    setBannerMessage(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await apiFetch<{
        status: string;
        invoice: { id: string; number: string; total_amount: number };
        state: string;
      }>("/ingest/upload", {
        method: "POST",
        body: formData,
      });

      setBannerMessage({
        title: "Bill Uploaded & Extracted Successfully",
        desc: `Invoice #${res.invoice?.number || "New"} for ₹${(res.invoice?.total_amount || 0).toLocaleString("en-IN")} was checked and added to your Inbox (${res.state}).`,
        type: res.state === "BLOCKED" ? "warning" : "success",
      });

      fetchDashboardData();
    } catch (err: unknown) {
      alert("Bill upload failed: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setUploadingBill(false);
      if (billInputRef.current) billInputRef.current.value = "";
    }
  };

  // Quick GSTR-2B File Upload Handler
  const handleUpload2B = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading2B(true);
    setBannerMessage(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await apiFetch<{
        status: string;
        entries_imported: number;
      }>("/gstr2b/upload?period=092026", {
        method: "POST",
        body: formData,
      });

      setBannerMessage({
        title: "GSTR-2B Statement Uploaded",
        desc: `Processed ${res.entries_imported} government B2B entries for September 2026. Reconciliation updated!`,
        type: "success",
      });

      fetchDashboardData();
    } catch (err: unknown) {
      alert("GSTR-2B upload failed: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setUploading2B(false);
      if (gstr2bInputRef.current) gstr2bInputRef.current.value = "";
    }
  };

  // Quick Download Tally XML
  const handleDownloadTally = async () => {
    setExportingTally(true);
    try {
      const invoicesRes = await apiFetch<{ invoices: Array<{ id: string; state: string }> }>("/invoices?status=ALL");
      const readyIds = (invoicesRes.invoices || [])
        .filter((i) => i.state === "READY_FOR_EXPORT" || i.state === "APPROVED" || i.state === "MATCHED")
        .map((i) => i.id);

      if (readyIds.length === 0) {
        alert("No approved or matched bills available to export right now. Please review and approve bills in your Inbox first.");
        return;
      }

      const filename = `Tally_Purchase_Vouchers_${activeTenant}_Sep2026.xml`;
      await downloadBlob("/tally/export", filename, {
        method: "POST",
        body: JSON.stringify({ invoice_ids: readyIds }),
      });

      setBannerMessage({
        title: "Tally XML Downloaded",
        desc: `Downloaded ${readyIds.length} purchase vouchers. In TallyPrime, press Alt + O > Import > Transactions to load.`,
        type: "success",
      });
    } catch (err: unknown) {
      alert("Failed downloading Tally XML: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setExportingTally(false);
    }
  };

  // Quick Download Reconciliation CSV
  const handleDownloadRecon = async () => {
    setExportingRecon(true);
    try {
      const filename = `GSTR2B_Reconciliation_${activeTenant}_Sep2026.csv`;
      await downloadBlob("/reconcile/092026/export-csv", filename);
      setBannerMessage({
        title: "Reconciliation Report Downloaded",
        desc: `Saved ${filename} for your audit working papers.`,
        type: "success",
      });
    } catch (err: unknown) {
      alert("Failed downloading report: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setExportingRecon(false);
    }
  };

  const tenantName = activeTenant === "apex" ? "Apex Auto Parts" : activeTenant;
  const needsReview = statusCounts.needs_review || 0;
  const totalBills = statusCounts.all || 0;

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
      {/* Calm Greeting with Plain Accounting Language */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-ink tracking-tight">
            Dashboard · {tenantName}
          </h1>
          <p className="text-muted text-sm">
            {needsReview === 0
              ? `All purchase bills reviewed. ${formatRupees(itc.at_risk_itc)} tax credit continuously monitored.`
              : `${needsReview} ${needsReview === 1 ? "bill needs" : "bills need"} review before posting. ${formatRupees(itc.at_risk_itc)} tax credit needs attention.`}
          </p>
        </div>

        {/* Live Channel Status Chip (WhatsApp only) */}
        <div className="flex items-center space-x-2 px-3 py-1.5 bg-surface border border-border rounded-lg text-xs font-semibold text-ink shadow-xs">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-success"></span>
          </span>
          <span>WhatsApp Channel Active: {businessPhone}</span>
        </div>
      </div>

      {/* Notification Banner */}
      {bannerMessage && (
        <div
          className={`p-4 rounded-xl border text-sm flex items-start justify-between shadow-xs ${
            bannerMessage.type === "success"
              ? "bg-success-light/60 border-success/30 text-ink"
              : "bg-warning-light/60 border-warning/30 text-ink"
          }`}
        >
          <div className="flex items-start space-x-3">
            {bannerMessage.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-success shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
            )}
            <div>
              <div className="font-bold text-ink">{bannerMessage.title}</div>
              <div className="text-xs text-muted mt-0.5">{bannerMessage.desc}</div>
            </div>
          </div>
          <button onClick={() => setBannerMessage(null)} className="text-muted hover:text-ink text-xs font-bold ml-4">
            ✕
          </button>
        </div>
      )}

      {/* QUICK ACTIONS BAR: Manual Import & Export (The primary user workflow) */}
      <div className="bg-surface border border-border rounded-2xl p-5 shadow-xs space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-ink uppercase tracking-wider">
            Quick Actions · Import Bills &amp; Export Files
          </span>
          <span className="text-xs text-muted">Zero manual typing · 1-click downloads</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {/* Action 1: Upload Purchase Bill */}
          <input
            ref={billInputRef}
            type="file"
            accept=".pdf,image/*"
            onChange={handleUploadBill}
            className="hidden"
          />
          <button
            onClick={() => billInputRef.current?.click()}
            disabled={uploadingBill}
            className="p-3.5 bg-background border border-border hover:border-primary rounded-xl text-left transition-all hover:shadow-xs group"
          >
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center mb-2 group-hover:bg-primary group-hover:text-white transition-colors">
              <Upload className="w-4 h-4" />
            </div>
            <div className="font-bold text-xs text-ink">
              {uploadingBill ? "Reading Bill..." : "Upload Bills"}
            </div>
            <div className="text-[11px] text-muted mt-0.5">PDF or Photo (AI Extract)</div>
          </button>

          {/* Action 2: Upload GSTR-2B Statement */}
          <input
            ref={gstr2bInputRef}
            type="file"
            accept=".json,.csv"
            onChange={handleUpload2B}
            className="hidden"
          />
          <button
            onClick={() => gstr2bInputRef.current?.click()}
            disabled={uploading2B}
            className="p-3.5 bg-background border border-border hover:border-success rounded-xl text-left transition-all hover:shadow-xs group"
          >
            <div className="w-8 h-8 rounded-lg bg-success-light text-success flex items-center justify-center mb-2 group-hover:bg-success group-hover:text-white transition-colors">
              <FileCheck className="w-4 h-4" />
            </div>
            <div className="font-bold text-xs text-ink">
              {uploading2B ? "Matching..." : "Upload GSTR-2B"}
            </div>
            <div className="text-[11px] text-muted mt-0.5">Government JSON statement</div>
          </button>

          {/* Action 3: Download Tally XML */}
          <button
            onClick={handleDownloadTally}
            disabled={exportingTally}
            className="p-3.5 bg-background border border-border hover:border-primary rounded-xl text-left transition-all hover:shadow-xs group"
          >
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center mb-2 group-hover:bg-primary group-hover:text-white transition-colors">
              <Download className="w-4 h-4" />
            </div>
            <div className="font-bold text-xs text-ink">
              {exportingTally ? "Generating..." : "Download for Tally"}
            </div>
            <div className="text-[11px] text-muted mt-0.5">TallyPrime XML (Alt+O)</div>
          </button>

          {/* Action 4: Download Reconciliation Report */}
          <button
            onClick={handleDownloadRecon}
            disabled={exportingRecon}
            className="p-3.5 bg-background border border-border hover:border-primary rounded-xl text-left transition-all hover:shadow-xs group"
          >
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center mb-2 group-hover:bg-primary group-hover:text-white transition-colors">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
            <div className="font-bold text-xs text-ink">
              {exportingRecon ? "Downloading..." : "Reconciliation Excel"}
            </div>
            <div className="text-[11px] text-muted mt-0.5">Audit Working Paper</div>
          </button>
        </div>
      </div>

      {/* ITC SUMMARY PROGRESS BAR */}
      <div className="bg-surface border border-border rounded-2xl p-5 space-y-3 shadow-xs">
        <div className="flex justify-between items-center text-xs font-semibold uppercase tracking-wider text-muted">
          <span>Tax Credit (ITC) Status · Sep 2026</span>
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
            title={`Timing Gap (${timingPct}%)`}
          />
          <div
            style={{ width: `${atRiskPct}%` }}
            className="bg-danger transition-all duration-300"
            title={`At Risk (${atRiskPct}%)`}
          />
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center justify-between text-xs pt-1 gap-2">
          <div className="flex items-center space-x-2">
            <span className="w-3 h-3 rounded-full bg-success"></span>
            <span className="font-medium text-ink">
              Safe to Claim: {formatRupees(itc.matched_itc)}
            </span>
            <span className="text-muted">({matchedPct}%)</span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="w-3 h-3 rounded-full bg-warning"></span>
            <span className="font-medium text-ink">
              Timing / Next Month: {formatRupees(itc.timing_gap_itc)}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="w-3 h-3 rounded-full bg-danger"></span>
            <span className="font-bold text-danger">
              Tax at Risk: {formatRupees(itc.at_risk_itc)}
            </span>
            <span className="text-muted">({atRiskPct}%)</span>
          </div>
        </div>
      </div>

      {/* 4 PRIMARY WORKFLOW CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Card 1: Review Bills */}
        <div className="bg-surface border border-border rounded-2xl p-5 flex flex-col justify-between space-y-4 shadow-xs hover:border-primary/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Purchase Bills</span>
              <div className="text-3xl font-bold text-ink">{needsReview} Needs Review</div>
              <p className="text-xs text-muted">
                {totalBills} total bills in your account.
              </p>
            </div>
            <div className="p-3 bg-primary/10 text-primary rounded-xl">
              <Inbox className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/inbox"
            className="inline-flex items-center justify-between w-full px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-xs font-bold rounded-xl transition-colors"
          >
            <span>Review Bills &amp; Approve</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Card 2: Tax Credit at Risk */}
        <div className="bg-surface border border-border rounded-2xl p-5 flex flex-col justify-between space-y-4 shadow-xs hover:border-danger/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Tax at Risk</span>
              <div className="text-3xl font-bold text-danger">{formatRupees(itc.at_risk_itc)}</div>
              <p className="text-xs text-muted">
                {reconData?.counts.missing_in_2b || 0} bills missing in GSTR-2B.
              </p>
            </div>
            <div className="p-3 bg-danger-light text-danger rounded-xl">
              <AlertTriangle className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/reconcile"
            className="inline-flex items-center justify-between w-full px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-xs font-bold rounded-xl transition-colors"
          >
            <span>Inspect 2B Statement Match</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Card 3: 180-Day Rule 37 Radar */}
        <div className="bg-surface border border-border rounded-2xl p-5 flex flex-col justify-between space-y-4 shadow-xs hover:border-warning/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">180-Day Deadlines</span>
              <div className="text-3xl font-bold text-ink">
                {rule37Count > 0 ? `${rule37Count} Aging Alerts` : "All Clear"}
              </div>
              <p className="text-xs text-muted">
                {rule37Count > 0
                  ? `${rule37Count} unpaid bills approaching 180-day tax reversal.`
                  : "Zero bills exceeding 150-day limit."}
              </p>
            </div>
            <div className="p-3 bg-warning-light text-warning rounded-xl">
              <Clock className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/reconcile"
            className="inline-flex items-center justify-between w-full px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-xs font-bold rounded-xl transition-colors"
          >
            <span>View Rule 37 Schedule</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Card 4: WhatsApp Supplier Follow-ups */}
        <div className="bg-surface border border-border rounded-2xl p-5 flex flex-col justify-between space-y-4 shadow-xs hover:border-success/40 transition-colors">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">WhatsApp Follow-ups</span>
              <div className="text-3xl font-bold text-ink">
                {highRiskVendorsCount > 0 ? `${highRiskVendorsCount} To Follow Up` : "Compliant"}
              </div>
              <p className="text-xs text-muted">
                {highRiskVendorsCount > 0
                  ? `${highRiskVendorsCount} suppliers have delayed their GSTR-1 returns.`
                  : "All suppliers in good standing."}
              </p>
            </div>
            <div className="p-3 bg-success-light text-success rounded-xl">
              <MessageSquare className="w-5 h-5" />
            </div>
          </div>
          <Link
            href="/whatsapp"
            className="inline-flex items-center justify-between w-full px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-xs font-bold rounded-xl transition-colors"
          >
            <span>Open WhatsApp Center</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      {/* WHATSAPP ASSISTANT & CHANNELS CARD (Replaces confusing developer automation section) */}
      <div className="bg-surface border border-border rounded-2xl p-6 shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-border gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-success text-white flex items-center justify-center shadow-xs">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-ink">WhatsApp Supplier Assistant</h3>
                <span className="px-2 py-0.5 bg-success-light text-success rounded-full text-[11px] font-bold">
                  Active
                </span>
              </div>
              <p className="text-xs text-muted">
                Receive bills from suppliers on WhatsApp &amp; send 1-click reminders for missing returns or payment holds.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <Link
              href="/whatsapp"
              className="px-4 py-2 bg-success text-white hover:bg-success/90 text-xs font-bold rounded-xl transition-colors shadow-xs flex items-center space-x-1.5"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Send WhatsApp to Supplier</span>
            </Link>

            <Link
              href="/settings"
              className="px-3.5 py-2 border border-border text-ink hover:bg-background text-xs font-semibold rounded-xl transition-colors"
            >
              Configure WhatsApp Number
            </Link>
          </div>
        </div>

        {/* 3 Simple WhatsApp Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-4 bg-background border border-border rounded-xl space-y-1">
            <div className="text-[11px] font-bold text-muted uppercase">Your WhatsApp Number</div>
            <div className="text-base font-bold font-mono text-success">{businessPhone}</div>
            <div className="text-[11px] text-muted">Give to suppliers for bill photos/PDFs</div>
          </div>

          <div className="p-4 bg-background border border-border rounded-xl space-y-1">
            <div className="text-[11px] font-bold text-muted uppercase">Bills Ingested Automatically</div>
            <div className="text-xl font-bold text-ink">{waStats?.invoices_ingested || 0} Bills</div>
            <div className="text-[11px] text-muted">Received via WhatsApp and verified</div>
          </div>

          <div className="p-4 bg-background border border-border rounded-xl space-y-1">
            <div className="text-[11px] font-bold text-muted uppercase">Messages Logged</div>
            <div className="text-xl font-bold text-ink">{waStats?.total || 0} Messages</div>
            <div className="text-[11px] text-muted">Reminders and payment hold notices</div>
          </div>
        </div>
      </div>
    </div>
  );
}
