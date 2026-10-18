"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { apiFetch, downloadBlob } from "@/lib/api";
import {
  MessageSquare,
  Send,
  Upload,
  Download,
  RefreshCw,
  FileText,
  CheckCircle2,
  AlertTriangle,
  ArrowDownLeft,
  ArrowUpRight,
  ShieldCheck,
  Sparkles,
  Paperclip,
  Clock,
  Check,
  Search,
  ExternalLink
} from "lucide-react";

interface WhatsAppMessage {
  id: string;
  direction: "INBOUND" | "OUTBOUND";
  sender_phone: string;
  recipient_phone: string;
  message_type: string;
  text: string;
  media_path?: string;
  media_filename?: string;
  invoice_id?: string;
  invoice_number?: string;
  vendor_name?: string;
  status: string;
  cost_inr: number;
  template_name?: string;
  timestamp: string;
}

interface MessageStats {
  total: number;
  inbound: number;
  outbound: number;
  invoices_ingested: number;
}

const SAMPLE_BILLS = [
  { id: "clean_intrastate", name: "Sharma Steels — Clean Intra-State (₹1,18,000)", phone: "+919876543210" },
  { id: "clean_interstate", name: "Reliable Transport — Interstate IGST (₹41,300)", phone: "+919876543211" },
  { id: "freight_roundoff_invoice", name: "Real-World Multi-Item + Freight + Roundoff (₹1,56,878)", phone: "+919876543210" },
  { id: "math_error", name: "Discrepancy Bill — Tax Math Mismatch (Auto-Blocked)", phone: "+919876543212" },
  { id: "wrong_tax_type", name: "Statutory Violation — CGST/SGST on Interstate", phone: "+919876543213" },
  { id: "old_invoice_rule37", name: "Aged Bill (>180 Days) — Rule 37 Reversal Alert", phone: "+919876543210" }
];

const QUICK_TEXT_CHIPS = [
  "What is status of our pending bills?",
  "Payment kab tak release hogi?",
  "Invoice INV-2026-001 filed in GSTR-1 yesterday",
  "STOP",
  "START"
];

