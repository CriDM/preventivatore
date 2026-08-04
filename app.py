from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
import tempfile
import os
import woo_sync
from pdf_generator import generate_quote_pdf

app = FastAPI(title="Preventivatore API")

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

@app.post("/generate-pdf")
async def generate_pdf(payload: QuotePayload):
    try:
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

        return StreamingResponse(
            iterfile(),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=preventivo.pdf"}
        )
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/woo-sync")
async def sync_woocommerce(payload: WooSyncPayload):
    try:
        products = woo_sync.fetch_woocommerce_products(
            url=payload.url,
            consumer_key=payload.consumer_key,
            consumer_secret=payload.consumer_secret
        )
        return {"status": "success", "products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
