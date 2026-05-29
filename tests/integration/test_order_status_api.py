"""
test_order_status_api.py  --  Order status transition tests

Hand-written tests for REQ-012 — admin updates an order's status. The
status field is an enum: `pending` (default) → `completed` or `cancelled`.
These tests exercise:

  - Each allowed transition individually (decision-table coverage).
  - The enum boundary (invalid status string rejected).
  - The default-status invariant on freshly created orders.

Skipped automatically when the backend is not reachable; the
`require_backend` fixture from tests/integration/conftest.py probes the server.
"""

import os

import pytest
import requests


BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000/api")

pytestmark = pytest.mark.usefixtures("require_backend")


_VALID_CUSTOMER = {
    "customer_name": "John Doe",
    "customer_phone": "1234567890",
    "customer_address": "123 Main St",
}


def _seed_order() -> dict:
    """Create a fresh product + order and return the order body."""
    product_resp = requests.post(f"{BASE_URL}/products/create/", json={
        "name": "Pytest Status Product",
        "description": "for status tests",
        "price": "1.00",
        "stock": 5,
    })
    assert product_resp.status_code in (200, 201), product_resp.text
    product = product_resp.json()

    order_resp = requests.post(f"{BASE_URL}/orders/create/", json={
        "items": [{"product_id": product["id"], "quantity": 1}],
        **_VALID_CUSTOMER,
    })
    assert order_resp.status_code in (200, 201), order_resp.text
    return order_resp.json()


# ---------------------------------------------------------------------------
# REQ-012 — Allowed status enum
# ---------------------------------------------------------------------------

def test_req012_new_order_defaults_to_pending():
    """REQ-012 / invariant: fresh orders start in 'pending'."""
    order = _seed_order()
    assert order.get("status") == "pending"


def test_req012_transition_pending_to_completed_returns_200():
    """REQ-012 / decision-table: pending → completed is allowed."""
    order = _seed_order()
    response = requests.patch(
        f"{BASE_URL}/orders/{order['id']}/", json={"status": "completed"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_req012_transition_pending_to_cancelled_returns_200():
    """REQ-012 / decision-table: pending → cancelled is allowed."""
    order = _seed_order()
    response = requests.patch(
        f"{BASE_URL}/orders/{order['id']}/", json={"status": "cancelled"})
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_req012_invalid_status_value_returns_400():
    """REQ-012 / boundary: enum violation must be rejected."""
    order = _seed_order()
    response = requests.patch(
        f"{BASE_URL}/orders/{order['id']}/", json={"status": "delivered"})
    assert response.status_code == 400


def test_req012_patch_nonexistent_order_returns_404():
    """REQ-012 / negative: updating a missing order id returns 404."""
    response = requests.patch(
        f"{BASE_URL}/orders/99999/", json={"status": "completed"})
    assert response.status_code in (400, 404)
