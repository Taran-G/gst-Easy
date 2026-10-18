# LedgerGraph — Phase-by-Phase Implementation Plan

Companion to `LedgerGraph_SRS.md` (put both in `docs/`). The SRS says **what**; this file says **how, in what order, and how to know each step is done.**

Deadline: **Sun 18 Oct 2026, 11:59 PM IST.** Plan written at ~14:45 IST.

---

## 0. How to run this with Antigravity

1. Create the repo, add `docs/SRS.md` and `docs/IMPLEMENTATION_PLAN.md`.
2. Paste the **Global Rules** (Section 1) once as the project's standing instructions.
3. Paste **one phase prompt at a time** (the block labelled "Prompt for Antigravity" in each phase). Do not give it the whole plan at once.
4. After each phase, run the phase's **Verify** commands yourself. Only continue when every box is ticked.
5. If Antigravity can run several agents in parallel, split work like this (always merge at each phase gate):
   - **Agent A (Backend/graph):** `api/`
   - **Agent B (Frontend):** `web/`
   - **Agent C (Fixtures/tests):** `fixtures/`, `api/tests/`
6. Commit at the end of every phase (`git tag p0 … p4`) so you can roll back.

### Timeline and cut-lines

| Phase | Window (IST) | Gate checkpoint | If behind, cut |
|---|---|---|---|
| P0 Foundation | 14:45–15:45 | Login → tenant switcher works | Drop email/password, use seeded login |
| P1 Ingest→Review | 15:45–17:45 | 8 fixture bills reach correct states | Skip real WhatsApp; upload + simulate only |
| P2 Graph resolution & memory | 17:45–18:45 | Approved exception changes next result | Skip fuzzy suggestions |
| P3 Tally XML + reconcile | 18:45–20:00 | XML sums to zero; recon counts match | Skip Excel export; keep on-screen tables |
| P4 Risk + graph panel | 20:00–21:30 | Full 2-minute demo runs | Skip Rule 37A re-claim UI; keep impact trace + PageRank |
| P4.5 Polish + README | 21:30–22:30 | Deployed URL + video | Skip deployment, submit with local video + repo |
| Submit | 22:30–23:30 | Submitted to all 3 tracks | Buffer; do not add features |

**Priority if time collapses:** impact trace + graph panel + PageRank + tenant switch + procedural memory > Tally XML > recon polish > everything else. The judges score what the graph visibly does.

---

## 1. Global Rules (paste once)

```
You are implementing LedgerGraph per docs/SRS.md and docs/IMPLEMENTATION_PLAN.md.

HARD RULES
1. The LLM only extracts fields from documents and drafts wording. All arithmetic,
   GST rules, status decisions and graph writes are deterministic Python. Use Decimal, never float, for money.
2. Never build Cypher by string concatenation. Use parameterised templates in api/app/graph/queries/*.cypher.
3. One FalkorDB graph per tenant: db.select_graph(f"t_{tenant_id}"). Never query across tenant graphs.
4. Every external system (WhatsApp, GSP, Tally, LLM) is behind an adapter interface with a working
   MOCK implementation that reads /fixtures. The whole app must run with no API keys except GEMINI_API_KEY
   (and even that must have a fixture-replay mode).
5. Nothing is posted, sent or reversed without an Approval record. No payment or portal actions, ever.
6. Statutory values (rates, due dates, thresholds) come from rules/rules.yaml, never hard-coded.
7. Never display "tax paid verified". Use the status vocabulary in SRS section 5.4.
8. UI: simple, spacious, sober. 5 nav items only (Home, Inbox, Reconcile, Suppliers, Settings).
   Palette and spacing from SRS section 7.2. Indian money formatting.
9. Write tests with each module. Do not mark a phase done until its Verify commands pass.
10. If something is uncertain legally or about an API, add it to docs/VERIFY.md instead of guessing.
11. Keep the repo runnable at all times: `docker compose up` must work after every phase.
```

---

## 2. Phase P0 — Foundation (≈ 60 min)

**Goal:** a running skeleton: containers up, auth, tenant graphs, empty UI shell.

