from mandate.downstream.fake import FakeDownstream
from mandate.money import Paise, rupees


def test_multiplier_inflates_only_the_marked_sku():
    d = FakeDownstream(amount_multiplier={"sku_0003": 10})
    order = d.create_order(rupees(100), receipt="r1", notes={}, skus=["sku_0003"])
    assert order["amount"] == int(rupees(1000))


def test_unmarked_order_is_untouched():
    d = FakeDownstream(amount_multiplier={"sku_0003": 10})
    order = d.create_order(rupees(100), receipt="r2", notes={}, skus=["sku_0009"])
    assert order["amount"] == int(rupees(100))


def test_no_multiplier_configured_is_identity():
    d = FakeDownstream()
    order = d.create_order(Paise(4242), receipt="r3", notes={}, skus=["sku_0001"])
    assert order["amount"] == 4242
