import os
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, Column, Integer, String, LargeBinary, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./preventivatore.db"

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, default="Croce e Cuore Arte Sacra")
    company_address = Column(String, default="")
    piva = Column(String, default="")
    email = Column(String, default="")
    phone = Column(String, default="")
    logo_data = Column(LargeBinary, nullable=True)
    logo_filename = Column(String, nullable=True)

    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="company", cascade="all, delete-orphan")
    quotes = relationship("Quote", back_populates="company", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")  # "admin" or "user"
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)

    company = relationship("Company", back_populates="users")
    quotes = relationship("Quote", back_populates="user")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False, index=True)
    address = Column(String, default="")
    contact = Column(String, default="")

    company = relationship("Company", back_populates="customers")


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quote_number = Column(String, nullable=False)
    customer_name = Column(String, default="")
    customer_address = Column(String, default="")
    contact_person = Column(String, default="")
    oggetto = Column(String, default="")
    quote_date = Column(String, default="")
    final_notes = Column(Text, default="")
    items_json = Column(Text, default="[]")
    version = Column(Integer, default=1)
    total_amount = Column(String, default="0.00")
    created_at = Column(String, default="")

    company = relationship("Company", back_populates="quotes")
    user = relationship("User", back_populates="quotes")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
