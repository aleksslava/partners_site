from django.urls import path
from . import views

urlpatterns = [
    path('', views.cart_view, name='cart'),
    path('order/<int:order_id>/', views.order_view, name='order_view'),
    path('remove_item/', views.cart_remove_item, name='cart_remove_item'),
    path('add/', views.add_to_cart, name='add_to_cart'),
    path('update_item/', views.cart_update_item, name='update_cart_item'),
    path('quantities/', views.get_cart_quantities, name='get_cart_quantities'),
    path('discount_type/', views.api_cart_discount_type, name='api_cart_discount_type'),
    path('set_bonuses_spend/', views.api_cart_set_bonuses_spend, name='api_cart_set_bonuses_spend'),
    path('set_order_discount/', views.api_cart_set_order_discount, name='api_cart_set_order_discount'),
    path('payment-type/', views.api_cart_payment_type, name='api_cart_payment_type'),
    path('requisites/search/',views.api_requisites_search, name='api_cart_search'),
    path('addresses/', views.api_addresses_list, name='api_addresses_list'),
    path("save-requisites/", views.api_cart_save_requisites, name="api_cart_save_requisites"),
    path('set-requisites/', views.api_cart_set_requisites, name="api_cart_set_requisites"),
    path("delivery-type/", views.api_cart_delivery_type, name="api_cart_delivery_type"),
    path("delivery/draft/", views.api_cart_delivery_draft, name="api_cart_delivery_draft"),
    path("delivery/save-address/", views.api_cart_delivery_save_address, name="api_cart_delivery_save_address"),
    path("checkout/", views.api_cart_checkout, name="api_cart_checkout"),
]
