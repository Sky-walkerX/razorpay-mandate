from mandate.gateway.resolve import MerchantResolver, normalise

KNOWN = {"zepto": "Zepto", "blinkit": "Blinkit", "instamart": "Instamart"}
R = MerchantResolver(KNOWN)

def test_exact_id_resolves():
    assert R.resolve("zepto") == "zepto"

def test_display_name_resolves():
    assert R.resolve("Zepto") == "zepto"

def test_case_and_whitespace_are_normalised():
    assert R.resolve("  ZEPTO  ") == "zepto"

def test_greek_homoglyph_does_not_resolve_to_zepto():
    """'zeptο' with a Greek omicron must not become 'zepto'."""
    assert R.resolve("zeptο") is None

def test_lookalike_suffix_does_not_resolve():
    assert R.resolve("zepto-fresh") is None
    assert R.resolve("Zepto Fresh") is None

def test_unknown_merchant_returns_none_not_an_exception():
    assert R.resolve("totally-new-shop") is None

def test_normalise_strips_confusables_to_ascii():
    assert normalise("Zeptο") != normalise("Zepto")
