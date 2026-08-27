import pytest

from mandate.money import Paise, fmt, rupees


def test_rupees_from_int():
    assert rupees(2000) == 200000

def test_rupees_from_decimal_string():
    assert rupees("1999.50") == 199950

def test_rupees_rejects_sub_paise_precision():
    with pytest.raises(ValueError):
        rupees("10.005")

def test_fmt_renders_rupees():
    assert fmt(Paise(199950)) == "₹1,999.50"

def test_fmt_zero():
    assert fmt(Paise(0)) == "₹0.00"
