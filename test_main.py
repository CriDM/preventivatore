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
