from django.urls import path
from .views import ProductListAPIView, ProductCreateAPIView, ProductDetailAPIView, OrderListAPIView, CreateOrderAPIView, OrderDetailAPIView

urlpatterns = [
    path('products/', ProductListAPIView.as_view(), name='product-list'),
    path('products/create/', ProductCreateAPIView.as_view(), name='product-create'),
    path('products/<int:pk>/', ProductDetailAPIView.as_view(), name='product-detail'),
    path('orders/', OrderListAPIView.as_view(), name='order-list'),
    path('orders/create/', CreateOrderAPIView.as_view(), name='order-create'),
    path('orders/<int:pk>/', OrderDetailAPIView.as_view(), name='order-detail'),
]
