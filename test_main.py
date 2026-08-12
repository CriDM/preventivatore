import sys
from unittest.mock import MagicMock

gui_modules = [
    "tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk",
    "customtkinter"
]
for m in gui_modules:
    if m not in sys.modules:
        sys.modules[m] = MagicMock()

from decimal import Decimal
from main import format_decimal

def test_format_decimal_basic():
    assert format_decimal(Decimal("1.23")) == "1,23"

def test_format_decimal_thousands():
    assert format_decimal(Decimal("1234.56")) == "1.234,56"

def test_format_decimal_large():
    assert format_decimal(Decimal("1000000")) == "1.000.000,00"

def test_format_decimal_rounding_down():
    assert format_decimal(Decimal("1.234")) == "1,23"

def test_format_decimal_rounding_up():
    assert format_decimal(Decimal("1.235")) == "1,24"

def test_format_decimal_zero():
    assert format_decimal(Decimal("0")) == "0,00"

def test_format_decimal_negative():
    assert format_decimal(Decimal("-1234.56")) == "-1.234,56"

def test_format_decimal_single_digit_integer():
    assert format_decimal(Decimal("5")) == "5,00"

def test_generate_quote_pdf_with_and_without_vat(tmp_path):
    from pdf_generator import generate_quote_pdf
    items = [
        {
            "name": "Articolo Test 1",
            "quantity": Decimal("2"),
            "unit_price": Decimal("100.00"),
            "total": Decimal("200.00"),
            "vat_percent": Decimal("22"),
            "total_with_vat": Decimal("244.00")
        }
    ]
    data_with_vat = {
        "company_name": "Test SRL",
        "quote_number": "100",
        "show_vat": True
    }
    data_without_vat = {
        "company_name": "Test SRL",
        "quote_number": "101",
        "show_vat": False
    }

    pdf1 = tmp_path / "pdf1.pdf"
    pdf2 = tmp_path / "pdf2.pdf"

    res1 = generate_quote_pdf(items, data_with_vat, str(pdf1))
    res2 = generate_quote_pdf(items, data_without_vat, str(pdf2))

    assert pdf1.exists() and pdf1.stat().st_size > 0
    assert pdf2.exists() and pdf2.stat().st_size > 0

    try:
        import pypdf
        reader2 = pypdf.PdfReader(str(pdf2))
        text2 = reader2.pages[0].extract_text()
        assert "200,00" in text2
    except ImportError:
        pass
