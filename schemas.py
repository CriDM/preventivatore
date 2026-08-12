from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from decimal import Decimal


# --- AUTH SCHEMAS ---
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


# --- COMPANY SCHEMAS ---
class CompanyBase(BaseModel):
    company_name: Optional[str] = ""
    company_address: Optional[str] = ""
    piva: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    piva: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class CompanyResponse(CompanyBase):
    id: int
    logo_filename: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- USER SCHEMAS ---
class UserBase(BaseModel):
    username: str
    role: str = "user"
    company_id: Optional[int] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    company_id: Optional[int] = None


class UserResponse(UserBase):
    id: int
    company: Optional[CompanyResponse] = None

    model_config = ConfigDict(from_attributes=True)


# --- CUSTOMER SCHEMAS ---
class CustomerBase(BaseModel):
    name: Optional[str] = ""
    address: Optional[str] = ""
    contact: Optional[str] = ""


class CustomerCreate(CustomerBase):
    name: str
    address: Optional[str] = ""
    contact: Optional[str] = ""


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None


class CustomerResponse(CustomerBase):
    id: int
    company_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# --- QUOTE SCHEMAS ---
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
    show_vat: Optional[bool] = True


class QuotePayload(BaseModel):
    quote_number: Optional[str] = ""
    version: Optional[int] = None
    data: QuoteData
    items: List[QuoteItem]


class QuoteResponse(BaseModel):
    id: int
    company_id: Optional[int] = None
    user_id: Optional[int] = None
    quote_number: Optional[str] = ""
    version: Optional[int] = 1
    customer_name: Optional[str] = ""
    customer_address: Optional[str] = ""
    contact_person: Optional[str] = ""
    oggetto: Optional[str] = ""
    quote_date: Optional[str] = ""
    final_notes: Optional[str] = ""
    show_vat: Optional[bool] = True
    total_amount: Optional[str] = "0.00"
    created_at: Optional[str] = ""

    model_config = ConfigDict(from_attributes=True)
