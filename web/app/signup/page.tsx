"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { setStoredToken, setStoredUser, setActiveTenant, UserProfile } from "@/lib/api";
import {
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  Building2,
  ShieldAlert,
  Sparkles,
  Bot,
  FileCheck,
  Clock,
  FileSpreadsheet,
  Lock,
  Mail,
  User,
  Briefcase
} from "lucide-react";

interface ProblemOption {
  id: string;
  title: string;
  description: string;
  solutionTitle: string;
  solutionDescription: string;
  icon: typeof ShieldAlert;
}

const PROBLEMS: ProblemOption[] = [
  {
    id: "itc_loss",
    title: "Loss of Input Tax Credit (ITC) due to vendor non-filing & GSTR-2B mismatches",
    description: "Suppliers collect GST but delay or forget to file GSTR-1, blocking your legal credit under Section 16(2)(aa).",
    solutionTitle: "Autonomous GSTR-2B Graph Reconciliation",
    solutionDescription: "LedgerGraph auto-scans monthly 2B notifications, cross-matches line items against your purchase ledger in milliseconds, and tags non-compliant vendors for payment holds.",
    icon: FileCheck,
  },
  {
    id: "rule_37",
    title: "180-Day Rule 37 reversal risks with 18% statutory interest penalties",
    description: "Invoices unpaid after 180 days must legally be reversed in GSTR-3B along with retroactive penal interest.",
    solutionTitle: "Rule 37 Zero-Loss Aging Radar",
    solutionDescription: "A continuous 150-day proactive countdown identifies at-risk invoices before statutory cutoff and drafts one-click payment hold notices.",
    icon: Clock,
  },
  {
    id: "manual_entry",
    title: "Manual data entry bottlenecks & chasing suppliers on WhatsApp/Email",
    description: "Invoices get buried across emails and WhatsApp threads, requiring hours of manual typing and ledger mapping.",
    solutionTitle: "AI Multi-Channel Ingestion & Auto-Reply",
    solutionDescription: "Background AI agent monitors your Gmail and WhatsApp channels, extracts line items, verifies GSTIN checksums, and auto-dispatches tax confirmations to suppliers.",
    icon: Bot,
  },
  {
    id: "tally_reconcile",
    title: "Tally Prime ledger coding errors & zero-sum voucher discrepancies",
    description: "Wrong Place of Supply or incorrect CGST/SGST vs IGST classifications break ledger audits.",
    solutionTitle: "Zero-Sum TallyPrime XML Sync",
    solutionDescription: "Generates balanced double-entry vouchers with verified tax splits and stock items ready for instant import into Tally Prime.",
    icon: FileSpreadsheet,
  },
];

