import pytest
from app.core.audit import record_audit_event, get_audit_trail, verify_audit_chain, compute_event_hash

def test_audit_hash_chain():
    tenant_id = "test_audit_tenant"
    
    # 1. Record series of events
    ev1 = record_audit_event(tenant_id, None, "LOGIN", "partner@demo", {"ip": "127.0.0.1"})
    ev2 = record_audit_event(tenant_id, None, "UPLOAD", "accountant@demo", {"file": "bill1.pdf"})
    ev3 = record_audit_event(tenant_id, None, "APPROVE", "partner@demo", {"invoice_id": "inv_123"})
    
    events = get_audit_trail(tenant_id, None)
    assert len(events) >= 3
    
    # 2. Verify untampered chain
    assert verify_audit_chain(events) is True

def test_audit_tamper_fails_verification():
    tenant_id = "test_tamper_tenant"
    
    ev1 = record_audit_event(tenant_id, None, "LOGIN", "u1", {"step": 1})
    ev2 = record_audit_event(tenant_id, None, "UPLOAD", "u2", {"step": 2})
    ev3 = record_audit_event(tenant_id, None, "APPROVE", "u3", {"step": 3})
    
    events = get_audit_trail(tenant_id, None)
    
    # Deliberately tamper with one event in the chain
    tampered_events = [dict(e) for e in events]
    tampered_events[1]["payload"] = {"tampered": True} # Tampering with payload
    
    # Must fail verification!
    assert verify_audit_chain(tampered_events) is False
