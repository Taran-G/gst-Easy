"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import {
  Bot,
  Play,
  Pause,
  RefreshCw,
  Mail,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Send,
  FileText,
  Check,
  Settings as SettingsIcon,
  Terminal,
  Zap,
  Inbox
} from "lucide-react";

interface AgentLog {
  id: string;
  timestamp: string;
  event: string;
  message: string;
  level: "INFO" | "SUCCESS" | "WARNING" | "ERROR" | "DEBUG";
  details: Record<string, unknown>;
}

interface AutomationStatus {
  is_running: boolean;
  interval_seconds: number;
  cycle_count: number;
  last_run: string | null;
  next_run: string | null;
  invoices_processed_count: number;
  alerts_generated_count: number;
  email_mode: string;
  email_username: string;
  email_unread_count: number;
  logs: AgentLog[];
}

interface EmailItem {
  id: string;
  from_addr: string;
  to_addr: string;
  subject: string;
  body: string;
  received_at?: string;
  sent_at?: string;
  is_read?: boolean;
  processed_invoice_id?: string | null;
  attachments?: Array<{ filename: string; path: string }>;
}

const SAMPLE_SUPPLIER_EMAILS = [
  {
    name: "Sharma Steels (Clean Bill)",
    from: "sharma@sharmasteels.com",
    subject: "Tax Invoice INV-2026-001 — Material Delivery",
    body: "Dear Apex Team, please find attached invoice copy for steel coil delivery. Kindly clear payment.",
    fixture: "clean_intrastate"
  },
  {
    name: "Reliable Transport (Interstate IGST)",
    from: "billing@reliabletransport.in",
    subject: "Transport Freight Invoice INV-2026-002",
    body: "Attaching inter-state freight transport bill for September.",
    fixture: "clean_interstate"
  },
  {
    name: "Precision Tools (Math Error Bill)",
    from: "accounts@precisiontools.com",
    subject: "Invoice INV-2026-003 for Machine Bits",
    body: "Please clear the attached invoice for machine tool supplies.",
    fixture: "math_error"
  },
  {
    name: "Delta Fasteners (Rule 37 Aged Bill)",
    from: "sales@deltafasteners.com",
    subject: "Pending Bill Copy INV-2026-009",
    body: "Sharing invoice copy as requested for old pending supplies.",
    fixture: "old_invoice_rule37"
  }
];

