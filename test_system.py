import pytest
import os
import json

from app import app
from database import Base, engine, SessionLocal, User, Company, Customer, Quote
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def test_initial_db_setup():
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").first()
        assert admin is not None
        assert admin.role == "admin"
        
        company = db.query(Company).first()
        assert company is not None
        assert company.company_name == "Croce e Cuore Arte Sacra"


def test_auth_login():
    response = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "admin"
    token = data["access_token"]

    me_resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == "admin"


def test_admin_user_and_company_management():
    login_resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    comp_resp = client.post("/api/admin/companies", headers=headers, json={
        "company_name": "Nuova Azienda Test",
        "company_address": "Via Test 123",
        "piva": "98765432101",
        "email": "test@azienda.it",
        "phone": "+39 02 99999"
    })
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()
    comp_id = comp_data["id"]

    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
    logo_resp = client.post(
        f"/api/admin/companies/{comp_id}/logo",
        headers=headers,
        files={"logo": ("logo.png", dummy_png, "image/png")}
    )
    assert logo_resp.status_code == 200

    get_logo_resp = client.get(f"/api/companies/{comp_id}/logo")
    assert get_logo_resp.status_code == 200
    assert get_logo_resp.content == dummy_png

    user_resp = client.post("/api/admin/users", headers=headers, json={
        "username": "utente_test_unique",
        "password": "userpass123",
        "role": "user",
        "company_id": comp_id
    })
    assert user_resp.status_code == 200
    user_data = user_resp.json()
    assert user_data["username"] == "utente_test_unique"

    u_login = client.post("/api/login", json={"username": "utente_test_unique", "password": "userpass123"})
    assert u_login.status_code == 200
    u_token = u_login.json()["access_token"]
    u_headers = {"Authorization": f"Bearer {u_token}"}

    u_me = client.get("/api/me", headers=u_headers)
    assert u_me.status_code == 200
    assert u_me.json()["company"]["company_name"] == "Nuova Azienda Test"


def test_quote_pdf_and_archive():
    login_resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "quote_number": "PREV-2026-0001",
        "data": {
            "customer_name": "Cliente Test Srl",
            "customer_address": "Via Roma 1, Milano",
            "contact_person": "Mario Rossi",
            "oggetto": "Fornitura Articoli Sacri",
            "quote_date": "05/08/2026",
            "final_notes": "Consegna entro 30 giorni."
        },
        "items": [
            {
                "name": "Statua in legno",
                "quantity": 2,
                "unit_price": 500.0,
                "total": 1000.0,
                "vat_percent": 22.0,
                "total_with_vat": 1220.0
            }
        ]
    }

    pdf_resp = client.post("/api/quotes/generate-pdf", headers=headers, json=payload)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 1000

    archive_resp = client.get("/api/quotes", headers=headers)
    assert archive_resp.status_code == 200
    quotes = archive_resp.json()
    assert len(quotes) >= 1
    
    found = any(q["quote_number"] == "PREV-2026-0001" for q in quotes)
    assert found

    target_quote = next(q for q in quotes if q["quote_number"] == "PREV-2026-0001")
    quote_id = target_quote["id"]
    dl_resp = client.get(f"/api/quotes/{quote_id}/download", headers=headers)
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"

    cust_resp = client.get("/api/customers", headers=headers)
    assert cust_resp.status_code == 200
    customers = cust_resp.json()
    assert any(c["name"] == "Cliente Test Srl" for c in customers)