### Steps
1. **Scaffold** (per SRS §3.2): `api/`, `web/`, `fixtures/`, `rules/`, `docs/`.
2. **docker-compose.yml:** services `falkordb` (image `falkordb/falkordb:latest`, port 6379), `redis`, `api` (port 8000), `web` (port 3000). Volume for FalkorDB data and for `/data/files`.
3. **api/app/core/config.py:** env settings (`FALKORDB_HOST`, `GEMINI_API_KEY`, `JWT_SECRET`, `MODE=mock|live`).
4. **api/app/graph/client.py:**
   - `get_db()` returns a `FalkorDB` client.
   - `tenant_graph(tenant_id)` → `db.select_graph(f"t_{tenant_id}")`.
   - `firm_graph(firm_id)` → `firm_<id>`.
   - `query(graph, template_name, params)` loads `queries/<template_name>.cypher`, runs with params, returns rows plus the Cypher text (needed for the UI drawer).
5. **api/app/graph/schema.py:** `bootstrap_tenant(tenant_id)` creates indexes: `Vendor(gstin)`, `Invoice(number_norm)`, `Invoice(fy)`, `GSTR2BEntry(period)`, `FilingStatus(gstin)`.
6. **Auth:** `POST /api/v1/auth/login` returning JWT with `user_id, firm_id, role`; dependency `require_tenant_access(tenant_id)` that checks the user's firm owns the tenant (this is the isolation guard; test it).
7. **Seed script** `python -m app.seed`: firm "Demo CA & Associates"; users `partner@demo` (Admin) and `accountant@demo` (Reviewer); tenants **Apex Auto Parts** and **Greenleaf Traders** with synthetic GSTINs (generate with the checksum function from P1 step 2 so they are valid).
8. **Adapter interfaces + mocks** (empty but importable): `WhatsAppPort`, `GspPort`, `TallyPort`, `ExtractorPort`.
9. **rules/rules.yaml:** GST rate set, FY start month, confidence threshold 0.85, Rule 37 alert days [120,150,170], chase limits, Rule 37A cut-off month/day, message cost table.
10. **Frontend shell** (Next.js + Tailwind + shadcn): login page; layout with left sidebar (5 items), top bar with **Client switcher** and period selector; Home with placeholder cards; global CSS tokens from SRS §7.2; `lib/api.ts` that adds `Authorization` and `X-Tenant` headers.

### Verify
- [ ] `docker compose up` starts all four services.
- [ ] `python -m app.seed` creates both tenant graphs (check with `GRAPH.LIST` in redis-cli).
- [ ] Login as accountant, switch tenant, UI shows tenant name.
- [ ] Test: accountant of firm A requesting tenant of firm B gets 403 (create a second firm in the test).

### Prompt for Antigravity
```
Implement Phase P0 of docs/IMPLEMENTATION_PLAN.md exactly. Follow Global Rules. Deliver: docker-compose,
FastAPI app with auth + tenant guard, FalkorDB client with per-tenant graphs and parameterised query loader
(returns rows AND cypher text), seed script, rules.yaml, adapter interfaces with mocks, and the Next.js shell
(login, sidebar with 5 items, tenant switcher). Then run the Verify checklist and report results.
```

---

## 3. Phase P1 — Ingest → Extract → Validate → Review (≈ 120 min)

**Goal:** a bill goes from file to the review screen with trustworthy validation.

### Steps
1. **Fixtures first** (`fixtures/bills/`): create 8 synthetic bills (images or PDFs) plus `fixtures/bills/golden/*.json` giving the correct extracted fields:
   1. `clean_intrastate.json` (CGST+SGST, ₹10,000 + ₹1,800 = ₹11,800)
   2. `clean_interstate.json` (IGST)
   3. `math_error.json` (line total wrong)
   4. `bad_gstin.json` (wrong check character)
   5. `wrong_tax_type.json` (IGST used for same-state)
   6. `wrong_buyer_gstin.json`
   7. `duplicate_of_1.json` (same supplier + number)
   8. `unknown_supplier.json`
   If time is short, generate bills as HTML→PDF from a template with Python; the golden JSON matters more than realistic looks. Add a **fixture-replay mode** to the extractor: if `MODE=mock`, return the golden JSON for a file by its hash/name.
