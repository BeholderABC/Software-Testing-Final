from django.db import transaction

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product, Order, OrderItem
from .serializers import ProductSerializer, OrderSerializer


# List all products
class ProductListAPIView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


# Create a product
class ProductCreateAPIView(generics.CreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


# Get, Update, Delete product details
class ProductDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


# List all orders
class OrderListAPIView(generics.ListAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


# Get, Update, Delete order details
class OrderDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    # Orders form a finite state machine: `completed` and `cancelled` are
    # terminal. A request that attempts to move an order out of a terminal
    # state is rejected so the status field cannot be rewritten freely.
    TERMINAL_STATES = ("completed", "cancelled")

    def update(self, request, *args, **kwargs):
        order = self.get_object()
        new_status = request.data.get("status")
        if (new_status is not None
                and order.status in self.TERMINAL_STATES
                and new_status != order.status):
            return Response(
                {"status": (
                    f"order is already '{order.status}' (a terminal state) "
                    f"and cannot transition to '{new_status}'")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)


# Create an order
class CreateOrderAPIView(APIView):
    @transaction.atomic
    def post(self, request):
        """
        Expected request data:
        {
            "items": [
                {"product_id": 1, "quantity": 2},
                {"product_id": 2, "quantity": 1}
            ],
            "customer_name": "John Doe",
            "customer_phone": "1234567890",
            "customer_address": "123 Main St, City, Country"
        }
        """

        items_data = request.data.get('items', [])
        customer_name = request.data.get('customer_name', '')
        customer_phone = request.data.get('customer_phone', '')
        customer_address = request.data.get('customer_address', '')

        if not items_data:
            return Response(
                {"error": "No items provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not customer_name or not customer_phone or not customer_address:
            return Response(
                {"error": "Customer information is required (name, phone, address)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        total_price = 0

        order = Order.objects.create(
            total_price=0,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_address=customer_address
        )

        try:
            for item in items_data:
                product_id = item.get('product_id')
                quantity = item.get('quantity')

                if product_id is None or quantity is None:
                    transaction.set_rollback(True)
                    return Response(
                        {"error": "product_id and quantity are required"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    quantity = int(quantity)
                except (TypeError, ValueError):
                    transaction.set_rollback(True)
                    return Response(
                        {"error": "Quantity must be a valid integer"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if quantity <= 0:
                    transaction.set_rollback(True)
                    return Response(
                        {"error": "Quantity must be greater than 0"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    product = Product.objects.get(id=product_id)
                except Product.DoesNotExist:
                    transaction.set_rollback(True)
                    return Response(
                        {"error": f"Product {product_id} does not exist"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if product.stock < quantity:
                    transaction.set_rollback(True)
                    return Response(
                        {
                            "error": (
                                f"Insufficient stock for {product.name}. "
                                f"Available: {product.stock}, Requested: {quantity}"
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                product.stock -= quantity
                product.save()

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity
                )

                total_price += product.price * quantity

            order.total_price = total_price
            order.save()

            serializer = OrderSerializer(order)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            transaction.set_rollback(True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
            