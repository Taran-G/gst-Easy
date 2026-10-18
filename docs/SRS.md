# LedgerGraph — Software Requirements Specification (SRS)

**Version:** 1.0  **Date:** 18 Oct 2026  **Audience:** Antigravity (implementing agent) and the founder
**Product:** WhatsApp-first GST invoice, reconciliation and vendor-risk agent for Indian CA firms and SMEs, built on FalkorDB.

---

## 0. How to use this document (instructions for Antigravity)

1. Build in the order of **Section 12 (Implementation Plan)**. Do not skip phases.
2. **Hackathon deadline: 18 Oct 2026, 11:59 PM IST.** Phases P0–P4 are the *submission cut*. Phases P5+ are the *product roadmap*. Never leave the repo in a broken state; each phase ends with a runnable demo.
3. Every requirement has an ID (`FR-*`, `NFR-*`, `UI-*`). Each phase lists which IDs it must satisfy. A requirement is done only when its **acceptance test** (Section 13) passes.
4. **Never let the LLM do arithmetic, compose Cypher, or decide tax outcomes.** The LLM only (a) extracts fields from images/PDFs and (b) drafts wording. All math, rules and graph writes are deterministic code (Section 4.3).
5. All external integrations (WhatsApp, GSP, Tally) sit behind **adapter interfaces with a `mock` mode** that reads fixtures from `/fixtures`. The app must run fully in mock mode with zero paid accounts.
6. Items marked **⚠ VERIFY** are legal or API facts that must be checked against current official sources or a practising CA before production use. Put them in `docs/VERIFY.md` and surface them in the UI "Rules" page as editable, versioned parameters, never hard-coded constants.

---

## 1. Introduction

### 1.1 Purpose
Define the complete requirements for LedgerGraph, a system that:
- captures purchase bills sent on WhatsApp/email,
- validates them deterministically,
- posts approved vouchers to Tally,
- reconciles them against GSTR-2B and supplier GSTR-3B filing status,
- warns about Input Tax Credit (ITC) risk before cash is lost,
- chases suppliers, with a human approving every consequential action.

### 1.2 Problem statement (plain language)
A buyer pays a supplier ₹10,000 + ₹1,800 GST. The buyer can only deduct that ₹1,800 from their own GST (ITC) if the supplier reports the bill and files returns. Today nobody tracks this: bills arrive as WhatsApp photos, are typed into Tally by hand, matched in Excel, and supplier defaults are discovered months later as lost cash plus interest. LedgerGraph connects the bill, the supplier, the payment and the government data in one graph so the risk is visible **before** payment and **before** deadlines.

### 1.3 Scope
**In scope (v1):** WhatsApp/email/upload ingestion, extraction, deterministic validation, GSTIN→Tally master resolution, Tally XML export (file first, live port second), GSTR-2B reconciliation, supplier filing-status monitoring, payment-hold advice, Rule 37 (180-day) and Rule 37A tracking, vendor chase drafts, audit log, multi-tenant isolation for CA firms.
**Out of scope (v1):** filing GSTR-3B/GSTR-1 on the portal, moving money, auto-creating Tally masters without approval, handwriting-heavy hospital documents, e-way bill generation, any legal/tax opinion.

### 1.4 Definitions
| Term | Meaning |
|---|---|
| GSTIN | 15-character GST registration ID; first 2 digits are the state code |
| ITC | Input Tax Credit: GST paid on purchases that can be deducted from GST owed on sales |
| GSTR-1 | Supplier's monthly/quarterly list of sales invoices |
| GSTR-2B | Buyer's static monthly statement of supplier-reported invoices (ITC eligibility) |
| GSTR-3B | Supplier's summary return in which tax is actually paid (lump sum) |
| QRMP / IFF | Quarterly filing scheme for small taxpayers / optional facility to report B2B invoices in months 1–2 |
| Rule 37 | Buyer must reverse ITC if supplier not paid within 180 days of invoice ⚠ VERIFY |
| Rule 37A | Buyer must reverse ITC if supplier's GSTR-3B for the period is not filed by the statutory cut-off, with a re-claim path ⚠ VERIFY |
| GSP | GST Suvidha Provider: licensed API gateway to GSTN |
| HITL | Human-in-the-loop approval |
| Tenant | One SME client of a CA firm; owns one isolated graph |

---

## 2. Overall description

### 2.1 Users
| Role | Description | Key needs |
|---|---|---|
| **CA Partner (Admin)** | Owns the firm account | Overview of all clients, risk, ITC at stake, billing |
| **Accountant (Reviewer)** | Does the daily work | Fast review queue, one-click approve, clear reasons |
| **SME Client (Submitter)** | Sends bills | Uses only WhatsApp; no login |
| **Supplier (Recipient)** | Receives chases | Clear, polite, transactional message |

### 2.2 Operating environment
Web app (desktop-first, responsive), Python 3.11+ backend, FalkorDB (Docker or FalkorDB Cloud), Node 20 frontend, runs on Railway/Render/any Docker host.

### 2.3 Design principles
1. **Zero habit change:** clients stay in WhatsApp; accountants stay in Tally.
2. **Deterministic core, probabilistic edge:** LLM extracts; code decides.
3. **Never silent:** nothing is posted, sent or reversed without an approval record.
4. **The graph must do real work:** multi-hop traversals, PageRank, shortest path, tenant isolation, procedural memory (hackathon Rule 3). If the graph were replaced by Postgres the demo must visibly lose capability (impact trace, provenance path, risk ranking).
5. **Honest labelling:** never claim "tax paid verified". Use exact statuses (Section 5.4).

### 2.4 Assumptions and constraints
- GSTN access is via a licensed GSP; buyer must authorise (OTP/session) per GSP flow ⚠ VERIFY exact auth flow and the availability of a public return-filing-status API per GSP.
- Tally integration: XML over HTTP on the Tally listener port (commonly 9000, configurable) requires a local bridge because Tally runs on the user's PC; the cloud app cannot reach `localhost`. v1 default is **downloadable XML file import**; the optional **Desktop Bridge** (small local agent) polls the cloud for approved batches.
- WhatsApp Business Cloud API needs Meta business verification; pricing and free-service-window rules change, so costs must come from a config table, not constants ⚠ VERIFY.
- GST law parameters (rates, due dates, rule numbers, cut-offs) change; they live in a versioned `rules.yaml`.

---

## 3. System architecture

