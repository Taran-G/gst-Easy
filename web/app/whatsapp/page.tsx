"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { apiFetch, downloadBlob, getBusinessWhatsAppPhone, setBusinessWhatsAppPhone } from "@/lib/api";
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
  ExternalLink,
  Copy,
  Check,
  Edit2,
  Sun,
  Moon
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

const KNOWN_SUPPLIERS = [
  { name: "Sharma Steels", phone: "+919876543210", gstin: "06AABCS1234S1Z4" },
  { name: "ABC Traders", phone: "+919876543211", gstin: "07AABCA5678A1ZX" },
  { name: "Delta Fasteners", phone: "+919876543212", gstin: "06AABCD9012D1Z6" },
];

const MESSAGE_TEMPLATES = [
  {
    id: "missing_2b",
    badge: "Missing in 2B",
    badgeColor: "bg-danger-light text-danger border-danger/30",
    title: "Bill Missing in GSTR-2B (Urgent Filing Request)",
    desc: "Ask supplier to file GSTR-1 immediately so you can claim tax credit.",
    textEn: "Dear Supplier,\n\nYour tax invoice is currently NOT reflecting in our government GSTR-2B statement. Under GST rules, we cannot claim Input Tax Credit until you file your GSTR-1.\n\nKindly file your return or amend the invoice so we can release your pending payment.\n\nThank you,\nAccounts Department",
    textHi: "नमस्ते जी,\n\nआपका बिल हमारे सरकारी GSTR-2B पोर्टल पर नहीं दिख रहा है। GST नियमों के तहत, जब तक आप GSTR-1 फ़ाइल नहीं करेंगे, हमें टैक्स इनपुट नहीं मिलेगा।\n\nकृपया अपना रिटर्न जल्दी फ़ाइल करें ताकि आपका पेमेंट क्लियर हो सके।\n\nधन्यवाद,\nअकाउंट्स विभाग",
    textHinglish: "Dear Supplier,\n\nAapka invoice hamare GSTR-2B portal par show nahi ho raha hai. GST rules ke mutabik jab tak aap GSTR-1 file nahi karenge, hum ITC claim nahi kar sakte.\n\nKindly jaldi se return file karein taaki payment release ho sake.\n\nThank you,\nAccounts Department",
  },
  {
    id: "payment_hold",
    badge: "Tax Hold",
    badgeColor: "bg-warning-light text-warning border-warning/30",
    title: "Tax Portion On Hold (Base Payment Released)",
    desc: "Inform supplier that basic amount is paid, but GST tax is held until 2B reflection.",
    textEn: "Dear Supplier,\n\nWe have approved and processed your base invoice amount. However, the GST tax portion is placed on temporary hold until the invoice reflects in our monthly GSTR-2B.\n\nOnce it appears on the GST portal, the remaining tax amount will be immediately released.\n\nThank you,\nAccounts Department",
    textHi: "नमस्ते जी,\n\nआपके बिल का मूल भुगतान (Base Amount) पास कर दिया गया है। लेकिन GST टैक्स का हिस्सा तब तक होल्ड पर रहेगा जब तक बिल GSTR-2B में नहीं दिखता।\n\nजैसे ही पोर्टल पर दिखेगा, टैक्स का भुगतान भी तुरंत जारी कर दिया जाएगा।\n\nधन्यवाद,\nअकाउंट्स विभाग",
    textHinglish: "Dear Supplier,\n\nAapke bill ka base amount humne release kar diya hai. Lekin GST tax ka amount temporary hold par hai jab tak bill GSTR-2B me reflect nahi hota.\n\nPortal par aate hi baaki payment bhi release ho jayegi.\n\nThank you,\nAccounts Department",
  },
  {
    id: "rule_37",
    badge: "180-Day Rule 37",
    badgeColor: "bg-danger-light text-danger border-danger/30",
    title: "180-Day Payment Cutoff Notice (Rule 37 Warning)",
    desc: "Warn supplier of statutory 180-day deadline to avoid GST tax reversal.",
    textEn: "Urgent GST Compliance Notice:\n\nUnder GST Rule 37, invoices unpaid beyond 180 days require statutory tax reversal with 18% penal interest. Your invoice is approaching this statutory deadline.\n\nPlease reconcile the outstanding balance immediately to avoid audit penalties.\n\nThank you,\nAccounts Department",
    textHi: "ज़रूरी GST सूचना:\n\nGST Rule 37 के अनुसार 180 दिन से पुराने अनपेड बिलों का टैक्स 18% ब्याज के साथ रिवर्स करना पड़ता है। आपका बिल इस समय सीमा के करीब पहुंच चुका है।\n\nकृपया तुरंत संपर्क करके हिसाब क्लियर करवाएं।\n\nधन्यवाद,\nअकाउंट्स विभाग",
    textHinglish: "Urgent Notice:\n\nGST Rule 37 ke mutabik 180 days ke baad unpaid bills ka tax reverse karna padta hai with 18% interest. Aapka invoice 180 days ke limit ke paas pahunch raha hai.\n\nKripya turant balance reconcile karwayein.\n\nThank you,\nAccounts Department",
  },
  {
    id: "bill_approved",
    badge: "Bill Approved",
    badgeColor: "bg-success-light text-success border-success/30",
    title: "Bill Received & Approved Confirmation",
    desc: "Confirm to supplier that their invoice was checked and approved.",
    textEn: "Dear Supplier,\n\nWe have received and verified your tax invoice. All math, GSTIN, and tax amounts have been approved and posted to our accounting records.\n\nPayment will be processed as per credit terms.\n\nThank you,\nAccounts Department",
    textHi: "नमस्ते जी,\n\nआपका बिल हमें प्राप्त हो गया है और उसकी जांच पूरी हो गई है। टैक्स और बिल की सभी डिटेल्स सही पाई गई हैं और अकाउंट्स में दर्ज कर ली गई हैं।\n\nपेमेंट समय पर कर दिया जाएगा।\n\nधन्यवाद,\nअकाउंट्स विभाग",
    textHinglish: "Dear Supplier,\n\nAapka tax invoice verify ho gaya hai aur hamare accounts me pass ho chuka hai. Credit terms ke hisaab se payment schedule ho jayegi.\n\nThank you,\nAccounts Department",
  },
];