2. **api/app/services/validate.py** — pure functions, each with unit tests:
   - `gstin_checksum_ok(gstin)`: regex `^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`, then standard mod-36 check:
     ```
     chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
     total = 0
     for i, c in enumerate(gstin[:14]):
         v = chars.index(c) * (1 if i % 2 == 0 else 2)
         total += v // 36 + v % 36
     expected = chars[(36 - total % 36) % 36]
     ok = expected == gstin[14]
     ```
   - `state_code_valid(code)` against a state-code table in `rules.yaml`.
   - `check_math(invoice)` with `Decimal`, per-line and total, ±round-off only if stated.
   - `check_tax_type(supplier_state, place_of_supply, cgst, sgst, igst)`.
   - `check_buyer_gstin(invoice, tenant)`.
   - `normalise_invoice_number(s)` (upper-case, strip spaces and leading zeros policy documented) and `fy_of(date)`.
   - `validate_invoice(invoice, tenant, is_duplicate)` returns `ValidationReport` of `{code, severity, field, message}`.
   - Codes: `MATH_MISMATCH, GSTIN_INVALID, STATE_CODE_INVALID, TAX_TYPE_MISMATCH, WRONG_BUYER_GSTIN, DUPLICATE_INVOICE, DATE_FUTURE, DATE_OLD, RATE_NOT_ALLOWED, LOW_CONFIDENCE, TDS_SUGGESTED`.
3. **api/app/adapters/llm_gemini.py:** `extract(path) -> ExtractionResult`. Use structured JSON output with the schema from SRS FR-EXT-1, temperature 0, per-field confidence, retry only on schema failure. Fixture-replay path for mock mode.
4. **Ingestion service:** `POST /ingest/upload` (multipart) → save file, SHA-256, create `:Document` node, enqueue extraction (FastAPI BackgroundTasks is fine for the hackathon). `POST /webhooks/whatsapp` accepts a **simulated payload** (`phone`, `media_path`) and routes tenant by `PhoneMap`; unrouted → `Unrouted` list. Add a UI button "Simulate WhatsApp message".
5. **Pipeline orchestrator** `process_document(doc_id)`: extract → validate → check duplicate via query `check_duplicate.cypher` → write `:Invoice` in state `DRAFT/BLOCKED/READY` → write `:Document-[:SOURCE_OF]->:Invoice`.
6. **WhatsApp reply:** one templated consolidated reply through `WhatsAppPort.send_text` (mock logs to console and to the UI activity feed).
7. **Review APIs:** `GET /inbox`, `GET /invoices/{id}`, `PATCH /invoices/{id}` (field edits re-run validation and store diffs), `POST /approve`, `POST /reject`.
8. **Audit:** `core/audit.py` appends events with a hash of the previous event; write for upload, extraction, edit, approve, reject.
9. **Frontend:**
   - Inbox list with tabs (Needs review / Blocked / Ready / All).
   - Review screen: image left (zoom), form right in groups (Supplier / Bill / Items / Tax / Totals), issues list on top in plain language, buttons Approve / Edit / Reject / Ask for better scan, Approve disabled while any BLOCK exists.
   - Upload dropzone + "Simulate WhatsApp".

### Verify
- [ ] `pytest api/tests/test_validate.py` passes (GSTIN, math, tax type, dates, duplicate).
- [ ] Each of the 8 fixtures yields the expected state and codes (table in `api/tests/test_fixtures.py`).
- [ ] Editing the wrong total in the UI clears the `MATH_MISMATCH` block live.
- [ ] Audit chain verification function passes; deliberately altering one event makes it fail.

### Prompt for Antigravity
```
Implement Phase P1 of docs/IMPLEMENTATION_PLAN.md. First generate the 8 fixture bills + golden JSON.
Then build validate.py as pure Decimal-based functions with unit tests, the Gemini extractor with fixture-replay,
ingestion + simulated WhatsApp, the process_document pipeline writing Document and Invoice nodes, review APIs,
audit hash-chain, and the Inbox + Review screens per SRS section 7. Run the Verify checklist.
```

---

## 4. Phase P2 — Graph resolution, master protection, memory (≈ 60 min)

**Goal:** the graph visibly drives decisions; approvals teach the system.