export default function WhatsAppHubPage() {
  const [messages, setMessages] = useState<WhatsAppMessage[]>([]);
  const [stats, setStats] = useState<MessageStats>({ total: 0, inbound: 0, outbound: 0, invoices_ingested: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Filters
  const [filterDirection, setFilterDirection] = useState<"ALL" | "INBOUND" | "OUTBOUND">("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Tab: "bill" | "text" | "outbound"
  const [activeTab, setActiveTab] = useState<"bill" | "text" | "outbound">("bill");

  // Inbound Bill Simulator State
  const [billFixture, setBillFixture] = useState("clean_intrastate");
  const [billPhone, setBillPhone] = useState("+919876543210");
  const [billCaption, setBillCaption] = useState("Attached purchase bill copy for GST clearance");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [simulatingBill, setSimulatingBill] = useState(false);

  // Inbound Text Simulator State
  const [textPhone, setTextPhone] = useState("+919876543210");
  const [textContent, setTextContent] = useState("What is status of our pending bills?");
  const [simulatingText, setSimulatingText] = useState(false);

  // Outbound Dispatch State
  const [outboundPhone, setOutboundPhone] = useState("+919876543210");
  const [outboundText, setOutboundText] = useState("Payment of Rs. 1,00,000 approved and released. Tax portion Rs. 18,000 on hold pending GSTR-2B reflection.");
  const [outboundInvoiceId, setOutboundInvoiceId] = useState("");
  const [sendingOutbound, setSendingOutbound] = useState(false);

  // Feedback Notification
  const [banner, setBanner] = useState<{ title: string; desc: string; type: "success" | "warning" | "info" } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  // Fetch all messages
  const fetchMessages = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const data = await apiFetch<{ messages: WhatsAppMessage[]; stats: MessageStats }>("/whatsapp/messages?limit=100");
      setMessages(data.messages || []);
      if (data.stats) {
        setStats(data.stats);
      }
    } catch (err) {
      console.error("Failed to load messages:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  // Scroll to bottom when messages update
  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Export CSV Working Paper
  const handleExportCsv = async () => {
    try {
      await downloadBlob("/whatsapp/export", "whatsapp_communications_audit.csv");
      setBanner({
        title: "Export Complete",
        desc: "Statutory WhatsApp communications log downloaded as CSV working paper.",
        type: "success"
      });
    } catch (err: unknown) {
      alert("Failed to export WhatsApp ledger: " + (err instanceof Error ? err.message : String(err)));
    }
  };

  // Submit Inbound Bill Simulation
  const handleSimulateBill = async (e: React.FormEvent) => {
    e.preventDefault();
    setSimulatingBill(true);
    setBanner(null);

    const formData = new FormData();
    formData.append("phone", billPhone);
    formData.append("caption", billCaption);

    if (selectedFile) {
      formData.append("file", selectedFile);
    } else {
      formData.append("fixture_name", billFixture);
    }

    try {
      const res = await apiFetch<{
        status: string;
        state: string;
        inbound_message: WhatsAppMessage;
        outbound_reply: WhatsAppMessage;
        invoice: { invoice_number: string; total_amount: number };
      }>("/whatsapp/simulate/bill", {
        method: "POST",
        body: formData
      });

      setBanner({
        title: `Bill Ingested via WhatsApp (${res.state})`,
        desc: `AI Agent extracted invoice #${res.invoice?.invoice_number || "new"} (₹${Number(res.invoice?.total_amount || 0).toLocaleString("en-IN")}) and sent automated WhatsApp confirmation back to ${billPhone}.`,
        type: res.state === "BLOCKED" ? "warning" : "success"
      });

      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await fetchMessages();
    } catch (err: unknown) {
      alert("Bill simulation failed: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSimulatingBill(false);
    }
  };

  // Submit Inbound Text Simulation
  const handleSimulateText = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textContent.trim()) return;
    setSimulatingText(true);
    setBanner(null);

    try {
      const res = await apiFetch<{
        status: string;
        inbound_message: WhatsAppMessage;
        outbound_reply: WhatsAppMessage;
      }>("/whatsapp/simulate/text", {
        method: "POST",
        body: JSON.stringify({
          phone: textPhone,
          text: textContent
        })
      });

      setBanner({
        title: "Incoming WhatsApp Text Processed",
        desc: `AI Agent analyzed message and generated contextual reply: "${res.outbound_reply?.text?.slice(0, 90)}..."`,
        type: "info"
      });

      setTextContent("");
      await fetchMessages();
    } catch (err: unknown) {
      alert("Text simulation failed: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSimulatingText(false);
    }
  };

  // Submit Outbound Agent Message
  const handleSendOutbound = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!outboundText.trim()) return;
    setSendingOutbound(true);
    setBanner(null);

    try {
      await apiFetch("/whatsapp/send", {
        method: "POST",
        body: JSON.stringify({
          to_phone: outboundPhone,
          text: outboundText,
          invoice_id: outboundInvoiceId || null
        })
      });

      setBanner({
        title: "Message Dispatched by Agent",
        desc: `Official notice delivered to ${outboundPhone} and recorded in the audit trail.`,
        type: "success"
      });

      await fetchMessages();
    } catch (err: unknown) {
      alert("Failed to send outbound message: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSendingOutbound(false);
    }
  };

  // Filter messages
  const filteredMessages = messages.filter((m) => {
    if (filterDirection !== "ALL" && m.direction !== filterDirection) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchText = (m.text || "").toLowerCase().includes(q);
      const matchPhone = (m.sender_phone || "").includes(q) || (m.recipient_phone || "").includes(q);
      const matchInv = (m.invoice_number || m.invoice_id || "").toLowerCase().includes(q);
      const matchVendor = (m.vendor_name || "").toLowerCase().includes(q);
      if (!matchText && !matchPhone && !matchInv && !matchVendor) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight flex items-center space-x-2">
            <MessageSquare className="w-6 h-6 text-primary" />
            <span>WhatsApp Agent & Communications Hub</span>
          </h1>
          <p className="text-sm text-muted">
            Import vendor PDF bills & client text messages via WhatsApp, auto-reply with GST validation status, and export statutory communication ledgers.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => fetchMessages(true)}
            disabled={refreshing}
            className="flex items-center space-x-1.5 px-3 py-1.5 border border-border rounded-md text-xs font-medium text-ink hover:bg-background transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-primary" : "text-muted"}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={handleExportCsv}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-primary hover:bg-primary-hover text-white rounded-md text-xs font-semibold shadow-sm transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export Messages (CSV)</span>
          </button>
        </div>
      </div>

      {/* Banner */}
      {banner && (
        <div
          className={`p-4 rounded-lg border text-sm flex items-start justify-between ${
            banner.type === "success"
              ? "bg-success-light/40 border-success/30 text-ink"
              : banner.type === "warning"
              ? "bg-warning-light/40 border-warning/30 text-ink"
              : "bg-primary-light/40 border-primary/30 text-ink"
          }`}
        >
          <div className="flex items-start space-x-3">
            {banner.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-success shrink-0 mt-0.5" />
            ) : banner.type === "warning" ? (
              <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
            ) : (
              <Sparkles className="w-5 h-5 text-primary shrink-0 mt-0.5" />
            )}
            <div>
              <div className="font-semibold text-ink">{banner.title}</div>
              <div className="text-xs text-muted mt-0.5">{banner.desc}</div>
            </div>
          </div>
          <button onClick={() => setBanner(null)} className="text-muted hover:text-ink text-xs ml-4">
            ✕
          </button>
        </div>
      )}

      {/* KPI Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 bg-surface rounded-lg border border-border shadow-sm">
          <div className="text-xs font-medium text-muted uppercase tracking-wider">Total Messages</div>
          <div className="text-2xl font-bold text-ink mt-1">{stats.total}</div>
          <div className="text-[11px] text-muted mt-1">Logged in knowledge graph</div>
        </div>

        <div className="p-4 bg-surface rounded-lg border border-border shadow-sm">
          <div className="text-xs font-medium text-muted uppercase tracking-wider flex items-center space-x-1">
            <ArrowDownLeft className="w-3.5 h-3.5 text-success" />
            <span>Inbound Received</span>
          </div>
          <div className="text-2xl font-bold text-success mt-1">{stats.inbound}</div>
          <div className="text-[11px] text-muted mt-1">Bills & client queries</div>
        </div>

        <div className="p-4 bg-surface rounded-lg border border-border shadow-sm">
          <div className="text-xs font-medium text-muted uppercase tracking-wider flex items-center space-x-1">
            <ArrowUpRight className="w-3.5 h-3.5 text-primary" />
            <span>Outbound Dispatched</span>
          </div>
          <div className="text-2xl font-bold text-primary mt-1">{stats.outbound}</div>
          <div className="text-[11px] text-muted mt-1">Auto-replies & reminders</div>
        </div>

        <div className="p-4 bg-surface rounded-lg border border-border shadow-sm">
          <div className="text-xs font-medium text-muted uppercase tracking-wider flex items-center space-x-1">
            <FileText className="w-3.5 h-3.5 text-ink" />
            <span>Bills Ingested</span>
          </div>
          <div className="text-2xl font-bold text-ink mt-1">{stats.invoices_ingested}</div>
          <div className="text-[11px] text-muted mt-1">Extracted & verified</div>
        </div>
      </div>

      {/* Two Column Layout: Simulator / Sender on Left, Live Message Stream on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (5 cols): Interactive Simulator & Dispatcher */}
        <div className="lg:col-span-5 space-y-4">
          <div className="bg-surface rounded-xl border border-border shadow-sm overflow-hidden">
            {/* Tab Header */}
            <div className="flex border-b border-border bg-background/50 p-1">
              <button
                onClick={() => setActiveTab("bill")}
                className={`flex-1 py-2 text-xs font-semibold rounded-md transition-colors flex items-center justify-center space-x-1.5 ${
                  activeTab === "bill"
                    ? "bg-surface text-primary shadow-xs border border-border/80"
                    : "text-muted hover:text-ink"
                }`}
              >
                <Paperclip className="w-3.5 h-3.5" />
                <span>Import Bill (PDF)</span>
              </button>

              <button
                onClick={() => setActiveTab("text")}
                className={`flex-1 py-2 text-xs font-semibold rounded-md transition-colors flex items-center justify-center space-x-1.5 ${
                  activeTab === "text"
                    ? "bg-surface text-primary shadow-xs border border-border/80"
                    : "text-muted hover:text-ink"
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Receive Text</span>
              </button>

              <button
                onClick={() => setActiveTab("outbound")}
                className={`flex-1 py-2 text-xs font-semibold rounded-md transition-colors flex items-center justify-center space-x-1.5 ${
                  activeTab === "outbound"
                    ? "bg-surface text-primary shadow-xs border border-border/80"
                    : "text-muted hover:text-ink"
                }`}
              >
                <Send className="w-3.5 h-3.5" />
                <span>Agent Send</span>
              </button>
            </div>

            {/* Tab 1: Inbound Bill Ingestion */}
            {activeTab === "bill" && (
              <form onSubmit={handleSimulateBill} className="p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-ink uppercase tracking-wider flex items-center space-x-1.5">
                    <ArrowDownLeft className="w-4 h-4 text-success" />
                    <span>Ingest Supplier WhatsApp Bill</span>
                  </span>
                  <span className="text-[10px] bg-success-light text-success font-semibold px-2 py-0.5 rounded-full">
                    Auto-Replies Enabled
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Sender Phone Number
                  </label>
                  <input
                    type="text"
                    value={billPhone}
                    onChange={(e) => setBillPhone(e.target.value)}
                    placeholder="+919876543210"
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink font-mono focus:outline-hidden focus:ring-1 focus:ring-primary"
                    required
                  />
                  <div className="flex items-center space-x-2 mt-1.5">
                    <span className="text-[10px] text-muted">Quick fill:</span>
                    <button
                      type="button"
                      onClick={() => setBillPhone("+919876543210")}
                      className="text-[10px] text-primary hover:underline font-mono"
                    >
                      Sharma Steels (+919876543210)
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Select Test Invoice / Bill Sample
                  </label>
                  <select
                    value={billFixture}
                    onChange={(e) => {
                      setBillFixture(e.target.value);
                      setSelectedFile(null);
                    }}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                  >
                    {SAMPLE_BILLS.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="relative border border-dashed border-border rounded-lg p-3 text-center bg-background/30">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setSelectedFile(e.target.files[0]);
                      }
                    }}
                    className="hidden"
                    id="custom-bill-upload"
                  />
                  <label htmlFor="custom-bill-upload" className="cursor-pointer block">
                    <Upload className="w-5 h-5 mx-auto text-muted mb-1" />
                    <span className="text-xs font-semibold text-primary hover:underline">
                      {selectedFile ? selectedFile.name : "Or upload custom bill PDF/Image"}
                    </span>
                    <p className="text-[10px] text-muted mt-0.5">PDF, JPG, PNG up to 15MB</p>
                  </label>
                  {selectedFile && (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = "";
                      }}
                      className="text-[10px] text-danger mt-1 hover:underline block mx-auto"
                    >
                      Remove custom file
                    </button>
                  )}
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    WhatsApp Message Caption
                  </label>
                  <input
                    type="text"
                    value={billCaption}
                    onChange={(e) => setBillCaption(e.target.value)}
                    placeholder="Attached bill copy"
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={simulatingBill}
                    className="w-full py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center justify-center space-x-2 disabled:opacity-50"
                  >
                    {simulatingBill ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Ingesting Bill & Generating Auto-Reply...</span>
                      </>
                    ) : (
                      <>
                        <Paperclip className="w-3.5 h-3.5" />
                        <span>Ingest WhatsApp Bill Document</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}

            {/* Tab 2: Inbound Supplier Text */}
            {activeTab === "text" && (
              <form onSubmit={handleSimulateText} className="p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-ink uppercase tracking-wider flex items-center space-x-1.5">
                    <ArrowDownLeft className="w-4 h-4 text-success" />
                    <span>Receive Supplier WhatsApp Query</span>
                  </span>
                  <span className="text-[10px] bg-primary-light text-primary font-semibold px-2 py-0.5 rounded-full">
                    AI Intent Parser
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Sender Phone Number
                  </label>
                  <input
                    type="text"
                    value={textPhone}
                    onChange={(e) => setTextPhone(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink font-mono focus:outline-hidden focus:ring-1 focus:ring-primary"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Incoming WhatsApp Text
                  </label>
                  <textarea
                    rows={3}
                    value={textContent}
                    onChange={(e) => setTextContent(e.target.value)}
                    placeholder="Type supplier inquiry or message..."
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                    required
                  />
                </div>

                <div>
                  <span className="block text-[11px] font-medium text-muted mb-1.5">
                    Quick Sample Messages:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {QUICK_TEXT_CHIPS.map((chip) => (
                      <button
                        key={chip}
                        type="button"
                        onClick={() => setTextContent(chip)}
                        className="text-[10px] px-2 py-1 bg-background border border-border rounded hover:bg-border/40 text-ink/80 transition-colors"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={simulatingText}
                    className="w-full py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center justify-center space-x-2 disabled:opacity-50"
                  >
                    {simulatingText ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Processing Text & Responding...</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-3.5 h-3.5" />
                        <span>Receive Supplier WhatsApp Message</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}

            {/* Tab 3: Outbound Agent Dispatch */}
            {activeTab === "outbound" && (
              <form onSubmit={handleSendOutbound} className="p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-ink uppercase tracking-wider flex items-center space-x-1.5">
                    <ArrowUpRight className="w-4 h-4 text-primary" />
                    <span>Dispatch Outbound Notice (Agent)</span>
                  </span>
                  <span className="text-[10px] bg-primary-light text-primary font-semibold px-2 py-0.5 rounded-full">
                    Audited Dispatch
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Recipient Phone Number
                  </label>
                  <input
                    type="text"
                    value={outboundPhone}
                    onChange={(e) => setOutboundPhone(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink font-mono focus:outline-hidden focus:ring-1 focus:ring-primary"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Linked Invoice Reference (Optional)
                  </label>
                  <input
                    type="text"
                    value={outboundInvoiceId}
                    onChange={(e) => setOutboundInvoiceId(e.target.value)}
                    placeholder="e.g. inv_clean_intrastate"
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Official Message Content
                  </label>
                  <textarea
                    rows={4}
                    value={outboundText}
                    onChange={(e) => setOutboundText(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                    required
                  />
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={sendingOutbound}
                    className="w-full py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center justify-center space-x-2 disabled:opacity-50"
                  >
                    {sendingOutbound ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Dispatching WhatsApp Notice...</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-3.5 h-3.5" />
                        <span>Dispatch WhatsApp Notice to Supplier</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Quick Help Card */}
          <div className="p-4 bg-background border border-border rounded-xl text-xs text-muted space-y-2">
            <div className="font-semibold text-ink flex items-center space-x-1.5">
              <ShieldCheck className="w-4 h-4 text-primary" />
              <span>How the WhatsApp Agent Operates</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px] leading-relaxed">
              <li>Suppliers send bills as PDF or photos via WhatsApp.</li>
              <li>Agent automatically runs deterministic OCR, GSTIN checksums, and tax math verification.</li>
              <li>Agent dispatches real-time confirmations: <code>READY</code> bills go to CA review, <code>BLOCKED</code> bills notify vendor of math errors.</li>
              <li>Accountants can chase non-filing vendors and export the full tamper-evident communication log for tax audit working papers.</li>
            </ul>
          </div>
        </div>

        {/* Right Column (7 cols): Live WhatsApp Stream & Communications History */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-surface rounded-xl border border-border shadow-sm flex flex-col h-[650px] overflow-hidden">
            {/* Thread Header & Filters */}
            <div className="p-4 border-b border-border bg-background/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-sm text-ink">Communications Ledger</span>
                <span className="text-xs bg-border/50 text-muted px-2 py-0.5 rounded-full">
                  {filteredMessages.length} messages
                </span>
              </div>

              {/* Filter Pills & Search */}
              <div className="flex items-center space-x-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search phone or text..."
                    className="pl-8 pr-2 py-1.5 text-xs bg-surface border border-border rounded-md text-ink focus:outline-hidden focus:ring-1 focus:ring-primary w-40"
                  />
                </div>

                <div className="flex items-center bg-surface border border-border rounded-md p-0.5">
                  <button
                    onClick={() => setFilterDirection("ALL")}
                    className={`px-2 py-1 text-[11px] font-medium rounded ${
                      filterDirection === "ALL" ? "bg-primary text-white" : "text-muted hover:text-ink"
                    }`}
                  >
                    All
                  </button>
                  <button
                    onClick={() => setFilterDirection("INBOUND")}
                    className={`px-2 py-1 text-[11px] font-medium rounded ${
                      filterDirection === "INBOUND" ? "bg-primary text-white" : "text-muted hover:text-ink"
                    }`}
                  >
                    In
                  </button>
                  <button
                    onClick={() => setFilterDirection("OUTBOUND")}
                    className={`px-2 py-1 text-[11px] font-medium rounded ${
                      filterDirection === "OUTBOUND" ? "bg-primary text-white" : "text-muted hover:text-ink"
                    }`}
                  >
                    Out
                  </button>
                </div>
              </div>
            </div>

            {/* Scrollable Message List */}
            <div ref={chatScrollRef} className="flex-1 p-4 overflow-y-auto space-y-4 bg-background/20">
              {loading ? (
                <div className="flex flex-col items-center justify-center h-full text-muted space-y-2">
                  <RefreshCw className="w-6 h-6 animate-spin text-primary" />
                  <span className="text-xs">Loading WhatsApp communications...</span>
                </div>
              ) : filteredMessages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-muted text-center space-y-2 p-6">
                  <MessageSquare className="w-8 h-8 text-border" />
                  <div className="text-sm font-semibold text-ink">No WhatsApp Messages Yet</div>
                  <p className="text-xs text-muted max-w-sm">
                    Use the simulator on the left to send an incoming bill (PDF) or inquiry, and observe the AI Agent reply in real time.
                  </p>
                </div>
              ) : (
                filteredMessages.map((m) => {
                  const isInbound = m.direction === "INBOUND";
                  return (
                    <div
                      key={m.id}
                      className={`flex flex-col ${isInbound ? "items-start" : "items-end"} space-y-1`}
                    >
                      {/* Meta header above bubble */}
                      <div className="flex items-center space-x-2 text-[10px] text-muted px-1">
                        <span className="font-semibold text-ink">
                          {isInbound ? m.vendor_name || m.sender_phone : "AI CA Agent"}
                        </span>
                        <span>•</span>
                        <span className="font-mono">{isInbound ? m.sender_phone : `to: ${m.recipient_phone}`}</span>
                        <span>•</span>
                        <span className="flex items-center space-x-1">
                          <Clock className="w-2.5 h-2.5" />
                          <span>{new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                        </span>
                      </div>

                      {/* Bubble Container */}
                      <div
                        className={`max-w-[85%] rounded-2xl p-3.5 shadow-xs border text-xs leading-relaxed ${
                          isInbound
                            ? "bg-surface border-border text-ink rounded-tl-xs"
                            : "bg-primary-light/50 border-primary/30 text-ink rounded-tr-xs"
                        }`}
                      >
                        {/* If Media / Document attached */}
                        {m.media_filename && (
                          <div className="mb-2 p-2 bg-background/80 border border-border rounded-lg flex items-center justify-between gap-3">
                            <div className="flex items-center space-x-2 min-w-0">
                              <FileText className="w-4 h-4 text-primary shrink-0" />
                              <div className="truncate">
                                <div className="font-semibold text-ink truncate text-[11px]">
                                  {m.media_filename}
                                </div>
                                <div className="text-[10px] text-muted uppercase">Attached Document</div>
                              </div>
                            </div>
                            <Link
                              href="/inbox"
                              className="shrink-0 text-[10px] text-primary hover:underline font-semibold flex items-center space-x-1 bg-surface px-2 py-1 rounded border border-border"
                            >
                              <span>View in Inbox</span>
                              <ExternalLink className="w-2.5 h-2.5" />
                            </Link>
                          </div>
                        )}

                        {/* Text Content */}
                        <p className="whitespace-pre-line text-xs font-normal">{m.text}</p>

                        {/* Invoice reference pill if present */}
                        {m.invoice_number && (
                          <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-[10px]">
                            <span className="text-muted">
                              Ref: <strong className="text-ink font-mono">{m.invoice_number}</strong>
                            </span>
                            <span className="bg-surface px-1.5 py-0.5 rounded text-[9px] font-semibold text-primary border border-border/60">
                              Linked Bill
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Status and Cost footnote */}
                      <div className="flex items-center space-x-2 text-[9px] text-muted px-1">
                        <span className="flex items-center space-x-0.5 text-success">
                          <Check className="w-2.5 h-2.5" />
                          <span>{m.status}</span>
                        </span>
                        {m.cost_inr > 0 && (
                          <>
                            <span>•</span>
                            <span>Statutory Utility Cost: ₹{m.cost_inr.toFixed(2)}</span>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Bottom Bar: Status Info */}
            <div className="p-3 border-t border-border bg-background/50 flex items-center justify-between text-xs text-muted">
              <span className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-success"></span>
                <span className="text-[11px]">WhatsApp Bot Webhook Active</span>
              </span>
              <span className="text-[11px] font-mono">
                API Endpoint: <code>/api/v1/webhooks/whatsapp</code>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