export default function SignUpPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form State
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"Admin" | "Client">("Admin");
  const [firmName, setFirmName] = useState("CA & Associates");
  const [companyName, setCompanyName] = useState("");
  const [gstin, setGstin] = useState("");

  // Questionnaire State
  const [selectedProblems, setSelectedProblems] = useState<string[]>([
    "itc_loss",
    "rule_37",
    "manual_entry",
  ]);
  const [invoiceVolume, setInvoiceVolume] = useState("50-200");
  const [accountingSoftware, setAccountingSoftware] = useState("Tally Prime");

  const toggleProblem = (id: string) => {
    if (selectedProblems.includes(id)) {
      if (selectedProblems.length > 1) {
        setSelectedProblems(selectedProblems.filter((p) => p !== id));
      }
    } else {
      setSelectedProblems([...selectedProblems, id]);
    }
  };

  const handleCompleteSignUp = async () => {
    setLoading(true);
    setError(null);

    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const payload = {
        name,
        email,
        password,
        role,
        firm_name: role === "Admin" ? firmName : undefined,
        company_name: companyName || (role === "Client" ? `${name}'s Company` : "Apex Auto Parts"),
        gstin: gstin || (role === "Client" ? "27AAACT1234A1Z5" : "06AAACA1234A1Z5"),
        state_code: gstin ? gstin.substring(0, 2) : undefined,
        pain_points: selectedProblems,
        monthly_invoice_volume: invoiceVolume,
        accounting_software: accountingSoftware,
      };

      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Registration failed" }));
        throw new Error(data.detail || "Sign up failed");
      }

      const data = await res.json();
      setStoredToken(data.access_token);
      setStoredUser(data.user as UserProfile);
      if (data.default_tenant_id) {
        setActiveTenant(data.default_tenant_id);
      }
      router.push("/");
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to register. Please check your connection.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center py-12 px-4 sm:px-6">
      <div className="max-w-2xl w-full bg-surface border border-border rounded-xl shadow-md p-8 sm:p-10 space-y-8">
        {/* Header / Brand */}
        <div className="text-center space-y-2">
          <div className="w-11 h-11 bg-primary text-white font-bold rounded-lg flex items-center justify-center text-xl mx-auto shadow-sm">
            LG
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">
            Create Your LedgerGraph Account
          </h1>
          <p className="text-sm text-muted max-w-md mx-auto">
            Autonomous GST compliance, multi-channel invoice ingestion, and GSTR-2B reconciliation.
          </p>

          {/* Stepper Progress */}
          <div className="pt-4 flex items-center justify-center space-x-3 text-xs font-semibold">
            <div className={`flex items-center space-x-1.5 ${step >= 1 ? "text-primary" : "text-muted"}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${step >= 1 ? "bg-primary text-white" : "bg-border text-muted"}`}>
                1
              </div>
              <span>Account Setup</span>
            </div>
            <div className="w-8 h-0.5 bg-border" />
            <div className={`flex items-center space-x-1.5 ${step >= 2 ? "text-primary" : "text-muted"}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${step >= 2 ? "bg-primary text-white" : "bg-border text-muted"}`}>
                2
              </div>
              <span>Accounting Assessment</span>
            </div>
            <div className="w-8 h-0.5 bg-border" />
            <div className={`flex items-center space-x-1.5 ${step >= 3 ? "text-primary" : "text-muted"}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${step >= 3 ? "bg-primary text-white" : "bg-border text-muted"}`}>
                3
              </div>
              <span>Tailored AI Solution</span>
            </div>
          </div>
        </div>

        {error && (
          <div className="p-4 bg-danger-light border border-danger/20 text-danger rounded-lg text-sm flex items-center space-x-2.5">
            <ShieldAlert className="w-5 h-5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* STEP 1: ACCOUNT SETUP */}
        {step === 1 && (
          <div className="space-y-6">
            <div className="space-y-3">
              <label className="block text-xs font-semibold text-muted uppercase tracking-wider">
                Select Your Role
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <button
                  type="button"
                  onClick={() => setRole("Admin")}
                  className={`p-4 rounded-lg border text-left transition-all ${
                    role === "Admin"
                      ? "border-primary bg-primary-light/40 ring-2 ring-primary/20"
                      : "border-border hover:bg-background"
                  }`}
                >
                  <div className="flex items-center space-x-2 text-primary font-semibold text-sm">
                    <Briefcase className="w-4 h-4" />
                    <span>Chartered Accountant / CA Firm</span>
                  </div>
                  <p className="text-xs text-muted mt-1.5 leading-relaxed">
                    Manage multiple client dashboards, switch between clients seamlessly, and automate reconciliations for your practice.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setRole("Client")}
                  className={`p-4 rounded-lg border text-left transition-all ${
                    role === "Client"
                      ? "border-primary bg-primary-light/40 ring-2 ring-primary/20"
                      : "border-border hover:bg-background"
                  }`}
                >
                  <div className="flex items-center space-x-2 text-primary font-semibold text-sm">
                    <Building2 className="w-4 h-4" />
                    <span>Business Client / Company</span>
                  </div>
                  <p className="text-xs text-muted mt-1.5 leading-relaxed">
                    Dedicated dashboard restricted strictly to your single business. Ingest supplier bills and view tax risk.
                  </p>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                  Full Name
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. CA Rajesh Sharma"
                    className="w-full pl-9 pr-3 py-2.5 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                  Work Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@firm.com"
                    className="w-full pl-9 pr-3 py-2.5 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 6 characters"
                  className="w-full pl-9 pr-3 py-2.5 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                />
              </div>
            </div>

            {role === "Admin" ? (
              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                  CA Firm / Practice Name
                </label>
                <input
                  type="text"
                  value={firmName}
                  onChange={(e) => setFirmName(e.target.value)}
                  placeholder="e.g. Sharma & Associates Chartered Accountants"
                  className="w-full px-3 py-2.5 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                />
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                    Company / Business Name
                  </label>
                  <input
                    type="text"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="e.g. Apex Auto Parts"
                    className="w-full px-3 py-2.5 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                    GSTIN (15 characters)
                  </label>
                  <input
                    type="text"
                    maxLength={15}
                    value={gstin}
                    onChange={(e) => setGstin(e.target.value.toUpperCase())}
                    placeholder="27AAACT1234A1Z5"
                    className="w-full px-3 py-2.5 bg-background border border-border rounded-lg text-sm font-mono text-ink uppercase focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  />
                </div>
              </div>
            )}

            <button
              type="button"
              disabled={!name || !email || password.length < 5}
              onClick={() => {
                setError(null);
                setStep(2);
              }}
              className="w-full py-3 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              <span>Continue to Accounting Assessment</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* STEP 2: ACCOUNTING PROBLEMS QUESTIONNAIRE */}
        {step === 2 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-ink">
                What are your biggest accounting & GST challenges?
              </h2>
              <p className="text-xs text-muted mt-1">
                Select all that apply. LedgerGraph will tailor its autonomous AI workflows to eliminate these bottlenecks.
              </p>
            </div>

            <div className="space-y-3">
              {PROBLEMS.map((prob) => {
                const isSelected = selectedProblems.includes(prob.id);
                const Icon = prob.icon;
                return (
                  <div
                    key={prob.id}
                    onClick={() => toggleProblem(prob.id)}
                    className={`p-4 rounded-lg border cursor-pointer transition-all flex items-start space-x-3.5 ${
                      isSelected
                        ? "border-primary bg-primary-light/30 shadow-sm"
                        : "border-border hover:bg-background opacity-80"
                    }`}
                  >
                    <div
                      className={`w-5 h-5 rounded border mt-0.5 flex items-center justify-center shrink-0 transition-colors ${
                        isSelected
                          ? "bg-primary border-primary text-white"
                          : "border-muted bg-surface"
                      }`}
                    >
                      {isSelected && <CheckCircle2 className="w-3.5 h-3.5" />}
                    </div>
                    <div className="space-y-1">
                      <div className="text-sm font-semibold text-ink leading-snug flex items-center space-x-1.5">
                        <Icon className="w-4 h-4 text-primary shrink-0" />
                        <span>{prob.title}</span>
                      </div>
                      <div className="text-xs text-muted leading-relaxed">
                        {prob.description}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                  Monthly Purchase Invoice Volume
                </label>
                <select
                  value={invoiceVolume}
                  onChange={(e) => setInvoiceVolume(e.target.value)}
                  className="w-full px-3 py-2.5 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="under-50">Under 50 Invoices / Month</option>
                  <option value="50-200">50 - 200 Invoices / Month (Standard SME)</option>
                  <option value="200-1000">200 - 1,000 Invoices / Month (Growing Practice)</option>
                  <option value="1000+">1,000+ High-Volume Multi-Branch</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                  Primary Accounting Software
                </label>
                <select
                  value={accountingSoftware}
                  onChange={(e) => setAccountingSoftware(e.target.value)}
                  className="w-full px-3 py-2.5 bg-background border border-border rounded-lg text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="Tally Prime">Tally Prime (XML Direct Export)</option>
                  <option value="Busy">Busy Accounting Software</option>
                  <option value="Marg ERP">Marg ERP</option>
                  <option value="Zoho Books">Zoho Books</option>
                </select>
              </div>
            </div>

            <div className="flex items-center space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="px-4 py-3 border border-border text-ink hover:bg-background rounded-lg text-sm font-medium transition-colors flex items-center space-x-1.5"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back</span>
              </button>
              <button
                type="button"
                onClick={() => setStep(3)}
                className="flex-1 py-3 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-sm flex items-center justify-center space-x-2"
              >
                <span>See How LedgerGraph Solves This</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: HOW OUR APPLICATION SOLVES IT */}
        {step === 3 && (
          <div className="space-y-6">
            <div className="space-y-1">
              <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 bg-success-light text-success rounded-full text-xs font-semibold">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Custom Solution Blueprint Generated</span>
              </div>
              <h2 className="text-xl font-bold text-ink">
                How LedgerGraph Solves Your Accounting Pain Points
              </h2>
              <p className="text-xs text-muted">
                Here is exactly how our autonomous agent operates to protect your Input Tax Credit and eliminate manual overhead.
              </p>
            </div>

            {/* Solution Cards */}
            <div className="space-y-3.5">
              {PROBLEMS.filter((p) => selectedProblems.includes(p.id)).map((prob) => {
                return (
                  <div
                    key={prob.id}
                    className="p-4 bg-background border border-border rounded-lg space-y-1.5 relative overflow-hidden"
                  >
                    <div className="flex items-center space-x-2 text-primary font-semibold text-sm">
                      <CheckCircle2 className="w-4 h-4 text-success" />
                      <span>{prob.solutionTitle}</span>
                    </div>
                    <p className="text-xs text-ink/80 leading-relaxed pl-6">
                      {prob.solutionDescription}
                    </p>
                  </div>
                );
              })}
            </div>

            {/* Summary Highlights */}
            <div className="p-4 bg-primary-light/40 border border-primary/20 rounded-lg text-xs space-y-2 text-ink">
              <div className="font-semibold text-primary flex items-center space-x-1.5">
                <Bot className="w-4 h-4" />
                <span>Autonomous AI Auto-Pilot Summary:</span>
              </div>
              <ul className="list-disc pl-5 space-y-1 text-muted">
                <li>
                  <strong className="text-ink">Live Channel Watching:</strong> Listens to real Gmail notifications (invoices & GSTR-2B filing intimations) and WhatsApp.
                </li>
                <li>
                  <strong className="text-ink">Zero Data Leakage:</strong> Role-based isolation ensures clients only see their own dashboard, while accountants switch clients in one click.
                </li>
                <li>
                  <strong className="text-ink">Audit-Ready Tally Export:</strong> Zero-sum balanced vouchers ready to import anytime.
                </li>
              </ul>
            </div>

            <div className="flex items-center space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="px-4 py-3 border border-border text-ink hover:bg-background rounded-lg text-sm font-medium transition-colors flex items-center space-x-1.5"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back</span>
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={handleCompleteSignUp}
                className="flex-1 py-3 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-md disabled:opacity-50 flex items-center justify-center space-x-2"
              >
                <span>{loading ? "Activating Workspace..." : "Complete Setup & Launch Dashboard"}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Footer Login Link */}
        <div className="pt-4 border-t border-border text-center text-xs text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-primary font-semibold hover:underline">
            Sign In here
          </Link>
        </div>
      </div>
    </div>
  );
}
