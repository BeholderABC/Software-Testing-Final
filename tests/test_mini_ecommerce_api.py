import requests


BASE_URL = "http://127.0.0.1:8000/api"


def create_test_product(stock=5):
    payload = {
        "name": "Pytest Product",
        "description": "Product created by automated test",
        "price": "39.99",
        "stock": stock
    }
    response = requests.post(f"{BASE_URL}/products/create/", json=payload)
    assert response.status_code in [200, 201]
    return response.json()


def test_get_all_products():
    response = requests.get(f"{BASE_URL}/products/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_valid_product_detail():
    product = create_test_product()
    product_id = product["id"]

    response = requests.get(f"{BASE_URL}/products/{product_id}/")
    assert response.status_code == 200
    assert response.json()["id"] == product_id


def test_get_invalid_product_detail():
    response = requests.get(f"{BASE_URL}/products/99999/")
    assert response.status_code in [400, 404]


def test_create_order_empty_items_should_fail():
    payload = {
        "items": [],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main St"
    }

    response = requests.post(f"{BASE_URL}/orders/create/", json=payload)
    assert response.status_code == 400


def test_create_order_missing_customer_name_should_fail():
    product = create_test_product()

    payload = {
        "items": [{"product_id": product["id"], "quantity": 1}],
        "customer_phone": "1234567890",
        "customer_address": "123 Main St"
    }

    response = requests.post(f"{BASE_URL}/orders/create/", json=payload)
    assert response.status_code == 400


def test_create_order_invalid_product_should_fail():
    payload = {
        "items": [{"product_id": 99999, "quantity": 1}],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main St"
    }

    response = requests.post(f"{BASE_URL}/orders/create/", json=payload)
    assert response.status_code == 400


def test_create_order_quantity_exceeds_stock_should_fail():
    product = create_test_product(stock=5)

    payload = {
        "items": [{"product_id": product["id"], "quantity": 6}],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main St"
    }

    response = requests.post(f"{BASE_URL}/orders/create/", json=payload)
    assert response.status_code == 400


def test_create_valid_order_should_reduce_stock():
    product = create_test_product(stock=5)
    product_id = product["id"]

    payload = {
        "items": [{"product_id": product_id, "quantity": 2}],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main St"
    }

    order_response = requests.post(f"{BASE_URL}/orders/create/", json=payload)
    assert order_response.status_code in [200, 201]

    product_response = requests.get(f"{BASE_URL}/products/{product_id}/")
    assert product_response.status_code == 200
    assert product_response.json()["stock"] == 3