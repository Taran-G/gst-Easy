"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch, formatRupees } from "@/lib/api";
import {
  Users,
  AlertTriangle,
  CheckCircle,
  ShieldCheck,
  Send,
  Search,
  FileText,
  Phone,
  Building,
  RefreshCw,
  Printer,
  X,
  MessageSquare
} from "lucide-react";

interface SupplierRanking {
  gstin: string;
  legal_name: string;
  gstin_status: string;
  filing_freq: string;
  risk_score: number;
  risk_level: string;
  pagerank_score: number;
  total_itc_at_risk: number;
  total_itc: number;
  total_spend: number;
  invoice_count: number;
}

interface InvoiceRow {
  id: string;
  number: string;
  date: string;
  taxable_amount: number;
  tax_amount: number;
  total_amount: number;
  state: string;
  itc_status: string;
  in_2b: boolean;
  hold_advice: string;
  recommended_hold: number;
  recommended_release: number;
  age_days: number;
  is_rule37_risk: boolean;
}

interface FilingRecord {
  form: string;
  period: string;
  status: string;
  filed_on?: string;
}

interface AccountingRisk {
  type: string;
  severity: "CRITICAL" | "DANGER" | "WARNING" | "INFO";
  title: string;
  description: string;
  statutory_ref: string;
}

interface SupplierProfileResponse {
  supplier: {
    gstin: string;
    legal_name: string;
    trade_name: string;
    state_code: string;
    gstin_status: string;
    filing_freq: string;
    phone: string;
    risk_score: number;
    risk_level: string;
    opted_out: boolean;
    tally_ledger?: string | null;
  };
  stats: {
    total_invoices: number;
    total_spend: number;
    total_taxable: number;
    total_itc: number;
    itc_in_2b: number;
    itc_missing_2b: number;
    hold_advised: number;
    safe_to_release: number;
  };
  invoices: InvoiceRow[];
  filing_history: FilingRecord[];
  accounting_risks: AccountingRisk[];
  rule_37_invoices: Array<{
    invoice_id: string;
    invoice_number: string;
    invoice_date: string;
    age_days: number;
    tax_at_stake: number;
    total_amount: number;
    days_remaining: number;
  }>;
}

