import pytest
import os
import json

from app import app
from database import Base, engine, SessionLocal, User, Company, Customer, Quote, run_migrations
from auth import hash_password
from fastapi.testclient import TestClient
from sqlalchemy import text, inspect


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    run_migrations()

    # Seed default company & admin user for tests
    db = SessionLocal()
    try:
        default_company = Company(
            company_name="Croce e Cuore Arte Sacra",
            company_address="Via Roma 100, Roma",
            piva="12345678901",
            email="info@croceecuore.it",
            phone="+39 06 12345678"
        )
        db.add(default_company)
        db.commit()
        db.refresh(default_company)

        admin_user = User(
            username="admin",
            password_hash=hash_password("admin123"),
            role="admin",
            company_id=default_company.id
        )
        db.add(admin_user)
        db.commit()
    finally:
        db.close()

    with TestClient(app) as test_client:
        yield test_client


def test_initial_db_setup(client):
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").first()
        assert admin is not None
        assert admin.role == "admin"
        
        company = db.query(Company).first()
        assert company is not None
        assert company.company_name == "Croce e Cuore Arte Sacra"


def test_auto_migration_missing_columns(client):
    # Simulate an old schema by dropping quotes table and creating it without 'version' column
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS quotes"))
        conn.execute(text("""
            CREATE TABLE quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                quote_number VARCHAR NOT NULL,
                customer_name VARCHAR DEFAULT '',
                customer_address VARCHAR DEFAULT '',
                contact_person VARCHAR DEFAULT '',
                oggetto VARCHAR DEFAULT '',
                quote_date VARCHAR DEFAULT '',
                final_notes TEXT DEFAULT '',
                items_json TEXT DEFAULT '[]',
                total_amount VARCHAR DEFAULT '0.00',
                created_at VARCHAR DEFAULT ''
            )
        """))
    
    # Confirm version column is missing
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("quotes")]
    assert "version" not in cols

    # Run auto migration
    run_migrations()

    # Confirm version column now exists
    inspector = inspect(engine)
    cols_after = [c["name"] for c in inspector.get_columns("quotes")]
    assert "version" in cols_after


def test_auth_login(client):
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


def test_admin_user_and_company_management(client):
    login_resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create company
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

    # Update company
    update_comp_resp = client.put(f"/api/admin/companies/{comp_id}", headers=headers, json={
        "company_name": "Azienda Modificata",
        "phone": "+39 02 88888"
    })
    assert update_comp_resp.status_code == 200
    assert update_comp_resp.json()["company_name"] == "Azienda Modificata"

    # Upload company logo
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

    # Create user
    user_resp = client.post("/api/admin/users", headers=headers, json={
        "username": "utente_test_unique",
        "password": "userpass123",
        "role": "user",
        "company_id": comp_id
    })
    assert user_resp.status_code == 200
    user_data = user_resp.json()
    assert user_data["username"] == "utente_test_unique"
    user_id = user_data["id"]

    # Update user
    update_user_resp = client.put(f"/api/admin/users/{user_id}", headers=headers, json={
        "username": "utente_aggiornato"
    })
    assert update_user_resp.status_code == 200
    assert update_user_resp.json()["username"] == "utente_aggiornato"

    # Login with updated username
    u_login = client.post("/api/login", json={"username": "utente_aggiornato", "password": "userpass123"})
    assert u_login.status_code == 200
    u_token = u_login.json()["access_token"]
    u_headers = {"Authorization": f"Bearer {u_token}"}

    u_me = client.get("/api/me", headers=u_headers)
    assert u_me.status_code == 200
    assert u_me.json()["company"]["company_name"] == "Azienda Modificata"

    # Delete company
    del_comp_resp = client.delete(f"/api/admin/companies/{comp_id}", headers=headers)
    assert del_comp_resp.status_code == 200


def test_customer_management_and_quote(client):
    login_resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create customer
    c_resp = client.post("/api/customers", headers=headers, json={
        "name": "Cliente Iniziale Srl",
        "address": "Via Roma 10, Roma",
        "contact": "Marco Rossi"
    })
    assert c_resp.status_code == 200
    cust_id = c_resp.json()["id"]

    # Update customer
    c_update = client.put(f"/api/customers/{cust_id}", headers=headers, json={
        "name": "Cliente Modificato Srl",
        "contact": "Giuseppe Verdi"
    })
    assert c_update.status_code == 200
    assert c_update.json()["name"] == "Cliente Modificato Srl"
    assert c_update.json()["contact"] == "Giuseppe Verdi"

    payload = {
        "quote_number": "PREV-2026-0001",
        "data": {
            "customer_name": "Cliente Modificato Srl",
            "customer_address": "Via Roma 10, Roma",
            "contact_person": "Giuseppe Verdi",
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
    assert target_quote["version"] == 1

    dl_resp = client.get(f"/api/quotes/{quote_id}/download", headers=headers)
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"

    # Test auto-incrementing version for same quote number
    pdf_resp_v2 = client.post("/api/quotes/generate-pdf", headers=headers, json=payload)
    assert pdf_resp_v2.status_code == 200

    archive_resp2 = client.get("/api/quotes", headers=headers)
    quotes2 = archive_resp2.json()
    v2_quote = next(q for q in quotes2 if q["quote_number"] == "PREV-2026-0001" and q["version"] == 2)
    assert v2_quote is not None

    # Test explicit new version endpoint
    new_ver_resp = client.post(f"/api/quotes/{v2_quote['id']}/new-version", headers=headers)
    assert new_ver_resp.status_code == 200
    new_ver_data = new_ver_resp.json()
    assert new_ver_data["version"] == 3

    # Test GET single quote details endpoint
    quote_details_resp = client.get(f"/api/quotes/{new_ver_data['new_quote_id']}", headers=headers)
    assert quote_details_resp.status_code == 200
    assert quote_details_resp.json()["version"] == 3
    assert len(quote_details_resp.json()["items"]) == 1