```
 WhatsApp / Email / Web Upload
            │
   [Ingestion Service]  ── stores raw file (object store) + message record
            │
   [Extraction Worker]  ── Gemini vision → raw JSON + per-field confidence
            │
   [Validation Engine]  ── deterministic checks (math, GSTIN, dates, HSN, TDS hint, duplicates)
            │
   [Resolution Engine]  ── FalkorDB: GSTIN→Tally ledger, item→stock item, duplicate lock
            │
   [Review Queue UI]  ◄── HITL approval (accountant)
            │ approved
   ┌────────┴───────────┐
 [Tally Exporter]   [Graph Commit]  ── Invoice/Voucher nodes, ApprovalRule memory
   │ file / bridge        │
   │                      ▼
   │              [Reconciliation Engine] ◄── [GSP Adapter] (GSTR-2B, filing status)
   │                      │
   │              [Risk Engine]: Rule 37, 37A, hold-GST, PageRank, impact path
   │                      │
   │              [Chase Service] ── drafts → approval → WhatsApp Utility template
   ▼                      ▼
 Tally            [Audit Log + Dashboard UI]
```

### 3.1 Technology choices
| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind, shadcn/ui, react-force-graph-2d or cytoscape.js | Graph canvas for provenance |
| Backend | FastAPI, Pydantic v2, `falkordb` Python client, APScheduler or Celery+Redis for jobs | |
| Graph DB | FalkorDB, **one graph per tenant** named `t_<tenant_id>`, plus one `firm_<firm_id>` graph for firm-level data | FalkorDB addresses graphs by key: `db.select_graph("t_123")` (do **not** use a `SELECT GRAPH` statement) |
| LLM | Gemini (vision) behind an `Extractor` interface; swappable | Structured-output JSON schema enforced |
| Files | Local disk in dev, S3-compatible in prod | |
| Auth | Email+password with JWT, role claims; magic-link optional | |
| Agent tools | FalkorDB exposed as MCP server / tool functions (Section 6.5) | Required by hackathon |

### 3.2 Repository layout
```
ledgergraph/
  docker-compose.yml        # falkordb, redis, api, web
  .env.example
  docs/ (SRS.md, VERIFY.md, DEMO.md, SCHEMA.md)
  fixtures/ (bills/, gstr2b/, gstr3b_status/, tally_masters/, whatsapp_events/)
  api/
    app/main.py
    app/core/ (config.py, security.py, rules.py, audit.py)
    app/graph/ (client.py, schema.py, queries/*.cypher, repo.py)
    app/services/ (ingest.py, extract.py, validate.py, resolve.py, tally_xml.py,
                   reconcile.py, risk.py, chase.py, impact.py)
    app/adapters/ (whatsapp_{mock,cloud}.py, gsp_{mock,live}.py, tally_{file,bridge}.py, llm_gemini.py)
    app/mcp/server.py       # exposes graph tools
    tests/
  web/ (app/, components/, lib/)
  bridge/ (optional Tally desktop bridge)
  rules/rules.yaml          # versioned statutory parameters
```

---

## 4. Functional requirements

### 4.1 Ingestion (FR-ING)
- **FR-ING-1** Accept bills via (a) WhatsApp webhook, (b) email inbox (IMAP/forwarding webhook), (c) drag-and-drop upload in UI. Formats: JPG, PNG, PDF (multi-page), XLSX/CSV.
- **FR-ING-2** Route each file to a tenant by (i) sender phone number mapped to tenant, else (ii) extracted buyer GSTIN matching a tenant, else (iii) `Unrouted` inbox for manual assignment. Never guess silently.
- **FR-ING-3** Store the original file immutably with SHA-256 hash. If the same hash was seen for the tenant, mark `DUPLICATE_FILE` and do not re-extract.
- **FR-ING-4** WhatsApp replies: send **one** consolidated reply per submission (summary + status), no intermediate "received/reading" messages. Reply text is templated, not LLM-free-form.
- **FR-ING-5** Webhook must verify Meta signature, respond 200 within seconds, and process asynchronously (idempotent on message ID).
- **FR-ING-6** Voice notes (Hindi/Punjabi/Marathi) are an **optional** extension (P7): transcribe, then show as a draft note attached to the bill. Never create a voucher from audio alone.

### 4.2 Extraction (FR-EXT)
- **FR-EXT-1** Extract into a strict schema: supplier name, supplier GSTIN, buyer name, buyer GSTIN, invoice number, invoice date, place of supply, line items (description, HSN/SAC, qty, UOM, rate, taxable value, GST rate), CGST/SGST/IGST/cess amounts, round-off, grand total, supplier phone/email if printed, IRN/QR presence.
- **FR-EXT-2** Every field carries a confidence (0–1) and a bounding-box/page reference where available, so the UI can highlight the source region.
- **FR-EXT-3** If a PDF has an embedded e-invoice QR/JSON, parse that first and skip the LLM (highest accuracy) ⚠ VERIFY QR format.
- **FR-EXT-4** On extraction failure or confidence below the configured threshold (default 0.85 per critical field), the document goes to review with `LOW_CONFIDENCE` and the field is blank, never invented.
- **FR-EXT-5** Handwritten or blurry documents are flagged `NEEDS_BETTER_SCAN`; the WhatsApp reply asks the sender for a clearer photo.

### 4.3 Deterministic validation (FR-VAL)
All implemented in plain Python with unit tests. The LLM is never called here.
- **FR-VAL-1 Arithmetic:** per line `qty × rate − discount = taxable`; `Σ taxable + Σ taxes + round_off = grand_total`; tolerance ±₹1 only for stated round-off. Use `Decimal`, never float.
- **FR-VAL-2 GSTIN:** 15 chars, regex, valid state code, PAN embedded at positions 3–12, 14th char `Z`, **check-character algorithm** (mod-36). Reject on failure.
- **FR-VAL-3 Tax type:** supplier state vs place of supply: same state → CGST+SGST (equal), different → IGST. Mismatch = blocking error.
- **FR-VAL-4 Rate sanity:** GST rate must be in the allowed set from `rules.yaml`; HSN prefix to rate hints are *warnings* only.
- **FR-VAL-5 Dates:** normalise to ISO; invoice date not in future, not older than configured window; map to FY (Apr–Mar). Tally export uses `YYYYMMDD`.
- **FR-VAL-6 Buyer GSTIN match:** buyer GSTIN on bill must equal the tenant GSTIN; otherwise `WRONG_BUYER_GSTIN` (ITC would be lost: surface loudly).
- **FR-VAL-7 TDS hint:** if SAC/PAN category suggests TDS applicability, show a **suggestion** with section and rate from `rules.yaml`; accountant confirms.
- **FR-VAL-8 Duplicate invoice:** same (supplier GSTIN, invoice number normalised, FY) already exists → block with link to the original.
- **FR-VAL-9** Output a `ValidationReport` = list of `{code, severity: BLOCK|WARN|INFO, field, message}`. Any BLOCK prevents approval until corrected.

