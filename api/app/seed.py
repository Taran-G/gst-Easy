import csv
import logging
from pathlib import Path
from app.core.config import settings
from app.core.security import hash_password
from app.graph.client import get_db, firm_graph, tenant_graph
from app.graph.schema import bootstrap_firm, bootstrap_tenant
from app.services.resolve import create_or_update_vendor_mapping
from app.services.impact import seed_supply_chain_layer
from app.services.risk import refresh_vendor_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

# Deterministic valid synthetic GSTINs
APEX_GSTIN = "06AAACA1234A1ZO"       # Haryana, State 06
GREENLEAF_GSTIN = "24AAACG5678G1ZK"  # Gujarat, State 24

SHARMA_GSTIN = "06AABCS1234S1Z4"
ABC_GSTIN = "07AABCA5678A1ZX"
DELTA_GSTIN = "06AABCD9012D1Z6"

def wipe_database():
    logger.info("Wiping existing demo graphs for clean repeatable demo state...")
    for g_func, g_id in [(tenant_graph, "apex"), (tenant_graph, "greenleaf"), (firm_graph, "demo")]:
        try:
            g = g_func(g_id)
            g.delete()
        except Exception as e:
            pass

def seed_database(reset: bool = False):
    if reset:
        wipe_database()
    logger.info("Initializing Seed Script for LedgerGraph...")
    
    firm_id = "demo"
    fg = firm_graph(firm_id)
    bootstrap_firm(firm_id)
    
    # 1. Seed Firm and Users
    fg.query(
        """
        MERGE (f:Firm {id: $firm_id})
        SET f.name = "Demo CA & Associates"
        
        MERGE (u1:User {email: "partner@demo"})
        SET u1.id = "u_partner",
            u1.name = "CA Rajesh Sharma",
            u1.role = "Admin",
            u1.password_hash = $partner_pw
            
        MERGE (u2:User {email: "accountant@demo"})
        SET u2.id = "u_accountant",
            u2.name = "Pooja Verma",
            u2.role = "Reviewer",
            u2.password_hash = $accountant_pw
            
        MERGE (f)-[:HAS_USER]->(u1)
        MERGE (f)-[:HAS_USER]->(u2)
        """,
        {
            "firm_id": firm_id,
            "partner_pw": hash_password("partner123"),
            "accountant_pw": hash_password("accountant123"),
        }
    )
    
    # 2. Seed Tenants in Firm graph
    fg.query(
        """
        MATCH (f:Firm {id: $firm_id})
        
        MERGE (t1:Tenant {id: "apex"})
        SET t1.name = "Apex Auto Parts",
            t1.gstin = $apex_gstin,
            t1.state_code = "06",
            t1.filing_freq = "Monthly"
            
        MERGE (t2:Tenant {id: "greenleaf"})
        SET t2.name = "Greenleaf Traders",
            t2.gstin = $greenleaf_gstin,
            t2.state_code = "24",
            t2.filing_freq = "Monthly"
            
        MERGE (f)-[:OWNS_TENANT]->(t1)
        MERGE (f)-[:OWNS_TENANT]->(t2)
        
        MERGE (pm1:PhoneMap {phone: "+919876543210"})
        SET pm1.tenant_id = "apex"
        
        MERGE (pm2:PhoneMap {phone: "+919876543211"})
        SET pm2.tenant_id = "greenleaf"
        """,
        {
            "firm_id": firm_id,
            "apex_gstin": APEX_GSTIN,
            "greenleaf_gstin": GREENLEAF_GSTIN
        }
    )
    
    # 3. Bootstrap and Seed Isolated Tenant Graph: t_apex
    bootstrap_tenant("apex")
    g_apex = tenant_graph("apex")
    g_apex.query(
        """
        MERGE (t:Tenant {id: "apex"})
        SET t.name = "Apex Auto Parts",
            t.gstin = $gstin,
            t.state_code = "06",
            t.filing_freq = "Monthly"
        """,
        {"gstin": APEX_GSTIN}
    )
    
    # Import Tally Masters for Apex
    csv_path = Path(settings.FIXTURES_DIR) / "tally_masters" / "apex.csv"
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                m_type = (row.get("type") or "").strip().lower()
                name = (row.get("name") or "").strip()
                parent = (row.get("parent") or "").strip()
                uom = (row.get("uom") or "").strip()
                rate = float(row.get("gst_rate") or 0.0)
                if m_type == "ledger":
                    g_apex.query(
                        "MERGE (tl:TallyLedger {name: $name}) SET tl.parent_group = $parent, tl.gst_rate = $rate",
                        {"name": name, "parent": parent, "rate": rate}
                    )
                elif m_type == "stock_item":
                    g_apex.query(
                        "MERGE (si:TallyStockItem {name: $name}) SET si.uom = $uom, si.gst_rate = $rate",
                        {"name": name, "uom": uom, "rate": rate}
                    )
                    
    # Seed vendor details
    g_apex.query(
        """
        MERGE (v1:Vendor {gstin: $sharma})
        SET v1.legal_name = "Sharma Steels", v1.trade_name = "Sharma Steels", v1.state_code = "06"
        MERGE (v2:Vendor {gstin: $abc})
        SET v2.legal_name = "ABC Traders", v2.trade_name = "ABC Traders", v2.state_code = "07"
        MERGE (v3:Vendor {gstin: $delta})
        SET v3.legal_name = "Delta Fasteners", v3.trade_name = "Delta Fasteners", v3.state_code = "06"
        """,
        {"sharma": SHARMA_GSTIN, "abc": ABC_GSTIN, "delta": DELTA_GSTIN}
    )

    # Map Known Vendors (Sharma Steels & ABC Traders)
    create_or_update_vendor_mapping("apex", SHARMA_GSTIN, "Sharma Steels (Sundry Creditors)", "CA Rajesh Sharma")
    create_or_update_vendor_mapping("apex", ABC_GSTIN, "ABC Traders (Sundry Creditors)", "CA Rajesh Sharma")
    
    # Link known items
    g_apex.query(
        """
        MATCH (v:Vendor {gstin: $gstin})
        MATCH (si:TallyStockItem {name: "HR Steel Coil 2.5mm"})
        MERGE (vi:VendorItem {raw_name: "HR Steel Coil 2.5mm"})
        MERGE (v)-[:SUPPLIES_ITEM]->(vi)
        MERGE (vi)-[:MAPS_TO_STOCK_ITEM]->(si)
        """,
        {"gstin": SHARMA_GSTIN}
    )
    g_apex.query(
        """
        MATCH (v:Vendor {gstin: $gstin})
        MATCH (si:TallyStockItem {name: "Bearing Units 6204"})
        MERGE (vi:VendorItem {raw_name: "Bearing Units 6204"})
        MERGE (v)-[:SUPPLIES_ITEM]->(vi)
        MERGE (vi)-[:MAPS_TO_STOCK_ITEM]->(si)
        """,
        {"gstin": ABC_GSTIN}
    )
    
    # Populate supply chain and filing statuses for demo
    seed_supply_chain_layer("apex")
    refresh_vendor_status("apex", SHARMA_GSTIN)
    refresh_vendor_status("apex", ABC_GSTIN)
    refresh_vendor_status("apex", DELTA_GSTIN)
    
    # 4. Bootstrap and Seed Isolated Tenant Graph: t_greenleaf
    bootstrap_tenant("greenleaf")
    g_greenleaf = tenant_graph("greenleaf")
    g_greenleaf.query(
        """
        MERGE (t:Tenant {id: "greenleaf"})
        SET t.name = "Greenleaf Traders",
            t.gstin = $gstin,
            t.state_code = "24",
            t.filing_freq = "Monthly"
        """,
        {"gstin": GREENLEAF_GSTIN}
    )
    
    logger.info("Successfully seeded Firm 'Demo CA & Associates', 2 Users, and Tenants 'Apex Auto Parts' & 'Greenleaf Traders'.")

if __name__ == "__main__":
    import sys
    do_reset = "--reset" in sys.argv
    seed_database(reset=do_reset)
