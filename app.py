import os
import tempfile
import json
import secrets
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, status, Response, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from database import Base, engine, get_db, Company, User, Customer, Quote
from auth import hash_password, verify_password, create_access_token, get_current_user, require_admin
import schemas
from pdf_generator import generate_quote_pdf


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create DB tables
    Base.metadata.create_all(bind=engine)

    # 2. Ensure initial default company & admin user exist
    db = next(get_db())
    try:
        default_company = db.query(Company).first()
        if not default_company:
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

        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_password = os.environ.get("ADMIN_INITIAL_PASSWORD", "admin123")
            admin_user = User(
                username="admin",
                password_hash=hash_password(admin_password),
                role="admin",
                company_id=default_company.id
            )
            db.add(admin_user)
            db.commit()
    finally:
        db.close()

    yield


app = FastAPI(title="Preventivatore API", lifespan=lifespan)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- PAGE ROUTES ---
@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/login")
async def login_page():
    return FileResponse("static/login.html")

@app.get("/admin")
async def admin_page():
    return FileResponse("static/admin.html")


# --- AUTH ENDPOINTS ---
@app.post("/api/login", response_model=schemas.TokenResponse)
async def login(payload: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nome utente o password errati"
        )

    token = create_access_token(data={"sub": str(user.id), "username": user.username, "role": user.role})
    
    # Also set HTTP cookie for browser navigation
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
        samesite="lax"
    )

    return schemas.TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        role=user.role
    )

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"status": "success", "message": "Logout effettuato"}

@app.get("/api/me")
async def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_data = None
    if current_user.company:
        company_data = schemas.CompanyResponse.model_validate(current_user.company)
    
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "company_id": current_user.company_id,
        "company": company_data
    }


# --- ADMIN USER MANAGEMENT ---
@app.get("/api/admin/users", response_model=List[schemas.UserResponse])
async def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

