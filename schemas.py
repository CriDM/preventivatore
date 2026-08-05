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
    company_name: str = ""
    company_address: str = ""
    piva: str = ""
    email: str = ""
    phone: str = ""


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
    name: str
    address: Optional[str] = ""
    contact: Optional[str] = ""


class CustomerCreate(CustomerBase):
    pass


class CustomerResponse(CustomerBase):
    id: int
    company_id: int

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


class QuotePayload(BaseModel):
    quote_number: Optional[str] = ""
    data: QuoteData
    items: List[QuoteItem]


class QuoteResponse(BaseModel):
    id: int
    company_id: int
    user_id: int
    quote_number: str
    customer_name: str
    customer_address: str
    contact_person: str
    oggetto: str
    quote_date: str
    final_notes: str
    total_amount: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)