### 4.4 Entity resolution and master protection (FR-RES)
- **FR-RES-1** Resolve supplier by GSTIN via graph traversal `(:Vendor)-[:MAPS_TO_LEDGER]->(:TallyLedger)` to the exact case-sensitive Tally ledger name.
- **FR-RES-2** Resolve items: `(:VendorItem {raw_name, hsn})-[:MAPS_TO_STOCK_ITEM]->(:TallyStockItem {name, uom})`. Offer fuzzy suggestions **only as suggestions**.
- **FR-RES-3** Unknown GSTIN or item → create a **Master Request** card in the review queue; nothing is created in Tally automatically.
- **FR-RES-4** Tally masters are imported by the accountant uploading a Tally master export (XML/CSV) or via the bridge; stored as `TallyLedger`/`TallyStockItem` nodes. Without this import, resolution cannot work (show a setup checklist).
- **FR-RES-5 Procedural memory:** when an accountant approves a mapping or an exception ("always hold GST for vendor X", "item Y → stock item Z"), store an `:ApprovalRule` node and apply it next time (shown as "Applied rule from <date>, approved by <user>").

### 4.5 Review and approval (FR-HITL)
- **FR-HITL-1** Review queue lists items in states: `NEEDS_REVIEW`, `MASTER_REQUEST`, `BLOCKED`, `READY`.
- **FR-HITL-2** Review screen shows source image beside extracted fields; edits are tracked field-by-field (old→new, user, time).
- **FR-HITL-3** Actions: Approve, Edit & Approve, Reject (reason required), Request better scan.
- **FR-HITL-4** Approval writes an `:Approval` node with user, timestamp, action, diff, and the validation report hash. Approvals are append-only.
- **FR-HITL-5** Roles: Reviewer can approve vouchers; only Admin can approve master creation, rule changes and chases above a configured amount.
- **FR-HITL-6** Optional WhatsApp approval buttons to an accountant's number for single-tap approvals of low-risk items; high-risk always requires the web UI.

### 4.6 Tally export (FR-TAL)
- **FR-TAL-1** Generate a Purchase voucher XML where total debits equal total credits (party credit positive, expense/tax debits negative with `ISDEEMEDPOSITIVE` flags per Tally convention). Verify sum == 0 in code before export; refuse otherwise.
- **FR-TAL-2** Ledger names for tax and purchase heads come from tenant configuration (`TallyConfig`), not hard-coded (they differ per company).
- **FR-TAL-3** Delivery modes: **(A) file download** (Alt+O import) as default; **(B) Desktop Bridge** polling approved batches and posting to the local Tally port, returning Tally's response (created/altered/errors) to the cloud.
- **FR-TAL-4** Parse Tally's response; on error set voucher `EXPORT_FAILED` with the message; never mark posted without a success response (bridge) or an accountant's "Imported" confirmation (file).
- **FR-TAL-5** Idempotency: stable voucher GUID derived from (tenant, supplier GSTIN, invoice no., FY).
- **FR-TAL-6** Never emit `ACTION="Create"` for ledgers/stock items in v1.
- **FR-TAL-7** Provide a sample-import test against a real TallyPrime instance in P6 ⚠ XML details must be verified on the user's Tally version.

### 4.7 GST reconciliation (FR-REC)
- **FR-REC-1** Import GSTR-2B for a period via GSP adapter, or by uploading the GSTR-2B JSON/Excel downloaded from the portal (**manual fallback is mandatory**, since GSP access may be unavailable).
- **FR-REC-2** Match each approved purchase invoice to a `GSTR2BEntry` by (supplier GSTIN, normalised invoice number, tax amounts, date proximity). Statuses: `MATCHED`, `MATCHED_WITH_DIFFERENCE` (amount/date/number variance with reason), `MISSING_IN_2B`, `IN_2B_NOT_IN_BOOKS`.
- **FR-REC-3** `IN_2B_NOT_IN_BOOKS` raises a "missing bill" task and a chase draft asking the supplier for the invoice copy.
- **FR-REC-4 Timing awareness:** if the supplier is a known quarterly filer, `MISSING_IN_2B` before quarter end is `EXPECTED_TIMING_GAP`, not `DEFAULT`; escalate after the quarter's GSTR-1 date.
- **FR-REC-5** Compute per tenant and per period: ITC eligible, ITC at risk, ITC blocked, cash paid as GST to suppliers not yet in 2B.
- **FR-REC-6** Output an exportable reconciliation (Excel) for the CA, with every row linking to the invoice and its provenance path.
- **FR-REC-7** IMS actions: show suggested Accept/Pending/Reject per invoice; **the system never acts on the portal**; the CA does. ⚠ VERIFY current IMS behaviour.

### 4.8 Risk engine (FR-RSK)
- **FR-RSK-1 Payment hold advice:** for each unpaid invoice compute `release_now` vs `hold` amounts using: present in 2B, supplier GSTR-3B status for the relevant period, supplier GSTIN status (active/suspended/cancelled), vendor risk score, and tenant policy. Output is **advice** with reasons; payment is never executed by the system.
- **FR-RSK-2 Supplier compliance status:** per supplier maintain `GSTR1_status`, `GSTR3B_status` per period, filing frequency (monthly/QRMP), GSTIN registration status. Refresh on a schedule (default weekly, plus before any payment advice).
- **FR-RSK-3 Rule 37 (180 days):** for every unpaid invoice with ITC claimed, compute days since invoice date; alerts at configurable thresholds (default 120, 150, 170) ⚠ VERIFY rule text and part-payment treatment. Payment link via `:BankPayment` (imported from bank statement CSV in P5).
- **FR-RSK-4 Rule 37A tracking:** for invoices whose ITC was claimed, flag supplier non-filing of GSTR-3B past the configured statutory date; stage a reversal worksheet (amounts by invoice) for the CA; after reversal keep state `REVERSED_RULE_37A` and monthly check for supplier's late filing, then raise a **re-claim task** ⚠ VERIFY table references (4(B)(2), 4(D)(1)), dates and interest provisions with a CA.
- **FR-RSK-5 Vendor risk ranking:** PageRank/centrality over the supplier–invoice–item graph weighted by ITC value at risk, combined with filing history, to rank vendors (top-N list in UI).
- **FR-RSK-6 Impact trace (hackathon centerpiece):** given a vendor (and optional delay in days), return all affected invoices, ITC amounts, downstream POs/customer deliveries, using multi-hop traversal; render the path in the graph panel with the Cypher shown.
- **FR-RSK-7** All risk results carry `explanation[]` (human-readable reasons) and the graph path used.
- **FR-RSK-8 Honest status vocabulary:** see Section 5.4. The product must never display "tax paid verified".

