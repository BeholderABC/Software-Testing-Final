import pytest
from decimal import Decimal
from rest_framework.test import APIClient
from store.models import Product, Order, OrderItem


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def product():
    return Product.objects.create(
        name="Test Product",
        description="A product used for backend API testing",
        price=Decimal("10.00"),
        stock=5
    )


@pytest.mark.django_db
def test_create_order_success_should_create_order_and_reduce_stock(api_client, product):
    payload = {
        "items": [
            {
                "product_id": product.id,
                "quantity": 2
            }
        ],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 201
    assert Order.objects.count() == 1
    assert OrderItem.objects.count() == 1

    product.refresh_from_db()
    assert product.stock == 3

    order = Order.objects.first()
    assert order.total_price == Decimal("20.00")
    assert order.customer_name == "John Doe"


@pytest.mark.django_db
def test_create_order_with_empty_items_should_return_400(api_client):
    payload = {
        "items": [],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_create_order_without_customer_name_should_return_400(api_client, product):
    payload = {
        "items": [
            {
                "product_id": product.id,
                "quantity": 1
            }
        ],
        "customer_phone": "1234567890",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_create_order_without_customer_phone_should_return_400(api_client, product):
    payload = {
        "items": [
            {
                "product_id": product.id,
                "quantity": 1
            }
        ],
        "customer_name": "John Doe",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_create_order_without_customer_address_should_return_400(api_client, product):
    payload = {
        "items": [
            {
                "product_id": product.id,
                "quantity": 1
            }
        ],
        "customer_name": "John Doe",
        "customer_phone": "1234567890"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_create_order_with_non_existing_product_should_return_400(api_client):
    payload = {
        "items": [
            {
                "product_id": 9999,
                "quantity": 1
            }
        ],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_create_order_with_quantity_equal_to_stock_should_success(api_client, product):
    payload = {
        "items": [
            {
                "product_id": product.id,
                "quantity": 5
            }
        ],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 201

    product.refresh_from_db()
    assert product.stock == 0


@pytest.mark.django_db
def test_create_order_with_quantity_greater_than_stock_should_return_400(api_client, product):
    payload = {
        "items": [
            {
                "product_id": product.id,
                "quantity": 6
            }
        ],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0

    product.refresh_from_db()
    assert product.stock == 5


@pytest.mark.django_db
def test_create_order_with_zero_quantity_should_return_400(api_client, product):
    payload = {
        "items": [
            {
                "product_id": product.id,
                "quantity": 0
            }
        ],
        "customer_name": "John Doe",
        "customer_phone": "1234567890",
        "customer_address": "123 Main Street"
    }

    response = api_client.post("/api/orders/create/", payload, format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0