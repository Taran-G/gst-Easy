"use client";

import { Suspense, useEffect, useState, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch, formatRupees, downloadBlob } from "@/lib/api";
import {
  Download,
  AlertTriangle,
  Clock,
  ShieldAlert,
  CheckCircle,
  HelpCircle,
  RefreshCw,
  Upload,
  FileSpreadsheet,
  X
} from "lucide-react";

interface ReconEntry {
  invoice_id?: string;
  invoice_number: string;
  supplier_name: string;
  supplier_gstin?: string;
  books_taxable?: number;
  books_tax?: number;
  gstr2b_taxable?: number;
  gstr2b_tax?: number;
  status: string;
  advice: string;
}

interface Rule37Alert {
  invoice_id: string;
  invoice_number: string;
  vendor_name: string;
  invoice_date: string;
  age_days: number;
  tax_at_stake: number;
  severity: string;
  message: string;
}

interface Rule37aCandidate {
  vendor_name: string;
  supplier_gstin: string;
  invoice_number: string;
  total_amount: number;
  reversal_amount: number;
  reason: string;
}

interface ReconResponse {
  period: string;
  counts: {
    matched: number;
    matched_with_difference: number;
    missing_in_2b: number;
    expected_timing_gap: number;
    in_2b_not_in_books: number;
  };
  itc_summary: {
    matched_itc: number;
    variance_itc: number;
    at_risk_itc: number;
    timing_gap_itc: number;
    total_claimable: number;
  };
  matched: ReconEntry[];
  matched_with_difference: ReconEntry[];
  missing_in_2b: ReconEntry[];
  expected_timing_gap: ReconEntry[];
  in_2b_not_in_books: ReconEntry[];
}

export default function ReconcilePage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted">Loading reconciliation...</div>}>
      <ReconcileContent />
    </Suspense>
  );
}

