# LedgerGraph — Verification Register (docs/VERIFY.md)

Items marked ⚠ VERIFY in the SRS and Implementation Plan to be reviewed by a practising CA and tested against production APIs prior to live commercial deployment.

## 1. Statutory & GST Law Parameters
- [ ] **Rule 37 (180 days)**: Confirm exact reversal mechanics, reporting in GSTR-3B Table 4(B)(2), interest calculation per Section 50(1) vs 50(3) from the invoice date, and treatment of part-payments.
- [ ] **Rule 37A**: Confirm cut-off date (currently 30th November following the end of the financial year), GSTR-3B Table 4(B)(2) for reversal, Table 4(A)(5) and Table 4(D)(1) for subsequent re-claim once supplier files GSTR-3B.
- [ ] **Section 16(2)(aa)**: Mandatory GSTR-2B reflection requirement.
- [ ] **Section 16(4)**: Time limit for claiming ITC on invoices/debit notes of a financial year (30th November or annual return filing date, whichever earlier).
- [ ] **TDS under GST (Section 51)**: Threshold ₹2.5 Lakhs contract value for specified persons (DDOs, PSUs). Suggestion rule only.

## 2. API & Integration Assumptions
- [ ] **GSP APIs**: Return filing status API availability, authentication lifecycle (OTP vs AuthToken), rate limits.
- [ ] **QRMP & IFF**: Invoice Furnishing Facility appearance in GSTR-2B for months 1 and 2 of the quarter.
- [ ] **TallyPrime XML Schema**: Purchase voucher XML tags, `ISDEEMEDPOSITIVE` convention, ledger naming rules across custom charts of accounts.
- [ ] **Meta WhatsApp Cloud API**: Approved utility templates, current Indian utility template pricing per conversation, 24h customer service window rules.
- [ ] **FalkorDB Procedures**: Verify `algo.pageRank` and graph algorithms procedure signatures on target deployment.

## 3. Product Status Vocabulary Compliance
- [ ] Strict adherence: Never display "tax paid verified" or "tax paid". Always display exact status: "In GSTR-2B · GSTR-3B filed", "In GSTR-2B · GSTR-3B not filed", "Not in GSTR-2B", "Quarterly filer, awaiting quarter-end".
