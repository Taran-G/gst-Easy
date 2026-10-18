"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { apiFetch, formatRupees, downloadBlob } from "@/lib/api";
import {
  Inbox,
  AlertTriangle,
  CheckCircle,
  Upload,
  FileText,
  X,
  ShieldCheck,
  Building,
  Search,
  Download,
  RotateCcw,
  MessageSquare
} from "lucide-react";

interface InvoiceItem {
  id: string;
  number: string;
  date: string;
  total_amount: number;
  taxable_amount: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  state: string;
  itc_status: string;
  hold_status: string;
  supplier_gstin: string;
  supplier_name: string;
  doc_id?: string;
  source?: string;
  issues: Array<{ code: string; severity: string; field?: string; message: string }>;
  line_count: number;
}

interface InvoiceDetail extends InvoiceItem {
  number_norm: string;
  fy: string;
  place_of_supply: string;
  file_path: string;
  applied_rules?: Array<Record<string, unknown>>;
  supplier: {
    gstin: string;
    name: string;
    state_code: string;
    tally_ledger?: string | null;
  };
  lines: Array<{
    no: number;
    description: string;
    hsn_sac?: string;
    qty?: number;
    uom?: string;
    rate?: number;
    taxable_value: number;
    gst_rate: number;
  }>;
}

interface SupplierOption {
  gstin: string;
  legal_name: string;
  bill_count: number;
}

