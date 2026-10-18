import json
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
from app.core.rules import get_rules
from app.graph.client import tenant_graph, query
from app.adapters.gsp_mock import MockGspAdapter

gsp_mock = MockGspAdapter()

def refresh_vendor_status(tenant_id: str, gstin: str) -> Dict[str, Any]:
    """
    Fetches filing status from GspPort mock and writes :FilingStatus nodes
    and [:HAS_STATUS] / [:COVERED_BY] edges.
    """
    g = tenant_graph(tenant_id)
    status_data = gsp_mock.get_filing_status(gstin)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Update vendor master fields
    g.query(
        """
        MERGE (v:Vendor {gstin: $gstin})
        SET v.gstin_status = $status,
            v.filing_freq = $freq,
            v.last_status_check = $now
        """,
        {
            "gstin": gstin,
            "status": status_data.get("status", "Active"),
            "freq": status_data.get("filing_freq", "Monthly"),
            "now": now_iso
        }
    )
    
    # Write filing statuses
    for f in status_data.get("filings", []):
        period = f["period"]
        form = f["form"]
        f_status = f["status"]
        filed_on = f.get("filed_on")
        
        g.query(
            """
            MATCH (v:Vendor {gstin: $gstin})
            MERGE (fs:FilingStatus {gstin: $gstin, period: $period, form: $form})
            SET fs.status = $f_status,
                fs.filed_on = $filed_on,
                fs.fetched_at = $now
            MERGE (v)-[:HAS_STATUS]->(fs)
            """,
            {
                "gstin": gstin,
                "period": period,
                "form": form,
                "f_status": f_status,
                "filed_on": filed_on,
                "now": now_iso
            }
        )
        
    return status_data

def get_supplier_display_label(in_2b: bool, gstr3b_status: Optional[str], filing_freq: str) -> str:
    """Strict status vocabulary per SRS section 5.4. Never 'Tax paid verified'."""
    if in_2b:
        if gstr3b_status == "FILED":
            return "In GSTR-2B · GSTR-3B filed"
        else:
            return "In GSTR-2B · GSTR-3B not filed"
    else:
        if filing_freq == "QRMP":
            return "Quarterly filer, awaiting quarter-end"
        return "Not in GSTR-2B"

def calculate_hold_advice(tenant_id: str, period: str = "092026") -> List[Dict[str, Any]]:
    """
    Computes payment hold advice (FR-RSK-1):
    - release_now vs hold amounts
    - based on 2B presence, GSTR-3B return status, GSTIN status
    """
    g = tenant_graph(tenant_id)
    q_res = query(g, "hold_advice.cypher", {"period": period})
    
    advice_list = []
    for r in q_res["rows"]:
        gstin, gstin_status, filing_freq, inv_id, total, tax, in_2b, gstr3b_status = r
        total = float(total)
        tax = float(tax)
        in_2b = bool(in_2b)
        
        explanations = []
        status_label = get_supplier_display_label(in_2b, gstr3b_status, filing_freq or "Monthly")
        
        if gstin_status == "Suspended" or gstin_status == "Cancelled":
            hold_amt = total
            release_amt = 0.0
            hold_status = "ADVISE_HOLD_GST"
            explanations.append(f"Supplier GSTIN registration is {gstin_status}! Immediate risk of complete ITC loss.")
        elif not in_2b:
            if filing_freq == "QRMP":
                hold_amt = 0.0
                release_amt = total
                hold_status = "ADVISE_RELEASE_ALL"
                explanations.append("Supplier is under quarterly filing (QRMP). Awaiting quarter-end filing; no hold advised.")
            else:
                hold_amt = tax
                release_amt = total - tax
                hold_status = "ADVISE_HOLD_GST"
                explanations.append(f"Bill not reflected in GSTR-2B. Advise holding GST amount (₹{tax:.2f}) until supplier uploads.")
        elif gstr3b_status != "FILED":
            hold_amt = tax
            release_amt = total - tax
            hold_status = "ADVISE_HOLD_GST"
            explanations.append(f"Bill reflected in GSTR-2B, but supplier has not filed GSTR-3B for {period}. Hold tax of ₹{tax:.2f}.")
        else:
            hold_amt = 0.0
            release_amt = total
            hold_status = "ADVISE_RELEASE_ALL"
            explanations.append(f"Bill confirmed in GSTR-2B and supplier GSTR-3B filed on portal. Safe to release full payment of ₹{total:.2f}.")
            
        advice_list.append({
            "invoice_id": inv_id,
            "supplier_gstin": gstin,
            "total_amount": total,
            "tax_amount": tax,
            "release_now": release_amt,
            "hold_amount": hold_amt,
            "hold_status": hold_status,
            "display_label": status_label,
            "explanations": explanations
        })
        
        # Update invoice hold_status in graph
        g.query("MATCH (i:Invoice {id: $id}) SET i.hold_status = $hs", {"id": inv_id, "hs": hold_status})
        
    return advice_list

