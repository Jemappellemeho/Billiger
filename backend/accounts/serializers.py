from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


MAX_LIST_ITEMS = 500
MAX_PREFERENCE_ENTRIES = 100


class ShoppingListItemSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=300)
    name = serializers.CharField(max_length=200)
    brand = serializers.CharField(max_length=100, allow_null=True)
    category = serializers.CharField(max_length=100, allow_null=True)
    favorite = serializers.BooleanField()
    quantity = serializers.IntegerField(min_value=1, max_value=999)


def _preference_field():
    return serializers.ListField(
        child=serializers.CharField(max_length=100), max_length=MAX_PREFERENCE_ENTRIES
    )


class PreferencesSerializer(serializers.Serializer):
    preferred_brands = _preference_field()
    excluded_ingredients = _preference_field()
    excluded_stores = _preference_field()


class ShoppingListSerializer(serializers.Serializer):
    """Wire format of the shopping list; mirrors the frontend's guest-mode state."""

    items = ShoppingListItemSerializer(many=True, max_length=MAX_LIST_ITEMS)
    preferences = PreferencesSerializer()

    def validate_items(self, items):
        ids = [entry["id"] for entry in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Artikel-IDs müssen eindeutig sein.")
        return items


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    guest_list = ShoppingListSerializer(required=False)

    def validate_email(self, value):
        # Accounts are identified by the lowercased email, stored as the username.
        email = value.strip().lower()
        if get_user_model().objects.filter(username=email).exists():
            raise serializers.ValidationError("Diese E-Mail ist bereits registriert.")
        return email

    def validate(self, attrs):
        candidate = get_user_model()(username=attrs["email"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    guest_list = ShoppingListSerializer(required=False)


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    guest_list = ShoppingListSerializer(required=False)
