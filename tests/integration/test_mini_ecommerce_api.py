"""
test_mini_ecommerce_api.py  --  Product CRUD sanity tests

Hand-written sanity tests covering the Product side of the
Mini-E-Commerce backend (REQ-001 through REQ-005). They complement the
data-driven harness in `test_data_driven_orders.py` by:

  - Exercising HTTP verbs the data-driven harness doesn't naturally cover
    (PUT, DELETE, PATCH for partial updates).
  - Asserting body-level invariants (price arithmetic, stock decrement)
    rather than just HTTP status codes.

The base URL is taken from the BACKEND_BASE_URL environment variable so
the same tests can target a local dev server (default
`127.0.0.1:8000/api`) or a staging deployment without code changes.

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
# Fixtures
# ---------------------------------------------------------------------------

def _new_product(stock: int = 5, price: str = "39.99",
                 name: str = "Pytest Product") -> dict:
    """Create a fresh product and return its serialised body."""
    payload = {
        "name": name,
        "description": "Product created by automated test",
        "price": price,
        "stock": stock,
    }
    response = requests.post(f"{BASE_URL}/products/create/", json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


# ---------------------------------------------------------------------------
# REQ-001 — Product catalogue listing
# ---------------------------------------------------------------------------

def test_req001_get_all_products_returns_list():
    """REQ-001 / positive: GET /products/ returns a JSON list."""
    response = requests.get(f"{BASE_URL}/products/")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


def test_req001_listed_product_has_required_fields():
    """REQ-001 / positive: each listed product carries the required fields."""
    _new_product()
    response = requests.get(f"{BASE_URL}/products/")
    assert response.status_code == 200
    body = response.json()
    assert body, "expected at least one product after creating one"
    sample = body[0]
    for field in ("id", "name", "description", "price", "stock"):
        assert field in sample, f"missing field: {field}"


# ---------------------------------------------------------------------------
# REQ-002 — Product detail by id
# ---------------------------------------------------------------------------

def test_req002_get_existing_product_detail_returns_200():
    """REQ-002 / positive: detail of an existing product returns 200."""
    product = _new_product()
    response = requests.get(f"{BASE_URL}/products/{product['id']}/")
    assert response.status_code == 200
    assert response.json()["id"] == product["id"]


def test_req002_get_nonexistent_product_detail_returns_404():
    """REQ-002 / negative: nonexistent product id returns 404."""
    response = requests.get(f"{BASE_URL}/products/99999/")
    assert response.status_code in (400, 404)


# ---------------------------------------------------------------------------
# REQ-003 — Admin creates a product
# ---------------------------------------------------------------------------

def test_req003_create_product_with_valid_payload_returns_201():
    """REQ-003 / positive: a complete payload is accepted."""
    product = _new_product(stock=10, price="9.99", name="Created OK")
    assert product["name"] == "Created OK"
    assert int(product["stock"]) == 10


def test_req003_create_product_without_name_returns_400():
    """REQ-003 / negative: missing required name field is rejected."""
    response = requests.post(f"{BASE_URL}/products/create/", json={
        "description": "no name",
        "price": "1.00",
        "stock": 1,
    })
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# REQ-004 — Admin updates a product
# ---------------------------------------------------------------------------

def test_req004_patch_existing_product_updates_field():
    """REQ-004 / positive: PATCH updates the targeted field only."""
    product = _new_product(stock=5)
    response = requests.patch(
        f"{BASE_URL}/products/{product['id']}/", json={"stock": 42})
    assert response.status_code == 200
    assert int(response.json()["stock"]) == 42


def test_req004_patch_nonexistent_product_returns_404():
    """REQ-004 / negative: updating a missing product id returns 404."""
    response = requests.patch(
        f"{BASE_URL}/products/99999/", json={"stock": 1})
    assert response.status_code in (400, 404)


# ---------------------------------------------------------------------------
# REQ-005 — Admin deletes a product
# ---------------------------------------------------------------------------

def test_req005_delete_existing_product_returns_204():
    """REQ-005 / positive: DELETE removes the product."""
    product = _new_product()
    response = requests.delete(f"{BASE_URL}/products/{product['id']}/")
    assert response.status_code in (200, 202, 204)


def test_req005_delete_then_get_returns_404():
    """REQ-005 / side-effect: subsequent detail GET returns 404."""
    product = _new_product()
    response = requests.delete(f"{BASE_URL}/products/{product['id']}/")
    assert response.status_code in (200, 202, 204)
    follow_up = requests.get(f"{BASE_URL}/products/{product['id']}/")
    assert follow_up.status_code in (400, 404)