### 4.9 Chasing (FR-CHS)
- **FR-CHS-1** Create chase **drafts** for: missing invoice copy, invoice not in GSTR-2B, supplier GSTR-3B pending, payment reminder from supplier (optional), PO delivery delay.
- **FR-CHS-2** Drafts use pre-approved **utility-category templates**; no promotional text. Languages: English, Hindi, Punjabi, Marathi (templates authored once, reviewed by a human).
- **FR-CHS-3** Sending requires approval; log message ID, template, cost, delivery status in `:VendorChase`.
- **FR-CHS-4** Rate-limit per supplier (default max 1 chase / 3 days, 3 total per issue); stop on supplier reply or resolution.
- **FR-CHS-5** Only message numbers that appear on the supplier's own invoice or the tenant's own party master; honour opt-out keywords ("STOP"), store opt-out on the vendor node. Consent/telemarketing compliance ⚠ VERIFY.
- **FR-CHS-6** Voice call via Bhashini is an optional P7 item.

### 4.10 Multi-tenancy and firms (FR-TEN)
- **FR-TEN-1** Firm → many tenants (clients). Each tenant = separate FalkorDB graph; no query may cross graphs except explicit firm-level aggregation done in application code over per-tenant results.
- **FR-TEN-2** Tenant switcher in the top bar; every API call carries tenant ID and is authorised against the user's firm and role.
- **FR-TEN-3** Tenant deletion/export: export all tenant data (JSON + files); delete = drop graph + delete files (DPDP readiness).

### 4.11 Audit, security and privacy (FR-AUD)
- **FR-AUD-1** Append-only audit events for: login, upload, extraction, edit, approval, export, chase, rule change, data export, deletion. Each event stores a hash of the previous event (tamper evidence).
- **FR-AUD-2** Audit viewer with filters and CSV export.
- **FR-AUD-3** PII minimisation: store only data needed; encrypt at rest; redact phone numbers in logs; retention policy configurable per tenant.
- **FR-AUD-4** LLM calls send only the document image; record provider, model, timestamp; allow a tenant setting to disable cloud LLM (then manual entry only).

### 4.12 Agent and MCP tools (FR-AGT) — hackathon requirement
Expose these as MCP/tool functions with JSON schemas; every call is logged and its Cypher is returned to the UI:
- `resolve_vendor(gstin)`, `check_duplicate(gstin, number, fy)`
- `run_cypher_readonly(template_id, params)` (only whitelisted templates; no free-form writes)
- `find_impact_path(vendor_gstin, delay_days)` (multi-hop / shortest path)
- `score_vendor_risk(top_n)` (PageRank)
- `reconcile_period(period)`, `list_itc_at_risk(period)`
- `commit_decision_to_memory(rule)` (procedural memory)
- `draft_chase(invoice_id, type, language)`
Three coordinated agents (Extractor, Graph-Risk, Action) communicate via **graph state** (status properties and `:Task` nodes), not via hidden prompts.

---

## 5. Data model

### 5.1 Per-tenant graph schema
```
(:Tenant {id, gstin, name, state_code, filing_freq})
(:Vendor {gstin, legal_name, trade_name, pan, state_code, filing_freq, gstin_status, phone, email,
          opted_out, risk_score, last_status_check})
(:TallyLedger {name, parent_group})
(:TallyStockItem {name, uom, gst_rate})
(:VendorItem {raw_name, hsn_sac})
(:Document {id, sha256, source, received_at, path, state})
(:Invoice {id, number, number_norm, date, fy, taxable, cgst, sgst, igst, cess, total,
           state, itc_status, hold_status, due_date})
(:InvoiceLine {no, desc, hsn_sac, qty, uom, rate, taxable, gst_rate})
(:TallyVoucher {guid, vch_no, export_state, exported_at})
(:BankPayment {utr, date, amount})
(:GSTR2BEntry {period, supplier_gstin, inv_no_norm, taxable, tax, ims_action, fetched_at})
(:FilingStatus {gstin, period, form: 'GSTR1'|'GSTR3B', status, filed_on, fetched_at})
(:PurchaseOrder {number, date, status, promised_date})
(:EWayBill {number, valid_until})
(:CustomerOrder {number, customer, due_date, value})   // downstream impact
(:Item {name})                                          // raw material / part
(:VendorChase {id, channel, template, lang, cost_inr, sent_at, status})
(:Approval {id, user, action, at, diff_hash})
(:ApprovalRule {id, kind, params, created_by, created_at, active})
(:Task {id, kind, state, due, owner})
```
Relationships:
```
(Vendor)-[:ISSUED]->(Invoice)
(Vendor)-[:MAPS_TO_LEDGER {approved_by, approved_at}]->(TallyLedger)
(Vendor)-[:SUPPLIES]->(Item)-[:USED_IN]->(CustomerOrder)        // for impact trace
(Vendor)-[:SUPPLIES_ITEM]->(VendorItem)-[:MAPS_TO_STOCK_ITEM]->(TallyStockItem)
(PurchaseOrder)-[:PLACED_WITH]->(Vendor)
(PurchaseOrder)-[:FOR_ITEM]->(Item)
(PurchaseOrder)-[:FULFILLS]->(CustomerOrder)
(Invoice)-[:AGAINST]->(PurchaseOrder)
(EWayBill)-[:COVERS]->(Invoice)
(Document)-[:SOURCE_OF]->(Invoice)
(Invoice)-[:HAS_LINE]->(InvoiceLine)
(Invoice)-[:POSTED_AS]->(TallyVoucher)-[:SETTLED_BY]->(BankPayment)
(Invoice)-[:REFLECTED_IN]->(GSTR2BEntry)
(Vendor)-[:HAS_STATUS]->(FilingStatus)
(Invoice)-[:COVERED_BY]->(FilingStatus)        // the 3B period for that invoice
(Invoice)-[:CHASED_VIA]->(VendorChase)
(Invoice)-[:APPROVED_BY]->(Approval)
(ApprovalRule)-[:GOVERNS]->(Vendor)
(Task)-[:ABOUT]->(Invoice|Vendor)
```
Indexes: `Vendor.gstin`, `Invoice.number_norm`, `Invoice.fy`, `GSTR2BEntry(period)`, `FilingStatus(gstin, period)`, uniqueness constraint on `Vendor.gstin` and on `Invoice(vendor gstin, number_norm, fy)` (enforce in code if constraint composite not supported).

