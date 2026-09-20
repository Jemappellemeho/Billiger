from django.urls import path

from accounts.views import GoogleLoginView, LoginView, LogoutView, RegisterView, ShoppingListView

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/google/", GoogleLoginView.as_view(), name="auth-google"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("shopping-list/", ShoppingListView.as_view(), name="shopping-list"),
]
