import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from app.graph.client import tenant_graph, query
from app.services.validate import normalise_invoice_number

def import_gstr2b_entries(tenant_id: str, period: str, entries: List[Dict[str, Any]]) -> int:
    """Stores GSTR2BEntry nodes in the tenant graph."""
    g = tenant_graph(tenant_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    count = 0
    
    for e in entries:
        supp_gstin = e.get("supplier_gstin", "").strip().upper()
        inv_no_norm = normalise_invoice_number(e.get("invoice_number", ""))
        taxable = float(e.get("taxable", 0.0))
        tax = float(e.get("tax", e.get("cgst", 0.0) + e.get("sgst", 0.0) + e.get("igst", 0.0)))
        ims = e.get("ims_action", "NO_ACTION")
        
        g.query(
            """
            MERGE (ge:GSTR2BEntry {
                period: $period,
                supplier_gstin: $gstin,
                inv_no_norm: $inv_no
            })
            SET ge.taxable = $taxable,
                ge.tax = $tax,
                ge.ims_action = $ims,
                ge.supplier_name = $supp_name,
                ge.fetched_at = $now
            """,
            {
                "period": period,
                "gstin": supp_gstin,
                "inv_no": inv_no_norm,
                "taxable": taxable,
                "tax": tax,
                "ims": ims,
                "supp_name": e.get("supplier_name", "Vendor"),
                "now": now_iso
            }
        )
        count += 1
    return count

def run_reconciliation(tenant_id: str, period: str, from_date: str = "2026-09-01", to_date: str = "2026-09-30") -> Dict[str, Any]:
    """
    Executes matching between purchase invoices in books and GSTR-2B entries.
    Produces exact counts for:
    - MATCHED
    - MATCHED_WITH_DIFFERENCE
    - MISSING_IN_2B
    - IN_2B_NOT_IN_BOOKS
    - EXPECTED_TIMING_GAP
    """
    g = tenant_graph(tenant_id)
    
    # 1. Fetch all books invoices for the period
    q_res = query(
        g,
        "reconcile_period.cypher",
        {
            "period": period,
            "from_date": from_date,
            "to_date": to_date
        }
    )
    
    # 2. Fetch all GSTR-2B entries for the period
    res_2b = g.query(
        """
        MATCH (ge:GSTR2BEntry {period: $period})
        RETURN ge.supplier_gstin, ge.inv_no_norm, ge.taxable, ge.tax, ge.supplier_name
        """,
        {"period": period}
    )
    
    entries_2b = {}
    for r in res_2b.result_set:
        key = (r[0], r[1])
        entries_2b[key] = {
            "supplier_gstin": r[0],
            "inv_no_norm": r[1],
            "taxable": float(r[2]),
            "tax": float(r[3]),
            "supplier_name": r[4],
            "matched": False
        }
        
    matched_list = []
    diff_list = []
    missing_list = []
    timing_gap_list = []
    
    # Check each book invoice
    for row in q_res["rows"]:
        supp_gstin, supp_name, filing_freq, inv_id, inv_num, norm_num, inv_date, taxable, tax, total, g_taxable, g_tax, g_period = row
        taxable = float(taxable)
        tax = float(tax)
        key = (supp_gstin, norm_num)
        
        # 1. Exact match
        if key in entries_2b:
            entry = entries_2b[key]
            entry["matched"] = True
            
            # Check for difference
            diff_taxable = abs(taxable - entry["taxable"])
            diff_tax = abs(tax - entry["tax"])
            
            if diff_taxable > 0.05 or diff_tax > 0.05:
                status = "MATCHED_WITH_DIFFERENCE"
                advice = f"Pay ₹{taxable:.2f} taxable now; ₹{abs(tax - entry['tax']):.2f} tax variance to verify with vendor."
                diff_list.append({
                    "invoice_id": inv_id,
                    "invoice_number": inv_num,
                    "supplier_gstin": supp_gstin,
                    "supplier_name": supp_name,
                    "books_taxable": taxable,
                    "books_tax": tax,
                    "gstr2b_taxable": entry["taxable"],
                    "gstr2b_tax": entry["tax"],
                    "status": status,
                    "advice": advice
                })
                # Link in graph
                g.query(
                    """
                    MATCH (i:Invoice {id: $inv_id})
                    MATCH (ge:GSTR2BEntry {period: $period, supplier_gstin: $gstin, inv_no_norm: $inv_no})
                    MERGE (i)-[:REFLECTED_IN {variance: true}]->(ge)
                    SET i.itc_status = "MATCHED_2B"
                    """,
                    {"inv_id": inv_id, "period": period, "gstin": supp_gstin, "inv_no": norm_num}
                )
            else:
                status = "MATCHED"
                advice = f"Full ITC of ₹{tax:.2f} matched in GSTR-2B. Safe to claim."
                matched_list.append({
                    "invoice_id": inv_id,
                    "invoice_number": inv_num,
                    "supplier_gstin": supp_gstin,
                    "supplier_name": supp_name,
                    "books_taxable": taxable,
                    "books_tax": tax,
                    "gstr2b_taxable": entry["taxable"],
                    "gstr2b_tax": entry["tax"],
                    "status": status,
                    "advice": advice
                })
                g.query(
                    """
                    MATCH (i:Invoice {id: $inv_id})
                    MATCH (ge:GSTR2BEntry {period: $period, supplier_gstin: $gstin, inv_no_norm: $inv_no})
                    MERGE (i)-[:REFLECTED_IN {variance: false}]->(ge)
                    SET i.itc_status = "MATCHED_2B"
                    """,
                    {"inv_id": inv_id, "period": period, "gstin": supp_gstin, "inv_no": norm_num}
                )
        else:
            # Not in 2B: Check QRMP timing gap vs true missing
            is_qrmp = (filing_freq == "QRMP")
            # Period 092026 is September (quarter-end month), but if before or supplier is quarterly:
            if is_qrmp:
                status = "EXPECTED_TIMING_GAP"
                advice = "Quarterly filer (QRMP). Awaiting quarterly GSTR-1 filing; not considered default."
                timing_gap_list.append({
                    "invoice_id": inv_id,
                    "invoice_number": inv_num,
                    "supplier_gstin": supp_gstin,
                    "supplier_name": supp_name,
                    "books_taxable": taxable,
                    "books_tax": tax,
                    "status": status,
                    "advice": advice
                })
                g.query(
                    "MATCH (i:Invoice {id: $id}) SET i.itc_status = 'EXPECTED_TIMING_GAP'",
                    {"id": inv_id}
                )
            else:
                status = "MISSING_IN_2B"
                advice = f"Hold ₹{tax:.2f} GST payment until supplier reflects bill in GSTR-1/2B."
                missing_list.append({
                    "invoice_id": inv_id,
                    "invoice_number": inv_num,
                    "supplier_gstin": supp_gstin,
                    "supplier_name": supp_name,
                    "books_taxable": taxable,
                    "books_tax": tax,
                    "status": status,
                    "advice": advice
                })
                g.query(
                    "MATCH (i:Invoice {id: $id}) SET i.itc_status = 'MISSING_2B', i.hold_status = 'ADVISE_HOLD_GST'",
                    {"id": inv_id}
                )
                
    # 3. Find Ghost Invoices: In 2B but not in books
    ghost_list = []
    for (gstin, norm_num), entry in entries_2b.items():
        if not entry["matched"]:
            advice = f"Ghost bill in GSTR-2B (₹{entry['tax']:.2f} tax). Missing in accounting books — request copy from supplier."
            ghost_list.append({
                "supplier_gstin": gstin,
                "supplier_name": entry["supplier_name"],
                "invoice_number": norm_num,
                "gstr2b_taxable": entry["taxable"],
                "gstr2b_tax": entry["tax"],
                "status": "IN_2B_NOT_IN_BOOKS",
                "advice": advice
            })
            # Create Task in graph
            task_id = f"task_missing_{gstin}_{norm_num}"
            g.query(
                """
                MERGE (t:Task {id: $task_id})
                SET t.kind = "MISSING_BILL",
                    t.state = "PENDING",
                    t.details = $details,
                    t.supplier_gstin = $gstin,
                    t.inv_number = $inv_no,
                    t.tax_at_stake = $tax
                """,
                {
                    "task_id": task_id,
                    "details": advice,
                    "gstin": gstin,
                    "inv_no": norm_num,
                    "tax": entry["tax"]
                }
            )
            
    # Calculate ITC Summary
    all_matched_tax = sum(item["books_tax"] for item in matched_list)
    diff_tax = sum(item["books_tax"] for item in diff_list)
    missing_tax = sum(item["books_tax"] for item in missing_list)
    timing_tax = sum(item["books_tax"] for item in timing_gap_list)
    
    total_eligible = all_matched_tax + diff_tax
    total_at_risk = missing_tax
    
    return {
        "period": period,
        "counts": {
            "matched": len(matched_list),
            "matched_with_difference": len(diff_list),
            "missing_in_2b": len(missing_list),
            "expected_timing_gap": len(timing_gap_list),
            "in_2b_not_in_books": len(ghost_list)
        },
        "itc_summary": {
            "matched_itc": all_matched_tax,
            "variance_itc": diff_tax,
            "at_risk_itc": total_at_risk,
            "timing_gap_itc": timing_tax,
            "total_claimable": total_eligible
        },
        "matched": matched_list,
        "matched_with_difference": diff_list,
        "missing_in_2b": missing_list,
        "expected_timing_gap": timing_gap_list,
        "in_2b_not_in_books": ghost_list
    }