### Steps
1. **Tally masters import:** `POST /masters/import` accepting CSV (`type,name,parent,uom,gst_rate`). Fixture: `fixtures/tally_masters/apex.csv` with ledgers (e.g. "Sharma Steels (Sundry Creditors)"), tax ledgers ("Input CGST @ 9%", "Input SGST @ 9%", "Input IGST @ 18%"), purchase ledger, stock items. Creates `:TallyLedger` / `:TallyStockItem` nodes. Configuration endpoint for `TallyConfig` (tax and purchase ledger names).
2. **Vendor onboarding:** on first approval of a vendor's bill, create `:Vendor` node from supplier fields.
3. **Resolution:** implement `resolve.py` using `resolve_vendor_items.cypher` (SRS Q1). Output: ledger name, stock item, uom, applicable rules, duplicate flag.
4. **Master request cards:** if the vendor has no `MAPS_TO_LEDGER` or an item has no mapping → create `:Task {kind: 'MASTER_REQUEST'}`; UI inline card with a dropdown of existing ledgers (suggestion from fuzzy match, labelled "suggestion") and button "Map to this ledger" (Admin only). Mapping writes `[:MAPS_TO_LEDGER {approved_by, approved_at}]` and an `:ApprovalRule`.
5. **Procedural memory:** `ApprovalRule` kinds: `ITEM_MAP`, `VENDOR_HOLD_GST`, `ALWAYS_REVIEW_TDS`. When a later bill matches, the review screen shows "Applied rule from <date>, approved by <user>" and pre-fills mappings.
6. **Graph commit on approval:** approval transitions invoice to `APPROVED` and writes `:Approval`, `[:APPROVED_BY]`.
7. **Frontend:** Settings → Tally page (import masters, ledger names); master request card in Review; rule chip with tooltip.

### Verify
- [ ] Upload bill from unknown vendor → master request appears; Approve disabled until mapped.
- [ ] Map once; upload a second bill from the same vendor → no master request, rule is cited.
- [ ] Cypher drawer (JSON from API) shows the exact Q1 query and rows.
- [ ] Tenant B has none of tenant A's mappings.

### Prompt for Antigravity
```
Implement Phase P2 of docs/IMPLEMENTATION_PLAN.md: Tally masters CSV import, vendor nodes, GSTIN->ledger and
item->stock resolution via the parameterised Q1 template, master request tasks with Admin approval, ApprovalRule
procedural memory applied on the next bill, graph commit on approval. Return the cypher text with every graph call so
the UI can show it. Run Verify.
```

---

## 5. Phase P3 — Tally XML + reconciliation (≈ 75 min)

**Goal:** approved bills become importable Tally files; GSTR-2B reconciliation works.

### Steps
1. **tally_xml.py:** build the Purchase voucher envelope (SRS FR-TAL-1..6). Algorithm:
   - Party ledger: positive amount (credit), `ISDEEMEDPOSITIVE=No`.
   - Inventory entries and tax ledgers: negative amounts, `ISDEEMEDPOSITIVE=Yes`.
   - Assert `sum(amounts) == Decimal('0.00')` before returning; raise otherwise.
   - GUID: `uuid5(NAMESPACE, f"{tenant}|{gstin}|{inv_no_norm}|{fy}")`.
   - Date as `YYYYMMDD`. Ledger names from `TallyConfig` and the resolved mappings. No ledger/stock `Create`.
   - Batch exporter: `POST /tally/export` with invoice IDs → one XML file download; mark `EXPORTED`; accountant clicks "Mark as imported" → `POSTED` (creating `:TallyVoucher`).
2. **GSTR-2B import:** `GspPort.get_gstr2b` mock reads `fixtures/gstr2b/<period>.json`; plus manual upload endpoint accepting the portal JSON/Excel (parse supplier GSTIN, invoice number, date, taxable, tax). Create `:GSTR2BEntry`.
3. **Matching engine `reconcile.py`:** exact match on (gstin, normalised invoice number); if not found, near match by (gstin, amount ±₹1, date ±5 days) → `MATCHED_WITH_DIFFERENCE`. Output statuses per SRS FR-REC-2. Set `itc_status` accordingly; create `:REFLECTED_IN` edges.
4. **Timing logic:** vendor `filing_freq='QRMP'` and period before quarter end → `EXPECTED_TIMING_GAP`.
5. **`IN_2B_NOT_IN_BOOKS`:** create `:Task` "Missing bill" and a chase draft record (sending is P4).
6. **ITC summary:** `GET /itc/summary?period=` returns eligible, matched, at risk, blocked, cash-paid-not-in-2B.
7. **Reconcile screen** with three sections, plain-language advice strings, Import GSTR-2B button, Export Excel (openpyxl) with links.
8. **Fixtures:** `fixtures/gstr2b/092026.json` built so the expected outcome is: 5 matched, 1 matched-with-difference, 2 missing, 1 timing gap, 1 ghost invoice.

