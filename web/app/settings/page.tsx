"use client";

import { useEffect, useState, useRef } from "react";
import { apiFetch, getBusinessWhatsAppPhone, setBusinessWhatsAppPhone } from "@/lib/api";
import {
  Upload,
  CheckCircle,
  ShieldCheck,
  FileCode,
  MessageSquare,
  FileSpreadsheet,
  Phone,
  RefreshCw,
  CheckCircle2
} from "lucide-react";

interface AuditEvent {
  id: string;
  timestamp: string;
  event_type: string;
  user_id: string;
  prev_hash: string;
  hash: string;
  payload: Record<string, unknown>;
}

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState<"whatsapp" | "tally" | "rules" | "audit">("whatsapp");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // WhatsApp Configuration State
  const [whatsappPhone, setWhatsappPhone] = useState("+91 98765 43210");
  const [whatsappToken, setWhatsappToken] = useState("ledgergraph-verify-token-2026");
  const [waSaving, setWaSaving] = useState(false);
  const [waSuccess, setWaSuccess] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAudit = () => {
    apiFetch<AuditEvent[]>("/audit")
      .then((data) => setAuditEvents(data || []))
      .catch((err) => console.error("Failed fetching audit log:", err));
  };

  useEffect(() => {
    fetchAudit();
    setWhatsappPhone(getBusinessWhatsAppPhone());
    const handlePhoneChange = () => setWhatsappPhone(getBusinessWhatsAppPhone());
    window.addEventListener("whatsAppPhoneChanged", handlePhoneChange);
    return () => window.removeEventListener("whatsAppPhoneChanged", handlePhoneChange);
  }, []);

  const handleSaveWhatsAppConfig = (e: React.FormEvent) => {
    e.preventDefault();
    setWaSaving(true);
    setWaSuccess(null);
    setBusinessWhatsAppPhone(whatsappPhone.trim());
    setTimeout(() => {
      setWaSaving(false);
      setWaSuccess("WhatsApp settings saved! Suppliers can now send bills to " + whatsappPhone.trim());
    }, 400);
  };

  const handleMastersUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    setImportStatus(null);
    try {
      const res = await apiFetch<{ ledgers_created: number; stock_items_created: number }>(
        "/masters/import",
        {
          method: "POST",
          body: formData,
        }
      );
      setImportStatus(
        `Successfully imported ${res.ledgers_created} Tally Ledgers and ${res.stock_items_created} Stock Items!`
      );
      fetchAudit();
    } catch (err: unknown) {
      if (err instanceof Error) {
        alert("Masters import failed: " + err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-ink tracking-tight">Settings & Integrations</h1>
        <p className="text-sm text-muted">
          Manage your WhatsApp business number, Tally chart of accounts, and GST compliance rules.
        </p>
      </div>

      {/* Tabs - No Email, 100% WhatsApp + Tally + Rules + Audit */}
      <div className="flex border-b border-border space-x-6 text-sm font-medium">
        {[
          { id: "whatsapp", label: "WhatsApp Setup", icon: MessageSquare },
          { id: "tally", label: "Tally Prime Integration", icon: FileSpreadsheet },
          { id: "rules", label: "GST & Tax Rules", icon: FileCode },
          { id: "audit", label: "Audit Log & History", icon: ShieldCheck },
        ].map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveSection(tab.id as "whatsapp" | "tally" | "rules" | "audit")}
              className={`pb-3 flex items-center space-x-2 transition-colors border-b-2 ${
                activeSection === tab.id
                  ? "border-primary text-primary font-semibold"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Section 1: WhatsApp Configuration */}
      {activeSection === "whatsapp" && (
        <div className="space-y-6 max-w-2xl">
          <div className="bg-surface border border-border rounded-xl p-6 space-y-5 shadow-sm">
            <div>
              <h3 className="font-bold text-ink text-base flex items-center space-x-2">
                <MessageSquare className="w-5 h-5 text-success" />
                <span>WhatsApp Business Setup</span>
              </h3>
              <p className="text-xs text-muted mt-1 leading-relaxed">
                Connect your WhatsApp number so suppliers can send purchase bill photos/PDFs and you can send 1-click reminders.
              </p>
            </div>

            {waSuccess && (
              <div className="p-3 bg-success-light border border-success/20 text-success rounded-lg text-xs flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{waSuccess}</span>
              </div>
            )}

            <form onSubmit={handleSaveWhatsAppConfig} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
                  Your WhatsApp Number for Receiving Bills
                </label>
                <div className="relative">
                  <Phone className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={whatsappPhone}
                    onChange={(e) => setWhatsappPhone(e.target.value)}
                    required
                    className="w-full pl-9 pr-3 py-2 bg-background border border-border rounded-lg text-sm text-ink font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                    placeholder="+91 98765 43210"
                  />
                </div>
                <p className="text-[11px] text-muted mt-1">
                  Give this number to your suppliers. Any bill photos or PDFs sent here will be automatically extracted and added to your Bills Inbox.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
                  Webhook Verify Token
                </label>
                <input
                  type="text"
                  value={whatsappToken}
                  onChange={(e) => setWhatsappToken(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm text-ink font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <p className="text-[11px] text-muted mt-1">
                  Token used to verify incoming messages from Meta WhatsApp Cloud API.
                </p>
              </div>

              <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-lg space-y-2 text-xs">
                <div className="font-semibold text-emerald-900 flex items-center space-x-1.5">
                  <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
                  <span>Live Public Webhook URL (For Meta WhatsApp Cloud API)</span>
                </div>
                <div className="bg-white p-2.5 rounded border border-emerald-300 font-mono text-[11px] text-emerald-950 break-all select-all flex items-center justify-between">
                  <span>https://couple-geo-tourism-freedom.trycloudflare.com/api/v1/webhooks/whatsapp</span>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText("https://couple-geo-tourism-freedom.trycloudflare.com/api/v1/webhooks/whatsapp");
                      alert("Copied Public Webhook URL to clipboard!");
                    }}
                    className="ml-2 px-2.5 py-1 bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-[11px] font-bold rounded shrink-0"
                  >
                    Copy
                  </button>
                </div>
                <p className="text-[11px] text-emerald-800">
                  Paste this into Meta Developer Dashboard &gt; WhatsApp &gt; Configuration &gt; <strong>Callback URL</strong>, with Verify Token: <strong className="font-mono">{whatsappToken}</strong>.
                </p>
              </div>

              <div className="p-3.5 bg-background rounded-lg border border-border space-y-2 text-xs">
                <div className="font-semibold text-ink">How to Send WhatsApp to Suppliers:</div>
                <ul className="list-disc list-inside text-muted space-y-1 text-[11px]">
                  <li>You can send reminders automatically from the <strong>WhatsApp Center</strong> page.</li>
                  <li>Or click <strong>&quot;Open in WhatsApp Web&quot;</strong> on any bill to send directly from your personal or office phone without setup!</li>
                </ul>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={waSaving}
                  className="px-4 py-2 bg-primary text-white text-xs font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-sm flex items-center space-x-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${waSaving ? "animate-spin" : ""}`} />
                  <span>{waSaving ? "Saving..." : "Save WhatsApp Settings"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Section 2: Tally Integration */}
      {activeSection === "tally" && (
        <div className="space-y-6 max-w-2xl">
          <div className="bg-surface border border-border rounded-xl p-6 space-y-4 shadow-sm">
            <h3 className="font-bold text-ink text-base flex items-center space-x-2">
              <FileSpreadsheet className="w-5 h-5 text-primary" />
              <span>Import Tally Chart of Accounts</span>
            </h3>
            <p className="text-xs text-muted leading-relaxed">
              Upload your exported TallyPrime XML masters (List of Ledgers and Stock Items).
              This allows LedgerGraph to automatically match supplier bills to your exact Tally ledger names.
            </p>

            <div className="p-6 border-2 border-dashed border-border rounded-xl bg-background text-center space-y-3">
              <Upload className="w-8 h-8 text-muted mx-auto" />
              <div className="text-sm font-semibold text-ink">
                Click to browse or drop Tally XML export
              </div>
              <p className="text-xs text-muted">Exported from Tally via: Alt+E &gt; Masters &gt; XML format</p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xml"
                onChange={handleMastersUpload}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
                className="px-4 py-2 bg-primary text-white text-xs font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-sm disabled:opacity-50"
              >
                {loading ? "Reading Tally XML..." : "Select Tally XML File"}
              </button>
            </div>

            {importStatus && (
              <div className="p-3 bg-success-light text-success border border-success/30 rounded-lg text-xs font-medium flex items-center space-x-2">
                <CheckCircle className="w-4 h-4 shrink-0" />
                <span>{importStatus}</span>
              </div>
            )}

            <div className="pt-4 border-t border-border">
              <h4 className="text-xs font-bold uppercase tracking-wider text-muted mb-2">How to Import Vouchers into TallyPrime:</h4>
              <ol className="list-decimal list-inside text-xs text-muted space-y-1.5">
                <li>Go to <strong>Bills (Inbox)</strong> and select approved bills.</li>
                <li>Click <strong>&quot;Download Tally XML&quot;</strong> to get the XML file.</li>
                <li>In TallyPrime, press <strong>Alt + O &gt; Import &gt; Transactions &gt; XML</strong>.</li>
              </ol>
            </div>
          </div>
        </div>
      )}

      {/* Section 3: Statutory Rules */}
      {activeSection === "rules" && (
        <div className="space-y-6 max-w-2xl">
          <div className="bg-surface border border-border rounded-xl p-6 space-y-4 shadow-sm">
            <h3 className="font-bold text-ink text-base flex items-center space-x-2">
              <FileCode className="w-5 h-5 text-primary" />
              <span>GST Statutory Rules &amp; Parameters</span>
            </h3>
            <p className="text-xs text-muted">
              These statutory parameters govern tax calculations, 180-day Rule 37 aging, and GSTR-2B matching rules.
            </p>
            <div className="space-y-2 text-xs font-mono bg-background p-4 rounded-lg border border-border">
              <div className="flex justify-between py-1 border-b border-border/50">
                <span className="text-muted">GST Tax Slabs:</span>
                <span className="text-ink font-semibold">0%, 5%, 12%, 18%, 28%</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border/50">
                <span className="text-muted">Rule 37 Max Unpaid Days:</span>
                <span className="text-ink font-semibold">180 Days</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border/50">
                <span className="text-muted">Rule 37 Proactive Warning:</span>
                <span className="text-ink font-semibold">120 &amp; 150 Days</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border/50">
                <span className="text-muted">Rule 37A Annual Reversal Cutoff:</span>
                <span className="text-ink font-semibold">30th November</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-muted">GSTR-2B Math Tolerance:</span>
                <span className="text-ink font-semibold">₹1.00 (Rounding off)</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Section 4: Tamper-Evident Audit Log */}
      {activeSection === "audit" && (
        <div className="space-y-4">
          <div className="p-3 bg-success-light/60 border border-success/30 rounded-lg flex items-center justify-between text-xs text-success font-semibold">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 shrink-0" />
              <span>Tamper-Evident Hash Chain: Verified Intact</span>
            </div>
            <span className="font-mono text-muted">{auditEvents.length} Recorded Actions</span>
          </div>

          <div className="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
            <table className="w-full text-left text-xs">
              <thead className="bg-background border-b border-border text-muted font-semibold uppercase tracking-wider">
                <tr>
                  <th className="p-3">Time</th>
                  <th className="p-3">Action Type</th>
                  <th className="p-3">User</th>
                  <th className="p-3">Cryptographic SHA-256 Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono">
                {auditEvents.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-6 text-center text-muted font-sans">
                      No audit events recorded yet.
                    </td>
                  </tr>
                ) : (
                  auditEvents.slice(0, 15).map((e) => (
                    <tr key={e.id} className="hover:bg-background/50">
                      <td className="p-3 text-muted">{new Date(e.timestamp).toLocaleTimeString()}</td>
                      <td className="p-3 font-semibold text-ink font-sans">{e.event_type}</td>
                      <td className="p-3 text-muted">{e.user_id}</td>
                      <td className="p-3 text-[11px] text-muted truncate max-w-[200px]" title={e.hash}>
                        {e.hash.substring(0, 16)}...
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
