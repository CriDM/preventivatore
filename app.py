from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
import tempfile
import os
import secrets
import woo_sync
from pdf_generator import generate_quote_pdf
from database import get_db, CompanySettings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from database import Base, engine
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Preventivatore API", lifespan=lifespan)
security = HTTPBasic()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    expected_password = os.environ.get("API_PASSWORD", "Antonio2026")
    is_correct_password = secrets.compare_digest(credentials.password, expected_password)
    if not is_correct_password:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

class QuoteItem(BaseModel):
    name: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    vat_percent: Decimal
    total_with_vat: Decimal

class QuoteData(BaseModel):
    company_name: Optional[str] = ""
    company_address: Optional[str] = ""
    piva: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    logo_path: Optional[str] = ""
    quote_date: Optional[str] = ""
    customer_name: Optional[str] = ""
    customer_address: Optional[str] = ""
    contact_person: Optional[str] = ""
    oggetto: Optional[str] = ""
    final_notes: Optional[str] = ""

class QuotePayload(BaseModel):
    items: List[QuoteItem]
    data: QuoteData

class WooSyncPayload(BaseModel):
    url: str
    consumer_key: str
    consumer_secret: str


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

@app.post("/generate-pdf")
async def generate_pdf(payload: QuotePayload, username: str = Depends(authenticate), db: Session = Depends(get_db)):
    try:
        # Load settings from db
        settings = db.query(CompanySettings).first()

        # Override payload data with DB settings if missing in payload
        if settings:
            if not payload.data.company_name: payload.data.company_name = settings.company_name
            if not payload.data.company_address: payload.data.company_address = settings.company_address
            if not payload.data.piva: payload.data.piva = settings.piva
            if not payload.data.email: payload.data.email = settings.email
            if not payload.data.phone: payload.data.phone = settings.phone

        # Handle Logo Temporary File
        temp_logo_path = None
        if settings and settings.logo_data:
            ext = ".png" # default
            if settings.logo_filename and "." in settings.logo_filename:
                ext = f".{settings.logo_filename.split('.')[-1]}"
            logo_fd, temp_logo_path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(logo_fd, 'wb') as f:
                f.write(settings.logo_data)
            payload.data.logo_path = temp_logo_path

        # Create a temporary file for the PDF
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        # Convert models to dicts for the existing pdf_generator function
        items_dict = [item.model_dump() for item in payload.items]
        data_dict = payload.data.model_dump()

        # Generate the PDF
        pdf_path = generate_quote_pdf(items_dict, data_dict, temp_path)

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

        return StreamingResponse(
            iterfile(),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=preventivo.pdf"}
        )
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        if 'temp_logo_path' in locals() and temp_logo_path and os.path.exists(temp_logo_path):
            os.remove(temp_logo_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/woo-sync")
async def sync_woocommerce(payload: WooSyncPayload, username: str = Depends(authenticate)):
    try:
        products = woo_sync.fetch_woocommerce_products(
            url=payload.url,
            consumer_key=payload.consumer_key,
            consumer_secret=payload.consumer_secret
        )
        return {"status": "success", "products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings")
async def update_settings(
    company_name: str = Form(""),
    company_address: str = Form(""),
    piva: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db),
    username: str = Depends(authenticate)
):
    settings = db.query(CompanySettings).first()
    if not settings:
        settings = CompanySettings()
        db.add(settings)

    if company_name: settings.company_name = company_name
    if company_address: settings.company_address = company_address
    if piva: settings.piva = piva
    if email: settings.email = email
    if phone: settings.phone = phone

    if logo and logo.filename:
        settings.logo_data = await logo.read()
        settings.logo_filename = logo.filename

    db.commit()
    return {"status": "success", "message": "Settings updated successfully"}