### 5.2 Firm graph (`firm_<id>`)
`(:Firm)`, `(:User {role})`, `(:Tenant)`, `(:PhoneMap {phone})`. Used for routing and access only; no financial data.

### 5.3 Core query templates (parameterised; stored in `queries/*.cypher`)
Always pass values as parameters; never string-concatenate.

**Q1 Resolve + duplicate guard**
```cypher
MATCH (v:Vendor {gstin: $gstin})
OPTIONAL MATCH (v)-[:ISSUED]->(d:Invoice {number_norm: $inv_no, fy: $fy})
OPTIONAL MATCH (v)-[:MAPS_TO_LEDGER]->(tl:TallyLedger)
OPTIONAL MATCH (v)-[:SUPPLIES_ITEM]->(vi:VendorItem {raw_name: $raw_item})-[:MAPS_TO_STOCK_ITEM]->(si:TallyStockItem)
OPTIONAL MATCH (r:ApprovalRule {active: true})-[:GOVERNS]->(v)
RETURN d IS NOT NULL AS is_duplicate, tl.name AS ledger, si.name AS stock_item, si.uom AS uom, collect(r.params) AS rules
```

**Q2 Reconcile a period (read, then app code writes statuses)**
```cypher
MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {fy: $fy})-[:POSTED_AS]->(:TallyVoucher)
WHERE i.date >= $from AND i.date <= $to
OPTIONAL MATCH (i)-[:REFLECTED_IN]->(e:GSTR2BEntry {period: $period})
RETURN v.gstin, i.id, i.number, i.cgst + i.sgst + i.igst AS tax, e IS NOT NULL AS in_2b
```

**Q3 Hold-GST advice inputs**
```cypher
MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {state: 'POSTED'})
WHERE i.hold_status IS NULL OR i.hold_status <> 'PAID'
OPTIONAL MATCH (i)-[:REFLECTED_IN]->(e:GSTR2BEntry)
OPTIONAL MATCH (v)-[:HAS_STATUS]->(f:FilingStatus {form: 'GSTR3B', period: $period})
RETURN v.gstin, v.gstin_status, v.filing_freq, i.id, i.total, i.cgst + i.sgst + i.igst AS tax,
       e IS NOT NULL AS in_2b, f.status AS gstr3b_status
```

**Q4 Rule 37 aging** (`$today` passed from app)
```cypher
MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {itc_status: 'CLAIMED'})
WHERE NOT (i)-[:POSTED_AS]->(:TallyVoucher)-[:SETTLED_BY]->(:BankPayment)
RETURN v.gstin, i.id, i.number, i.date, duration.inDays(date(i.date), date($today)).days AS age_days
```
(If the installed FalkorDB lacks the duration function, compute age in application code.)

**Q5 Rule 37A candidates** (cut-off passed as parameter from `rules.yaml`)
```cypher
MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {fy: $fy, itc_status: 'CLAIMED'})-[:COVERED_BY]->(f:FilingStatus {form: 'GSTR3B'})
WHERE f.status = 'NOT_FILED'
RETURN v.gstin, i.id, i.number, i.cgst + i.sgst + i.igst AS reversal_amount
```

**Q6 Impact trace (multi-hop)**
```cypher
MATCH p = (v:Vendor {gstin: $gstin})-[:SUPPLIES]->(it:Item)-[:USED_IN]->(co:CustomerOrder)
OPTIONAL MATCH (v)-[:ISSUED]->(i:Invoice)-[:REFLECTED_IN]->(e:GSTR2BEntry)
RETURN p, collect(DISTINCT i.id) AS invoices, sum(i.cgst + i.sgst + i.igst) AS itc_exposed, collect(DISTINCT co.number) AS orders
```
Shortest path for provenance: `MATCH (a:Vendor {gstin:$g}), (b:FilingStatus {period:$p}) MATCH p = shortestPath((a)-[*..6]->(b)) RETURN p`.

**Q7 PageRank** ⚠ VERIFY procedure signature against installed FalkorDB version
```cypher
CALL algo.pageRank('Vendor', 'SUPPLIES') YIELD node, score
RETURN node.gstin, node.legal_name, score ORDER BY score DESC LIMIT $n
```
Final vendor risk = weighted blend of PageRank, ITC value at risk, filing history; computed in code and written back to `Vendor.risk_score`.

### 5.4 Status vocabulary (UI and API)
| Field | Allowed values |
|---|---|
| `Document.state` | RECEIVED, EXTRACTING, NEEDS_BETTER_SCAN, NEEDS_REVIEW, REJECTED, DUPLICATE_FILE |
| `Invoice.state` | DRAFT, BLOCKED, READY, APPROVED, EXPORTED, POSTED, EXPORT_FAILED |
| `Invoice.itc_status` | NOT_CLAIMED, ELIGIBLE_PENDING_2B, MATCHED_2B, MISSING_2B, EXPECTED_TIMING_GAP, CLAIMED, BLOCKED_SEC_16_2_AA, REVERSED_RULE_37A, READY_FOR_RECLAIM, REVERSED_RULE_37 |
| `Invoice.hold_status` | NONE, ADVISE_HOLD_GST, ADVISE_RELEASE_ALL, PAID |
| Supplier display label | "In GSTR-2B · GSTR-3B filed" / "In GSTR-2B · GSTR-3B not filed" / "Not in GSTR-2B" / "Quarterly filer, awaiting quarter-end". Never "Tax paid verified". |

### 5.5 Known limits stated in UI help text
- Portal cannot show whether tax was paid for one specific invoice; the tool shows return-level filing status.
- A supplier filing GSTR-3B but underpaying is outside buyer-side detection; it is surfaced only as general vendor-risk signals (e.g., late filing pattern, GSTIN status change).
- The product supports a CA's judgement; it gives no legal guarantee.

---

## 6. External interfaces

