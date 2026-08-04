from sqlalchemy import create_engine, Column, Integer, String, LargeBinary, Text
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@localhost/dbname")

# Configure connection to PostgreSQL
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class CompanySettings(Base):
    __tablename__ = "company_settings"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, default="")
    company_address = Column(String, default="")
    piva = Column(String, default="")
    email = Column(String, default="")
    phone = Column(String, default="")
    logo_data = Column(LargeBinary, nullable=True)
    logo_filename = Column(String, nullable=True)

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