export default function AutomationPage() {
  const [status, setStatus] = useState<AutomationStatus | null>(null);
  const [emails, setEmails] = useState<{ inbox: EmailItem[]; sent: EmailItem[]; unread_count: number }>({
    inbox: [],
    sent: [],
    unread_count: 0
  });
  const [triggeringCycle, setTriggeringCycle] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [emailTab, setEmailTab] = useState<"inbox" | "sent" | "simulate" | "config">("simulate");

  // Email simulation form
  const [simFrom, setSimFrom] = useState("sharma@sharmasteels.com");
  const [simSubject, setSimSubject] = useState("Tax Invoice INV-2026-001 — Material Delivery");
  const [simBody, setSimBody] = useState("Dear Apex Team, please find attached invoice copy for steel coil delivery. Kindly clear payment.");
  const [simFixture, setSimFixture] = useState("clean_intrastate");
  const [deliveringEmail, setDeliveringEmail] = useState(false);

  // Live Gmail Config
  const [gmailMode, setGmailMode] = useState<"prototype" | "live_gmail">("prototype");
  const [gmailUser, setGmailUser] = useState("");
  const [gmailPass, setGmailPass] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);

  const [notification, setNotification] = useState<{ title: string; desc: string; type: "success" | "warning" | "info" } | null>(null);

  const terminalRef = useRef<HTMLDivElement>(null);

  // Fetch status & emails
  const fetchStatusAndEmails = useCallback(async () => {
    try {
      const [statusData, emailData] = await Promise.all([
        apiFetch<AutomationStatus>("/automation/status"),
        apiFetch<{ inbox: EmailItem[]; sent: EmailItem[]; unread_count: number }>("/automation/emails")
      ]);
      setStatus(statusData);
      setEmails(emailData);
      setGmailMode((statusData.email_mode as "prototype" | "live_gmail") || "prototype");
      if (statusData.email_username && statusData.email_username !== "invoices@apexautoparts.com") {
        setGmailUser(statusData.email_username);
      }
    } catch (err) {
      console.error("Failed to load automation data:", err);
    }
  }, []);

  // Poll status every 3 seconds for live streaming
  useEffect(() => {
    fetchStatusAndEmails();
    const timer = setInterval(() => {
      fetchStatusAndEmails();
    }, 3000);
    return () => clearInterval(timer);
  }, [fetchStatusAndEmails]);

  // Toggle agent running state
  const handleToggleAgent = async () => {
    if (!status) return;
    setToggling(true);
    try {
      const newEnabled = !status.is_running;
      await apiFetch("/automation/toggle", {
        method: "POST",
        body: JSON.stringify({ enabled: newEnabled })
      });
      await fetchStatusAndEmails();
      setNotification({
        title: newEnabled ? "Autonomous Agent Resumed" : "Autonomous Agent Paused",
        desc: newEnabled
          ? `Agent is now actively watching Gmail inbox & channels every ${status.interval_seconds}s.`
          : "Autonomous cycles paused. You can trigger on-demand runs anytime.",
        type: newEnabled ? "success" : "info"
      });
    } catch (err: unknown) {
      alert("Failed to toggle agent: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setToggling(false);
    }
  };

  // Change interval
  const handleIntervalChange = async (newSec: number) => {
    try {
      await apiFetch("/automation/interval", {
        method: "POST",
        body: JSON.stringify({ interval_seconds: newSec })
      });
      await fetchStatusAndEmails();
    } catch (err: unknown) {
      alert("Failed to update interval: " + (err instanceof Error ? err.message : String(err)));
    }
  };

  // Trigger cycle now
  const handleTriggerCycleNow = async () => {
    setTriggeringCycle(true);
    setNotification(null);
    try {
      const res = await apiFetch<{
        status: string;
        summary: { cycle_number: number; processed_bills: number; alerts: number };
      }>("/automation/run-now", { method: "POST" });
      await fetchStatusAndEmails();
      setNotification({
        title: `Autonomous Cycle #${res.summary.cycle_number} Completed`,
        desc: `Scanned inbox: ${res.summary.processed_bills} bill(s) processed & replied to, ${res.summary.alerts} risk alert(s) evaluated.`,
        type: "success"
      });
    } catch (err: unknown) {
      alert("Failed running cycle: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setTriggeringCycle(false);
    }
  };

  // Deliver simulated incoming email to watched inbox
  const handleDeliverEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setDeliveringEmail(true);
    setNotification(null);
    try {
      await apiFetch("/automation/email/simulate-incoming", {
        method: "POST",
        body: JSON.stringify({
          from_addr: simFrom,
          subject: simSubject,
          body: simBody,
          fixture_name: simFixture
        })
      });
      await fetchStatusAndEmails();
      setNotification({
        title: "Invoice Email Delivered to Watched Inbox",
        desc: `Email from '${simFrom}' landed in inbox. The Autonomous Agent will pick it up automatically on its next background cycle!`,
        type: "success"
      });
      setEmailTab("inbox");
    } catch (err: unknown) {
      alert("Failed delivering email: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setDeliveringEmail(false);
    }
  };

  // Save live Gmail configuration
  const handleSaveGmailConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConfig(true);
    try {
      await apiFetch("/automation/email/configure", {
        method: "POST",
        body: JSON.stringify({
          mode: gmailMode,
          username: gmailUser,
          password: gmailPass,
          imap_server: "imap.gmail.com",
          smtp_server: "smtp.gmail.com"
        })
      });
      await fetchStatusAndEmails();
      setNotification({
        title: "Email Settings Updated",
        desc: `Agent is now configured in '${gmailMode}' mode.`,
        type: "success"
      });
    } catch (err: unknown) {
      alert("Failed saving configuration: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSavingConfig(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight flex items-center space-x-2">
            <Bot className="w-6 h-6 text-primary" />
            <span>Autonomous AI Agent Center</span>
          </h1>
          <p className="text-sm text-muted">
            Continuous background AI worker monitoring Gmail & WhatsApp inboxes, ingesting vendor bills, verifying GST math, and auto-replying.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleToggleAgent}
            disabled={toggling}
            className={`flex items-center space-x-1.5 px-3.5 py-2 rounded-md text-xs font-semibold shadow-xs transition-colors ${
              status?.is_running
                ? "bg-warning-light text-warning hover:bg-warning-light/80 border border-warning/40"
                : "bg-success text-white hover:bg-success/90"
            }`}
          >
            {status?.is_running ? (
              <>
                <Pause className="w-3.5 h-3.5" />
                <span>Pause Agent</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                <span>Resume Autonomous Agent</span>
              </>
            )}
          </button>

          <button
            onClick={handleTriggerCycleNow}
            disabled={triggeringCycle}
            className="flex items-center space-x-1.5 px-3.5 py-2 bg-primary hover:bg-primary-hover text-white rounded-md text-xs font-semibold shadow-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${triggeringCycle ? "animate-spin" : ""}`} />
            <span>Trigger Agent Cycle Now</span>
          </button>
        </div>
      </div>

      {/* Notification Banner */}
      {notification && (
        <div
          className={`p-4 rounded-lg border text-sm flex items-start justify-between ${
            notification.type === "success"
              ? "bg-success-light/40 border-success/30 text-ink"
              : notification.type === "warning"
              ? "bg-warning-light/40 border-warning/30 text-ink"
              : "bg-primary-light/40 border-primary/30 text-ink"
          }`}
        >
          <div className="flex items-start space-x-3">
            {notification.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-success shrink-0 mt-0.5" />
            ) : notification.type === "warning" ? (
              <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
            ) : (
              <Sparkles className="w-5 h-5 text-primary shrink-0 mt-0.5" />
            )}
            <div>
              <div className="font-semibold text-ink">{notification.title}</div>
              <div className="text-xs text-muted mt-0.5">{notification.desc}</div>
            </div>
          </div>
          <button onClick={() => setNotification(null)} className="text-muted hover:text-ink text-xs ml-4">
            ✕
          </button>
        </div>
      )}

      {/* Autonomous Status Hero Card */}
      <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/80 pb-4">
          <div className="flex items-center space-x-3">
            <div className="relative">
              <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                <Bot className="w-5 h-5 text-primary" />
              </div>
              {status?.is_running && (
                <span className="absolute top-0 right-0 w-3 h-3 rounded-full bg-success ring-2 ring-surface animate-pulse" />
              )}
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-ink text-base">Autonomous AI Worker</span>
                <span
                  className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                    status?.is_running
                      ? "bg-success-light text-success"
                      : "bg-border text-muted"
                  }`}
                >
                  {status?.is_running ? "RUNNING CONTINUOUSLY" : "PAUSED"}
                </span>
              </div>
              <div className="text-xs text-muted flex items-center space-x-2 mt-0.5">
                <span>Watching: <strong>{status?.email_username || "invoices@apexautoparts.com"}</strong></span>
                <span>•</span>
                <span>Mode: <strong className="capitalize">{status?.email_mode}</strong></span>
              </div>
            </div>
          </div>

          {/* Polling Interval Selector */}
          <div className="flex items-center space-x-2 text-xs">
            <span className="text-muted font-medium">Polling Cadence:</span>
            <div className="flex items-center bg-background border border-border rounded-md p-0.5">
              {[
                { label: "10s", val: 10 },
                { label: "30s", val: 30 },
                { label: "60s", val: 60 }
              ].map((opt) => (
                <button
                  key={opt.val}
                  onClick={() => handleIntervalChange(opt.val)}
                  className={`px-2 py-1 text-[11px] font-medium rounded transition-colors ${
                    status?.interval_seconds === opt.val
                      ? "bg-primary text-white"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Real-Time Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4">
          <div>
            <div className="text-[11px] font-medium text-muted uppercase tracking-wider">Completed Cycles</div>
            <div className="text-2xl font-bold text-ink mt-0.5">{status?.cycle_count || 0}</div>
            <div className="text-[10px] text-muted">Periodic sweeps executed</div>
          </div>

          <div>
            <div className="text-[11px] font-medium text-muted uppercase tracking-wider">Auto-Ingested Bills</div>
            <div className="text-2xl font-bold text-success mt-0.5">{status?.invoices_processed_count || 0}</div>
            <div className="text-[10px] text-muted">Parsed without manual clicks</div>
          </div>

          <div>
            <div className="text-[11px] font-medium text-muted uppercase tracking-wider">Unread Email Bills</div>
            <div className="text-2xl font-bold text-primary mt-0.5">{status?.email_unread_count || 0}</div>
            <div className="text-[10px] text-muted">In monitored inbox</div>
          </div>

          <div>
            <div className="text-[11px] font-medium text-muted uppercase tracking-wider">Statutory Risk Alerts</div>
            <div className="text-2xl font-bold text-ink mt-0.5">{status?.alerts_generated_count || 0}</div>
            <div className="text-[10px] text-muted">Rule 37 aging sweeps</div>
          </div>
        </div>
      </div>

      {/* Main Grid: Left = Monitored Email Channel, Right = Live Agent Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (6 cols): Email Watcher & Ingestion Simulator */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-surface rounded-xl border border-border shadow-sm overflow-hidden flex flex-col h-[600px]">
            {/* Tab header */}
            <div className="flex border-b border-border bg-background/50 p-1">
              <button
                onClick={() => setEmailTab("simulate")}
                className={`flex-1 py-2 text-xs font-semibold rounded-md transition-colors flex items-center justify-center space-x-1.5 ${
                  emailTab === "simulate"
                    ? "bg-surface text-primary shadow-xs border border-border/80"
                    : "text-muted hover:text-ink"
                }`}
              >
                <Zap className="w-3.5 h-3.5" />
                <span>Deliver Test Email</span>
              </button>

              <button
                onClick={() => setEmailTab("inbox")}
                className={`flex-1 py-2 text-xs font-semibold rounded-md transition-colors flex items-center justify-center space-x-1.5 ${
                  emailTab === "inbox"
                    ? "bg-surface text-primary shadow-xs border border-border/80"
                    : "text-muted hover:text-ink"
                }`}
              >
                <Inbox className="w-3.5 h-3.5" />
                <span>Inbox ({emails.inbox.length})</span>
              </button>

              <button
                onClick={() => setEmailTab("sent")}
                className={`flex-1 py-2 text-xs font-semibold rounded-md transition-colors flex items-center justify-center space-x-1.5 ${
                  emailTab === "sent"
                    ? "bg-surface text-primary shadow-xs border border-border/80"
                    : "text-muted hover:text-ink"
                }`}
              >
                <Send className="w-3.5 h-3.5" />
                <span>Agent Replies ({emails.sent.length})</span>
              </button>

              <button
                onClick={() => setEmailTab("config")}
                className={`flex-1 py-2 text-xs font-semibold rounded-md transition-colors flex items-center justify-center space-x-1.5 ${
                  emailTab === "config"
                    ? "bg-surface text-primary shadow-xs border border-border/80"
                    : "text-muted hover:text-ink"
                }`}
              >
                <SettingsIcon className="w-3.5 h-3.5" />
                <span>Gmail Setup</span>
              </button>
            </div>

            {/* Tab: Deliver Test Email */}
            {emailTab === "simulate" && (
              <form onSubmit={handleDeliverEmail} className="p-5 space-y-4 overflow-y-auto flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-ink uppercase tracking-wider flex items-center space-x-1.5">
                    <Mail className="w-4 h-4 text-primary" />
                    <span>Send Incoming Invoice Email</span>
                  </span>
                  <span className="text-[10px] bg-primary-light text-primary font-semibold px-2 py-0.5 rounded-full">
                    Auto-Watcher Watches This
                  </span>
                </div>

                <p className="text-xs text-muted leading-relaxed">
                  Drop an incoming invoice email into the monitored mailbox. The Autonomous AI Agent will automatically detect it, parse the attachment, and send a reply without clicking any upload buttons!
                </p>

                {/* Quick Templates */}
                <div>
                  <span className="block text-[11px] font-semibold text-ink mb-1.5">
                    Quick Sample Suppliers:
                  </span>
                  <div className="grid grid-cols-2 gap-2">
                    {SAMPLE_SUPPLIER_EMAILS.map((tpl) => (
                      <button
                        key={tpl.name}
                        type="button"
                        onClick={() => {
                          setSimFrom(tpl.from);
                          setSimSubject(tpl.subject);
                          setSimBody(tpl.body);
                          setSimFixture(tpl.fixture);
                        }}
                        className="text-left p-2 rounded border border-border bg-background hover:bg-border/30 text-xs transition-colors"
                      >
                        <div className="font-semibold text-ink truncate text-[11px]">{tpl.name}</div>
                        <div className="text-[10px] text-muted truncate">{tpl.from}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    From (Supplier Email Address)
                  </label>
                  <input
                    type="email"
                    value={simFrom}
                    onChange={(e) => setSimFrom(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink font-mono focus:outline-hidden focus:ring-1 focus:ring-primary"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Email Subject
                  </label>
                  <input
                    type="text"
                    value={simSubject}
                    onChange={(e) => setSimSubject(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Attached Bill / Fixture
                  </label>
                  <select
                    value={simFixture}
                    onChange={(e) => setSimFixture(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                  >
                    <option value="clean_intrastate">Sharma Steels — Clean Intra-State (₹1,18,000)</option>
                    <option value="clean_interstate">Reliable Transport — Interstate IGST (₹41,300)</option>
                    <option value="freight_roundoff_invoice">Real-World Multi-Item + Freight (₹1,56,878)</option>
                    <option value="math_error">Math Discrepancy Bill (Auto-Blocked)</option>
                    <option value="old_invoice_rule37">Old Bill (180+ Days, Rule 37 Risk)</option>
                  </select>
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={deliveringEmail}
                    className="w-full py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-md shadow-sm transition-colors flex items-center justify-center space-x-2 disabled:opacity-50"
                  >
                    {deliveringEmail ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Delivering Email...</span>
                      </>
                    ) : (
                      <>
                        <Mail className="w-3.5 h-3.5" />
                        <span>Deliver Invoice Email to Monitored Inbox</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}

            {/* Tab: Monitored Inbox */}
            {emailTab === "inbox" && (
              <div className="p-4 overflow-y-auto flex-1 space-y-3">
                {emails.inbox.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-muted text-center space-y-2 py-12">
                    <Mail className="w-8 h-8 text-border" />
                    <div className="text-sm font-semibold text-ink">Monitored Inbox is Empty</div>
                    <p className="text-xs text-muted max-w-xs">
                      Deliver a sample invoice email or configure real Gmail to start watching.
                    </p>
                  </div>
                ) : (
                  emails.inbox.map((eml) => (
                    <div
                      key={eml.id}
                      className={`p-3.5 rounded-lg border text-xs space-y-1.5 transition-colors ${
                        eml.is_read
                          ? "bg-background/40 border-border"
                          : "bg-primary-light/30 border-primary/40 shadow-xs"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-ink font-mono">{eml.from_addr}</span>
                        <span className="text-[10px] text-muted">
                          {eml.received_at ? new Date(eml.received_at).toLocaleTimeString() : ""}
                        </span>
                      </div>
                      <div className="font-medium text-ink">{eml.subject}</div>
                      <p className="text-muted text-[11px] line-clamp-2">{eml.body}</p>

                      {eml.attachments && eml.attachments.length > 0 && (
                        <div className="pt-1 flex items-center justify-between text-[11px]">
                          <span className="flex items-center space-x-1 text-primary font-semibold">
                            <FileText className="w-3.5 h-3.5" />
                            <span>{eml.attachments[0].filename}</span>
                          </span>
                          {eml.is_read ? (
                            <span className="bg-success-light text-success font-semibold px-2 py-0.5 rounded text-[10px] flex items-center space-x-1">
                              <Check className="w-3 h-3" />
                              <span>Auto-Processed & Cleared</span>
                            </span>
                          ) : (
                            <span className="bg-warning-light text-warning font-semibold px-2 py-0.5 rounded text-[10px]">
                              Waiting in Queue
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab: Agent Sent Outbox */}
            {emailTab === "sent" && (
              <div className="p-4 overflow-y-auto flex-1 space-y-3">
                {emails.sent.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-muted text-center space-y-2 py-12">
                    <Send className="w-8 h-8 text-border" />
                    <div className="text-sm font-semibold text-ink">No Outbound Replies Sent Yet</div>
                    <p className="text-xs text-muted max-w-xs">
                      When the agent autonomously ingests a bill, it automatically sends confirmation replies here.
                    </p>
                  </div>
                ) : (
                  emails.sent.map((eml) => (
                    <div key={eml.id} className="p-3.5 rounded-lg border border-border bg-surface text-xs space-y-1.5 shadow-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="bg-primary-light text-primary font-semibold px-1.5 py-0.5 rounded text-[10px]">
                            Auto-Reply
                          </span>
                          <span className="font-semibold text-ink font-mono text-[11px]">To: {eml.to_addr}</span>
                        </div>
                        <span className="text-[10px] text-muted">
                          {eml.sent_at ? new Date(eml.sent_at).toLocaleTimeString() : ""}
                        </span>
                      </div>
                      <div className="font-medium text-ink">{eml.subject}</div>
                      <pre className="text-[11px] text-muted whitespace-pre-wrap font-sans bg-background/50 p-2 rounded border border-border/50">
                        {eml.body}
                      </pre>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab: Gmail Config */}
            {emailTab === "config" && (
              <form onSubmit={handleSaveGmailConfig} className="p-5 space-y-4 overflow-y-auto flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-ink uppercase tracking-wider flex items-center space-x-1.5">
                    <SettingsIcon className="w-4 h-4 text-primary" />
                    <span>Real Gmail & IMAP Settings</span>
                  </span>
                  <span className="text-[10px] bg-border text-muted font-semibold px-2 py-0.5 rounded-full">
                    Optional Production Bridge
                  </span>
                </div>

                <p className="text-xs text-muted leading-relaxed">
                  Switch from prototype mode to live Gmail monitoring. Generate a 16-character <strong>App Password</strong> in Google Account Security to allow the agent to fetch bills directly from Gmail.
                </p>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Operating Mode
                  </label>
                  <select
                    value={gmailMode}
                    onChange={(e) => setGmailMode(e.target.value as "prototype" | "live_gmail")}
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink focus:outline-hidden focus:ring-1 focus:ring-primary"
                  >
                    <option value="prototype">Prototype / Local Drop-Box (Zero Credentials Required)</option>
                    <option value="live_gmail">Live Gmail IMAP / SMTP (Real Email Watching)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Gmail Address
                  </label>
                  <input
                    type="email"
                    value={gmailUser}
                    onChange={(e) => setGmailUser(e.target.value)}
                    placeholder="invoices.firm@gmail.com"
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink font-mono focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Gmail App Password (16 characters)
                  </label>
                  <input
                    type="password"
                    value={gmailPass}
                    onChange={(e) => setGmailPass(e.target.value)}
                    placeholder="••••••••••••••••"
                    className="w-full px-3 py-2 text-xs border border-border rounded-md bg-background text-ink font-mono focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                  <p className="text-[10px] text-muted mt-1">
                    Generated via Google Account $\rightarrow$ Security $\rightarrow$ 2-Step Verification $\rightarrow$ App Passwords.
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={savingConfig}
                    className="w-full py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-md shadow-sm transition-colors disabled:opacity-50"
                  >
                    {savingConfig ? "Saving..." : "Save Email Monitoring Settings"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>

        {/* Right Column (6 cols): Live Agent Autonomous Terminal / Activity Feed */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-surface rounded-xl border border-border shadow-sm flex flex-col h-[600px] overflow-hidden">
            {/* Terminal Header */}
            <div className="p-3.5 border-b border-border bg-background/50 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Terminal className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm text-ink">Autonomous Agent Terminal</span>
                <span className="text-[10px] bg-success-light text-success font-semibold px-2 py-0.5 rounded-full flex items-center space-x-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-success animate-ping" />
                  <span>LIVE FEED</span>
                </span>
              </div>
              <span className="text-[11px] text-muted font-mono">
                Updates every 3s
              </span>
            </div>

            {/* Terminal Body */}
            <div
              ref={terminalRef}
              className="flex-1 p-4 overflow-y-auto space-y-2.5 bg-[#0D1117] font-mono text-[11px] leading-relaxed text-slate-300"
            >
              {status?.logs && status.logs.length > 0 ? (
                status.logs.map((log) => {
                  const isSuccess = log.level === "SUCCESS";
                  const isWarn = log.level === "WARNING";
                  const isErr = log.level === "ERROR";

                  return (
                    <div key={log.id} className="flex items-start space-x-2 hover:bg-slate-800/40 p-1 rounded">
                      <span className="text-slate-500 shrink-0 select-none">
                        {new Date(log.timestamp).toLocaleTimeString([], { hour12: false })}
                      </span>
                      <span
                        className={`font-bold shrink-0 px-1.5 py-0.2 rounded text-[9px] uppercase ${
                          isSuccess
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                            : isWarn
                            ? "bg-amber-950 text-amber-400 border border-amber-800"
                            : isErr
                            ? "bg-rose-950 text-rose-400 border border-rose-800"
                            : "bg-slate-800 text-sky-400 border border-slate-700"
                        }`}
                      >
                        {log.event}
                      </span>
                      <span
                        className={`flex-1 break-words ${
                          isSuccess
                            ? "text-emerald-300"
                            : isWarn
                            ? "text-amber-300"
                            : isErr
                            ? "text-rose-300"
                            : "text-slate-300"
                        }`}
                      >
                        {log.message}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="text-slate-500 text-center py-12">
                  No autonomous log entries yet. Click &quot;Trigger Agent Cycle Now&quot; to initiate a run.
                </div>
              )}
            </div>

            {/* Terminal Footer */}
            <div className="p-3 border-t border-border bg-background/50 flex items-center justify-between text-xs text-muted">
              <span className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-success"></span>
                <span className="text-[11px]">Heartbeat Active</span>
              </span>
              <span className="text-[11px]">
                Last sweep: {status?.last_run ? new Date(status.last_run).toLocaleTimeString() : "Never"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