### 6.1 WhatsApp (adapter `WhatsAppPort`)
Methods: `parse_webhook`, `download_media`, `send_text`, `send_template`. Mock mode reads `/fixtures/whatsapp_events/*.json` and a UI "Simulate WhatsApp message" button (also used in the demo). Cloud mode: Meta Cloud API with signature verification and idempotency. Template registry in DB with category, language, approval status. Per-message cost table is config-driven ⚠ VERIFY current rates; show estimated monthly messaging cost on the Settings page.

### 6.2 GSP (adapter `GspPort`)
Methods: `get_gstr2b(gstin, period)`, `get_filing_status(gstin)`, `get_gstin_details(gstin)`. Mock reads `/fixtures/gstr2b` and `/fixtures/gstr3b_status`. Live adapter targets one chosen GSP (decide in P6) ⚠ VERIFY availability, auth, pricing and whether public filing-status lookup is offered. **Manual fallback:** upload of GSTR-2B Excel/JSON and a vendor-status CSV.

### 6.3 Tally (adapter `TallyPort`)
`FileExporter` (default) and `BridgeExporter`. Master import accepts Tally "List of Accounts" export. Bridge is a small signed local app that authenticates with a device token, polls for approved batches, posts to `http://localhost:<port>`, returns the response.

### 6.4 LLM (adapter `ExtractorPort`)
`extract(document) -> ExtractionResult{fields, confidences, raw}`. JSON-schema constrained output, temperature 0, retries with a "re-read" prompt only on schema failure. Golden-set regression tests run on `/fixtures/bills`.

### 6.5 MCP / tool server
`app/mcp/server.py` exposes the tools in FR-AGT. Each tool returns `{result, cypher, path_ids}` so the UI can highlight the graph path.

### 6.6 REST API (selection; all under `/api/v1`, JWT auth, tenant in header `X-Tenant`)
`POST /ingest/upload`, `POST /webhooks/whatsapp`, `GET /inbox`, `GET /invoices/{id}`, `PATCH /invoices/{id}`, `POST /invoices/{id}/approve|reject`, `GET /masters/requests`, `POST /masters/requests/{id}/approve`, `POST /tally/export`, `POST /gstr2b/import`, `POST /reconcile/{period}`, `GET /risk/vendors`, `GET /risk/impact?gstin=&delay=`, `GET /itc/summary?period=`, `GET /rules37/aging`, `POST /chases/draft`, `POST /chases/{id}/approve`, `GET /audit`, `GET /graph/subgraph?ids=`.

---

## 7. UI / UX specification

### 7.1 Principles
Simple, spacious, sober, calm. One primary action per screen. No jargon without a tooltip in plain language. Never more than 5 top-level destinations. Everything is reachable in at most 2 clicks from Home.

### 7.2 Visual system
- **Palette:** background `#FAFAF9`, surface `#FFFFFF`, border `#E7E5E4`, text `#1C1917`, muted `#78716C`, primary `#1E3A5F` (deep navy), success `#2F7D5B`, warning `#B7791F`, danger `#B4443C`. No gradients, no neon, no heavy shadows (1px border + very soft shadow only).
- **Type:** Inter (UI), tabular numerals for money. Base 16px, line-height 1.6; headings 24/20/16 semibold.
- **Spacing:** 8-pt grid; page padding 32px; card padding 24px; generous whitespace; max content width 1120px.
- **Money format:** Indian grouping (₹1,18,000.00), always right-aligned.
- **Motion:** minimal (150ms fades). Respect `prefers-reduced-motion`.
- **Accessibility:** WCAG AA contrast, full keyboard navigation, visible focus rings, status never conveyed by colour alone (icon + text).
- **Language:** UI in English with Hindi toggle in P7; plain labels.

### 7.3 Layout
Left sidebar (collapsible, 220px) with 5 items; top bar with **Client switcher** (tenant dropdown) and period selector; main content centred; right-hand slide-over "Details" drawer for any record. A persistent, quiet banner when the client is in demo/mock mode.

### 7.4 Navigation (5 items only)
1. **Home** · 2. **Inbox** · 3. **Reconcile** · 4. **Suppliers** · 5. **Settings**
(Audit log and Rules live under Settings; Graph view is a tab inside Suppliers and inside any invoice.)

### 7.5 Screens
**UI-1 Home (calm dashboard).** Greeting + one sentence: "3 bills need your review. ₹42,300 of tax credit needs attention." Four large cards only: *To review*, *Tax credit at risk (₹)*, *Deadlines coming up* (next 3), *Suppliers to follow up*. Each card has one button. No charts above the fold except one simple bar of ITC (matched / pending / at risk).

**UI-2 Inbox (review queue).** Single-column list: supplier, amount, status chip, received time. Filter tabs: *Needs review · Blocked · Ready · All*. Clicking opens the **Review screen**.
- **Review screen:** left = bill image (zoom, highlight region on field focus), right = extracted fields in a simple form grouped as Supplier / Bill / Items / Tax / Totals. Issues appear as a short plain-language list at the top ("Total does not match items: difference ₹100"). Primary button **Approve**; secondary **Edit**, **Reject**, **Ask for better scan**. Master requests appear inline ("New supplier – add to Tally first").
- Bottom tab "How we checked this" shows validation results and the graph path used.

**UI-3 Reconcile.** Period selector → three clear sections: *Matched*, *Not in GSTR-2B*, *In GSTR-2B but not in your books*. Each row shows ₹ tax and a one-line advice ("Pay ₹10,000 now, hold ₹1,800 until the supplier files"). Buttons: *Import GSTR-2B*, *Export for CA*. Also a *Deadlines* tab showing Rule 37 aging and Rule 37A items, each with plain-English "what this means" text.

**UI-4 Suppliers.** List with risk badge (Low/Medium/High) and filing label from the vocabulary in 5.4. Supplier detail: filing history strip, open invoices, ITC at risk, chase history, **Draft message** button. Tab **Graph**: two-column explorer (see 7.6).

**UI-5 Settings.** Sections: Clients (firm admin), Tally (masters import, ledger names, export mode), WhatsApp (numbers, templates, estimated cost), GST connection (GSP or manual upload), Rules & thresholds (versioned `rules.yaml` values, read-only for Reviewer), Team & roles, Audit log, Data export/delete.

### 7.6 Graph / provenance panel (hackathon showcase)
Split view: **left** chat-style "Ask" box with approve/reject cards; **right** force-graph canvas that lights up the nodes/edges of the latest query, with a collapsible drawer showing the exact Cypher and returned rows. Example question: "If Sharma Steels is 4 days late, what breaks?" → highlighted path Vendor→Item→CustomerOrder plus ITC exposed and a *Draft chase* approval card. This panel is available from Suppliers → Graph and from any invoice → "See connections".

