import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.graph.client import tenant_graph, firm_graph

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

def compute_event_hash(prev_hash: str, timestamp: str, event_type: str, user_id: str, payload: Dict[str, Any]) -> str:
    payload_str = json.dumps(payload, sort_keys=True)
    raw = f"{prev_hash}|{timestamp}|{event_type}|{user_id}|{payload_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def record_audit_event(
    tenant_id: Optional[str],
    firm_id: Optional[str],
    event_type: str,
    user_id: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Appends an audit event to the tenant or firm graph with hash chaining."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Select graph
    if tenant_id:
        g = tenant_graph(tenant_id)
    elif firm_id:
        g = firm_graph(firm_id)
    else:
        raise ValueError("Must specify tenant_id or firm_id for audit logging")
    
    # Find latest event
    res = g.query("MATCH (e:AuditEvent) RETURN e.hash, e.timestamp ORDER BY e.timestamp DESC LIMIT 1")
    if res.result_set and len(res.result_set) > 0:
        prev_hash = res.result_set[0][0]
    else:
        prev_hash = GENESIS_HASH
        
    curr_hash = compute_event_hash(prev_hash, now_iso, event_type, user_id, payload)
    
    event_id = f"aud_{curr_hash[:12]}"
    payload_str = json.dumps(payload)
    
    # Write event node
    g.query(
        """
        CREATE (e:AuditEvent {
            id: $id,
            timestamp: $timestamp,
            event_type: $event_type,
            user_id: $user_id,
            prev_hash: $prev_hash,
            hash: $hash,
            payload: $payload
        })
        """,
        {
            "id": event_id,
            "timestamp": now_iso,
            "event_type": event_type,
            "user_id": user_id,
            "prev_hash": prev_hash,
            "hash": curr_hash,
            "payload": payload_str
        }
    )
    
    return {
        "id": event_id,
        "timestamp": now_iso,
        "event_type": event_type,
        "user_id": user_id,
        "prev_hash": prev_hash,
        "hash": curr_hash,
        "payload": payload
    }

def get_audit_trail(tenant_id: Optional[str], firm_id: Optional[str]) -> List[Dict[str, Any]]:
    if tenant_id:
        g = tenant_graph(tenant_id)
    elif firm_id:
        g = firm_graph(firm_id)
    else:
        return []
        
    res = g.query("MATCH (e:AuditEvent) RETURN e.id, e.timestamp, e.event_type, e.user_id, e.prev_hash, e.hash, e.payload ORDER BY e.timestamp ASC")
    events = []
    for r in res.result_set:
        payload_data = {}
        try:
            payload_data = json.loads(r[6]) if r[6] else {}
        except Exception:
            payload_data = {"raw": r[6]}
            
        events.append({
            "id": r[0],
            "timestamp": r[1],
            "event_type": r[2],
            "user_id": r[3],
            "prev_hash": r[4],
            "hash": r[5],
            "payload": payload_data
        })
    return events

def verify_audit_chain(events: List[Dict[str, Any]]) -> bool:
    """Verifies that the entire audit chain is untampered."""
    expected_prev = GENESIS_HASH
    for ev in events:
        if ev["prev_hash"] != expected_prev:
            return False
        calc_hash = compute_event_hash(
            ev["prev_hash"],
            ev["timestamp"],
            ev["event_type"],
            ev["user_id"],
            ev["payload"]
        )
        if ev["hash"] != calc_hash:
            return False
        expected_prev = ev["hash"]
    return True
