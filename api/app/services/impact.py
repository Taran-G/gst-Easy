from typing import Any, Dict, List, Optional
from app.graph.client import tenant_graph, query

def seed_supply_chain_layer(tenant_id: str):
    """
    Populates the multi-hop supply chain network for impact tracing:
    Vendor -> Item -> CustomerOrder
    """
    g = tenant_graph(tenant_id)
    
    # 1. Create items
    g.query(
        """
        MERGE (i1:Item {name: "HR Steel Coil"})
        MERGE (i2:Item {name: "Bearing Units"})
        MERGE (i3:Item {name: "High Tensile Bolts"})
        
        MERGE (co1:CustomerOrder {number: "Maruti-504"})
        SET co1.customer = "Maruti Suzuki India Ltd",
            co1.due_date = "2026-10-25",
            co1.value = 450000.0
            
        MERGE (co2:CustomerOrder {number: "Maruti-511"})
        SET co2.customer = "Maruti Suzuki India Ltd",
            co2.due_date = "2026-11-05",
            co2.value = 320000.0
            
        MERGE (co3:CustomerOrder {number: "TataMotors-102"})
        SET co3.customer = "Tata Motors Ltd",
            co3.due_date = "2026-10-30",
            co3.value = 280000.0
            
        MERGE (i1)-[:USED_IN]->(co1)
        MERGE (i1)-[:USED_IN]->(co2)
        MERGE (i3)-[:USED_IN]->(co1)
        MERGE (i2)-[:USED_IN]->(co3)
        """
    )
    
    # 2. Connect Sharma Steels, ABC Traders, Delta Fasteners
    g.query(
        """
        MATCH (sharma:Vendor {gstin: "06AABCS1234S1Z4"}), (i1:Item {name: "HR Steel Coil"})
        MERGE (sharma)-[:SUPPLIES]->(i1)
        
        WITH sharma
        MATCH (abc:Vendor {gstin: "07AABCA5678A1ZX"}), (i2:Item {name: "Bearing Units"})
        MERGE (abc)-[:SUPPLIES]->(i2)
        
        WITH sharma
        MATCH (delta:Vendor {gstin: "06AABCD9012D1Z6"}), (i3:Item {name: "High Tensile Bolts"})
        MERGE (delta)-[:SUPPLIES]->(i3)
        """
    )

def find_impact_path(tenant_id: str, gstin: str, delay_days: int = 4) -> Dict[str, Any]:
    """
    Centerpiece hackathon query Q6:
    Given a supplier GSTIN and expected delay in days:
    Returns the downstream delivery impact, affected customer orders,
    ITC amounts at risk, highlighted node/edge IDs, and exact Cypher query.
    """
    g = tenant_graph(tenant_id)
    
    # Ensure supply chain layer exists
    seed_supply_chain_layer(tenant_id)
    
    q_res = query(g, "impact_trace.cypher", {"gstin": gstin})
    
    nodes = []
    edges = []
    orders_affected = []
    invoices_affected = []
    total_itc_exposed = 0.0
    supplier_name = ""
    
    # Track node and edge IDs for visual highlighting on graph canvas
    node_ids = set()
    edge_ids = set()
    
    for r in q_res["rows"]:
        v_gstin, v_name, item_name, co_number, customer, due_date, order_value, inv_ids, itc_exposed = r
        supplier_name = v_name
        total_itc_exposed = float(itc_exposed or 0.0)
        invoices_affected = inv_ids or []
        
        orders_affected.append({
            "order_number": co_number,
            "customer": customer,
            "due_date": due_date,
            "order_value": float(order_value or 0.0),
            "item_name": item_name,
            "delay_warning": f"{delay_days} days supplier delay jeopardizes delivery promise ({due_date}) for {customer}."
        })
        
        # Build graph node & link objects
        v_node_id = f"Vendor_{v_gstin}"
        it_node_id = f"Item_{item_name}"
        co_node_id = f"CustomerOrder_{co_number}"
        
        if v_node_id not in node_ids:
            nodes.append({"id": v_node_id, "label": v_name, "type": "Vendor", "color": "#1E3A5F"})
            node_ids.add(v_node_id)
            
        if it_node_id not in node_ids:
            nodes.append({"id": it_node_id, "label": item_name, "type": "Item", "color": "#78716C"})
            node_ids.add(it_node_id)
            
        if co_node_id not in node_ids:
            nodes.append({"id": co_node_id, "label": f"{co_number} ({customer})", "type": "CustomerOrder", "color": "#B4443C"})
            node_ids.add(co_node_id)
            
        e1_id = f"{v_node_id}->{it_node_id}"
        if e1_id not in edge_ids:
            edges.append({"source": v_node_id, "target": it_node_id, "label": "SUPPLIES"})
            edge_ids.add(e1_id)
            
        e2_id = f"{it_node_id}->{co_node_id}"
        if e2_id not in edge_ids:
            edges.append({"source": it_node_id, "target": co_node_id, "label": "USED_IN"})
            edge_ids.add(e2_id)
            
    summary_msg = (
        f"If {supplier_name or gstin} is delayed by {delay_days} days, "
        f"{len(orders_affected)} downstream customer delivery schedules are broken "
        f"including order(s) {[o['order_number'] for o in orders_affected]}, "
        f"with ₹{total_itc_exposed:.2f} of Input Tax Credit at stake."
    )
    
    return {
        "supplier_gstin": gstin,
        "supplier_name": supplier_name,
        "delay_days": delay_days,
        "itc_exposed": total_itc_exposed,
        "orders_affected": orders_affected,
        "invoices_affected": invoices_affected,
        "summary": summary_msg,
        "graph_data": {
            "nodes": nodes,
            "edges": edges,
            "highlight_node_ids": list(node_ids),
            "highlight_edge_ids": list(edge_ids)
        },
        "cypher": q_res["cypher"],
        "params": q_res["params"]
    }
