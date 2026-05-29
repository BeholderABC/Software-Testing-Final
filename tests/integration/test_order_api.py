"""
test_order_api.py  --  Order creation sanity tests

Hand-written sanity tests covering the Order Create / Read paths of the
Mini-E-Commerce backend (REQ-006 through REQ-011). They focus on the
trickier behavioural invariants the data-driven harness can't easily
express:

  - Multi-item orders aggregate `total_price` correctly.
  - Stock is decremented by the exact ordered quantity (REQ-010).
  - Boundary cases on `quantity` (= stock, > stock, = 0) all return
    appropriate HTTP codes.

Skipped automatically when the backend is not reachable; the
`require_backend` fixture from tests/integration/conftest.py probes the server.
"""

import os
from decimal import Decimal

import pytest
import requests


BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000/api")

pytestmark = pytest.mark.usefixtures("require_backend")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CUSTOMER = {
    "customer_name": "John Doe",
    "customer_phone": "1234567890",
    "customer_address": "123 Main St, City",
}


def _new_product(stock: int = 5, price: str = "39.99",
                 name: str = "Pytest Order Product") -> dict:
    """Create a fresh product the order tests can reference."""
    response = requests.post(f"{BASE_URL}/products/create/", json={
        "name": name,
        "description": "Product created by order tests",
        "price": price,
        "stock": stock,
    })
    assert response.status_code in (200, 201), response.text
    return response.json()


def _create_order(items: list, **customer_overrides) -> requests.Response:
    """Send POST /orders/create/ with `items` and a valid customer block."""
    payload = {"items": items, **_VALID_CUSTOMER, **customer_overrides}
    return requests.post(f"{BASE_URL}/orders/create/", json=payload)


# ---------------------------------------------------------------------------
# REQ-006 — Customer creates an order
# ---------------------------------------------------------------------------

def test_req006_create_order_with_single_item_returns_201():
    """REQ-006 / positive: a valid single-item order is created."""
    product = _new_product()
    response = _create_order([{"product_id": product["id"], "quantity": 1}])
    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert "id" in body


def test_req006_create_order_with_multiple_items_aggregates_total_price():
    """REQ-006 + REQ-010 / positive: multi-item order computes total_price
    as sum(price * quantity)."""
    p1 = _new_product(stock=5, price="10.00")
    p2 = _new_product(stock=5, price="2.50")
    response = _create_order([
        {"product_id": p1["id"], "quantity": 2},
        {"product_id": p2["id"], "quantity": 4},
    ])
    assert response.status_code in (200, 201)
    total = Decimal(str(response.json()["total_price"]))
    assert total == Decimal("30.00"), f"unexpected total: {total}"


# ---------------------------------------------------------------------------
# REQ-007 — Reject empty orders
# ---------------------------------------------------------------------------

def test_req007_create_order_with_empty_items_returns_400():
    """REQ-007 / boundary: items length = 0 must be rejected."""
    response = _create_order(items=[])
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# REQ-008 — Reject orders with missing customer info
# ---------------------------------------------------------------------------

def test_req008_missing_customer_name_returns_400():
    """REQ-008 / negative: missing customer_name is rejected."""
    product = _new_product()
    response = _create_order(
        [{"product_id": product["id"], "quantity": 1}],
        customer_name="")
    assert response.status_code == 400


def test_req008_missing_customer_phone_returns_400():
    """REQ-008 / negative: missing customer_phone is rejected."""
    product = _new_product()
    response = _create_order(
        [{"product_id": product["id"], "quantity": 1}],
        customer_phone="")
    assert response.status_code == 400


def test_req008_missing_customer_address_returns_400():
    """REQ-008 / negative: missing customer_address is rejected."""
    product = _new_product()
    response = _create_order(
        [{"product_id": product["id"], "quantity": 1}],
        customer_address="")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# REQ-009 — Quantity vs stock boundary
# ---------------------------------------------------------------------------

def test_req009_quantity_equal_to_stock_is_accepted():
    """REQ-009 / boundary upper-valid: quantity == stock is accepted."""
    product = _new_product(stock=5)
    response = _create_order(
        [{"product_id": product["id"], "quantity": 5}])
    assert response.status_code in (200, 201)


def test_req009_quantity_one_above_stock_returns_400():
    """REQ-009 / boundary upper-invalid: quantity > stock returns 400."""
    product = _new_product(stock=5)
    response = _create_order(
        [{"product_id": product["id"], "quantity": 6}])
    assert response.status_code == 400


def test_req009_quantity_zero_returns_400():
    """REQ-009 / boundary lower-invalid: quantity = 0 must be rejected."""
    product = _new_product(stock=5)
    response = _create_order(
        [{"product_id": product["id"], "quantity": 0}])
    assert response.status_code == 400


def test_req009_nonexistent_product_id_returns_400():
    """REQ-009 / negative: non-existing product_id is rejected."""
    response = _create_order([{"product_id": 99999, "quantity": 1}])
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# REQ-010 — Stock reduction after a successful order
# ---------------------------------------------------------------------------

def test_req010_successful_order_decrements_stock_by_quantity():
    """REQ-010 / side-effect: stock drops by the ordered quantity."""
    product = _new_product(stock=5)
    response = _create_order(
        [{"product_id": product["id"], "quantity": 2}])
    assert response.status_code in (200, 201)
    follow_up = requests.get(f"{BASE_URL}/products/{product['id']}/")
    assert follow_up.status_code == 200
    assert int(follow_up.json()["stock"]) == 3


def test_req010_rejected_order_leaves_stock_untouched():
    """REQ-010 / invariant: a rejected order must not silently decrement
    stock — a regression on this would surface as a silent data loss."""
    product = _new_product(stock=5)
    response = _create_order(
        [{"product_id": product["id"], "quantity": 99}])
    assert response.status_code == 400
    follow_up = requests.get(f"{BASE_URL}/products/{product['id']}/")
    assert int(follow_up.json()["stock"]) == 5


def test_req010_multi_item_partial_failure_rolls_back_all_stock():
    """REQ-010 / decision-table invariant: when a multi-item order fails
    on a later item, the stock already deducted for earlier items must be
    rolled back. This guards the atomicity of the order-creation
    transaction; without it, a rejected order silently leaks stock."""
    product = _new_product(stock=5)
    response = _create_order([
        {"product_id": product["id"], "quantity": 2},   # earlier, valid
        {"product_id": 999999, "quantity": 1},          # later, missing
    ])
    assert response.status_code == 400
    follow_up = requests.get(f"{BASE_URL}/products/{product['id']}/")
    assert int(follow_up.json()["stock"]) == 5, (
        "First item's stock was deducted but the order was rejected — "
        "the failed order leaked stock (no rollback)")


# ---------------------------------------------------------------------------
# REQ-011 — Customer views order detail
# ---------------------------------------------------------------------------

def test_req011_get_existing_order_detail_returns_200():
    """REQ-011 / positive: detail of an existing order returns 200."""
    product = _new_product()
    order = _create_order([{"product_id": product["id"], "quantity": 1}])
    assert order.status_code in (200, 201)
    order_id = order.json()["id"]
    response = requests.get(f"{BASE_URL}/orders/{order_id}/")
    assert response.status_code == 200
    assert response.json()["id"] == order_id


def test_req011_get_nonexistent_order_returns_404():
    """REQ-011 / negative: nonexistent order id returns 404."""
    response = requests.get(f"{BASE_URL}/orders/99999/")
    assert response.status_code in (400, 404)