export default function InboxPage() {
  // Tab and Filters
  const [tab, setTab] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [supplierFilter, setSupplierFilter] = useState<string>("ALL");
  const [itcFilter, setItcFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Metadata from backend
  const [availableSuppliers, setAvailableSuppliers] = useState<SupplierOption[]>([]);
  const [statusCounts, setStatusCounts] = useState<{
    all?: number;
    needs_review?: number;
    ready?: number;
    blocked?: number;
    approved?: number;
  }>({});

  // Data and UI states
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedInvoice, setSelectedInvoice] = useState<InvoiceDetail | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editTotal, setEditTotal] = useState<string>("");
  const [actionLoading, setActionLoading] = useState(false);
  const [availableLedgers, setAvailableLedgers] = useState<Array<{ name: string; parent: string }>>([]);
  const [selectedLedgerToMap, setSelectedLedgerToMap] = useState<string>("");
  const [notification, setNotification] = useState<{ message: string; type: "info" | "success" | "warning" } | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchInbox = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (tab && tab !== "all") params.set("tab", tab);
    if (statusFilter && statusFilter !== "ALL") params.set("status", statusFilter);
    if (supplierFilter && supplierFilter !== "ALL") params.set("supplier_gstin", supplierFilter);
    if (itcFilter && itcFilter !== "ALL") params.set("itc_status", itcFilter);
    if (searchQuery.trim()) params.set("search", searchQuery.trim());

    apiFetch<{
      invoices: InvoiceItem[];
      available_suppliers?: SupplierOption[];
      status_counts?: {
        all: number;
        needs_review: number;
        ready: number;
        blocked: number;
        approved: number;
      };
    }>(`/invoices?${params.toString()}`)
      .then((data) => {
        setInvoices(data.invoices || []);
        if (data.available_suppliers) {
          setAvailableSuppliers(data.available_suppliers);
        }
        if (data.status_counts) {
          setStatusCounts(data.status_counts);
        }
      })
      .catch((err) => console.error("Failed fetching inbox:", err))
      .finally(() => setLoading(false));
  }, [tab, statusFilter, supplierFilter, itcFilter, searchQuery]);

  useEffect(() => {
    fetchInbox();
  }, [fetchInbox]);

  useEffect(() => {
    // Fetch ledgers for mapping dropdown
    apiFetch<Array<{ name: string; parent: string }>>("/masters/ledgers")
      .then((ledgers) => setAvailableLedgers(ledgers || []))
      .catch(() => {});
  }, []);

  const openInvoiceModal = (id: string) => {
    setActionLoading(true);
    apiFetch<InvoiceDetail>(`/invoices/${id}`)
      .then((data) => {
        setSelectedInvoice(data);
        setEditTotal(data.total_amount.toString());
        setModalOpen(true);
      })
      .catch((err) => alert(err.message))
      .finally(() => setActionLoading(false));
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    try {
      const res = await apiFetch<{
        invoice_id?: string;
        state?: string;
        is_duplicate?: boolean;
        message?: string;
      }>("/ingest/upload", {
        method: "POST",
        body: formData,
      });

      if (res?.is_duplicate) {
        setNotification({
          message: res.message || "This bill has already been ingested. Existing record retained.",
          type: "info",
        });
      } else {
        setNotification({
          message: `Bill uploaded successfully (${res?.state || "Needs Review"}).`,
          type: "success",
        });
      }
      fetchInbox();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({
          message: "Upload failed: " + err.message,
          type: "warning",
        });
      }
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setTimeout(() => setNotification(null), 5000);
    }
  };

  const handleSaveEditTotal = async () => {
    if (!selectedInvoice) return;
    setActionLoading(true);
    try {
      await apiFetch<{ new_state: string }>(`/invoices/${selectedInvoice.id}`, {
        method: "PATCH",
        body: JSON.stringify({ total_amount: parseFloat(editTotal) }),
      });
      openInvoiceModal(selectedInvoice.id);
      fetchInbox();
    } catch (err: unknown) {
      if (err instanceof Error) {
        alert("Update failed: " + err.message);
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!selectedInvoice) return;
    setActionLoading(true);
    try {
      await apiFetch<{ state: string }>(`/invoices/${selectedInvoice.id}/approve`, {
        method: "POST",
      });
      setModalOpen(false);
      fetchInbox();
    } catch (err: unknown) {
      if (err instanceof Error) {
        alert("Approval failed: " + err.message);
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selectedInvoice) return;
    const reason = prompt("Enter rejection reason:");
    if (!reason) return;

    setActionLoading(true);
    try {
      await apiFetch<{ state: string }>(`/invoices/${selectedInvoice.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setModalOpen(false);
      fetchInbox();
    } catch (err: unknown) {
      if (err instanceof Error) {
        alert("Rejection failed: " + err.message);
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleMapLedger = async () => {
    if (!selectedInvoice || !selectedLedgerToMap) return;
    setActionLoading(true);
    try {
      await apiFetch("/masters/map", {
        method: "POST",
        body: JSON.stringify({
          vendor_gstin: selectedInvoice.supplier.gstin,
          tally_ledger_name: selectedLedgerToMap,
          invoice_id: selectedInvoice.id,
        }),
      });
      openInvoiceModal(selectedInvoice.id);
      fetchInbox();
    } catch (err: unknown) {
      if (err instanceof Error) {
        alert("Mapping failed: " + err.message);
      }
    } finally {
      setActionLoading(false);
    }
  };

  const toggleSelectInvoice = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (invoices.length > 0 && selectedIds.length === invoices.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(invoices.map((inv) => inv.id));
    }
  };

  const handleBulkApprove = async () => {
    if (selectedIds.length === 0) return;
    setBatchLoading(true);
    try {
      const res = await apiFetch<{
        status: string;
        approved_count: number;
        skipped_count: number;
        skipped: Array<{ id: string; reason: string }>;
      }>("/invoices/bulk-approve", {
        method: "POST",
        body: JSON.stringify({ invoice_ids: selectedIds }),
      });

      if (res.skipped_count > 0) {
        setNotification({
          message: `Approved ${res.approved_count} bills. ${res.skipped_count} skipped (${res.skipped[0]?.reason || "blocking issues"}).`,
          type: "warning",
        });
      } else {
        setNotification({
          message: `Successfully approved ${res.approved_count} bills for Tally export!`,
          type: "success",
        });
      }
      setSelectedIds([]);
      fetchInbox();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({ message: "Bulk approve failed: " + err.message, type: "warning" });
      }
    } finally {
      setBatchLoading(false);
      setTimeout(() => setNotification(null), 6000);
    }
  };

  const handleExportTallyXML = async (targetIds?: string[]) => {
    const idsToExport = targetIds || selectedIds;
    if (idsToExport.length === 0) return;
    setBatchLoading(true);
    try {
      const tenant = typeof window !== "undefined" ? localStorage.getItem("lg_active_tenant") || "apex" : "apex";
      const filename = `tally_batch_${tenant}_${new Date().toISOString().slice(0, 10)}.xml`;
      await downloadBlob("/tally/export", filename, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice_ids: idsToExport }),
      });
      setNotification({
        message: `Tally XML downloaded (${idsToExport.length} vouchers). Import into TallyPrime via Alt+O > Import > Vouchers.`,
        type: "success",
      });
      fetchInbox();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({ message: "Tally XML export failed: " + err.message, type: "warning" });
      }
    } finally {
      setBatchLoading(false);
      setTimeout(() => setNotification(null), 6000);
    }
  };

  const handleDirectSyncTally = async () => {
    if (selectedIds.length === 0) return;
    setBatchLoading(true);
    try {
      const res = await apiFetch<{
        status: string;
        message: string;
        detail?: string;
      }>("/tally/sync-direct", {
        method: "POST",
        body: JSON.stringify({ invoice_ids: selectedIds }),
      });
      if (res.status === "synced") {
        setNotification({
          message: `Directly synced ${selectedIds.length} vouchers to TallyPrime (Port 9000). Marked as POSTED.`,
          type: "success",
        });
        setSelectedIds([]);
        fetchInbox();
      } else {
        setNotification({
          message: `${res.message || "Tally port 9000 not reachable"}. Use 'Export Tally XML' button to import file into TallyPrime.`,
          type: "info",
        });
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setNotification({ message: "Tally sync failed: " + err.message, type: "warning" });
      }
    } finally {
      setBatchLoading(false);
      setTimeout(() => setNotification(null), 6000);
    }
  };

  const clearAllFilters = () => {
    setTab("all");
    setStatusFilter("ALL");
    setSupplierFilter("ALL");
    setItcFilter("ALL");
    setSearchQuery("");
    setSelectedIds([]);
  };

  const hasActiveFilters =
    statusFilter !== "ALL" ||
    supplierFilter !== "ALL" ||
    itcFilter !== "ALL" ||
    searchQuery.trim() !== "";

  const getStateBadge = (state: string) => {
    switch (state) {
      case "READY":
        return <span className="px-2 py-0.5 bg-success-light text-success text-xs font-semibold rounded">Ready for Review</span>;
      case "BLOCKED":
        return <span className="px-2 py-0.5 bg-danger-light text-danger text-xs font-semibold rounded">Blocked</span>;
      case "MASTER_REQUEST":
        return <span className="px-2 py-0.5 bg-warning-light text-warning text-xs font-semibold rounded">New Supplier</span>;
      case "APPROVED":
        return <span className="px-2 py-0.5 bg-primary-light text-primary text-xs font-semibold rounded">Approved</span>;
      default:
        return <span className="px-2 py-0.5 bg-border text-ink text-xs font-semibold rounded">{state}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Action Toolbar */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink tracking-tight flex items-center space-x-2">
            <Inbox className="w-6 h-6 text-primary" />
            <span>Purchase Bill Inbox</span>
          </h1>
          <p className="text-sm text-muted">
            Incoming purchase bills from WhatsApp and file upload with deterministic math and tax checks.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <Link
            href="/whatsapp"
            className="px-3.5 py-2 border border-border bg-surface hover:bg-background text-ink text-sm font-semibold rounded-md shadow-xs transition-colors flex items-center space-x-1.5"
          >
            <MessageSquare className="w-4 h-4 text-primary" />
            <span>WhatsApp Agent</span>
          </Link>

          {/* Upload Bill Button */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept=".pdf,.png,.jpg,.jpeg"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-3.5 py-2 bg-primary text-white hover:bg-primary-hover text-sm font-semibold rounded-md shadow-sm transition-colors flex items-center space-x-2"
          >
            <Upload className="w-4 h-4" />
            <span>Upload Bill</span>
          </button>
        </div>
      </div>

      {/* Notification / Toast Banner */}
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

      {/* Filter Tabs with Live Badges */}
      <div className="flex border-b border-border space-x-6 text-sm font-medium">
        {[
          { id: "all", label: "All Bills", count: statusCounts.all },
          { id: "needs_review", label: "Needs Review", count: statusCounts.needs_review },
          { id: "ready", label: "Ready to Approve", count: statusCounts.ready },
          { id: "blocked", label: "Blocked", count: statusCounts.blocked },
          { id: "approved", label: "Approved", count: statusCounts.approved },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => {
              setTab(t.id);
              setStatusFilter("ALL");
            }}
            className={`pb-3 transition-colors border-b-2 flex items-center space-x-2 ${
              tab === t.id
                ? "border-primary text-primary font-semibold"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            <span>{t.label}</span>
            {t.count !== undefined && (
              <span
                className={`text-[11px] px-1.5 py-0.5 rounded-full font-bold ${
                  tab === t.id ? "bg-primary text-white" : "bg-border/60 text-muted"
                }`}
              >
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Multi-Criteria Inbox Filter Toolbar */}
      <div className="bg-surface border border-border rounded-lg p-3.5 space-y-3 shadow-xs">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
          {/* Real-time Search Box */}
          <div className="md:col-span-4 relative">
            <Search className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by Invoice #, Supplier, or GSTIN..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-7 py-1.5 bg-background border border-border rounded-md text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                title="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Status Dropdown Filter */}
          <div className="md:col-span-3">
            <div className="flex items-center space-x-2">
              <label htmlFor="status-filter" className="text-[11px] font-semibold text-muted uppercase tracking-wider whitespace-nowrap">
                Status:
              </label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full py-1.5 px-2 bg-background border border-border rounded-md text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary font-medium"
              >
                <option value="ALL">All Statuses</option>
                <option value="READY">Ready for Review (Valid)</option>
                <option value="BLOCKED">Blocked (Validation Error)</option>
                <option value="MASTER_REQUEST">New Supplier (Needs Tally Map)</option>
                <option value="APPROVED">Approved / Exported</option>
              </select>
            </div>
          </div>

          {/* Supplier Dropdown Filter */}
          <div className="md:col-span-3">
            <div className="flex items-center space-x-2">
              <label htmlFor="supplier-filter" className="text-[11px] font-semibold text-muted uppercase tracking-wider whitespace-nowrap">
                Supplier:
              </label>
              <select
                id="supplier-filter"
                value={supplierFilter}
                onChange={(e) => setSupplierFilter(e.target.value)}
                className="w-full py-1.5 px-2 bg-background border border-border rounded-md text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary font-medium truncate"
              >
                <option value="ALL">All Suppliers ({availableSuppliers.length})</option>
                {availableSuppliers.map((s) => (
                  <option key={s.gstin} value={s.gstin}>
                    {s.legal_name} ({s.bill_count} {s.bill_count === 1 ? "bill" : "bills"})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* GSTR-2B Dropdown Filter */}
          <div className="md:col-span-2">
            <div className="flex items-center space-x-2">
              <label htmlFor="itc-filter" className="text-[11px] font-semibold text-muted uppercase tracking-wider whitespace-nowrap">
                2B:
              </label>
              <select
                id="itc-filter"
                value={itcFilter}
                onChange={(e) => setItcFilter(e.target.value)}
                className="w-full py-1.5 px-2 bg-background border border-border rounded-md text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary font-medium"
              >
                <option value="ALL">All 2B Statuses</option>
                <option value="ELIGIBLE_IN_2B">In GSTR-2B</option>
                <option value="ELIGIBLE_PENDING_2B">Missing in GSTR-2B</option>
              </select>
            </div>
          </div>
        </div>

        {/* Active Filter Indicators & Clear All */}
        {hasActiveFilters && (
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/60 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted font-medium text-[11px]">Active Filters:</span>
              {searchQuery && (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 bg-primary-light/40 border border-primary/20 rounded text-[11px] text-primary font-medium">
                  <span>Search: &quot;{searchQuery}&quot;</span>
                  <button onClick={() => setSearchQuery("")} className="hover:text-primary-hover">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {statusFilter !== "ALL" && (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 bg-primary-light/40 border border-primary/20 rounded text-[11px] text-primary font-medium">
                  <span>Status: {statusFilter}</span>
                  <button onClick={() => setStatusFilter("ALL")} className="hover:text-primary-hover">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {supplierFilter !== "ALL" && (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 bg-primary-light/40 border border-primary/20 rounded text-[11px] text-primary font-medium">
                  <span>
                    Supplier: {availableSuppliers.find((s) => s.gstin === supplierFilter)?.legal_name || supplierFilter}
                  </span>
                  <button onClick={() => setSupplierFilter("ALL")} className="hover:text-primary-hover">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {itcFilter !== "ALL" && (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 bg-primary-light/40 border border-primary/20 rounded text-[11px] text-primary font-medium">
                  <span>2B: {itcFilter === "ELIGIBLE_IN_2B" ? "In GSTR-2B" : "Missing in 2B"}</span>
                  <button onClick={() => setItcFilter("ALL")} className="hover:text-primary-hover">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
            </div>

            <div className="flex items-center space-x-3">
              <span className="text-muted text-[11px]">
                Showing <strong className="text-ink">{invoices.length}</strong> matching bills
              </span>
              <button
                onClick={clearAllFilters}
                className="text-xs text-primary hover:underline font-semibold flex items-center space-x-1"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset All Filters</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Invoice List Table */}
      <div className="bg-surface border border-border rounded-lg overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 text-center text-sm text-muted">Loading purchase bills...</div>
        ) : invoices.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Inbox className="w-8 h-8 text-muted mx-auto" />
            <div className="text-sm font-semibold text-ink">
              {hasActiveFilters ? "No bills match the selected filters" : "No bills in this queue"}
            </div>
            <p className="text-xs text-muted max-w-sm mx-auto">
              {hasActiveFilters
                ? "Try clearing some of your filter criteria or search query above to view other purchase bills."
                : "Simulate an incoming WhatsApp bill or upload an invoice to test deterministic parsing."}
            </p>
            {hasActiveFilters && (
              <button
                onClick={clearAllFilters}
                className="mt-2 px-3 py-1.5 bg-primary text-white text-xs font-semibold rounded hover:bg-primary-hover transition-colors"
              >
                Clear All Filters
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-left text-sm border-collapse">
            <thead>
              <tr className="bg-background/80 border-b border-border text-xs font-semibold text-muted uppercase tracking-wider">
                <th className="py-3 px-3 w-10 text-center">
                  <input
                    type="checkbox"
                    checked={invoices.length > 0 && selectedIds.length === invoices.length}
                    onChange={toggleSelectAll}
                    className="rounded border-border text-primary focus:ring-primary w-4 h-4 cursor-pointer align-middle"
                    title="Select/Deselect all visible bills"
                  />
                </th>
                <th className="py-3 px-4">Supplier</th>
                <th className="py-3 px-4">Invoice #</th>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4 text-right">Amount (₹)</th>
                <th className="py-3 px-4 text-center">Status</th>
                <th className="py-3 px-4 text-center">GSTR-2B</th>
                <th className="py-3 px-4">Issues / Checks</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {invoices.map((inv) => {
                const isSelected = selectedIds.includes(inv.id);
                return (
                  <tr
                    key={inv.id}
                    className={`transition-colors cursor-pointer ${
                      isSelected ? "bg-primary-light/30" : "hover:bg-background/40"
                    }`}
                    onClick={() => toggleSelectInvoice(inv.id)}
                  >
                    <td className="py-3 px-3 w-10 text-center" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelectInvoice(inv.id)}
                        className="rounded border-border text-primary focus:ring-primary w-4 h-4 cursor-pointer align-middle"
                      />
                    </td>
                    <td className="py-3 px-4">
                      <div className="font-semibold text-ink">{inv.supplier_name}</div>
                      <div className="text-xs text-muted font-mono">{inv.supplier_gstin}</div>
                    </td>
                    <td className="py-3 px-4 font-medium text-ink">{inv.number}</td>
                    <td className="py-3 px-4 text-muted text-xs">{inv.date}</td>
                    <td className="py-3 px-4 money-cell text-ink font-semibold">
                      {formatRupees(inv.total_amount)}
                    </td>
                    <td className="py-3 px-4 text-center">{getStateBadge(inv.state)}</td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          inv.itc_status === "ELIGIBLE_IN_2B"
                            ? "bg-success-light text-success"
                            : "bg-warning-light text-warning"
                        }`}
                      >
                        {inv.itc_status === "ELIGIBLE_IN_2B" ? "In 2B" : "Missing 2B"}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {inv.issues && inv.issues.length > 0 ? (
                        <div className="space-y-0.5">
                          {inv.issues.slice(0, 2).map((iss, idx) => (
                            <div
                              key={idx}
                              className={`text-[11px] font-medium flex items-center space-x-1 ${
                                iss.severity === "BLOCK" ? "text-danger" : "text-warning"
                              }`}
                            >
                              <AlertTriangle className="w-3 h-3 shrink-0" />
                              <span className="truncate max-w-[200px]" title={iss.message}>
                                {iss.code}: {iss.message}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-success flex items-center space-x-1">
                          <CheckCircle className="w-3.5 h-3.5" />
                          <span>All checks passed</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => openInvoiceModal(inv.id)}
                        className="px-3 py-1 bg-surface border border-border text-ink hover:bg-primary hover:text-white text-xs font-semibold rounded transition-colors shadow-sm"
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Sticky Batch Operations Action Bar */}
      {selectedIds.length > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-ink text-white px-5 py-3 rounded-xl shadow-2xl border border-white/10 flex items-center space-x-4 animate-in fade-in slide-in-from-bottom-4 duration-200">
          <div className="flex items-center space-x-2 text-xs font-semibold pr-3 border-r border-white/20">
            <span className="w-5 h-5 rounded-full bg-primary flex items-center justify-center text-white text-[11px] font-bold">
              {selectedIds.length}
            </span>
            <span>{selectedIds.length === 1 ? "bill selected" : "bills selected"}</span>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleBulkApprove}
              disabled={batchLoading}
              className="px-3 py-1.5 bg-success text-white hover:bg-success/90 text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center space-x-1.5 disabled:opacity-50"
            >
              <CheckCircle className="w-3.5 h-3.5" />
              <span>Approve Selected</span>
            </button>

            <button
              onClick={() => handleExportTallyXML()}
              disabled={batchLoading}
              className="px-3 py-1.5 bg-primary text-white hover:bg-primary-hover text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center space-x-1.5 disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Tally XML (Alt+O)</span>
            </button>

            <button
              onClick={handleDirectSyncTally}
              disabled={batchLoading}
              className="px-3 py-1.5 bg-surface text-ink hover:bg-background text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center space-x-1.5 disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${batchLoading ? "animate-spin" : ""}`} />
              <span>Sync to Tally (Port 9000)</span>
            </button>

            <button
              onClick={() => setSelectedIds([])}
              className="text-white/60 hover:text-white p-1 text-xs"
              title="Deselect all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Review Modal / Drawer */}
      {modalOpen && selectedInvoice && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-lg max-w-4xl w-full max-h-[90vh] flex flex-col shadow-xl overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-background/50">
              <div className="flex items-center space-x-3">
                <FileText className="w-5 h-5 text-primary" />
                <h2 className="font-bold text-ink text-lg">
                  Review Bill: {selectedInvoice.number} ({selectedInvoice.supplier_name})
                </h2>
                {getStateBadge(selectedInvoice.state)}
              </div>
              <button
                onClick={() => setModalOpen(false)}
                className="text-muted hover:text-ink p-1 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {/* Issues Alert Box */}
              {selectedInvoice.issues && selectedInvoice.issues.length > 0 && (
                <div className="p-4 bg-danger-light/50 border border-danger/30 rounded-lg space-y-2">
                  <div className="text-xs font-semibold text-danger uppercase tracking-wider flex items-center space-x-1.5">
                    <AlertTriangle className="w-4 h-4" />
                    <span>Deterministic Validation Issues</span>
                  </div>
                  <ul className="space-y-1 text-sm text-danger/90">
                    {selectedInvoice.issues.map((iss, i) => (
                      <li key={i} className="flex items-start space-x-2">
                        <span className="font-mono text-xs font-bold shrink-0">[{iss.code}]</span>
                        <span>{iss.message}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Master Request Card if unknown supplier */}
              {selectedInvoice.state === "MASTER_REQUEST" && (
                <div className="p-4 bg-warning-light border border-warning/40 rounded-lg space-y-3">
                  <div className="flex items-center space-x-2 text-warning font-semibold text-sm">
                    <Building className="w-4 h-4" />
                    <span>New Supplier Master Request</span>
                  </div>
                  <p className="text-xs text-ink/80">
                    Supplier GSTIN <span className="font-mono font-semibold">{selectedInvoice.supplier.gstin}</span> is not mapped to any Tally ledger. Please map to an existing Tally Sundry Creditor ledger.
                  </p>
                  <div className="flex items-center space-x-3">
                    <select
                      value={selectedLedgerToMap}
                      onChange={(e) => setSelectedLedgerToMap(e.target.value)}
                      className="bg-surface border border-border text-sm rounded px-3 py-1.5 font-medium flex-1 focus:ring-1 focus:ring-primary"
                    >
                      <option value="">Select Tally Ledger...</option>
                      {availableLedgers.map((l) => (
                        <option key={l.name} value={l.name}>
                          {l.name} ({l.parent})
                        </option>
                      ))}
                      {availableLedgers.length === 0 && (
                        <option value="Sharma Steels (Sundry Creditors)">Sharma Steels (Sundry Creditors)</option>
                      )}
                    </select>
                    <button
                      onClick={handleMapLedger}
                      disabled={!selectedLedgerToMap || actionLoading}
                      className="px-4 py-1.5 bg-primary text-white text-xs font-semibold rounded hover:bg-primary-hover disabled:opacity-50"
                    >
                      Map to this Ledger
                    </button>
                  </div>
                </div>
              )}

              {/* Procedural Memory Citation */}
              {selectedInvoice.applied_rules && selectedInvoice.applied_rules.length > 0 && (
                <div className="p-3 bg-primary-light/40 border border-primary/20 rounded-md text-xs text-primary flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 shrink-0" />
                  <span>
                    Applied procedural memory rule: Approved mapping by CA Partner on previous bill.
                  </span>
                </div>
              )}

              {/* Bill Details Groups */}
              <div className="grid grid-cols-2 gap-6">
                {/* Left: Supplier & Invoice Metadata */}
                <div className="space-y-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted border-b border-border pb-1">
                    Supplier & Metadata
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted">Supplier Name:</span>
                      <span className="font-semibold text-ink">{selectedInvoice.supplier.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">Supplier GSTIN:</span>
                      <span className="font-mono text-ink">{selectedInvoice.supplier.gstin}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">Invoice Number:</span>
                      <span className="font-semibold text-ink">{selectedInvoice.number}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">Invoice Date:</span>
                      <span className="text-ink">{selectedInvoice.date}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">Financial Year:</span>
                      <span className="font-semibold text-ink">{selectedInvoice.fy}</span>
                    </div>
                  </div>
                </div>

                {/* Right: Amounts and Live Correction Form */}
                <div className="space-y-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted border-b border-border pb-1">
                    Tax & Totals (Live Math Verification)
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted">Taxable Amount:</span>
                      <span className="font-semibold">{formatRupees(selectedInvoice.taxable_amount)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">CGST + SGST:</span>
                      <span>{formatRupees(selectedInvoice.cgst_amount + selectedInvoice.sgst_amount)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">IGST:</span>
                      <span>{formatRupees(selectedInvoice.igst_amount)}</span>
                    </div>
                    <div className="flex items-center justify-between pt-2 border-t border-border">
                      <span className="font-semibold text-ink">Grand Total:</span>
                      <div className="flex items-center space-x-2">
                        <input
                          type="number"
                          step="0.01"
                          value={editTotal}
                          onChange={(e) => setEditTotal(e.target.value)}
                          className="w-32 px-2 py-1 bg-background border border-border text-right font-bold text-sm rounded focus:ring-1 focus:ring-primary"
                        />
                        {parseFloat(editTotal) !== selectedInvoice.total_amount && (
                          <button
                            onClick={handleSaveEditTotal}
                            disabled={actionLoading}
                            className="px-2 py-1 bg-primary text-white text-xs rounded hover:bg-primary-hover"
                          >
                            Recalculate
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Line Items Table */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Line Items</h3>
                <table className="w-full text-xs text-left border border-border rounded overflow-hidden">
                  <thead className="bg-background">
                    <tr className="border-b border-border text-muted">
                      <th className="py-2 px-3">#</th>
                      <th className="py-2 px-3">Description</th>
                      <th className="py-2 px-3">HSN/SAC</th>
                      <th className="py-2 px-3 text-right">Qty</th>
                      <th className="py-2 px-3 text-right">Rate</th>
                      <th className="py-2 px-3 text-right">Taxable</th>
                      <th className="py-2 px-3 text-right">GST %</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {selectedInvoice.lines.map((l) => (
                      <tr key={l.no}>
                        <td className="py-1.5 px-3">{l.no}</td>
                        <td className="py-1.5 px-3 font-medium">{l.description}</td>
                        <td className="py-1.5 px-3 font-mono">{l.hsn_sac || "-"}</td>
                        <td className="py-1.5 px-3 text-right">{l.qty} {l.uom}</td>
                        <td className="py-1.5 px-3 text-right">{formatRupees(l.rate)}</td>
                        <td className="py-1.5 px-3 text-right font-medium">{formatRupees(l.taxable_value)}</td>
                        <td className="py-1.5 px-3 text-right">{l.gst_rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Modal Actions Footer */}
            <div className="px-6 py-4 border-t border-border bg-background flex justify-between items-center">
              <button
                onClick={handleReject}
                disabled={actionLoading}
                className="px-4 py-2 border border-danger/40 text-danger hover:bg-danger-light text-sm font-semibold rounded transition-colors"
              >
                Reject Bill
              </button>

              <div className="flex items-center space-x-3">
                {(selectedInvoice.state === "APPROVED" ||
                  selectedInvoice.state === "EXPORTED" ||
                  selectedInvoice.state === "POSTED") && (
                  <button
                    onClick={() => handleExportTallyXML([selectedInvoice.id])}
                    disabled={batchLoading}
                    className="px-3.5 py-2 bg-surface border border-border text-ink hover:bg-background text-xs font-semibold rounded shadow-sm flex items-center space-x-1.5 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5 text-primary" />
                    <span>Download Tally XML</span>
                  </button>
                )}
                <button
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 border border-border text-ink hover:bg-border/30 text-sm font-medium rounded"
                >
                  Close
                </button>
                <button
                  onClick={handleApprove}
                  disabled={
                    selectedInvoice.state === "BLOCKED" ||
                    selectedInvoice.state === "MASTER_REQUEST" ||
                    actionLoading
                  }
                  title={
                    selectedInvoice.state === "BLOCKED"
                      ? "Cannot approve while blocking issues exist"
                      : selectedInvoice.state === "MASTER_REQUEST"
                      ? "Map supplier to Tally ledger before approving"
                      : "Approve and stage for Tally export"
                  }
                  className="px-5 py-2 bg-success text-white text-sm font-semibold rounded hover:bg-success/90 transition-colors shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {selectedInvoice.state === "APPROVED" ? "Approved ✓" : "Approve Bill"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