function ReconcileContent() {
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") || "reconciliation";
  const [activeTab, setActiveTab] = useState<string>(initialTab);
  const period = "092026";
  const [data, setData] = useState<ReconResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [rule37Alerts, setRule37Alerts] = useState<Rule37Alert[]>([]);
  const [rule37aCandidates, setRule37aCandidates] = useState<Rule37aCandidate[]>([]);
  const [exporting, setExporting] = useState<boolean>(false);
  const [exportingCsv, setExportingCsv] = useState<boolean>(false);
  const [uploading2B, setUploading2B] = useState<boolean>(false);
  const [notification, setNotification] = useState<{ message: string; type: "info" | "success" | "warning" } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchRecon = () => {
    setLoading(true);
    apiFetch<ReconResponse>(`/reconcile/${period}`)
      .then((res) => setData(res))
      .catch((err) => console.error("Failed fetching reconciliation:", err))
      .finally(() => setLoading(false));

    // Fetch deadlines
    apiFetch<Rule37Alert[]>("/rules37/aging")
      .then((res) => setRule37Alerts(res || []))
      .catch(() => {});

    apiFetch<Rule37aCandidate[]>(`/rules37a/candidates?period=${period}`)
      .then((res) => setRule37aCandidates(res || []))
      .catch(() => {});
  };

  useEffect(() => {
    fetchRecon();
  }, [period]);

  const handleImport2B = async () => {
    setLoading(true);
    try {
      await apiFetch(`/gstr2b/import?period=${period}`, { method: "POST" });
      setNotification({
        message: "Successfully synchronized GSTR-2B data from GST portal gateway.",
        type: "success",
      });
      fetchRecon();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({
          message: "GSTR-2B import failed: " + err.message,
          type: "warning",
        });
      }
    } finally {
      setLoading(false);
      setTimeout(() => setNotification(null), 6000);
    }
  };

  const handleUpload2BFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setUploading2B(true);
    try {
      const res = await apiFetch<{
        status: string;
        period: string;
        entries_imported: number;
      }>(`/gstr2b/upload?period=${period}`, {
        method: "POST",
        body: formData,
      });

      setNotification({
        message: `Successfully uploaded GSTR-2B JSON! Processed ${res.entries_imported} B2B invoice entries for period ${period}.`,
        type: "success",
      });
      fetchRecon();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({
          message: "GSTR-2B upload failed: " + err.message,
          type: "warning",
        });
      }
    } finally {
      setUploading2B(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setTimeout(() => setNotification(null), 6000);
    }
  };

  const handleExportCSV = async () => {
    setExportingCsv(true);
    try {
      const tenant = typeof window !== "undefined" ? localStorage.getItem("lg_active_tenant") || "apex" : "apex";
      const filename = `GSTR2B_Reconciliation_${tenant}_${period}.csv`;
      await downloadBlob(`/reconcile/${period}/export-csv`, filename);
      setNotification({
        message: `Audit working paper exported: ${filename}`,
        type: "success",
      });
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({
          message: "CSV export failed: " + err.message,
          type: "warning",
        });
      }
    } finally {
      setExportingCsv(false);
      setTimeout(() => setNotification(null), 6000);
    }
  };

  const handleExportTallyXML = async () => {
    setExporting(true);
    try {
      const invoiceIds = [
        ...(data?.matched.map((m) => m.invoice_id).filter(Boolean) || []),
        ...(data?.matched_with_difference.map((m) => m.invoice_id).filter(Boolean) || []),
      ] as string[];

      if (invoiceIds.length === 0) {
        alert("No matched or approved invoices available to export.");
        return;
      }

      const tenant = typeof window !== "undefined" ? localStorage.getItem("lg_active_tenant") || "apex" : "apex";
      const filename = `tally_batch_${tenant}_${period}.xml`;
      await downloadBlob("/tally/export", filename, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice_ids: invoiceIds }),
      });
      setNotification({
        message: `Tally XML downloaded (${invoiceIds.length} vouchers). Import in TallyPrime via Alt+O > Import > Vouchers.`,
        type: "success",
      });
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({ message: "Tally XML export failed: " + err.message, type: "warning" });
      }
    } finally {
      setExporting(false);
      setTimeout(() => setNotification(null), 6000);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink tracking-tight">GST Reconciliation & Deadlines</h1>
          <p className="text-sm text-muted">
            Matching books of accounts against GSTR-2B government statements and tracking Rule 37/37A statutory cut-offs.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Hidden GSTR-2B file input */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleUpload2BFile}
            className="hidden"
            accept=".json,.csv"
          />

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading2B}
            className="px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-sm font-medium rounded-md shadow-sm transition-colors flex items-center space-x-2"
            title="Upload standard JSON downloaded from GST portal (docdata.b2b)"
          >
            <Upload className={`w-4 h-4 text-primary ${uploading2B ? "animate-pulse" : ""}`} />
            <span>{uploading2B ? "Uploading..." : "Upload GSTR-2B JSON"}</span>
          </button>

          <button
            onClick={handleImport2B}
            disabled={loading}
            className="px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-sm font-medium rounded-md shadow-sm transition-colors flex items-center space-x-2"
          >
            <RefreshCw className={`w-4 h-4 text-primary ${loading ? "animate-spin" : ""}`} />
            <span>Sync Live Gateway</span>
          </button>

          <button
            onClick={handleExportCSV}
            disabled={exportingCsv}
            className="px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-sm font-medium rounded-md shadow-sm transition-colors flex items-center space-x-2"
            title="Download multi-section CSV audit paper for CA working files"
          >
            <FileSpreadsheet className="w-4 h-4 text-success" />
            <span>{exportingCsv ? "Exporting..." : "Export Audit CSV"}</span>
          </button>

          <button
            onClick={handleExportTallyXML}
            disabled={exporting}
            className="px-4 py-2 bg-primary text-white text-sm font-semibold rounded-md hover:bg-primary-hover shadow-sm transition-colors flex items-center space-x-2"
          >
            <Download className="w-4 h-4" />
            <span>{exporting ? "Generating..." : "Export Tally XML (Alt+O)"}</span>
          </button>
        </div>
      </div>

      {/* Notification Toast Banner */}
      {notification && (
        <div
          className={`px-4 py-2.5 rounded-lg text-xs font-medium border flex items-center justify-between transition-all ${
            notification.type === "success"
              ? "bg-success-light text-success border-success/30"
              : notification.type === "warning"
              ? "bg-danger-light text-danger border-danger/30"
              : "bg-primary-light text-primary border-primary/30"
          }`}
        >
          <span>{notification.message}</span>
          <button onClick={() => setNotification(null)} className="hover:opacity-75">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-border space-x-6 text-sm font-medium">
        <button
          onClick={() => setActiveTab("reconciliation")}
          className={`pb-3 transition-colors border-b-2 ${
            activeTab === "reconciliation"
              ? "border-primary text-primary font-semibold"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          GSTR-2B Statement Match
        </button>
        <button
          onClick={() => setActiveTab("deadlines")}
          className={`pb-3 transition-colors border-b-2 flex items-center space-x-2 ${
            activeTab === "deadlines"
              ? "border-primary text-primary font-semibold"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          <span>Statutory Deadlines (Rule 37 / 37A)</span>
          {rule37Alerts.length > 0 && (
            <span className="px-1.5 py-0.2 bg-danger-light text-danger text-xs rounded-full font-bold">
              {rule37Alerts.length}
            </span>
          )}
        </button>
      </div>

      {activeTab === "reconciliation" ? (
        <div className="space-y-6">
          {/* Summary KPIs */}
          {data && (
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-surface border border-border rounded-lg p-4">
                <span className="text-xs font-semibold text-muted uppercase tracking-wider">Matched in 2B</span>
                <div className="text-2xl font-bold text-success mt-1">
                  {formatRupees(data.itc_summary.matched_itc)}
                </div>
                <div className="text-xs text-muted mt-1">{data.counts.matched} invoices perfectly matched</div>
              </div>

              <div className="bg-surface border border-border rounded-lg p-4">
                <span className="text-xs font-semibold text-muted uppercase tracking-wider">Amount Variance</span>
                <div className="text-2xl font-bold text-warning mt-1">
                  {formatRupees(data.itc_summary.variance_itc)}
                </div>
                <div className="text-xs text-muted mt-1">{data.counts.matched_with_difference} with minor round-off</div>
              </div>

              <div className="bg-surface border border-border rounded-lg p-4">
                <span className="text-xs font-semibold text-muted uppercase tracking-wider">ITC at Risk</span>
                <div className="text-2xl font-bold text-danger mt-1">
                  {formatRupees(data.itc_summary.at_risk_itc)}
                </div>
                <div className="text-xs text-muted mt-1">{data.counts.missing_in_2b} invoices missing in 2B</div>
              </div>

              <div className="bg-surface border border-border rounded-lg p-4">
                <span className="text-xs font-semibold text-muted uppercase tracking-wider">QRMP Timing Gap</span>
                <div className="text-2xl font-bold text-ink mt-1">
                  {formatRupees(data.itc_summary.timing_gap_itc)}
                </div>
                <div className="text-xs text-muted mt-1">Quarterly filer awaiting filing</div>
              </div>
            </div>
          )}

          {/* Section 1: Matched in 2B */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="px-5 py-3.5 bg-background border-b border-border flex justify-between items-center">
              <div className="flex items-center space-x-2">
                <CheckCircle className="w-4 h-4 text-success" />
                <h3 className="font-semibold text-ink text-sm">
                  1. Matched Invoices ({data?.counts.matched || 0})
                </h3>
              </div>
              <span className="text-xs text-muted">Eligible for 100% ITC claim</span>
            </div>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border text-muted font-medium bg-background/40">
                  <th className="py-2.5 px-4">Supplier</th>
                  <th className="py-2.5 px-4">Invoice #</th>
                  <th className="py-2.5 px-4 text-right">Tax (Books)</th>
                  <th className="py-2.5 px-4 text-right">Tax (2B)</th>
                  <th className="py-2.5 px-4">One-Line CA Advice</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data?.matched.map((m, idx) => (
                  <tr key={idx} className="hover:bg-background/30">
                    <td className="py-2.5 px-4 font-semibold text-ink">{m.supplier_name}</td>
                    <td className="py-2.5 px-4 font-mono">{m.invoice_number}</td>
                    <td className="py-2.5 px-4 text-right font-medium">{formatRupees(m.books_tax)}</td>
                    <td className="py-2.5 px-4 text-right font-medium text-success">{formatRupees(m.gstr2b_tax)}</td>
                    <td className="py-2.5 px-4 text-muted">{m.advice}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Section 2: Missing in 2B / Timing Gap */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="px-5 py-3.5 bg-background border-b border-border flex justify-between items-center">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 text-danger" />
                <h3 className="font-semibold text-ink text-sm">
                  2. Not in GSTR-2B ({data?.counts.missing_in_2b || 0} Missing · {data?.counts.expected_timing_gap || 0} QRMP Timing)
                </h3>
              </div>
              <span className="text-xs text-danger font-medium">Payment Hold Advised</span>
            </div>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border text-muted font-medium bg-background/40">
                  <th className="py-2.5 px-4">Supplier</th>
                  <th className="py-2.5 px-4">Invoice #</th>
                  <th className="py-2.5 px-4 text-right">Tax at Risk (₹)</th>
                  <th className="py-2.5 px-4">Status</th>
                  <th className="py-2.5 px-4">One-Line CA Advice</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data?.missing_in_2b.map((m, idx) => (
                  <tr key={idx} className="hover:bg-background/30 bg-danger-light/10">
                    <td className="py-2.5 px-4 font-semibold text-ink">{m.supplier_name}</td>
                    <td className="py-2.5 px-4 font-mono">{m.invoice_number}</td>
                    <td className="py-2.5 px-4 text-right font-bold text-danger">{formatRupees(m.books_tax)}</td>
                    <td className="py-2.5 px-4">
                      <span className="px-2 py-0.5 bg-danger-light text-danger text-[11px] font-semibold rounded">
                        Missing in 2B
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-ink font-medium">{m.advice}</td>
                  </tr>
                ))}
                {data?.expected_timing_gap.map((tg, idx) => (
                  <tr key={`tg-${idx}`} className="hover:bg-background/30 bg-amber-50/20">
                    <td className="py-2.5 px-4 font-semibold text-ink">{tg.supplier_name}</td>
                    <td className="py-2.5 px-4 font-mono">{tg.invoice_number}</td>
                    <td className="py-2.5 px-4 text-right font-medium">{formatRupees(tg.books_tax)}</td>
                    <td className="py-2.5 px-4">
                      <span className="px-2 py-0.5 bg-warning-light text-warning text-[11px] font-semibold rounded">
                        QRMP Timing Gap
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-muted">{tg.advice}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Section 3: In 2B but not in Books (Ghost Invoices) */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="px-5 py-3.5 bg-background border-b border-border flex justify-between items-center">
              <div className="flex items-center space-x-2">
                <HelpCircle className="w-4 h-4 text-warning" />
                <h3 className="font-semibold text-ink text-sm">
                  3. In GSTR-2B But Not in Your Books ({data?.counts.in_2b_not_in_books || 0} Ghost Bills)
                </h3>
              </div>
              <span className="text-xs text-muted">Missing physical invoice copy</span>
            </div>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border text-muted font-medium bg-background/40">
                  <th className="py-2.5 px-4">Supplier</th>
                  <th className="py-2.5 px-4">Invoice # in 2B</th>
                  <th className="py-2.5 px-4 text-right">Taxable (₹)</th>
                  <th className="py-2.5 px-4 text-right">Tax (₹)</th>
                  <th className="py-2.5 px-4">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data?.in_2b_not_in_books.map((g, idx) => (
                  <tr key={idx} className="hover:bg-background/30">
                    <td className="py-2.5 px-4 font-semibold text-ink">{g.supplier_name}</td>
                    <td className="py-2.5 px-4 font-mono font-medium">{g.invoice_number}</td>
                    <td className="py-2.5 px-4 text-right">{formatRupees(g.gstr2b_taxable)}</td>
                    <td className="py-2.5 px-4 text-right font-bold text-ink">{formatRupees(g.gstr2b_tax)}</td>
                    <td className="py-2.5 px-4 text-muted">{g.advice}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Deadlines Tab: Rule 37 & 37A */
        <div className="space-y-6">
          {/* Rule 37 Section */}
          <div className="bg-surface border border-border rounded-lg p-6 space-y-4 shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-ink flex items-center space-x-2">
                  <Clock className="w-5 h-5 text-warning" />
                  <span>Rule 37: 180-Day Payment Reversal Tracking</span>
                </h3>
                <p className="text-sm text-muted mt-1">
                  Under Rule 37 of CGST Rules, if a buyer fails to pay the supplier within 180 days from the invoice date, the Input Tax Credit claimed must be reversed with interest.
                </p>
              </div>
            </div>

            {rule37Alerts.length === 0 ? (
              <div className="p-4 bg-success-light text-success text-sm rounded font-medium flex items-center space-x-2">
                <CheckCircle className="w-4 h-4" />
                <span>No invoices approaching the 180-day cut-off threshold.</span>
              </div>
            ) : (
              <div className="space-y-3">
                {rule37Alerts.map((alt, idx) => (
                  <div
                    key={idx}
                    className={`p-4 rounded-lg border flex items-center justify-between ${
                      alt.severity === "DANGER"
                        ? "bg-danger-light/50 border-danger/30 text-danger"
                        : "bg-warning-light/50 border-warning/30 text-warning"
                    }`}
                  >
                    <div>
                      <div className="font-bold text-sm text-ink">{alt.message}</div>
                      <div className="text-xs text-muted mt-0.5">
                        Invoice #{alt.invoice_number} · Date: {alt.invoice_date} · Unpaid for {alt.age_days} days
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-danger">
                        {formatRupees(alt.tax_at_stake)} at risk
                      </div>
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                        Alert Day {alt.age_days >= 170 ? "170" : "150"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Rule 37A Section */}
          <div className="bg-surface border border-border rounded-lg p-6 space-y-4 shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-ink flex items-center space-x-2">
                  <ShieldAlert className="w-5 h-5 text-danger" />
                  <span>Rule 37A: Supplier GSTR-3B Non-Filing Reversal</span>
                </h3>
                <p className="text-sm text-muted mt-1">
                  Rule 37A mandates reversal of ITC if the supplier does not file GSTR-3B by 30th November following the end of the financial year. Once the supplier subsequently files, the credit is re-claimable.
                </p>
              </div>
            </div>

            {rule37aCandidates.length === 0 ? (
              <div className="p-4 bg-background border border-border text-sm text-muted rounded">
                All suppliers have completed GSTR-3B filings for the current statutory window.
              </div>
            ) : (
              <div className="space-y-3">
                {rule37aCandidates.map((c, idx) => (
                  <div key={idx} className="p-4 bg-background border border-border rounded-lg flex items-center justify-between">
                    <div>
                      <div className="font-bold text-sm text-ink">{c.vendor_name} ({c.supplier_gstin})</div>
                      <div className="text-xs text-muted">
                        Invoice #{c.invoice_number} · Total: {formatRupees(c.total_amount)}
                      </div>
                      <div className="text-xs text-danger font-medium mt-1">{c.reason}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-danger">
                        {formatRupees(c.reversal_amount)}
                      </div>
                      <span className="text-[11px] text-muted">Reversal Worksheet Staged</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
