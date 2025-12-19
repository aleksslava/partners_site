from django.urls import path
from shop import views

urlpatterns = [
    path('', views.catalog_view, name='catalog'),
    path('products/', views.catalog_view, name='catalog'),
    path('product/group/<int:pk>/', views.product_group_detail, name='product_group_detail'),
    path('api/product/group/<int:pk>/', views.product_group_api, name='product_group_api')
]