### Verify
- [ ] Unit test: exported XML sums to 0.00 for all clean fixtures; refuses an unbalanced input.
- [ ] Re-export of the same invoice yields the same GUID.
- [ ] Recon counts equal the fixture expectations exactly (`test_reconcile.py`).
- [ ] If a real TallyPrime is available, import the XML into a test company and record the result in `docs/VERIFY.md`.

### Prompt for Antigravity
```
Implement Phase P3 of docs/IMPLEMENTATION_PLAN.md: zero-sum Tally Purchase voucher XML builder with stable GUIDs and
config-driven ledger names, export endpoint and Mark-as-imported flow, GSTR-2B import (mock + manual upload), the
matching engine with MATCHED / MATCHED_WITH_DIFFERENCE / MISSING_IN_2B / IN_2B_NOT_IN_BOOKS / EXPECTED_TIMING_GAP,
ITC summary, and the Reconcile screen. Create the gstr2b fixtures with the expected counts and write tests for them.
```

---

## 6. Phase P4 — Risk engine, impact trace, graph panel (≈ 90 min) — the part judges see

**Goal:** the graph does visible, irreplaceable work; agents coordinate through graph state.

### Steps
1. **Extra fixtures:** supply-chain layer for Apex: `Item` nodes (e.g. "HR Steel Coil"), `CustomerOrder` nodes (e.g. Maruti-504, Maruti-511), `PurchaseOrder`, `USED_IN`, `SUPPLIES`, `FULFILLS` edges; filing statuses `fixtures/gstr3b_status/*.json` for each vendor (Sharma: filed; ABC: QRMP, pending; Delta: not filed, GSTIN status "Suspended" in one month).
2. **Filing status:** `GspPort.get_filing_status(gstin)` mock; `refresh_vendor_status()` writes `:FilingStatus` nodes and `[:COVERED_BY]` edges from invoices to the relevant 3B period.
3. **risk.py:**
   - `hold_advice(invoice)` implementing SRS FR-RSK-1 with explanation list; writes `hold_status`.
   - `rule37_aging(today)` using Q4 (or app-side age calc), producing tasks at 120/150/170 days.
   - `rule37a_candidates(fy)` using Q5; creates a reversal worksheet and `REVERSED_RULE_37A` state on CA approval; a monthly job checks late filing and creates `READY_FOR_RECLAIM` + task. Label everything "⚠ for CA review".
   - `vendor_risk_ranking()` calls PageRank (Q7), blends with ITC at risk and filing history, writes `Vendor.risk_score`. If the procedure name differs on your FalkorDB version, check `CALL dbms.procedures()` and fix; record in VERIFY.md.
4. **impact.py:** `find_impact_path(gstin, delay_days)` using Q6 + shortest-path provenance; returns `{nodes, edges, invoices, itc_exposed, orders_affected, cypher}` for the UI.
5. **MCP/tool server** `app/mcp/server.py` exposing tools in SRS FR-AGT with JSON schemas; each returns `{result, cypher, path_ids}`. Whitelist template names; no free-form Cypher writes.
6. **Three coordinated agents (graph-state hand-off):**
   - *Extractor Agent* (existing pipeline) sets `Invoice.state` and creates `:Task {kind:'RISK_CHECK'}`.
   - *Graph-Risk Agent* picks up RISK_CHECK tasks, runs risk functions, writes advice and `:Task {kind:'ACTION'}`.
   - *Action Agent* turns ACTION tasks into approval cards (chase drafts, hold advice).
   Implement as simple worker loops reading tasks from the graph; the UI shows the task trail. (An LLM may phrase explanations, but the decisions come from the code.)
7. **Chase service:** `draft_chase(invoice_id, type, language)` picks a template from a registry (English + Hindi minimum), enforces rate limits, requires approval, sends through mock `WhatsAppPort`, writes `:VendorChase` with cost from config.
8. **Frontend:**
   - Suppliers list + detail (filing strip, open invoices, ITC at risk, chase history, Draft message).
   - **Graph panel** (react-force-graph-2d): left "Ask" box with approval cards, right canvas highlighting returned nodes/edges, collapsible Cypher drawer. Quick-question chips: "If Sharma Steels is 4 days late, what breaks?", "Which supplier is riskiest?", "What tax credit is at risk this month?".
   - Reconcile → Deadlines tab (Rule 37 aging, Rule 37A items) with plain-English explanations.
   - Home cards now fed from real data.

