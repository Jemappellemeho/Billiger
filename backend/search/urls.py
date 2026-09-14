from django.urls import path

from search.views import ProductSearchView

urlpatterns = [
    path("search/", ProductSearchView.as_view(), name="product-search"),
]
