import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.seed import seed_database
from app.graph.client import tenant_graph

client = TestClient(app)

def get_auth_token():
    res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    assert res.status_code == 200
    return res.json()["access_token"]

def get_auth_headers():
    token = get_auth_token()
    return {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

def test_whatsapp_simulate_incoming_bill():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    # Simulate receiving WhatsApp bill (Sharma Steels clean intrastate)
    res = client.post(
        "/api/v1/whatsapp/simulate/bill",
        data={
            "fixture_name": "clean_intrastate",
            "phone": "+919876543210",
            "caption": "Please find attached steel purchase invoice"
        },
        headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["state"] == "READY"
    assert data["inbound_message"]["direction"] == "INBOUND"
    assert data["inbound_message"]["sender_phone"] == "+919876543210"
    assert data["outbound_reply"]["direction"] == "OUTBOUND"
    assert "READY" in data["outbound_reply"]["text"]
    assert "Sharma Steels" in data["outbound_reply"]["text"] or "Bill" in data["outbound_reply"]["text"]
    
    # Verify both messages are in the message list
    res_list = client.get("/api/v1/whatsapp/messages", headers=headers)
    assert res_list.status_code == 200
    msgs = res_list.json()["messages"]
    assert len(msgs) >= 2
    inbound_found = any(m["direction"] == "INBOUND" and m["sender_phone"] == "+919876543210" for m in msgs)
    outbound_found = any(m["direction"] == "OUTBOUND" and "READY" in m["text"] for m in msgs)
    assert inbound_found
    assert outbound_found

def test_whatsapp_simulate_incoming_text_status_query():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    # First ingest a bill so there is an invoice in graph
    client.post(
        "/api/v1/whatsapp/simulate/bill",
        data={"fixture_name": "clean_intrastate", "phone": "+919876543210"},
        headers=headers
    )
    
    # Send text asking for status
    res = client.post(
        "/api/v1/whatsapp/simulate/text",
        json={"phone": "+919876543210", "text": "What is status of our pending bills?"},
        headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["inbound_message"]["direction"] == "INBOUND"
    assert data["outbound_reply"]["direction"] == "OUTBOUND"
    assert "Account Update" in data["outbound_reply"]["text"] or "Bill #" in data["outbound_reply"]["text"]

def test_whatsapp_simulate_incoming_text_stop_optout():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    # First ingest a bill to create vendor
    client.post(
        "/api/v1/whatsapp/simulate/bill",
        data={"fixture_name": "clean_intrastate", "phone": "+919876543210"},
        headers=headers
    )
    
    # Send STOP command
    res = client.post(
        "/api/v1/whatsapp/simulate/text",
        json={"phone": "+919876543210", "text": "STOP"},
        headers=headers
    )
    assert res.status_code == 200
    assert "unsubscribed" in res.json()["outbound_reply"]["text"].lower()

def test_whatsapp_send_outbound_agent_message():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    res = client.post(
        "/api/v1/whatsapp/send",
        json={
            "to_phone": "+919876543210",
            "text": "Your payment for bill INV-2026-001 has been scheduled for Friday.",
            "invoice_id": "inv_test123"
        },
        headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "sent"
    assert data["message"]["direction"] == "OUTBOUND"
    assert data["message"]["recipient_phone"] == "+919876543210"

def test_whatsapp_export_messages_csv():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    # Create inbound bill + auto reply
    client.post(
        "/api/v1/whatsapp/simulate/bill",
        data={"fixture_name": "clean_intrastate", "phone": "+919876543210"},
        headers=headers
    )
    # Create outbound message
    client.post(
        "/api/v1/whatsapp/send",
        json={"to_phone": "+919876543210", "text": "Audit confirmation note"},
        headers=headers
    )
    
    # Export CSV
    res = client.get("/api/v1/whatsapp/export", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    csv_text = res.text
    assert "Message ID,Timestamp (UTC),Direction" in csv_text
    assert "INBOUND" in csv_text
    assert "OUTBOUND" in csv_text
    assert "+919876543210" in csv_text