@app.post("/api/admin/users", response_model=schemas.UserResponse)
async def create_user(payload: schemas.UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == payload.username.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nome utente già in uso")

    new_user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        company_id=payload.company_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.put("/api/admin/users/{user_id}", response_model=schemas.UserResponse)
async def update_user(user_id: int, payload: schemas.UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    if payload.username and payload.username.strip() != user.username:
        existing = db.query(User).filter(User.username == payload.username.strip()).first()
        if existing:
            raise HTTPException(status_code=400, detail="Nome utente già in uso")
        user.username = payload.username.strip()

    if payload.password:
        user.password_hash = hash_password(payload.password)

    if payload.role:
        user.role = payload.role

    if payload.company_id is not None:
        user.company_id = payload.company_id

    db.commit()
    db.refresh(user)
    return user

@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="Impossibile eliminare il proprio account amministratore")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    db.delete(user)
    db.commit()
    return {"status": "success", "message": "Utente eliminato"}


# --- ADMIN COMPANY MANAGEMENT ---
@app.get("/api/admin/companies", response_model=List[schemas.CompanyResponse])
async def list_companies(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Company).all()

@app.post("/api/admin/companies", response_model=schemas.CompanyResponse)
async def create_company(payload: schemas.CompanyCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    company = Company(**payload.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company

@app.put("/api/admin/companies/{company_id}", response_model=schemas.CompanyResponse)
async def update_company(company_id: int, payload: schemas.CompanyUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Azienda non trovata")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(company, key, value)

    db.commit()
    db.refresh(company)
    return company

@app.post("/api/admin/companies/{company_id}/logo")
async def upload_company_logo(company_id: int, logo: UploadFile = File(...), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Azienda non trovata")

    contents = await logo.read()
    company.logo_data = contents
    company.logo_filename = logo.filename

    db.commit()
    return {"status": "success", "message": "Logo caricato con successo"}

@app.get("/api/companies/{company_id}/logo")
async def get_company_logo(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company or not company.logo_data:
        raise HTTPException(status_code=404, detail="Logo non presente")

    media_type = "image/png"
    if company.logo_filename:
        if company.logo_filename.endswith(".jpg") or company.logo_filename.endswith(".jpeg"):
            media_type = "image/jpeg"
        elif company.logo_filename.endswith(".svg"):
            media_type = "image/svg+xml"

    return Response(content=company.logo_data, media_type=media_type)


@app.delete("/api/admin/companies/{company_id}")
async def delete_company(company_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Azienda non trovata")

    total_companies = db.query(Company).count()
    if total_companies <= 1:
        raise HTTPException(status_code=400, detail="Impossibile eliminare l'unica azienda presente nel sistema")

    db.delete(company)
    db.commit()
    return {"status": "success", "message": "Azienda eliminata"}


# --- CUSTOMER REGISTRY ---
@app.get("/api/customers", response_model=List[schemas.CustomerResponse])
async def list_customers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.company_id:
        return []
    return db.query(Customer).filter(Customer.company_id == user.company_id).all()

@app.post("/api/customers", response_model=schemas.CustomerResponse)
async def create_or_update_customer(payload: schemas.CustomerCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.company_id:
        raise HTTPException(status_code=400, detail="L'utente non è associato a nessuna azienda")

    customer_name = payload.name.strip()
    customer = db.query(Customer).filter(Customer.company_id == user.company_id, Customer.name == customer_name).first()
    if customer:
        if payload.address: customer.address = payload.address
        if payload.contact: customer.contact = payload.contact
    else:
        customer = Customer(
            company_id=user.company_id,
            name=customer_name,
            address=payload.address or "",
            contact=payload.contact or ""
        )
        db.add(customer)

    db.commit()
    db.refresh(customer)
    return customer

@app.put("/api/customers/{customer_id}", response_model=schemas.CustomerResponse)
async def update_customer(customer_id: int, payload: schemas.CustomerUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.company_id == user.company_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    if payload.name is not None and payload.name.strip():
        customer.name = payload.name.strip()
    if payload.address is not None:
        customer.address = payload.address
    if payload.contact is not None:
        customer.contact = payload.contact

    db.commit()
    db.refresh(customer)
    return customer

@app.delete("/api/customers/{customer_id}")
async def delete_customer(customer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.company_id == user.company_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    db.delete(customer)
    db.commit()
    return {"status": "success", "message": "Cliente eliminato"}


# --- QUOTES & PDF GENERATION ---
@app.post("/api/quotes/generate-pdf")
async def generate_pdf_endpoint(
    payload: schemas.QuotePayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Load user company settings
        company = None
        if user.company_id:
            company = db.query(Company).filter(Company.id == user.company_id).first()

        # Fill company data if missing in payload
        if company:
            if not payload.data.company_name: payload.data.company_name = company.company_name
            if not payload.data.company_address: payload.data.company_address = company.company_address
            if not payload.data.piva: payload.data.piva = company.piva
            if not payload.data.email: payload.data.email = company.email
            if not payload.data.phone: payload.data.phone = company.phone

        # Handle Logo Temporary File if present in DB
        temp_logo_path = None
        if company and company.logo_data:
            ext = ".png"
            if company.logo_filename and "." in company.logo_filename:
                ext = f".{company.logo_filename.split('.')[-1]}"
            logo_fd, temp_logo_path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(logo_fd, 'wb') as f:
                f.write(company.logo_data)
            payload.data.logo_path = temp_logo_path

        # Generate quote number if empty
        if not payload.quote_number:
            count = db.query(Quote).filter(Quote.company_id == (user.company_id or 1)).count() + 1
            year = datetime.now().strftime("%Y")
            payload.quote_number = f"PREV-{year}-{count:04d}"

        # Create temporary file for PDF
        fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        # Convert items to list of dicts for ReportLab
        items_dict = [item.model_dump() for item in payload.items]
        data_dict = payload.data.model_dump()

        # Calculate totals
        total_amount = sum(item.total_with_vat for item in payload.items)
        total_amount_str = f"{total_amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

        # Generate PDF with ReportLab
        pdf_path = generate_quote_pdf(items_dict, data_dict, temp_pdf_path)

        # Automatically save quote to Customer Anagrafica & Quote Archive
        if user.company_id:
            if payload.data.customer_name and payload.data.customer_name.strip():
                c_name = payload.data.customer_name.strip()
                existing_c = db.query(Customer).filter(Customer.company_id == user.company_id, Customer.name == c_name).first()
                if not existing_c:
                    db.add(Customer(
                        company_id=user.company_id,
                        name=c_name,
                        address=payload.data.customer_address or "",
                        contact=payload.data.contact_person or ""
                    ))

            items_json_str = json.dumps([item.model_dump() for item in payload.items], default=str)
            quote_record = Quote(
                company_id=user.company_id,
                user_id=user.id,
                quote_number=payload.quote_number,
                customer_name=payload.data.customer_name or "",
                customer_address=payload.data.customer_address or "",
                contact_person=payload.data.contact_person or "",
                oggetto=payload.data.oggetto or "",
                quote_date=payload.data.quote_date or datetime.now().strftime("%d/%m/%Y"),
                final_notes=payload.data.final_notes or "",
                items_json=items_json_str,
                total_amount=total_amount_str,
                created_at=datetime.now().isoformat()
            )
            db.add(quote_record)
            db.commit()

        def iterfile():
            try:
                with open(pdf_path, mode="rb") as file_like:
                    while chunk := file_like.read(8192):
                        yield chunk
            finally:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                if temp_logo_path and os.path.exists(temp_logo_path):
                    os.remove(temp_logo_path)

        filename = f"preventivo_{payload.quote_number}.pdf"
        return StreamingResponse(
            iterfile(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        if 'temp_pdf_path' in locals() and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
        if 'temp_logo_path' in locals() and temp_logo_path and os.path.exists(temp_logo_path):
            os.remove(temp_logo_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quotes", response_model=List[schemas.QuoteResponse])
async def list_quotes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "admin":
        quotes = db.query(Quote).order_by(Quote.id.desc()).all()
    else:
        if not user.company_id:
            return []
        quotes = db.query(Quote).filter(Quote.company_id == user.company_id).order_by(Quote.id.desc()).all()
    return quotes


@app.get("/api/quotes/{quote_id}/download")
async def download_archived_quote_pdf(
    quote_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Preventivo non trovato")

    if user.role != "admin" and quote.company_id != user.company_id:
        raise HTTPException(status_code=403, detail="Accesso negato")

    company = db.query(Company).filter(Company.id == quote.company_id).first()
    
    # Temporary logo
    temp_logo_path = None
    if company and company.logo_data:
        ext = ".png"
        if company.logo_filename and "." in company.logo_filename:
            ext = f".{company.logo_filename.split('.')[-1]}"
        logo_fd, temp_logo_path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(logo_fd, 'wb') as f:
            f.write(company.logo_data)

    data_dict = {
        "company_name": company.company_name if company else "",
        "company_address": company.company_address if company else "",
        "piva": company.piva if company else "",
        "email": company.email if company else "",
        "phone": company.phone if company else "",
        "logo_path": temp_logo_path or "",
        "quote_date": quote.quote_date,
        "customer_name": quote.customer_name,
        "customer_address": quote.customer_address,
        "contact_person": quote.contact_person,
        "oggetto": quote.oggetto,
        "final_notes": quote.final_notes
    }

    items_dict = json.loads(quote.items_json) if quote.items_json else []

    fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)

    pdf_path = generate_quote_pdf(items_dict, data_dict, temp_pdf_path)

    def iterfile():
        try:
            with open(pdf_path, mode="rb") as file_like:
                while chunk := file_like.read(8192):
                    yield chunk
        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if temp_logo_path and os.path.exists(temp_logo_path):
                os.remove(temp_logo_path)

    filename = f"preventivo_{quote.quote_number}.pdf"
    return StreamingResponse(
        iterfile(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.delete("/api/quotes/{quote_id}")
async def delete_quote(quote_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Preventivo non trovato")

    if user.role != "admin" and quote.company_id != user.company_id:
        raise HTTPException(status_code=403, detail="Accesso negato")

    db.delete(quote)
    db.commit()
    return {"status": "success", "message": "Preventivo eliminato dallo storico"}
