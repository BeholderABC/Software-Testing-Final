"""
mec_request_builder.py  --  Map a generated test case to a concrete HTTP call

The rule pipeline produces generic test cases (test_data may be empty when
the rule engine can't infer a concrete payload from a free-text coverage
item). To still drive the Mini-E-Commerce backend, this module turns each
generated case into one of the request templates below, keyed by
``(requirement_id, coverage_type)``.

This keeps the data-driven harness deterministic and lets the report state
that the generated test cases (after this domain adapter) successfully
exercised the backend.

The templates are intentionally simple and observable -- each one targets a
single requirement so that a FAILED test points directly to the offending
backend behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class HttpExpectation:
    """A self-contained executable HTTP step + its expected outcome."""

    description: str
    request: Callable[[str], "requests.Response"]
    expected_status_min: int
    expected_status_max: int
    # Optional keyword that must appear in the response body for richer asserts
    must_contain: Optional[str] = None
    # Optional side-effect assertion, called with the base url + response
    side_effect: Optional[Callable[[str, "requests.Response"], None]] = None

    def expect_ok(self, status: int) -> bool:
        return self.expected_status_min <= status <= self.expected_status_max


# ---------------------------------------------------------------------------
# Helpers — minimal product setup
# ---------------------------------------------------------------------------

def ensure_product(base_url: str, stock: int = 5, price: str = "39.99",
                   name: str = "Pytest Product") -> Dict[str, Any]:
    """Create a product on the backend and return its serialised body."""
    r = requests.post(f"{base_url}/products/create/", json={
        "name": name,
        "description": "Created by data-driven harness",
        "price": price,
        "stock": stock,
    })
    r.raise_for_status()
    return r.json()


def _valid_customer() -> Dict[str, str]:
    return {
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main St",
    }


# ---------------------------------------------------------------------------
# Request templates per (requirement_id, coverage_type)
# ---------------------------------------------------------------------------

def _req001_list_products(base_url: str, ctype: str) -> HttpExpectation:
    return HttpExpectation(
        description="GET /api/products/ returns the product list",
        request=lambda bu: requests.get(f"{bu}/products/"),
        expected_status_min=200, expected_status_max=200,
    )


def _req002_product_detail(base_url: str, ctype: str) -> HttpExpectation:
    if ctype in ("negative", "boundary", "combination"):
        # non-existing product id
        return HttpExpectation(
            description="GET /api/products/99999/ returns 404",
            request=lambda bu: requests.get(f"{bu}/products/99999/"),
            expected_status_min=400, expected_status_max=404,
        )
    product = ensure_product(base_url)
    pid = product["id"]
    return HttpExpectation(
        description=f"GET /api/products/{pid}/ returns 200",
        request=lambda bu: requests.get(f"{bu}/products/{pid}/"),
        expected_status_min=200, expected_status_max=200,
    )


def _req003_create_product(base_url: str, ctype: str) -> HttpExpectation:
    if ctype in ("negative", "boundary", "combination"):
        # missing required field -> 400
        return HttpExpectation(
            description="POST /api/products/create/ with empty name -> 400",
            request=lambda bu: requests.post(
                f"{bu}/products/create/",
                json={"name": "", "description": "", "price": "1.00", "stock": 1}),
            expected_status_min=400, expected_status_max=400,
        )
    return HttpExpectation(
        description="POST /api/products/create/ with valid payload -> 201",
        request=lambda bu: requests.post(
            f"{bu}/products/create/",
            json={"name": "Sample", "description": "desc",
                  "price": "1.00", "stock": 1}),
        expected_status_min=200, expected_status_max=201,
    )


def _req004_update_product(base_url: str, ctype: str) -> HttpExpectation:
    if ctype in ("negative", "boundary", "combination"):
        return HttpExpectation(
            description="PATCH /api/products/99999/ on missing id -> 404",
            request=lambda bu: requests.patch(
                f"{bu}/products/99999/", json={"stock": 1}),
            expected_status_min=400, expected_status_max=404,
        )
    product = ensure_product(base_url)
    pid = product["id"]
    return HttpExpectation(
        description=f"PATCH /api/products/{pid}/ updates the product",
        request=lambda bu: requests.patch(
            f"{bu}/products/{pid}/", json={"stock": 99}),
        expected_status_min=200, expected_status_max=200,
    )


def _req005_delete_product(base_url: str, ctype: str) -> HttpExpectation:
    if ctype in ("negative", "boundary", "combination"):
        return HttpExpectation(
            description="DELETE /api/products/99999/ on missing id -> 404",
            request=lambda bu: requests.delete(f"{bu}/products/99999/"),
            expected_status_min=400, expected_status_max=404,
        )
    product = ensure_product(base_url)
    pid = product["id"]
    return HttpExpectation(
        description=f"DELETE /api/products/{pid}/ -> 204",
        request=lambda bu: requests.delete(f"{bu}/products/{pid}/"),
        expected_status_min=200, expected_status_max=204,
    )


def _req006_create_order_valid(base_url: str, ctype: str) -> HttpExpectation:
    product = ensure_product(base_url, stock=5)
    if ctype in ("negative", "boundary", "combination"):
        # Fire the same endpoint with an unsatisfiable payload (no product).
        payload = {
            "items": [{"product_id": 99999, "quantity": 1}],
            **_valid_customer(),
        }
        return HttpExpectation(
            description="POST /api/orders/create/ with non-existing product",
            request=lambda bu: requests.post(f"{bu}/orders/create/",
                                             json=payload),
            expected_status_min=400, expected_status_max=400,
        )
    payload = {
        "items": [{"product_id": product["id"], "quantity": 1}],
        **_valid_customer(),
    }
    return HttpExpectation(
        description="POST /api/orders/create/ with one valid item -> 201",
        request=lambda bu: requests.post(f"{bu}/orders/create/", json=payload),
        expected_status_min=200, expected_status_max=201,
    )


def _req007_empty_items(base_url: str, ctype: str) -> HttpExpectation:
    if ctype == "positive":
        # The "happy path" for an empty-rejection rule is to confirm the
        # equivalent non-empty case still works.
        product = ensure_product(base_url)
        payload = {
            "items": [{"product_id": product["id"], "quantity": 1}],
            **_valid_customer(),
        }
        return HttpExpectation(
            description="POST /api/orders/create/ with non-empty items -> 201",
            request=lambda bu: requests.post(f"{bu}/orders/create/",
                                             json=payload),
            expected_status_min=200, expected_status_max=201,
        )
    payload = {"items": [], **_valid_customer()}
    return HttpExpectation(
        description="POST /api/orders/create/ with empty items -> 400",
        request=lambda bu: requests.post(f"{bu}/orders/create/", json=payload),
        expected_status_min=400, expected_status_max=400,
    )


def _req008_missing_customer(base_url: str, ctype: str) -> HttpExpectation:
    product = ensure_product(base_url)
    if ctype == "positive":
        payload = {
            "items": [{"product_id": product["id"], "quantity": 1}],
            **_valid_customer(),
        }
        return HttpExpectation(
            description="POST /api/orders/create/ with full customer info -> 201",
            request=lambda bu: requests.post(f"{bu}/orders/create/",
                                             json=payload),
            expected_status_min=200, expected_status_max=201,
        )
    payload = {
        "items": [{"product_id": product["id"], "quantity": 1}],
        "customer_phone": "123",
        "customer_address": "addr",
        # customer_name intentionally missing
    }
    return HttpExpectation(
        description="POST /api/orders/create/ missing customer_name -> 400",
        request=lambda bu: requests.post(f"{bu}/orders/create/", json=payload),
        expected_status_min=400, expected_status_max=400,
    )


def _req009_quantity_vs_stock(base_url: str, ctype: str) -> HttpExpectation:
    product = ensure_product(base_url, stock=5)
    if ctype == "boundary":
        # Boundary cases include `quantity == stock` (valid) and
        # `quantity == 0`. We exercise the canonical-but-accepted `==`
        # case to demonstrate the upper bound is inclusive.
        qty = product["stock"]
        payload = {
            "items": [{"product_id": product["id"], "quantity": qty}],
            **_valid_customer(),
        }
        return HttpExpectation(
            description=f"order with quantity = stock ({qty}) -> 201",
            request=lambda bu: requests.post(f"{bu}/orders/create/",
                                             json=payload),
            expected_status_min=200, expected_status_max=201,
        )
    if ctype in ("negative", "combination"):
        qty = product["stock"] + 1
        payload = {
            "items": [{"product_id": product["id"], "quantity": qty}],
            **_valid_customer(),
        }
        return HttpExpectation(
            description=f"order with quantity > stock ({qty}) -> 400",
            request=lambda bu: requests.post(f"{bu}/orders/create/",
                                             json=payload),
            expected_status_min=400, expected_status_max=400,
        )
    # positive
    payload = {
        "items": [{"product_id": product["id"], "quantity": 1}],
        **_valid_customer(),
    }
    return HttpExpectation(
        description="order with quantity within stock -> 201",
        request=lambda bu: requests.post(f"{bu}/orders/create/", json=payload),
        expected_status_min=200, expected_status_max=201,
    )


def _req010_stock_reduction(base_url: str, ctype: str) -> HttpExpectation:
    product = ensure_product(base_url, stock=5)
    pid = product["id"]
    if ctype in ("negative", "boundary", "combination"):
        # Rejected order — the invariant we're protecting is "stock
        # stays untouched". Send a quantity that exceeds stock.
        payload = {
            "items": [{"product_id": pid, "quantity": 99}],
            **_valid_customer(),
        }

        def stock_unchanged(bu: str, _resp: "requests.Response") -> None:
            r = requests.get(f"{bu}/products/{pid}/")
            assert r.status_code == 200
            assert r.json()["stock"] == 5, "stock must not change after a rejection"

        return HttpExpectation(
            description="rejected order leaves stock untouched",
            request=lambda bu: requests.post(f"{bu}/orders/create/",
                                             json=payload),
            expected_status_min=400, expected_status_max=400,
            side_effect=stock_unchanged,
        )

    payload = {
        "items": [{"product_id": pid, "quantity": 2}],
        **_valid_customer(),
    }

    def stock_drops(bu: str, _resp: "requests.Response") -> None:
        r = requests.get(f"{bu}/products/{pid}/")
        assert r.status_code == 200
        assert r.json()["stock"] == 3, "stock should drop from 5 to 3"

    return HttpExpectation(
        description="successful order reduces product stock by ordered qty",
        request=lambda bu: requests.post(f"{bu}/orders/create/", json=payload),
        expected_status_min=200, expected_status_max=201,
        side_effect=stock_drops,
    )


def _req011_order_detail(base_url: str, ctype: str) -> HttpExpectation:
    if ctype in ("negative", "boundary", "combination"):
        return HttpExpectation(
            description="GET /api/orders/99999/ on missing id -> 404",
            request=lambda bu: requests.get(f"{bu}/orders/99999/"),
            expected_status_min=400, expected_status_max=404,
        )
    product = ensure_product(base_url)
    order = requests.post(f"{base_url}/orders/create/", json={
        "items": [{"product_id": product["id"], "quantity": 1}],
        **_valid_customer(),
    })
    order.raise_for_status()
    oid = order.json()["id"]
    return HttpExpectation(
        description=f"GET /api/orders/{oid}/ -> 200",
        request=lambda bu: requests.get(f"{bu}/orders/{oid}/"),
        expected_status_min=200, expected_status_max=200,
    )


def _req012_order_status(base_url: str, ctype: str) -> HttpExpectation:
    product = ensure_product(base_url)
    order = requests.post(f"{base_url}/orders/create/", json={
        "items": [{"product_id": product["id"], "quantity": 1}],
        **_valid_customer(),
    })
    order.raise_for_status()
    oid = order.json()["id"]
    if ctype in ("negative", "boundary", "combination"):
        return HttpExpectation(
            description=f"PATCH /api/orders/{oid}/ with invalid status -> 400",
            request=lambda bu: requests.patch(
                f"{bu}/orders/{oid}/", json={"status": "unknown"}),
            expected_status_min=400, expected_status_max=400,
        )
    return HttpExpectation(
        description=f"PATCH /api/orders/{oid}/ status=completed -> 200",
        request=lambda bu: requests.patch(
            f"{bu}/orders/{oid}/", json={"status": "completed"}),
        expected_status_min=200, expected_status_max=200,
    )


# Map a state-machine event to the target status it requests.
_EVENT_TO_STATUS = {"complete": "completed", "cancel": "cancelled"}


def _req012_state_sequence(base_url: str, ctype: str,
                           sequence: List[str]) -> HttpExpectation:
    """White-box ST execution: walk an event sequence on a fresh order.

    A new order is created (state ``pending``), then each event in the
    sequence is applied as a PATCH. Every step but the last is expected
    to succeed (the prefix that drives the order to the edge's source).
    The final step is the edge under test: for a ``positive`` (valid)
    case it must succeed (200); for a ``negative`` (invalid-guard) case
    it must be rejected (4xx), because the state machine forbids leaving
    a terminal state. A terminal-guard step that the backend accepts
    therefore fails the assertion, exposing a missing guard.
    """
    product = ensure_product(base_url)
    order = requests.post(f"{base_url}/orders/create/", json={
        "items": [{"product_id": product["id"], "quantity": 1}],
        **_valid_customer(),
    })
    order.raise_for_status()
    oid = order.json()["id"]
    is_positive = ctype == "positive"

    def _walk(bu: str) -> "requests.Response":
        last: Optional["requests.Response"] = None
        for i, event in enumerate(sequence):
            status_value = _EVENT_TO_STATUS.get(event, event)
            last = requests.patch(
                f"{bu}/orders/{oid}/", json={"status": status_value})
            is_final = i == len(sequence) - 1
            # The prefix (all but the final step) must land cleanly so the
            # order reaches the edge's source state.
            if not is_final and last.status_code >= 400:
                return last
        assert last is not None
        return last

    seq_label = " -> ".join(sequence)
    if is_positive:
        return HttpExpectation(
            description=f"ST valid sequence [{seq_label}] on order {oid} -> 2xx",
            request=_walk,
            expected_status_min=200, expected_status_max=201,
        )
    return HttpExpectation(
        description=(f"ST invalid-guard sequence [{seq_label}] on order "
                     f"{oid} -> rejected"),
        request=_walk,
        expected_status_min=400, expected_status_max=409,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_BUILDERS: Dict[str, Callable[[str, str], HttpExpectation]] = {
    "REQ-001": _req001_list_products,
    "REQ-002": _req002_product_detail,
    "REQ-003": _req003_create_product,
    "REQ-004": _req004_update_product,
    "REQ-005": _req005_delete_product,
    "REQ-006": _req006_create_order_valid,
    "REQ-007": _req007_empty_items,
    "REQ-008": _req008_missing_customer,
    "REQ-009": _req009_quantity_vs_stock,
    "REQ-010": _req010_stock_reduction,
    "REQ-011": _req011_order_detail,
    "REQ-012": _req012_order_status,
}


SUPPORTED_REQUIREMENTS: Tuple[str, ...] = tuple(sorted(_BUILDERS.keys()))


def build(test_case: Dict[str, Any], base_url: str
          ) -> Optional[HttpExpectation]:
    """Return an HttpExpectation for the given generated test case, or
    ``None`` if the requirement is outside the Mini-E-Commerce domain
    (so the harness can skip it cleanly).

    The dispatch is keyed by ``requirement_id``; each per-requirement
    builder picks the concrete request template using the case's
    ``coverage_type``. The test case's ``oracle`` field (FR 5.0) is
    consulted only as a soft hint: if it ships a ``must_contain``
    keyword it is attached to the expectation, but the template's own
    status range remains authoritative because each template is built
    to match the actual backend semantics.
    """
    rid = str(test_case.get("requirement_id", ""))
    ctype = str(test_case.get("coverage_type", "positive")).lower()
    builder = _BUILDERS.get(rid)
    if not builder:
        return None
    # White-box state-transition cases carry an event sequence; route them
    # to the multi-step walker rather than the single-PATCH black-box
    # template so that the state machine's guards are actually exercised.
    test_data = _coerce_dict(test_case.get("test_data"))
    sequence = test_data.get("event_sequence")
    if rid == "REQ-012" and isinstance(sequence, (list, tuple)) and sequence:
        expectation = _req012_state_sequence(
            base_url, ctype, [str(e) for e in sequence])
    else:
        expectation = builder(base_url, ctype)
    oracle = _coerce_dict(test_case.get("oracle"))
    keywords = oracle.get("must_contain") or []
    if keywords:
        expectation.must_contain = str(keywords[0])
    return expectation


def _coerce_dict(value: Any) -> Dict[str, Any]:
    """Return a dict from a value that may already be a dict, a Python /
    JSON repr string of a dict (test cases that round-tripped through a
    DataFrame store nested fields as strings), or anything else."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        import ast
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, SyntaxError):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}