export default function WhatsAppHubPage() {
  const [messages, setMessages] = useState<WhatsAppMessage[]>([]);
  const [stats, setStats] = useState<MessageStats>({ total: 0, inbound: 0, outbound: 0, invoices_ingested: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Form State for Sending WhatsApp
  const [selectedSupplierPhone, setSelectedSupplierPhone] = useState("+919876543210");
  const [customPhone, setCustomPhone] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("missing_2b");
  const [language, setLanguage] = useState<"en" | "hi" | "hinglish">("en");
  const [customText, setCustomText] = useState("");
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);

  // Inbound Simulation state
  const [simulatingUpload, setSimulatingUpload] = useState(false);
  const [copiedNumber, setCopiedNumber] = useState(false);
  const [banner, setBanner] = useState<{ title: string; desc: string; type: "success" | "warning" | "info" } | null>(null);

  // Business Phone Number State (User's own number)
  const [businessPhone, setBusinessPhone] = useState("+91 98765 43210");
  const [isEditingPhone, setIsEditingPhone] = useState(false);
  const [tempPhoneInput, setTempPhoneInput] = useState("+91 98765 43210");

  // Message Preview Theme: "light" vs "dark"
  const [previewTheme, setPreviewTheme] = useState<"light" | "dark">("light");

  const fileInputRef = useRef<HTMLInputElement>(null);

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
    const current = getBusinessWhatsAppPhone();
    setBusinessPhone(current);
    setTempPhoneInput(current);
    if (current && current.replace(/[^0-9]/g, "") !== "919876543210") {
      setSelectedSupplierPhone(current);
    }

    const handlePhoneChange = () => {
      const updated = getBusinessWhatsAppPhone();
      setBusinessPhone(updated);
      setTempPhoneInput(updated);
      if (updated && updated.replace(/[^0-9]/g, "") !== "919876543210") {
        setSelectedSupplierPhone(updated);
      }
    };
    window.addEventListener("whatsAppPhoneChanged", handlePhoneChange);
    return () => window.removeEventListener("whatsAppPhoneChanged", handlePhoneChange);
  }, [fetchMessages]);

  const handleSaveBusinessPhone = () => {
    const clean = tempPhoneInput.trim();
    if (!clean) return;
    setBusinessWhatsAppPhone(clean);
    setBusinessPhone(clean);
    setSelectedSupplierPhone(clean);
    setIsEditingPhone(false);
    setBanner({
      title: "WhatsApp Number Saved!",
      desc: `Your receiving number is now saved as ${clean}. Buttons and test chats will now use this number.`,
      type: "success",
    });
  };

  const activeTemplate = MESSAGE_TEMPLATES.find((t) => t.id === selectedTemplateId) || MESSAGE_TEMPLATES[0];

  const currentMessageText = isCustomMode
    ? customText
    : language === "hi"
    ? activeTemplate.textHi
    : language === "hinglish"
    ? activeTemplate.textHinglish
    : activeTemplate.textEn;

  const targetPhoneNumber = customPhone.trim() ? customPhone.trim() : selectedSupplierPhone;

  // Open direct chat with user's receiving business number
  const handleOpenChatWithMyNumber = () => {
    const cleanDigits = businessPhone.replace(/[^0-9]/g, "");
    if (!cleanDigits || cleanDigits === "919876543210" || cleanDigits.length < 10) {
      alert("Please update the placeholder number (+91 98765 43210) to your real WhatsApp number first by clicking 'Change Number'.");
      setIsEditingPhone(true);
      return;
    }
    const prefilled = encodeURIComponent("Hello! Sending our purchase tax invoice for accounting & GST entry.");
    window.open(`https://wa.me/${cleanDigits}?text=${prefilled}`, "_blank");
  };

  // 1. Send via Backend API
  const handleSendViaApi = async () => {
    let phoneToSend = targetPhoneNumber;
    const cleanDigits = phoneToSend.replace(/[^0-9]/g, "");
    if (!cleanDigits || cleanDigits === "919876543210" || cleanDigits.length < 10) {
      const fallback = businessPhone.replace(/[^0-9]/g, "") !== "919876543210" ? businessPhone : "";
      const entered = prompt(
        "The current recipient number is a dummy placeholder (+91 98765 43210).\n\nPlease enter the recipient's real 10-digit WhatsApp number:",
        fallback
      );
      if (!entered || !entered.trim()) return;
      phoneToSend = entered.trim();
      setCustomPhone(phoneToSend);
    }

    setSendingMessage(true);
    setBanner(null);

    try {
      await apiFetch("/whatsapp/send", {
        method: "POST",
        body: JSON.stringify({
          to_phone: phoneToSend,
          text: currentMessageText,
        }),
      });

      setBanner({
        title: "WhatsApp Message Sent!",
        desc: `Message delivered to ${phoneToSend} and recorded in the audit log.`,
        type: "success",
      });

      await fetchMessages();
    } catch (err: unknown) {
      alert("Failed to send message: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSendingMessage(false);
    }
  };

  // 2. Open directly in WhatsApp Web
  const handleOpenWhatsAppWeb = () => {
    let phoneToUse = targetPhoneNumber;
    let cleanDigits = phoneToUse.replace(/[^0-9]/g, "");

    // If still the dummy number or invalid, prompt user or use their saved business phone
    if (!cleanDigits || cleanDigits === "919876543210" || cleanDigits.length < 10) {
      const fallback = businessPhone.replace(/[^0-9]/g, "") !== "919876543210" ? businessPhone : "";
      const entered = prompt(
        "The selected number (+91 98765 43210) is a sample dummy number that does not exist.\n\nPlease enter the recipient's real 10-digit WhatsApp number (or your own number for testing):",
        fallback
      );
      if (!entered || !entered.trim()) return;
      const cleanEntered = entered.trim().replace(/[^0-9]/g, "");
      if (cleanEntered.length < 10) {
        alert("Please enter a valid 10-digit phone number.");
        return;
      }
      setCustomPhone(entered.trim());
      phoneToUse = entered.trim();
      cleanDigits = cleanEntered;
    }

    const encoded = encodeURIComponent(currentMessageText);
    const url = `https://wa.me/${cleanDigits}?text=${encoded}`;
    window.open(url, "_blank");
  };

  // 3. Test receiving a bill via WhatsApp upload
  const handleTestReceiveBill = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSimulatingUpload(true);
    setBanner(null);

    const formData = new FormData();
    formData.append("phone", targetPhoneNumber);
    formData.append("caption", "Here is our tax invoice for material supplied.");
    formData.append("file", file);

    try {
      const res = await apiFetch<{
        status: string;
        state: string;
        invoice: { invoice_number: string; total_amount: number };
      }>("/whatsapp/simulate/bill", {
        method: "POST",
        body: formData,
      });

      setBanner({
        title: "Bill Received via WhatsApp!",
        desc: `AI extracted invoice #${res.invoice?.invoice_number || "New"} (₹${Number(
          res.invoice?.total_amount || 0
        ).toLocaleString("en-IN")}) and sent back an auto-confirmation. Check your Bills Inbox.`,
        type: res.state === "BLOCKED" ? "warning" : "success",
      });

      await fetchMessages();
    } catch (err: unknown) {
      alert("Upload failed: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSimulatingUpload(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleCopyNumber = () => {
    navigator.clipboard.writeText(businessPhone);
    setCopiedNumber(true);
    setTimeout(() => setCopiedNumber(false), 2000);
  };

  const handleExportCsv = async () => {
    try {
      await downloadBlob("/whatsapp/export", "whatsapp_communications_audit.csv");
      setBanner({
        title: "Export Complete",
        desc: "WhatsApp message history downloaded as CSV file.",
        type: "success",
      });
    } catch (err: unknown) {
      alert("Failed to export: " + (err instanceof Error ? err.message : String(err)));
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Title & Top Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink tracking-tight flex items-center space-x-2">
            <MessageSquare className="w-6 h-6 text-success" />
            <span>WhatsApp Center</span>
          </h1>
          <p className="text-sm text-muted">
            Send payment &amp; tax reminders to suppliers, or receive bill photos directly on WhatsApp.
          </p>
          <div className="flex items-center space-x-2 pt-2 text-xs">
            <span className="px-2.5 py-1 bg-surface border border-border rounded-lg text-ink font-semibold shadow-2xs">
              <strong className="text-success">{stats.invoices_ingested}</strong> Bills Received
            </span>
            <span className="px-2.5 py-1 bg-surface border border-border rounded-lg text-ink font-semibold shadow-2xs">
              <strong className="text-primary">{stats.outbound}</strong> Reminders Sent
            </span>
            <span className="px-2.5 py-1 bg-surface border border-border rounded-lg text-ink font-semibold shadow-2xs">
              <strong className="text-ink">{stats.total}</strong> Messages Logged
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => fetchMessages(true)}
            disabled={refreshing}
            className="flex items-center space-x-1.5 px-3 py-1.5 border border-border rounded-lg text-xs font-semibold text-ink hover:bg-background transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-primary" : "text-muted"}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={handleExportCsv}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-surface border border-border hover:bg-background text-ink rounded-lg text-xs font-semibold shadow-xs transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-primary" />
            <span>Download Message Log (CSV)</span>
          </button>
        </div>
      </div>

      {/* Alert Banner */}
      {banner && (
        <div
          className={`p-4 rounded-xl border text-sm flex items-start justify-between shadow-xs ${
            banner.type === "success"
              ? "bg-success-light/60 border-success/30 text-ink"
              : banner.type === "warning"
              ? "bg-warning-light/60 border-warning/30 text-ink"
              : "bg-primary-light/60 border-primary/30 text-ink"
          }`}
        >
          <div className="flex items-start space-x-3">
            {banner.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-success shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
            )}
            <div>
              <div className="font-bold text-ink">{banner.title}</div>
              <div className="text-xs text-muted mt-0.5">{banner.desc}</div>
            </div>
          </div>
          <button onClick={() => setBanner(null)} className="text-muted hover:text-ink text-xs font-bold ml-4">
            ✕
          </button>
        </div>
      )}

      {/* HOW SUPPLIERS SEND YOU BILLS (Simple Banner) */}
      <div className="bg-gradient-to-r from-success-light/50 via-surface to-surface border border-success/30 rounded-2xl p-5 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <span className="px-2 py-0.5 bg-success text-white rounded text-[11px] font-bold uppercase tracking-wider">
                Receiving Bills
              </span>
              <span className="text-xs text-muted font-medium">How suppliers send you bills on WhatsApp</span>
            </div>

            {!isEditingPhone ? (
              <div className="flex items-center flex-wrap gap-2.5">
                <span className="text-base font-bold text-ink">Give your suppliers this WhatsApp Number:</span>
                <span className="text-success font-mono font-bold text-base px-2.5 py-0.5 bg-success-light rounded-lg border border-success/30">
                  {businessPhone}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setTempPhoneInput(businessPhone);
                    setIsEditingPhone(true);
                  }}
                  className="px-2.5 py-1 bg-surface border border-border hover:bg-background text-primary text-xs font-semibold rounded-lg flex items-center space-x-1 shadow-2xs transition-colors"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                  <span>Change Number</span>
                </button>
              </div>
            ) : (
              <div className="p-3 bg-surface border-2 border-primary/40 rounded-xl space-y-2 max-w-md shadow-xs">
                <label className="block text-xs font-bold text-ink">
                  Enter Your WhatsApp Business Number:
                </label>
                <div className="flex items-center space-x-2">
                  <input
                    type="text"
                    value={tempPhoneInput}
                    onChange={(e) => setTempPhoneInput(e.target.value)}
                    placeholder="+91 98765 43210"
                    className="flex-1 px-3 py-1.5 bg-background border border-border rounded-lg text-xs font-mono font-bold text-ink focus:outline-none focus:ring-1 focus:ring-primary"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={handleSaveBusinessPhone}
                    className="px-3.5 py-1.5 bg-success hover:bg-success/90 text-white text-xs font-bold rounded-lg shadow-xs transition-colors"
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsEditingPhone(false)}
                    className="px-2.5 py-1.5 border border-border hover:bg-background text-xs text-muted hover:text-ink rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            <p className="text-xs text-muted leading-relaxed max-w-2xl">
              Suppliers can take a photo of their bill or send a PDF to this number. Our AI reads the bill numbers,
              calculates GST, and automatically puts it in your <strong>Bills Inbox</strong> for your review!
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={handleOpenChatWithMyNumber}
              className="px-3.5 py-2 bg-surface border border-success/40 text-success hover:bg-success-light/40 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition-colors shadow-xs"
              title="Open WhatsApp chat with this receiving number"
            >
              <ExternalLink className="w-3.5 h-3.5 text-success" />
              <span>Open Chat in WhatsApp Web</span>
            </button>

            <button
              onClick={handleCopyNumber}
              className="px-3.5 py-2 bg-surface border border-border hover:bg-background text-ink rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors shadow-xs"
            >
              {copiedNumber ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5 text-muted" />}
              <span>{copiedNumber ? "Copied!" : "Copy Number"}</span>
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,image/*"
              onChange={handleTestReceiveBill}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={simulatingUpload}
              className="px-4 py-2 bg-success text-white hover:bg-success/90 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors shadow-xs"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>{simulatingUpload ? "Reading Bill..." : "Test Receiving a Bill Photo / PDF"}</span>
            </button>
          </div>
        </div>
      </div>

      {/* MAIN TWO-COLUMN SECTION: Left = Send Message to Supplier, Right = Message History */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (7 cols): Easy WhatsApp Message Builder */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-surface rounded-2xl border border-border shadow-xs p-6 space-y-5">
            <div>
              <h2 className="text-base font-bold text-ink flex items-center space-x-2">
                <Send className="w-4 h-4 text-primary" />
                <span>Send WhatsApp Reminder to Supplier</span>
              </h2>
              <p className="text-xs text-muted mt-0.5">
                Choose a supplier, select a ready-made template, and send with 1 click.
              </p>
            </div>

            {/* STEP 1: Select Supplier */}
            <div className="space-y-2">
              <label className="block text-xs font-bold text-ink uppercase tracking-wider">
                Step 1: Choose Recipient / Phone Number
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {/* Quick Test on My Saved Number */}
                <button
                  type="button"
                  onClick={() => {
                    setSelectedSupplierPhone(businessPhone);
                    setCustomPhone("");
                  }}
                  className={`p-3 rounded-xl border text-left text-xs transition-all ${
                    (selectedSupplierPhone === businessPhone || targetPhoneNumber === businessPhone) && !customPhone
                      ? "border-primary bg-primary-light/40 text-primary font-semibold ring-1 ring-primary"
                      : "border-border hover:bg-background text-ink"
                  }`}
                >
                  <div className="font-bold flex items-center justify-between">
                    <span>📱 My Saved Number</span>
                    <span className="px-1.5 py-0.5 bg-success text-white text-[10px] rounded font-bold">Quick Test</span>
                  </div>
                  <div className="text-[11px] text-muted font-mono mt-1">{businessPhone}</div>
                </button>

                {KNOWN_SUPPLIERS.map((s) => (
                  <button
                    key={s.phone}
                    type="button"
                    onClick={() => {
                      setSelectedSupplierPhone(s.phone);
                      setCustomPhone("");
                    }}
                    className={`p-3 rounded-xl border text-left text-xs transition-all ${
                      selectedSupplierPhone === s.phone && !customPhone && selectedSupplierPhone !== businessPhone
                        ? "border-primary bg-primary-light/40 text-primary font-semibold ring-1 ring-primary"
                        : "border-border hover:bg-background text-ink"
                    }`}
                  >
                    <div className="font-bold">{s.name}</div>
                    <div className="text-[11px] text-muted font-mono">{s.phone}</div>
                  </button>
                ))}
              </div>

              <div className="pt-1">
                <input
                  type="text"
                  placeholder="Or enter any custom phone number (e.g. +91 98111 22334)"
                  value={customPhone}
                  onChange={(e) => setCustomPhone(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-xs font-mono text-ink placeholder:font-sans focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>

            {/* STEP 2: Choose Message Template */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-bold text-ink uppercase tracking-wider">
                  Step 2: What do you want to tell them?
                </label>
                <button
                  type="button"
                  onClick={() => setIsCustomMode(!isCustomMode)}
                  className="text-xs font-semibold text-primary hover:underline"
                >
                  {isCustomMode ? "Use Ready Templates" : "Write Custom Text"}
                </button>
              </div>

              {!isCustomMode ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {MESSAGE_TEMPLATES.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setSelectedTemplateId(t.id)}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        selectedTemplateId === t.id
                          ? "border-primary bg-primary-light/40 text-primary ring-1 ring-primary"
                          : "border-border hover:bg-background text-ink"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${t.badgeColor}`}>
                          {t.badge}
                        </span>
                      </div>
                      <div className="text-xs font-bold text-ink leading-tight">{t.title}</div>
                      <div className="text-[11px] text-muted mt-1 leading-snug">{t.desc}</div>
                    </button>
                  ))}
                </div>
              ) : (
                <textarea
                  rows={4}
                  value={customText}
                  onChange={(e) => setCustomText(e.target.value)}
                  placeholder="Type your message to the supplier here..."
                  className="w-full p-3 bg-background border border-border rounded-xl text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary"
                />
              )}
            </div>

            {/* STEP 3: Language Choice */}
            {!isCustomMode && (
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink uppercase tracking-wider">
                  Step 3: Choose Language
                </label>
                <div className="flex space-x-2">
                  {[
                    { id: "en", label: "English" },
                    { id: "hinglish", label: "Hinglish (Everyday)" },
                    { id: "hi", label: "हिंदी (Hindi)" },
                  ].map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => setLanguage(l.id as "en" | "hi" | "hinglish")}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all ${
                        language === l.id
                          ? "bg-success text-white border-success shadow-xs ring-1 ring-success"
                          : "bg-surface text-ink border-border hover:bg-background"
                      }`}
                    >
                      {l.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* STEP 4: Live WhatsApp Preview */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-bold text-ink uppercase tracking-wider">
                  <span>Message Preview</span>
                </label>
                <div className="flex items-center space-x-2">
                  <span className="text-[11px] text-muted">Preview Theme:</span>
                  <div className="flex items-center border border-border rounded-lg overflow-hidden text-[11px] font-semibold bg-background">
                    <button
                      type="button"
                      onClick={() => setPreviewTheme("light")}
                      className={`px-2 py-0.5 flex items-center space-x-1 transition-colors ${
                        previewTheme === "light"
                          ? "bg-surface text-ink shadow-2xs font-bold"
                          : "text-muted hover:text-ink"
                      }`}
                    >
                      <Sun className="w-3 h-3 text-warning" />
                      <span>Light</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreviewTheme("dark")}
                      className={`px-2 py-0.5 flex items-center space-x-1 transition-colors ${
                        previewTheme === "dark"
                          ? "bg-stone-800 text-white shadow-2xs font-bold"
                          : "text-muted hover:text-ink"
                      }`}
                    >
                      <Moon className="w-3 h-3 text-primary-light" />
                      <span>Dark</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Chat bubble styled like WhatsApp */}
              <div
                className={`p-4 rounded-xl border space-y-2 transition-colors ${
                  previewTheme === "light"
                    ? "bg-[#EFEAE2] border-stone-300"
                    : "bg-[#0B141A] border-stone-800"
                }`}
              >
                <div
                  className={`max-w-md p-3.5 rounded-lg rounded-tl-none shadow-sm text-xs whitespace-pre-wrap leading-relaxed border transition-colors ${
                    previewTheme === "light"
                      ? "bg-[#DCF8C6] text-black border-[#C5EDB3]"
                      : "bg-[#005C4B] text-white border-[#004A3C]"
                  }`}
                >
                  <div className="font-sans font-medium">{currentMessageText}</div>
                  <div
                    className={`text-[10px] text-right mt-1.5 flex items-center justify-end space-x-1 ${
                      previewTheme === "light" ? "text-stone-600" : "text-stone-200"
                    }`}
                  >
                    <span>Just now</span>
                    <span className={previewTheme === "light" ? "text-primary font-bold" : "text-emerald-300 font-bold"}>
                      ✓✓
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* STEP 5: Action Buttons */}
            <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
              <button
                type="button"
                onClick={handleSendViaApi}
                disabled={sendingMessage}
                className="w-full sm:flex-1 py-2.5 px-4 bg-success hover:bg-success/90 text-white text-xs font-bold rounded-xl transition-colors shadow-xs flex items-center justify-center space-x-2 disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
                <span>{sendingMessage ? "Sending via WhatsApp..." : "Send Message to Supplier"}</span>
              </button>

              <button
                type="button"
                onClick={handleOpenWhatsAppWeb}
                className="w-full sm:w-auto py-2.5 px-4 bg-surface border border-border hover:bg-background text-ink text-xs font-bold rounded-xl transition-colors shadow-xs flex items-center justify-center space-x-1.5"
                title="Opens WhatsApp Web or App with this text pre-filled so you can send from your personal/office number"
              >
                <ExternalLink className="w-4 h-4 text-primary" />
                <span>Open in WhatsApp Web ({targetPhoneNumber})</span>
              </button>
            </div>
          </div>
        </div>

        {/* Right Column (5 cols): Messages History */}
        <div className="lg:col-span-5 space-y-4">
          <div className="bg-surface rounded-2xl border border-border shadow-xs p-5 space-y-4 flex flex-col h-full min-h-[500px]">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div>
                <h3 className="font-bold text-ink text-sm">Recent WhatsApp Activity</h3>
                <p className="text-[11px] text-muted">Messages sent to &amp; received from suppliers</p>
              </div>
              <span className="px-2 py-0.5 bg-background border border-border rounded text-[11px] font-mono text-muted">
                {messages.length} messages
              </span>
            </div>

            {/* Message Feed */}
            <div className="space-y-3 overflow-y-auto max-h-[600px] flex-1 pr-1">
              {loading ? (
                <div className="p-8 text-center text-xs text-muted">Loading messages...</div>
              ) : messages.length === 0 ? (
                <div className="p-8 text-center text-xs text-muted space-y-2">
                  <MessageSquare className="w-8 h-8 text-muted mx-auto opacity-50" />
                  <p>No WhatsApp messages yet.</p>
                  <p className="text-[11px]">Send a reminder on the left or test receiving a bill!</p>
                </div>
              ) : (
                messages.map((m) => {
                  const isOutbound = m.direction === "OUTBOUND";
                  return (
                    <div
                      key={m.id}
                      className={`p-3.5 rounded-xl border text-xs space-y-1.5 ${
                        isOutbound
                          ? "bg-surface border-border ml-2"
                          : "bg-success-light/30 border-success/20 mr-2"
                      }`}
                    >
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-bold flex items-center space-x-1">
                          {isOutbound ? (
                            <>
                              <ArrowUpRight className="w-3.5 h-3.5 text-primary" />
                              <span className="text-primary">Sent to {m.recipient_phone}</span>
                            </>
                          ) : (
                            <>
                              <ArrowDownLeft className="w-3.5 h-3.5 text-success" />
                              <span className="text-success">Received from {m.sender_phone}</span>
                            </>
                          )}
                        </span>
                        <span className="text-muted text-[10px]">
                          {m.timestamp ? new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                        </span>
                      </div>

                      <p className="text-ink text-xs whitespace-pre-wrap leading-relaxed line-clamp-4">
                        {m.text}
                      </p>

                      {m.media_filename && (
                        <div className="flex items-center space-x-1 text-[11px] text-primary font-semibold pt-1">
                          <FileText className="w-3 h-3" />
                          <span>Attached Bill: {m.media_filename}</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
