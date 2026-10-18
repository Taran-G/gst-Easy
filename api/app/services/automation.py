import asyncio
from collections import deque
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings
from app.graph.client import tenant_graph, firm_graph
from app.services.email_service import email_service
from app.services.ingest import process_document
from app.services.reconcile import run_reconciliation
from app.services.risk import check_rule_37_aging

logger = logging.getLogger(__name__)

class AutonomousAgentEngine:
    """
    Autonomous AI Agent Background Engine.
    Periodically wakes up, scans monitored channels (Gmail inbox, WhatsApp),
    ingests pending supplier bills, verifies GST compliance, auto-dispatches
    statutory confirmations and Rule 37 aging alerts, and reconciles ledgers.
    """
    def __init__(self):
        self.is_running = settings.AUTOMATION_ENABLED
        self.interval_seconds = settings.AUTOMATION_INTERVAL_SECONDS
        self.cycle_count = 0
        self.last_run: Optional[str] = None
        self.next_run: Optional[str] = None
        self.invoices_processed_count = 0
        self.alerts_generated_count = 0
        self.logs: deque = deque(maxlen=100)
        self._task: Optional[asyncio.Task] = None

    def log(self, event: str, message: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None):
        """Records an entry in the agent's live autonomous activity stream."""
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": f"log_{uuid.uuid4().hex[:8]}",
            "timestamp": now_iso,
            "event": event,
            "message": message,
            "level": level,
            "details": details or {}
        }
        self.logs.appendleft(entry)
        logger.info("[Autonomous Agent] [%s] %s", event, message)

    async def run_cycle(self, manual: bool = False) -> Dict[str, Any]:
        """
        Executes a complete autonomous cycle across all monitored statutory workflows.
        """
        self.cycle_count += 1
        now = datetime.now(timezone.utc)
        self.last_run = now.isoformat()
        self.next_run = (now + timedelta(seconds=self.interval_seconds)).isoformat()
        
        cycle_num = self.cycle_count
        trigger_label = "Manual Trigger" if manual else "Autonomous Scheduler"
        self.log("CYCLE_START", f"Cycle #{cycle_num} started via {trigger_label}.", "INFO")

        processed_this_cycle = 0
        alerts_this_cycle = 0

        # Step 1: Scan Monitored Email Inbox (Gmail IMAP or Prototype)
        try:
            unread_emails = email_service.fetch_unread_emails()
            if unread_emails:
                self.log(
                    "EMAIL_SCAN",
                    f"Discovered {len(unread_emails)} unread email(s) in monitored inbox.",
                    "INFO",
                    {"unread_count": len(unread_emails)}
                )
                
                for eml in unread_emails:
                    from_addr = eml.get("from_addr", "")
                    subject = eml.get("subject", "")
                    attachments = eml.get("attachments", [])
                    
                    if attachments:
                        for att in attachments:
                            att_path = att.get("path")
                            att_name = att.get("filename", "bill.pdf")
                            self.log(
                                "BILL_INGEST_START",
                                f"Autonomous ingestion triggered for '{att_name}' from {from_addr}.",
                                "INFO"
                            )
                            
                            # Ingest bill into default tenant apex
                            ingest_res = process_document(
                                tenant_id="apex",
                                file_path=att_path,
                                source="gmail_autonomous",
                                sender_phone="+919876543210",
                                user_id="autonomous_ai_agent"
                            )
                            
                            inv_num = ingest_res.get("invoice_number", "New")
                            total_amt = float(ingest_res.get("total_amount") or 0.0)
                            inv_state = ingest_res.get("state", "NEEDS_REVIEW")
                            inv_id = ingest_res.get("invoice_id")
                            val_issues = ingest_res.get("validation_issues", [])
                            
                            processed_this_cycle += 1
                            self.invoices_processed_count += 1
                            
                            email_service.mark_email_as_read(eml["id"], invoice_id=inv_id)
                            
                            self.log(
                                "BILL_INGEST_SUCCESS",
                                f"Bill #{inv_num} (Rs. {total_amt:,.2f}) ingested into ledger. State: {inv_state}.",
                                "SUCCESS",
                                {"invoice_id": inv_id, "state": inv_state}
                            )
                            
                            # Send automated email reply
                            if inv_state == "READY":
                                reply_body = (
                                    f"Dear Supplier,\n\n"
                                    f"Thank you for submitting your invoice #{inv_num} for Rs. {total_amt:,.2f}.\n\n"
                                    f"Our autonomous accounting system has verified your GSTIN checksum, place of supply, "
                                    f"and tax calculations. The invoice has been entered in READY status and scheduled "
                                    f"for payment authorization.\n\n"
                                    f"Best regards,\n"
                                    f"LedgerGraph CA Autonomous Accounting Desk"
                                )
                            elif inv_state == "BLOCKED":
                                issues_txt = "; ".join([iss.get("message", "") for iss in val_issues[:2]])
                                reply_body = (
                                    f"Dear Supplier,\n\n"
                                    f"Your invoice #{inv_num} for Rs. {total_amt:,.2f} could not be cleared for payment.\n\n"
                                    f"Statutory Reason: {issues_txt}\n\n"
                                    f"Please upload or reply with a rectified tax invoice to avoid payment delays.\n\n"
                                    f"Best regards,\n"
                                    f"LedgerGraph CA Autonomous Accounting Desk"
                                )
                            else:
                                reply_body = (
                                    f"Dear Supplier,\n\n"
                                    f"Your invoice #{inv_num} for Rs. {total_amt:,.2f} has been received and queued "
                                    f"for CA partner review.\n\n"
                                    f"Best regards,\n"
                                    f"LedgerGraph CA Autonomous Accounting Desk"
                                )
                                
                            email_service.send_email_reply(
                                to_addr=from_addr,
                                subject=f"Invoice #{inv_num} Receipt & GST Verification",
                                body_text=reply_body,
                                in_reply_to_id=eml["id"]
                            )
                            self.log("EMAIL_REPLY_SENT", f"Sent automated confirmation email to {from_addr}.", "INFO")
                    else:
                        # Text inquiry
                        self.log("EMAIL_QUERY", f"Received query email from {from_addr}: '{subject}'.", "INFO")
                        reply_body = (
                            f"Namaste,\n\n"
                            f"We received your message regarding '{subject}'. Our autonomous accounting engine has "
                            f"recorded your inquiry in your vendor file. For payment schedule or bill updates, "
                            f"you may also reply directly with your invoice PDF.\n\n"
                            f"Best regards,\nDemo CA & Associates"
                        )
                        email_service.send_email_reply(
                            to_addr=from_addr,
                            subject=subject,
                            body_text=reply_body,
                            in_reply_to_id=eml["id"]
                        )
                        email_service.mark_email_as_read(eml["id"])
            else:
                self.log("EMAIL_SCAN", "Monitored inbox checked. 0 new emails waiting.", "DEBUG")
        except Exception as e:
            self.log("EMAIL_ERROR", f"Error scanning emails: {str(e)}", "ERROR")

        # Step 2: Autonomous Rule 37 Aging Sweeper
        try:
            aging_invoices = check_rule_37_aging(tenant_id="apex")
            critical_aging = [inv for inv in aging_invoices if inv.get("age_days", 0) >= 150]
            if critical_aging:
                alerts_this_cycle += len(critical_aging)
                self.alerts_generated_count += len(critical_aging)
                for inv in critical_aging:
                    self.log(
                        "RULE37_ALERT",
                        f"Statutory Risk: Invoice #{inv.get('invoice_number')} is {inv.get('age_days')} days old. "
                        f"Rs. {inv.get('tax_at_stake', 0):,.2f} ITC at risk of Rule 37 reversal.",
                        "WARNING",
                        {"invoice_id": inv.get("invoice_id")}
                    )
        except Exception as e:
            self.log("RULE37_ERROR", f"Error checking Rule 37 aging: {str(e)}", "ERROR")

        # Step 3: Autonomous Reconciliation Refresh
        try:
            recon_res = run_reconciliation(tenant_id="apex", period="092026")
            counts = recon_res.get("counts", {})
            self.log(
                "RECON_CHECK",
                f"GSTR-2B Recon status: {counts.get('matched', 0)} matched, {counts.get('missing_in_2b', 0)} missing in 2B.",
                "DEBUG"
            )
        except Exception as e:
            pass

        self.log(
            "CYCLE_COMPLETE",
            f"Cycle #{cycle_num} finished. {processed_this_cycle} bill(s) processed, {alerts_this_cycle} risk alert(s) checked. Next in {self.interval_seconds}s.",
            "SUCCESS"
        )

        return {
            "cycle_number": cycle_num,
            "processed_bills": processed_this_cycle,
            "alerts": alerts_this_cycle,
            "timestamp": self.last_run
        }

    async def start_background_loop(self):
        """Starts the persistent background loop."""
        logger.info("[Autonomous Agent] Background loop started with interval %ds", self.interval_seconds)
        while True:
            try:
                if self.is_running:
                    await self.run_cycle(manual=False)
            except Exception as e:
                logger.error("[Autonomous Agent] Error in background cycle: %s", e)
            await asyncio.sleep(self.interval_seconds)

    def start(self):
        self.is_running = True
        self.log("AGENT_RESUMED", "Autonomous Agent background watcher enabled.", "SUCCESS")

    def pause(self):
        self.is_running = False
        self.log("AGENT_PAUSED", "Autonomous Agent paused by user.", "WARNING")

    def set_interval(self, seconds: int):
        self.interval_seconds = max(5, min(seconds, 3600))
        self.log("INTERVAL_CHANGED", f"Agent polling interval set to {self.interval_seconds} seconds.", "INFO")

agent_engine = AutonomousAgentEngine()