interface ChaseDraft {
  rendered_text: string;
  cost_inr: number;
  eligible: boolean;
  eligibility_reason: string;
  phone: string;
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<SupplierRanking[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [selectedGstin, setSelectedGstin] = useState<string | null>(null);

  // Profile data for selected supplier
  const [profile, setProfile] = useState<SupplierProfileResponse | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [filterRisk, setFilterRisk] = useState<"ALL" | "HIGH" | "ACTION_REQUIRED">("ALL");
  const [showHoldAdviceModal, setShowHoldAdviceModal] = useState<boolean>(false);

  // Accounting WhatsApp Chase builder
  const [chaseNoticeType, setChaseNoticeType] = useState<string>("missing_2b");
  const [chaseLanguage, setChaseLanguage] = useState<string>("en");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string>("");
  const [chaseDraft, setChaseDraft] = useState<ChaseDraft | null>(null);
  const [draftingChase, setDraftingChase] = useState(false);
  const [sendingChase, setSendingChase] = useState(false);
  const [chaseSuccessMsg, setChaseSuccessMsg] = useState<string | null>(null);

  // 1. Fetch supplier list
  const fetchSuppliers = useCallback(() => {
    setLoadingList(true);
    apiFetch<SupplierRanking[]>("/risk/vendors?top_n=20")
      .then((data) => {
        setSuppliers(data || []);
        if (data && data.length > 0 && !selectedGstin) {
          // Select the first supplier or highest risk
          setSelectedGstin(data[0].gstin);
        }
      })
      .catch((err) => console.error("Failed fetching suppliers:", err))
      .finally(() => setLoadingList(false));
  }, [selectedGstin]);

  useEffect(() => {
    fetchSuppliers();
  }, [fetchSuppliers]);

  // 2. Fetch selected supplier's profile
  const fetchProfile = useCallback((gstin: string) => {
    setLoadingProfile(true);
    setChaseSuccessMsg(null);
    setChaseDraft(null);
    apiFetch<SupplierProfileResponse>(`/risk/vendors/${gstin}`)
      .then((data) => {
        setProfile(data);
        if (data.invoices && data.invoices.length > 0) {
          setSelectedInvoiceId(data.invoices[0].id);
        } else {
          setSelectedInvoiceId("");
        }
      })
      .catch((err) => console.error("Failed fetching vendor profile:", err))
      .finally(() => setLoadingProfile(false));
  }, []);

  useEffect(() => {
    if (selectedGstin) {
      fetchProfile(selectedGstin);
    }
  }, [selectedGstin, fetchProfile]);

  // 3. Draft chase whenever invoice, notice type, or language changes
  const updateChaseDraft = useCallback(() => {
    if (!selectedInvoiceId) {
      setChaseDraft(null);
      return;
    }
    setDraftingChase(true);
    setChaseSuccessMsg(null);
    apiFetch<ChaseDraft>("/chases/draft", {
      method: "POST",
      body: JSON.stringify({
        invoice_id: selectedInvoiceId,
        type: chaseNoticeType,
        language: chaseLanguage,
        firm_name: "Demo CA & Associates"
      })
    })
      .then((res) => setChaseDraft(res))
      .catch((err) => {
        console.error("Failed to draft chase:", err);
        setChaseDraft(null);
      })
      .finally(() => setDraftingChase(false));
  }, [selectedInvoiceId, chaseNoticeType, chaseLanguage]);

  useEffect(() => {
    if (selectedInvoiceId) {
      updateChaseDraft();
    }
  }, [selectedInvoiceId, chaseNoticeType, chaseLanguage, updateChaseDraft]);

  // 4. Send approved chase
  const handleSendChase = async () => {
    if (!selectedInvoiceId || !chaseDraft || !chaseDraft.eligible) return;
    setSendingChase(true);
    setChaseSuccessMsg(null);
    try {
      await apiFetch("/chases/approve", {
        method: "POST",
        body: JSON.stringify({
          invoice_id: selectedInvoiceId,
          type: chaseNoticeType,
          language: chaseLanguage
        })
      });
      setChaseSuccessMsg("Accounting reminder sent to supplier via WhatsApp & recorded in the immutable audit trail.");
      // Refresh draft to reflect updated cooldown
      updateChaseDraft();
    } catch (err: unknown) {
      if (err instanceof Error) {
        alert("Failed sending notice: " + err.message);
      }
    } finally {
      setSendingChase(false);
    }
  };

  // Filtered suppliers
  const filteredSuppliers = suppliers.filter((s) => {
    const matchesSearch =
      s.legal_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.gstin.toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;
    if (filterRisk === "HIGH") return s.risk_level === "High" || s.gstin_status !== "Active";
    if (filterRisk === "ACTION_REQUIRED") return s.total_itc_at_risk > 0;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight flex items-center space-x-2">
            <Users className="w-6 h-6 text-primary" />
            <span>Suppliers & Tax Compliance</span>
          </h1>
          <p className="text-sm text-muted">
            Ground payment decisions in real book transactions, GSTR-2B presence, and statutory tax risks.
          </p>
        </div>
        <button
          onClick={fetchSuppliers}
          className="self-start sm:self-auto px-3 py-1.5 bg-surface border border-border hover:bg-background text-xs font-medium rounded-md text-ink flex items-center space-x-1.5 transition-colors shadow-sm"
        >
          <RefreshCw className="w-3.5 h-3.5 text-muted" />
          <span>Refresh Compliance</span>
        </button>
      </div>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Supplier Directory & Ledger */}
        <div className="lg:col-span-4 space-y-4">
          <div className="bg-surface border border-border rounded-lg p-4 space-y-3 shadow-sm">
            {/* Search and Filters */}
            <div className="relative">
              <Search className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search vendor or GSTIN..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div className="flex items-center space-x-1 border border-border/60 p-0.5 rounded-md bg-background text-[11px] font-medium">
              <button
                onClick={() => setFilterRisk("ALL")}
                className={`flex-1 py-1 text-center rounded transition-colors ${
                  filterRisk === "ALL" ? "bg-surface text-ink font-semibold shadow-xs" : "text-muted hover:text-ink"
                }`}
              >
                All ({suppliers.length})
              </button>
              <button
                onClick={() => setFilterRisk("HIGH")}
                className={`flex-1 py-1 text-center rounded transition-colors ${
                  filterRisk === "HIGH" ? "bg-danger-light text-danger font-semibold shadow-xs" : "text-muted hover:text-ink"
                }`}
              >
                High Risk
              </button>
              <button
                onClick={() => setFilterRisk("ACTION_REQUIRED")}
                className={`flex-1 py-1 text-center rounded transition-colors ${
                  filterRisk === "ACTION_REQUIRED" ? "bg-warning-light text-warning font-semibold shadow-xs" : "text-muted hover:text-ink"
                }`}
              >
                Hold Advised
              </button>
            </div>
          </div>

          {/* Supplier Cards List */}
          <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
            {loadingList ? (
              <div className="bg-surface border border-border rounded-lg p-8 text-center text-xs text-muted">
                Loading supplier ledgers...
              </div>
            ) : filteredSuppliers.length === 0 ? (
              <div className="bg-surface border border-border rounded-lg p-8 text-center text-xs text-muted">
                No suppliers matching filter.
              </div>
            ) : (
              filteredSuppliers.map((s) => {
                const isSelected = s.gstin === selectedGstin;
                const isSuspended = s.gstin_status === "Suspended" || s.gstin_status === "Cancelled";
                return (
                  <div
                    key={s.gstin}
                    onClick={() => setSelectedGstin(s.gstin)}
                    className={`p-3.5 bg-surface border rounded-lg cursor-pointer transition-all shadow-xs ${
                      isSelected
                        ? "border-primary ring-1 ring-primary bg-primary-light/10"
                        : "border-border hover:border-border-hover hover:bg-background/50"
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <div className="space-y-0.5">
                        <div className="font-semibold text-sm text-ink">{s.legal_name}</div>
                        <div className="text-[11px] font-mono text-muted">{s.gstin}</div>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          s.risk_level === "High"
                            ? "bg-danger-light text-danger"
                            : s.risk_level === "Medium"
                            ? "bg-warning-light text-warning"
                            : "bg-success-light text-success"
                        }`}
                      >
                        {s.risk_level} Risk
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs pt-3 mt-2 border-t border-border/60">
                      <div className="flex items-center space-x-2 text-[11px]">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            isSuspended ? "bg-danger" : "bg-success"
                          }`}
                        />
                        <span className={isSuspended ? "text-danger font-bold" : "text-muted"}>
                          {s.gstin_status}
                        </span>
                        <span className="text-muted/40">·</span>
                        <span className="text-muted">{s.filing_freq}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-ink font-semibold">
                          {s.invoice_count} {s.invoice_count === 1 ? "bill" : "bills"}
                        </span>
                        {s.total_itc_at_risk > 0 && (
                          <div className="text-[11px] font-bold text-danger">
                            Hold: {formatRupees(s.total_itc_at_risk)}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Accounting Risk & Action Workspace */}
        <div className="lg:col-span-8 space-y-5">
          {loadingProfile ? (
            <div className="bg-surface border border-border rounded-lg p-12 text-center text-sm text-muted">
              Loading accounting profile for {selectedGstin}...
            </div>
          ) : !profile ? (
            <div className="bg-surface border border-border rounded-lg p-12 text-center text-sm text-muted">
              Select a supplier from the directory to review their accounting profile and invoices.
            </div>
          ) : (
            <>
              {/* 1. Supplier Master & Ledger Verification Card */}
              <div className="bg-surface border border-border rounded-lg p-5 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border pb-4">
                  <div>
                    <div className="flex items-center space-x-2">
                      <h2 className="text-xl font-bold text-ink">{profile.supplier.legal_name}</h2>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-bold ${
                          profile.supplier.gstin_status === "Active"
                            ? "bg-success-light text-success"
                            : "bg-danger-light text-danger"
                        }`}
                      >
                        GSTIN {profile.supplier.gstin_status}
                      </span>
                    </div>
                    <div className="text-xs text-muted flex items-center space-x-2 pt-1 font-mono">
                      <span>GSTIN: {profile.supplier.gstin}</span>
                      <span>·</span>
                      <span>State Code: {profile.supplier.state_code}</span>
                      <span>·</span>
                      <span>{profile.supplier.filing_freq} Filer</span>
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2.5">
                    <button
                      onClick={() => setShowHoldAdviceModal(true)}
                      className="px-3 py-1.5 bg-surface border border-border text-ink hover:bg-background text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center space-x-1.5"
                      title="Generate official statutory payment hold certificate for accounts payable"
                    >
                      <FileText className="w-3.5 h-3.5 text-primary" />
                      <span>Statutory Payment Advice</span>
                    </button>
                    <div className="text-left sm:text-right sm:pl-3 sm:border-l border-border/80">
                      <div className="text-[11px] text-muted font-medium">Tally Ledger Mapping</div>
                      <div className="text-xs font-semibold text-ink flex items-center sm:justify-end space-x-1">
                        <Building className="w-3.5 h-3.5 text-primary" />
                        <span>{profile.supplier.tally_ledger || "Sundry Creditors (Default)"}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 2. Payment Hold Recommendation (FR-RSK-1) */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="p-4 bg-success-light/40 border border-success/20 rounded-lg">
                    <div className="text-xs font-semibold text-success uppercase tracking-wider flex items-center space-x-1.5">
                      <ShieldCheck className="w-4 h-4" />
                      <span>Safe to Release (Base Value)</span>
                    </div>
                    <div className="text-2xl font-bold text-ink mt-1">
                      {formatRupees(profile.stats.safe_to_release)}
                    </div>
                    <p className="text-xs text-muted mt-1">
                      Base goods/services taxable amount verified against physical invoices in books.
                    </p>
                  </div>

                  <div
                    className={`p-4 rounded-lg border ${
                      profile.stats.hold_advised > 0
                        ? "bg-danger-light/50 border-danger/30"
                        : "bg-surface border-border"
                    }`}
                  >
                    <div
                      className={`text-xs font-semibold uppercase tracking-wider flex items-center space-x-1.5 ${
                        profile.stats.hold_advised > 0 ? "text-danger" : "text-muted"
                      }`}
                    >
                      <AlertTriangle className="w-4 h-4" />
                      <span>Recommend Hold (GST Portion)</span>
                    </div>
                    <div
                      className={`text-2xl font-bold mt-1 ${
                        profile.stats.hold_advised > 0 ? "text-danger" : "text-ink"
                      }`}
                    >
                      {formatRupees(profile.stats.hold_advised)}
                    </div>
                    <p className="text-xs text-muted mt-1">
                      {profile.stats.hold_advised > 0
                        ? "GST component missing in GSTR-2B or vendor registration suspended. Hold to protect cash flow."
                        : "All invoices reflected in GSTR-2B. No payment hold advised."}
                    </p>
                  </div>
                </div>

                {/* Statutory Accounting Risks Alerts */}
                {profile.accounting_risks.length > 0 && (
                  <div className="space-y-2 pt-2">
                    <div className="text-xs font-semibold uppercase tracking-wider text-muted">
                      Statutory Compliance Risks Detected
                    </div>
                    {profile.accounting_risks.map((risk, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-md text-xs space-y-1 border ${
                          risk.severity === "CRITICAL" || risk.severity === "DANGER"
                            ? "bg-danger-light/40 border-danger/20 text-danger"
                            : "bg-warning-light/40 border-warning/20 text-warning-dark"
                        }`}
                      >
                        <div className="flex justify-between items-center font-bold">
                          <span>{risk.title}</span>
                          <span className="text-[10px] font-mono uppercase bg-surface/80 px-1.5 py-0.5 rounded border border-current">
                            {risk.statutory_ref}
                          </span>
                        </div>
                        <p className="text-ink/80 leading-relaxed">{risk.description}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 3. Real Invoices & Inbox Ledger Table */}
              <div className="bg-surface border border-border rounded-lg shadow-sm overflow-hidden">
                <div className="p-4 border-b border-border flex justify-between items-center bg-background/50">
                  <div>
                    <h3 className="font-semibold text-sm text-ink">
                      Real Transaction Ledger ({profile.invoices.length} {profile.invoices.length === 1 ? "Bill" : "Bills"})
                    </h3>
                    <p className="text-xs text-muted">
                      Extracted and validated invoices issued by {profile.supplier.legal_name}.
                    </p>
                  </div>
                  <div className="text-xs text-muted font-mono">
                    Total Spend: <span className="font-bold text-ink">{formatRupees(profile.stats.total_spend)}</span>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-background border-b border-border text-[11px] font-semibold text-muted uppercase tracking-wider">
                        <th className="py-2.5 px-3">Invoice #</th>
                        <th className="py-2.5 px-3">Date</th>
                        <th className="py-2.5 px-3 text-right">Taxable</th>
                        <th className="py-2.5 px-3 text-right">GST Tax</th>
                        <th className="py-2.5 px-3 text-right">Total</th>
                        <th className="py-2.5 px-3 text-center">GSTR-2B</th>
                        <th className="py-2.5 px-3 text-center">Rule 37 Age</th>
                        <th className="py-2.5 px-3 text-right">Hold Advice</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {profile.invoices.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="py-6 text-center text-muted">
                            No invoices recorded for this supplier yet.
                          </td>
                        </tr>
                      ) : (
                        profile.invoices.map((inv) => {
                          const isTarget = inv.id === selectedInvoiceId;
                          return (
                            <tr
                              key={inv.id}
                              onClick={() => setSelectedInvoiceId(inv.id)}
                              className={`cursor-pointer transition-colors ${
                                isTarget ? "bg-primary-light/20 font-medium" : "hover:bg-background/60"
                              }`}
                            >
                              <td className="py-2.5 px-3 font-semibold text-ink">
                                <div className="flex items-center space-x-1.5">
                                  <span>{inv.number}</span>
                                  {isTarget && (
                                    <span className="text-[10px] bg-primary text-white px-1 rounded font-normal">
                                      Active
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="py-2.5 px-3 text-muted">{inv.date}</td>
                              <td className="py-2.5 px-3 text-right font-mono">
                                {formatRupees(inv.taxable_amount)}
                              </td>
                              <td className="py-2.5 px-3 text-right font-mono">
                                {formatRupees(inv.tax_amount)}
                              </td>
                              <td className="py-2.5 px-3 text-right font-bold text-ink font-mono">
                                {formatRupees(inv.total_amount)}
                              </td>
                              <td className="py-2.5 px-3 text-center">
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    inv.in_2b
                                      ? "bg-success-light text-success"
                                      : "bg-warning-light text-warning"
                                  }`}
                                >
                                  {inv.in_2b ? "In GSTR-2B" : "Missing in 2B"}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-center">
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] ${
                                    inv.age_days >= 170
                                      ? "bg-danger-light text-danger font-bold"
                                      : inv.age_days >= 120
                                      ? "bg-warning-light text-warning font-semibold"
                                      : "text-muted"
                                  }`}
                                >
                                  {inv.age_days}d
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-right">
                                {inv.recommended_hold > 0 ? (
                                  <span className="text-danger font-bold">
                                    Hold {formatRupees(inv.recommended_hold)}
                                  </span>
                                ) : (
                                  <span className="text-success font-medium">Safe to Pay</span>
                                )}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 4. Accounting Reminders & WhatsApp Actions (No delivery / logistics noise) */}
              <div className="bg-surface border border-border rounded-lg p-5 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border pb-3">
                  <div>
                    <h3 className="text-sm font-bold text-ink flex items-center space-x-2">
                      <Send className="w-4 h-4 text-primary" />
                      <span>Accounting Notice & WhatsApp Reminder</span>
                    </h3>
                    <p className="text-xs text-muted">
                      Draft statutory reminders for bill #{profile.invoices.find((i) => i.id === selectedInvoiceId)?.number || "..."}
                    </p>
                  </div>
                  <div className="text-xs font-mono text-muted">
                    Meta Utility: <span className="font-semibold text-ink">₹0.35/notice</span>
                  </div>
                </div>

                {/* Template & Language Selectors */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
                      Statutory Notice Type
                    </label>
                    <select
                      value={chaseNoticeType}
                      onChange={(e) => setChaseNoticeType(e.target.value)}
                      className="w-full py-1.5 px-2.5 text-xs bg-background border border-border rounded-md text-ink focus:outline-none focus:ring-1 focus:ring-primary font-medium"
                    >
                      <option value="missing_2b">Missing in GSTR-2B (GSTR-1 Upload Request)</option>
                      <option value="gstr3b_pending">GSTR-3B Return Pending (Rule 37A Notice)</option>
                      <option value="missing_bill_copy">Missing Physical Bill Copy (Books Reconciliation)</option>
                      <option value="rule_37_warning">Rule 37 180-Day Aging Reversal Warning</option>
                      <option value="payment_hold_notice">Payment Advice (GST Portion on Hold)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
                      Communication Language
                    </label>
                    <div className="flex border border-border rounded-md bg-background p-0.5 text-xs">
                      <button
                        type="button"
                        onClick={() => setChaseLanguage("en")}
                        className={`flex-1 py-1 rounded text-center font-medium transition-colors ${
                          chaseLanguage === "en" ? "bg-surface text-ink font-bold shadow-xs" : "text-muted hover:text-ink"
                        }`}
                      >
                        English
                      </button>
                      <button
                        type="button"
                        onClick={() => setChaseLanguage("hi")}
                        className={`flex-1 py-1 rounded text-center font-medium transition-colors ${
                          chaseLanguage === "hi" ? "bg-surface text-ink font-bold shadow-xs" : "text-muted hover:text-ink"
                        }`}
                      >
                        हिंदी (Hindi)
                      </button>
                      <button
                        type="button"
                        onClick={() => setChaseLanguage("hinglish")}
                        className={`flex-1 py-1 rounded text-center font-medium transition-colors ${
                          chaseLanguage === "hinglish" ? "bg-surface text-ink font-bold shadow-xs" : "text-muted hover:text-ink"
                        }`}
                      >
                        Hinglish
                      </button>
                    </div>
                  </div>
                </div>

                {/* Notice Preview */}
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs text-muted">
                    <span className="flex items-center space-x-1">
                      <Phone className="w-3.5 h-3.5 text-muted" />
                      <span>Recipient: {profile.supplier.phone}</span>
                    </span>
                    {chaseDraft && (
                      <span className={chaseDraft.eligible ? "text-success font-medium" : "text-danger font-medium"}>
                        {chaseDraft.eligibility_reason}
                      </span>
                    )}
                  </div>

                  <div className="p-3.5 bg-background border border-border rounded-md font-mono text-xs text-ink/90 whitespace-pre-wrap leading-relaxed shadow-inner">
                    {draftingChase ? (
                      <div className="text-muted italic">Drafting compliant message with firm signature...</div>
                    ) : chaseDraft ? (
                      chaseDraft.rendered_text
                    ) : (
                      <div className="text-muted italic">Select an invoice to generate reminder notice.</div>
                    )}
                  </div>
                </div>

                {/* Feedback message */}
                {chaseSuccessMsg && (
                  <div className="p-2.5 bg-success-light text-success text-xs font-semibold rounded-md flex items-center space-x-2">
                    <CheckCircle className="w-4 h-4 shrink-0" />
                    <span>{chaseSuccessMsg}</span>
                  </div>
                )}

                {/* Send Buttons */}
                <div className="flex flex-col sm:flex-row items-center justify-between pt-2 gap-3">
                  <div className="text-[11px] text-muted">
                    Statutory audit requirement: Reminders are rate-limited to 1 per 3 days per vendor.
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (!chaseDraft?.rendered_text) return;
                        let cleanDigits = (profile.supplier.phone || "").replace(/[^0-9]/g, "");
                        if (!cleanDigits || cleanDigits === "919876543210" || cleanDigits.length < 10) {
                          const entered = prompt(
                            `Enter WhatsApp phone number for supplier "${profile.supplier.legal_name}":`,
                            ""
                          );
                          if (!entered || !entered.trim()) return;
                          cleanDigits = entered.trim().replace(/[^0-9]/g, "");
                          if (cleanDigits.length < 10) {
                            alert("Please enter a valid 10-digit phone number.");
                            return;
                          }
                        }
                        const encoded = encodeURIComponent(chaseDraft.rendered_text);
                        window.open(`https://wa.me/${cleanDigits}?text=${encoded}`, "_blank");
                      }}
                      className="px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-xs font-semibold rounded-md shadow-xs transition-colors flex items-center space-x-1.5"
                    >
                      <MessageSquare className="w-3.5 h-3.5 text-success" />
                      <span>Open in WhatsApp Web</span>
                    </button>
                    <button
                      onClick={handleSendChase}
                      disabled={sendingChase || !chaseDraft || !chaseDraft.eligible}
                      className="px-4 py-2 bg-success hover:bg-success/90 text-white text-xs font-semibold rounded-md shadow-xs transition-colors disabled:opacity-50 flex items-center space-x-1.5"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>{sendingChase ? "Sending..." : "Send via WhatsApp"}</span>
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Statutory Payment Hold Certificate & Advice Modal */}
      {showHoldAdviceModal && profile && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl max-w-3xl w-full max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-background/50">
              <div className="flex items-center space-x-2.5">
                <FileText className="w-5 h-5 text-primary" />
                <h2 className="font-bold text-ink text-base">
                  Statutory Payment Advice Statement — {profile.supplier.legal_name}
                </h2>
              </div>
              <button
                onClick={() => setShowHoldAdviceModal(false)}
                className="text-muted hover:text-ink p-1 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Printable Content */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1 text-ink">
              {/* Official Header */}
              <div className="border-b-2 border-primary/20 pb-4 flex justify-between items-start">
                <div>
                  <div className="text-xs font-bold uppercase tracking-widest text-primary">
                    STATUTORY AUDIT & GST COMPLIANCE ADVISORY
                  </div>
                  <h1 className="text-xl font-extrabold text-ink tracking-tight mt-1">
                    AP Payment Hold & Release Directive
                  </h1>
                  <p className="text-xs text-muted mt-0.5">
                    Issued under Section 16(2)(aa) of CGST Act, 2017 & Rule 37 of CGST Rules, 2017
                  </p>
                </div>
                <div className="text-right text-xs space-y-1">
                  <div>
                    <span className="text-muted">Date: </span>
                    <strong className="text-ink">{new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}</strong>
                  </div>
                  <div>
                    <span className="text-muted">Client Account: </span>
                    <strong className="text-ink">{typeof window !== "undefined" && localStorage.getItem("lg_active_tenant") === "greenleaf" ? "Greenleaf Traders" : "Apex Auto Parts"}</strong>
                  </div>
                </div>
              </div>

              {/* Vendor Information Box */}
              <div className="grid grid-cols-2 gap-4 bg-background/60 border border-border p-3.5 rounded-lg text-xs">
                <div>
                  <div className="text-muted uppercase text-[10px] font-semibold tracking-wider">Vendor Details</div>
                  <div className="font-bold text-sm text-ink mt-0.5">{profile.supplier.legal_name}</div>
                  <div className="font-mono text-muted mt-0.5">GSTIN: {profile.supplier.gstin}</div>
                  <div className="text-muted">State: {profile.supplier.state_code} · {profile.supplier.filing_freq} Filer</div>
                </div>
                <div className="text-right">
                  <div className="text-muted uppercase text-[10px] font-semibold tracking-wider">Statutory Registration Status</div>
                  <div className="mt-0.5">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${profile.supplier.gstin_status === "Active" ? "bg-success-light text-success" : "bg-danger-light text-danger"}`}>
                      GSTIN {profile.supplier.gstin_status}
                    </span>
                  </div>
                  <div className="text-muted mt-1">
                    Tally Ledger: <span className="font-semibold text-ink">{profile.supplier.tally_ledger || "Sundry Creditors"}</span>
                  </div>
                </div>
              </div>

              {/* Action Directive Summary */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-success-light/30 border border-success/30 rounded-lg">
                  <div className="text-xs font-bold text-success uppercase tracking-wider">
                    ✓ Safe to Release (Base Value)
                  </div>
                  <div className="text-2xl font-black text-ink mt-1">
                    {formatRupees(profile.stats.safe_to_release)}
                  </div>
                  <div className="text-[11px] text-muted mt-1 leading-snug">
                    Verified goods/services taxable base. Safe to pay to maintain business relationship and supplier continuity.
                  </div>
                </div>

                <div className={`p-4 rounded-lg border ${profile.stats.hold_advised > 0 ? "bg-danger-light/40 border-danger/40" : "bg-background border-border"}`}>
                  <div className={`text-xs font-bold uppercase tracking-wider ${profile.stats.hold_advised > 0 ? "text-danger" : "text-muted"}`}>
                    ⚠ Statutory Hold Recommended (GST Portion)
                  </div>
                  <div className={`text-2xl font-black mt-1 ${profile.stats.hold_advised > 0 ? "text-danger" : "text-ink"}`}>
                    {formatRupees(profile.stats.hold_advised)}
                  </div>
                  <div className="text-[11px] text-muted mt-1 leading-snug">
                    {profile.stats.hold_advised > 0
                      ? "Hold pending reflection in Form GSTR-2B. Claiming ITC prior to GSTR-2B appearance violates Section 16(2)(aa)."
                      : "All invoices verified in Form GSTR-2B. 100% ITC is eligible for claim in Form GSTR-3B."}
                  </div>
                </div>
              </div>

              {/* Invoices Breakdown Table */}
              <div className="space-y-2">
                <div className="text-xs font-bold uppercase tracking-wider text-muted">
                  Invoice-by-Invoice Payment Breakdown
                </div>
                <table className="w-full text-xs text-left border border-border rounded overflow-hidden">
                  <thead className="bg-background text-muted font-semibold">
                    <tr className="border-b border-border">
                      <th className="py-2 px-3">Invoice #</th>
                      <th className="py-2 px-3">Date</th>
                      <th className="py-2 px-3 text-right">Taxable (₹)</th>
                      <th className="py-2 px-3 text-right">GST (₹)</th>
                      <th className="py-2 px-3 text-center">GSTR-2B</th>
                      <th className="py-2 px-3 text-right">Safe to Pay</th>
                      <th className="py-2 px-3 text-right">Hold Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {profile.invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-background/20">
                        <td className="py-2 px-3 font-semibold text-ink font-mono">{inv.number}</td>
                        <td className="py-2 px-3 text-muted">{inv.date}</td>
                        <td className="py-2 px-3 text-right font-medium">{formatRupees(inv.taxable_amount)}</td>
                        <td className="py-2 px-3 text-right text-muted">{formatRupees(inv.tax_amount)}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${inv.in_2b ? "bg-success-light text-success" : "bg-danger-light text-danger"}`}>
                            {inv.in_2b ? "In 2B" : "Missing"}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-right font-bold text-success">{formatRupees(inv.recommended_release)}</td>
                        <td className={`py-2 px-3 text-right font-bold ${inv.recommended_hold > 0 ? "text-danger" : "text-muted"}`}>
                          {formatRupees(inv.recommended_hold)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Statutory Certification Footnote */}
              <div className="p-3 bg-background border border-border rounded-lg text-[11px] text-muted space-y-1">
                <div className="font-bold text-ink">STATUTORY AUDITOR CERTIFICATION NOTE:</div>
                <p>
                  This advisory certificate is generated automatically by gstEasy pursuant to statutory compliance verification rules.
                  Under the Finance Act amendments to Section 16(2)(aa) of the CGST Act, no registered person shall be entitled to credit of any input tax unless the details of invoice or debit note have been communicated in Form GSTR-2B. Releasing the tax portion prior to GSTR-2B reflection incurs direct client cash liability and non-appealable interest @ 18% p.a.
                </p>
              </div>
            </div>

            {/* Modal Actions Footer */}
            <div className="px-6 py-4 border-t border-border bg-background flex justify-between items-center">
              <span className="text-xs text-muted">
                Press Print or Cmd+P to save as official PDF.
              </span>

              <div className="flex items-center space-x-3">
                <button
                  onClick={() => setShowHoldAdviceModal(false)}
                  className="px-4 py-2 border border-border text-ink hover:bg-border/30 text-xs font-medium rounded-md transition-colors"
                >
                  Close
                </button>
                <button
                  onClick={() => window.print()}
                  className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center space-x-1.5"
                >
                  <Printer className="w-3.5 h-3.5" />
                  <span>Print Advice Sheet</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