### 7.7 Empty, loading and error states
Every list has a friendly empty state with the next action ("Send a bill on WhatsApp or drop a file here"). Skeleton loaders, never spinners over blank pages. Errors explain what happened and what to do, with a retry button.

### 7.8 Copy rules
Short sentences, no unexplained acronyms (first use shows a tooltip: "ITC – the GST you can deduct from your own GST"). Never alarmist; danger colour only for blocking issues and deadlines within 7 days.

---

## 8. Non-functional requirements
- **NFR-1 Accuracy:** deterministic validation unit-test coverage ≥ 95% of branches; extraction golden-set field accuracy tracked, target ≥ 95% on clean printed invoices.
- **NFR-2 Performance:** extraction to review-ready ≤ 30 s p95 for a single-page bill; page loads ≤ 2 s; Cypher templates ≤ 300 ms on 50k-invoice tenant.
- **NFR-3 Scalability:** ≥ 200 tenants per FalkorDB instance in v1; batch jobs are idempotent and resumable.
- **NFR-4 Reliability:** webhook idempotency, retry with exponential back-off, dead-letter queue visible to Admin.
- **NFR-5 Security:** TLS, encrypted secrets, RBAC, per-request tenant authorisation tests, rate limiting, signed file URLs expiring in 5 min, dependency scanning.
- **NFR-6 Privacy/DPDP readiness:** consent record for data processing, purpose limitation, retention and deletion, breach-log process, data-processing agreement template ⚠ VERIFY with counsel.
- **NFR-7 Observability:** structured logs with request ID, metrics (queue depth, extraction confidence, approval turnaround), error tracking.
- **NFR-8 Maintainability:** statutory parameters only in `rules.yaml` with effective dates; adapters isolated; type hints and linting in CI.
- **NFR-9 Usability:** a new accountant completes review-and-approve in ≤ 3 clicks without training; usability test with 3 real accountants before launch.

---

## 9. Gap register (what could go wrong and how it is closed)
| # | Gap | Closure | Residual risk |
|---|---|---|---|
| 1 | LLM misreads a number | Deterministic cross-foot, confidence gates, QR-first, human approval | Low |
| 2 | Wrong or duplicate Tally ledger | Graph GSTIN mapping, master requests, no auto-create, GUID idempotency | Low |
| 3 | Tally cannot be reached from the cloud | File export default; local Bridge optional | Medium (setup) |
| 4 | GSTR-2B unavailable via GSP | Manual upload fallback | Low |
| 5 | Supplier GSTR-3B status unavailable | Manual vendor-status CSV; show "unknown" rather than guess | Medium |
| 6 | Quarterly supplier false alarms | `EXPECTED_TIMING_GAP` logic using filing frequency | Low |
| 7 | Supplier never sends the bill | `IN_2B_NOT_IN_BOOKS` discovery + chase draft | Low |
| 8 | Underpayment inside lump-sum GSTR-3B | Not detectable per invoice; vendor-risk signals; honest labels and help text | Accepted |
| 9 | Legal parameters change | Versioned `rules.yaml`, VERIFY list, CA review | Medium |
| 10 | WhatsApp cost/compliance | Single reply, utility templates, opt-out, config-driven rates | Low |
| 11 | Cross-client data leak | Graph-per-tenant, per-request authorisation tests | Low |
| 12 | Unsafe automation | HITL on all consequential actions; no portal or payment actions | Low |
| 13 | Handwritten/blurry bills | Flag and request re-scan; out of scope for v1 accuracy promises | Medium |
| 14 | Partial payments and credit notes | Out of v1 for ITC maths; credit/debit note nodes planned in P8, until then flagged `MANUAL_REVIEW` | Medium |
| 15 | Reverse charge, imports, RCM/ISD invoices | Detected by keywords/HSN and sent to manual review in v1 | Medium |

---

## 10. Hackathon alignment (FalkorDB × WeMakeDevs)
- **Graph does real work (Rule 3):** impact trace (multi-hop), provenance shortest path, PageRank vendor risk, per-tenant graphs, procedural memory rules. State plainly in README which features would not work on a vector DB.
- **Tracks:** Agents That Act on Connected Data (impact + chase cards), Agent Memory & Coordination (tenant graphs, `ApprovalRule`, graph-state hand-offs), Company Brain (people, documents, vendors, decisions in one graph).
- **README must contain:** Mermaid schema diagram, the 5–7 actual Cypher queries from 5.3, algorithms used, MCP tool list, demo GIF/video, tenant-switch screenshot, and an honest "limits" section.

---

## 11. Demo dataset (fixtures)
Create tenants **Apex Auto Parts (Haryana)** and **Greenleaf Traders (Gujarat)**. Vendors: Sharma Steels (monthly filer, GSTR-3B filed), ABC Traders (QRMP, GSTR-3B pending), Delta Fasteners (GSTR-3B not filed, GSTIN cancelled soon), 4 more. 25 invoices across 2 months covering: clean match, name mismatch, wrong buyer GSTIN, arithmetic error, duplicate, missing in 2B, in 2B but not in books, quarterly timing gap, day-150 unpaid, Rule 37A candidate with later re-claim. Use **synthetic but format-valid GSTINs** (with correct check characters) and clearly fake names.

---

## 12. Implementation plan

Estimated order for the remaining hackathon window (now ≈ 14:40 IST; deadline 23:59 IST). Times are budgets, not promises; cut scope rather than slip.

### P0 — Foundation (≈ 60 min)
Repo scaffold, docker-compose (FalkorDB, Redis, API, web), config, JWT auth with seeded firm + 2 tenants, FalkorDB client with graph-per-tenant helper, schema bootstrap + indexes, adapter interfaces with mock implementations, `rules.yaml`, fixtures folder, CI lint/test.
**Done when:** `docker compose up` shows login → tenant switcher → empty Home. (FR-TEN-1/2, NFR-8)

### P1 — Ingest → Extract → Validate → Review (≈ 120 min)
Upload + simulated WhatsApp, Gemini extractor with schema, deterministic validator with full unit tests (GSTIN checksum, math, tax type, dates, duplicates), review screen with image-beside-form, approve/reject, audit events.
**Done when:** the 8 fixture bills reach the correct states with the right validation codes. (FR-ING-1/2/3/4, FR-EXT-*, FR-VAL-*, FR-HITL-1..4, FR-AUD-1)