def check_rule_37_aging(tenant_id: str, today_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Evaluates unpaid invoices approaching or exceeding 180 days (Rule 37).
    Generates alert tasks at 120, 150, 170 days.
    """
    g = tenant_graph(tenant_id)
    today = today_date or date(2026, 10, 18)
    rules = get_rules()
    alert_days_set = rules.rule_37_alert_days # [120, 150, 170]
    
    q_res = query(g, "rule37_aging.cypher")
    alerts = []
    
    for r in q_res["rows"]:
        gstin, vendor_name, inv_id, inv_number, inv_date_str, total, tax = r
        try:
            inv_date = datetime.strptime(inv_date_str[:10], "%Y-%m-%d").date()
            age_days = (today - inv_date).days
        except Exception:
            continue
            
        if age_days >= 120:
            severity = "DANGER" if age_days >= 170 else ("WARNING" if age_days >= 150 else "INFO")
            msg = (
                f"Invoice #{inv_number} ({vendor_name}) is {age_days} days unpaid. "
                f"Statutory reversal of ₹{float(tax):.2f} required under Rule 37 after 180 days."
            )
            alerts.append({
                "invoice_id": inv_id,
                "invoice_number": inv_number,
                "vendor_name": vendor_name,
                "vendor_gstin": gstin,
                "invoice_date": inv_date_str,
                "age_days": age_days,
                "tax_at_stake": float(tax),
                "total_amount": float(total),
                "severity": severity,
                "message": msg
            })
            
            # Create Task in graph if >= 150 days
            if age_days >= 150:
                task_id = f"task_r37_{inv_id}"
                g.query(
                    """
                    MERGE (t:Task {id: $task_id})
                    SET t.kind = "RULE_37_ALERT",
                        t.details = $msg,
                        t.age_days = $age_days,
                        t.state = "PENDING"
                    """,
                    {"task_id": task_id, "msg": msg, "age_days": age_days}
                )
    return alerts

def get_rule37a_candidates(tenant_id: str, fy: str = "2026-27", period: str = "092026") -> List[Dict[str, Any]]:
    """
    Identifies candidates for Rule 37A reversal due to supplier non-filing of GSTR-3B.
    """
    g = tenant_graph(tenant_id)
    q_res = query(g, "rule37a_candidates.cypher", {"fy": fy, "period": period})
    
    candidates = []
    for r in q_res["rows"]:
        gstin, vendor_name, inv_id, inv_num, total, rev_amt = r
        candidates.append({
            "supplier_gstin": gstin,
            "vendor_name": vendor_name,
            "invoice_id": inv_id,
            "invoice_number": inv_num,
            "total_amount": float(total),
            "reversal_amount": float(rev_amt),
            "reason": f"Supplier GSTR-3B for {period} not filed past statutory cut-off. ⚠ For CA review."
        })
    return candidates

def calculate_vendor_risk_ranking(tenant_id: str, top_n: int = 10) -> List[Dict[str, Any]]:
    """
    Blends FalkorDB PageRank with ITC value at risk and filing history.
    """
    g = tenant_graph(tenant_id)
    
    # 1. Run PageRank on Vendor SUPPLIES Item graph
    pagerank_scores = {}
    try:
        pr_res = query(g, "vendor_pagerank.cypher", {"n": top_n})
        for r in pr_res["rows"]:
            pagerank_scores[r[0]] = float(r[2])
    except Exception as e:
        # Fallback if supplies edges not yet loaded
        pass

    # 2. Query all vendors, invoices, and filing statuses
    v_res = g.query(
        """
        MATCH (v:Vendor)
        OPTIONAL MATCH (v)-[:ISSUED]->(i:Invoice)
        OPTIONAL MATCH (v)-[:HAS_STATUS]->(fs:FilingStatus {form: 'GSTR3B'})
        RETURN v.gstin, v.legal_name, v.gstin_status, v.filing_freq,
               sum(i.cgst + i.sgst + i.igst) AS total_itc,
               count(i) AS invoice_count,
               collect(fs.status) AS filing_statuses
        """
    )
    
    ranking = []
    for r in v_res.result_set:
        gstin, name, g_status, freq, total_itc, inv_count, f_statuses = r
        total_itc = float(total_itc or 0.0)
        inv_count = int(inv_count or 0)
        
        pr_score = pagerank_scores.get(gstin, 0.15)
        
        # Penalties:
        # Suspended / cancelled status: severe penalty
        status_penalty = 0.5 if g_status in ["Suspended", "Cancelled"] else 0.0
        # Non-filing penalty
        not_filed_count = f_statuses.count("NOT_FILED")
        filing_penalty = min(0.4, not_filed_count * 0.2)
        
        # Combined risk score (0 to 1)
        risk_score = round(min(1.0, pr_score + status_penalty + filing_penalty + (0.1 if total_itc > 20000 else 0.0)), 3)
        
        # Write back to Vendor node
        g.query("MATCH (v:Vendor {gstin: $gstin}) SET v.risk_score = $score", {"gstin": gstin, "score": risk_score})
        
        risk_level = "High" if risk_score >= 0.6 else ("Medium" if risk_score >= 0.35 else "Low")
        
        ranking.append({
            "gstin": gstin,
            "legal_name": name,
            "gstin_status": g_status or "Active",
            "filing_freq": freq or "Monthly",
            "risk_score": risk_score,
            "risk_level": risk_level,
            "pagerank_score": pr_score,
            "total_itc_at_risk": total_itc if (status_penalty > 0 or filing_penalty > 0) else 0.0,
            "total_itc": total_itc,
            "invoice_count": inv_count
        })
        
    ranking.sort(key=lambda x: x["risk_score"], reverse=True)
    return ranking[:top_n]
