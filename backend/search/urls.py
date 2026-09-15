from django.urls import path

from search.views import CartComparisonView, ProductSearchView

urlpatterns = [
    path("search/", ProductSearchView.as_view(), name="product-search"),
    path("compare/", CartComparisonView.as_view(), name="cart-comparison"),
]