### P2 — Graph resolution, masters, memory (≈ 60 min)
Tally masters import, GSTIN→ledger and item→stock traversal (Q1), master-request cards, `ApprovalRule` memory applied on the second encounter, graph commit on approval.
**Done when:** approving an exception once changes behaviour on the next bill and the UI cites the rule. (FR-RES-*, FR-HITL-5)

### P3 — Tally XML + reconciliation (≈ 75 min)
Zero-sum voucher XML with tenant ledger config and GUID, file download, GSTR-2B import (mock + manual upload), matching engine (Q2), Reconcile screen with the three sections and Excel export.
**Done when:** the sample XML imports into a TallyPrime test company (if available; otherwise XML passes schema/zero-sum tests) and recon statuses match expected fixtures. (FR-TAL-1..6, FR-REC-1..6)

### P4 — Risk, impact trace, graph panel (≈ 90 min) — **hackathon centerpiece**
Filing-status adapter (mock), hold-GST advice (Q3), Rule 37 aging (Q4), Rule 37A candidates (Q5), PageRank (Q7), impact trace (Q6), MCP tool server, chase drafts with approval card, split-view graph panel with Cypher drawer, Suppliers screens.
**Done when:** the 2-minute demo script (Section 14) runs end-to-end without manual DB edits. (FR-RSK-*, FR-CHS-1..4, FR-AGT)

### P4.5 — Submission polish (≈ 45 min, before 22:30)
README with Mermaid schema + queries, demo video, seed command, deployment (Railway/Render + FalkorDB Cloud), smoke test, submit to **all three tracks**. Freeze features at 22:30.

### Post-hackathon roadmap
- **P5** Bank statement import → `BankPayment` nodes, part-payment handling, Rule 37 accuracy.
- **P6** Live adapters: Meta WhatsApp Cloud API, chosen GSP, Tally Bridge; real TallyPrime tests.
- **P7** Vernacular: Hindi/Punjabi/Marathi templates and UI toggle, voice-note transcription, Bhashini voice chase.
- **P8** Credit/debit notes, RCM, e-invoice QR ingestion, e-way bill linkage, TDS ledger split.
- **P9** Pilot with 2 CA firms (14-day shadow mode on 5 clients), measure hours saved and ITC issues caught, fix top 10 issues.
- **P10** Billing, firm onboarding, DPDP documentation, security review.

---

## 13. Acceptance tests (minimum set)
| ID | Test | Pass criteria |
|---|---|---|
| AT-1 | Upload clean fixture bill | Reaches `READY`, all fields match golden JSON |
| AT-2 | Bill with Qty×Rate mismatch | `BLOCK` with code `MATH_MISMATCH`, Approve disabled |
| AT-3 | GSTIN with bad check character | `BLOCK GSTIN_INVALID` |
| AT-4 | Intra vs inter-state tax mismatch | `BLOCK TAX_TYPE_MISMATCH` |
| AT-5 | Same invoice sent twice (WhatsApp + upload) | Second blocked `DUPLICATE_INVOICE` linking the first |
| AT-6 | Unknown supplier | Master request created; no Tally output until approved |
| AT-7 | Approve vendor exception, resend similar bill | Rule applied and cited in UI |
| AT-8 | Export approved bill | XML debits+credits sum to 0.00; stable GUID on re-export |
| AT-9 | Reconcile with fixture 2B | Counts of matched / missing / not-in-books equal expected |
| AT-10 | QRMP supplier before quarter-end | `EXPECTED_TIMING_GAP`, not default |
| AT-11 | Supplier GSTR-3B not filed | Advice `HOLD_GST`, label reads "In GSTR-2B · GSTR-3B not filed" |
| AT-12 | Invoice unpaid at day 150 | Rule 37 alert raised |
| AT-13 | Rule 37A candidate then late filing | State moves to `REVERSED_RULE_37A` then re-claim task appears |
| AT-14 | Impact trace for vendor + 4-day delay | Returns affected orders and ITC amount; graph highlights path; Cypher shown |
| AT-15 | Tenant isolation | User of tenant A receives 403 for tenant B; direct graph query for B never executes |
| AT-16 | Chase flow | Draft → approval → send (mock) logged with cost; stops after reply/opt-out |
| AT-17 | Audit chain | Tampering with an event breaks hash-chain verification |
| AT-18 | Usability | New user approves a bill in ≤ 3 clicks; keyboard-only completes the flow |

---

## 14. Two-minute demo script
1. Switch tenant to **Apex Auto Parts**.
2. Click *Simulate WhatsApp* with 3 files: a Sharma Steels bill, an ABC Traders bill, a Delta Fasteners bill.
3. Watch Extractor → Validator → Graph agents populate the graph; Inbox shows one clean, one math error, one unknown supplier.
4. Approve the clean bill; approve the new-supplier master request; show XML download.
5. Open **Reconcile**: one bill missing from 2B, one timing gap, one ghost invoice in 2B.
6. In the graph panel ask: *"If Sharma Steels delays by 4 days, which deliveries break and how much ITC is at risk?"* — path lights up, Cypher drawer opens, ₹ at risk shown.
7. Approve the suggested chase card (mock WhatsApp), show the audit trail, then switch to **Greenleaf Traders** to show isolation.
8. Close with the Suppliers risk ranking (PageRank).

---

## 15. ⚠ Items to verify before production (also copy into `docs/VERIFY.md`)
1. Exact wording, dates and table references for Rule 37, Rule 37A, Section 16(2)(aa), Section 16(4), Section 50 interest, and the reversal/re-claim mechanics.
2. Whether a public return-filing-status API is available via the chosen GSP, auth flow for GSTR-2B, rate limits and pricing.
3. QRMP/IFF behaviour and how it appears in GSTR-2B; current IMS functioning.
4. Tally XML specifics on the client's version (voucher fields, ledger naming, port configuration).
5. Meta WhatsApp categories, current per-message rates and free-service allowances; template approval timelines.
6. Telemarketing/consent rules and DPDP obligations for messaging suppliers and processing financial documents.
7. FalkorDB procedure names/signatures (`algo.pageRank`, shortest-path syntax, date functions) on the version in use.
8. A practising CA reviews the statuses, advice text and help copy for legal accuracy.

*Positioning statement for sales material:* "LedgerGraph prepares and checks; your accountant approves. It reports GSTR-2B match and GSTR-3B filing status and does not certify that tax has been paid."