### Verify
- [ ] The 2-minute demo script (SRS §14) runs start to finish with no manual DB edits.
- [ ] Impact trace for Sharma Steels + 4 days returns Maruti-504 and the correct ITC amount, and the canvas highlights exactly those nodes.
- [ ] PageRank ranking returns Delta Fasteners above Sharma Steels in the fixture.
- [ ] QRMP vendor before quarter-end shows "Quarterly filer, awaiting quarter-end", not a default.
- [ ] Chase is blocked on the second attempt inside 3 days and after opt-out.
- [ ] Tenant switch to Greenleaf shows a different graph with no Apex data.

### Prompt for Antigravity
```
Implement Phase P4 of docs/IMPLEMENTATION_PLAN.md. Add the supply-chain and filing-status fixtures, risk.py
(hold advice, Rule 37 aging, Rule 37A candidates, PageRank vendor ranking), impact.py (multi-hop impact + shortest-path
provenance), the MCP tool server with whitelisted templates, the three graph-state agents, the chase service with
rate limits and templates, and the UI: Suppliers, Deadlines tab, and the split graph panel with a Cypher drawer.
Every graph answer must return the Cypher and the node/edge ids to highlight. Run Verify and the full demo script.
```

---

## 7. Phase P4.5 — Polish, README, deploy, submit (≈ 60 min + 60 min buffer)

### Steps (21:30–22:30)
1. **UI pass:** empty states, skeleton loaders, error messages, tooltips for every acronym on first use, keyboard focus order, contrast check, ₹ formatting.
2. **README.md** (judges read this): problem in 5 lines; Mermaid schema diagram; the 5–7 real Cypher queries; algorithms used (PageRank, shortest path, multi-hop, multi-graph tenancy); MCP tool list; the sentence "what would break if FalkorDB were replaced by a vector DB or Postgres"; architecture diagram; run instructions (`docker compose up`, `python -m app.seed`); demo GIF; honest limits section; list of **all three tracks** entered.
3. **Seed + reset:** `make demo` that wipes and reseeds so the demo is repeatable.
4. **Deploy:** API on Railway/Render, frontend on Vercel or same host, FalkorDB Cloud free tier (or a Docker service). Set env vars; run smoke test script `scripts/smoke.sh` hitting login, upload, recon, impact.
5. **Record a 2–3 minute video** following SRS §14, narrating *why the graph is needed*.
6. **Feature freeze at 22:30.**

### Steps (22:30–23:30)
7. Submit on the WeMakeDevs page: repo link, live URL, video, description naming all three tracks. Re-check the page for any required fields. Submit by 23:15 at the latest; do not wait for 23:59.

### Verify
- [ ] Fresh clone → `docker compose up` → `make demo` works on a clean machine (or clean Docker).
- [ ] README renders the Mermaid diagram.
- [ ] Video link opens in a private window.

---

## 8. Test matrix mapping (tie to SRS §13)

| Phase | Tests that must pass |
|---|---|
| P0 | AT-15 (tenant isolation) |
| P1 | AT-1..AT-5, AT-17 |
| P2 | AT-6, AT-7 |
| P3 | AT-8, AT-9, AT-10 |
| P4 | AT-11..AT-14, AT-16 |
| P4.5 | AT-18 (quick manual run) |

---

## 9. Risks and what to do when they hit

| Risk | Response |
|---|---|
| Gemini key/quota problems | Fixture-replay mode is the demo path; live extraction shown only if working |
| FalkorDB procedure names differ | Inspect `CALL dbms.procedures()`; adapt template; note in VERIFY.md |
| Antigravity produces float money maths | Reject the change; Global Rule 1 and tests with `Decimal` |
| Frontend takes too long | Ship Inbox + Review + Graph panel first; Home and Settings can be minimal |
| Real WhatsApp/GSP temptation | Do not attempt before submission; mock adapters are fully acceptable and documented |
| Scope creep at 21:00 | Freeze list: no new tables, no new screens; only fixes |

---

## 10. After submission (not for today)
P5 bank statement import and Rule 37 accuracy → P6 live WhatsApp/GSP/Tally bridge and a real TallyPrime test → P7 vernacular templates and voice → P8 credit/debit notes, RCM, e-invoice QR → P9 pilot with 2 CA firms (14-day shadow mode, measure hours saved) → P10 billing and DPDP documentation. Have a practising CA review `docs/VERIFY.md` before any paying client.
