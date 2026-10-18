import logging
from app.graph.client import tenant_graph, firm_graph

logger = logging.getLogger(__name__)

TENANT_INDEXES = [
    ("Vendor", "gstin"),
    ("Invoice", "number_norm"),
    ("Invoice", "fy"),
    ("GSTR2BEntry", "period"),
    ("FilingStatus", "gstin"),
    ("WhatsAppMessage", "id"),
    ("WhatsAppMessage", "timestamp"),
]

FIRM_INDEXES = [
    ("User", "email"),
    ("Tenant", "id"),
    ("PhoneMap", "phone"),
]

def bootstrap_tenant(tenant_id: str):
    """Create indexes and constraints for an isolated tenant graph."""
    g = tenant_graph(tenant_id)
    for label, prop in TENANT_INDEXES:
        cmd = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        try:
            g.query(cmd)
            logger.info("Created index on %s(%s) for tenant %s", label, prop, tenant_id)
        except Exception as e:
            if "already indexed" in str(e).lower():
                pass
            else:
                logger.warning("Index creation warning on %s(%s): %s", label, prop, e)

def bootstrap_firm(firm_id: str):
    """Create indexes for the firm-level isolation graph."""
    g = firm_graph(firm_id)
    for label, prop in FIRM_INDEXES:
        cmd = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        try:
            g.query(cmd)
            logger.info("Created index on %s(%s) for firm %s", label, prop, firm_id)
        except Exception as e:
            if "already indexed" in str(e).lower():
                pass
            else:
                logger.warning("Index creation warning on %s(%s): %s", label, prop, e)
