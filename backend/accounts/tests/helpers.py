REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
LOGOUT_URL = "/api/auth/logout/"
GOOGLE_URL = "/api/auth/google/"
LIST_URL = "/api/shopping-list/"

# The boundary the tests fake to stand in for Google's ID-token verification.
VERIFY_GOOGLE_TOKEN = "accounts.google.id_token.verify_oauth2_token"


def google_claims(email="anna@example.com", email_verified=True):
    return {"email": email, "email_verified": email_verified, "sub": "1234567890"}


def item(name, brand=None, quantity=1, favorite=False, category=None):
    key = f"{brand.lower()}|{name.lower()}" if brand else name.lower()
    return {
        "id": key,
        "name": name,
        "brand": brand,
        "category": category,
        "favorite": favorite,
        "quantity": quantity,
    }


def shopping_list(items=(), preferred_brands=(), excluded_ingredients=(), excluded_stores=()):
    return {
        "items": list(items),
        "preferences": {
            "preferred_brands": list(preferred_brands),
            "excluded_ingredients": list(excluded_ingredients),
            "excluded_stores": list(excluded_stores),
        },
    }


def auth(token):
    return {"HTTP_AUTHORIZATION": f"Token {token}"}


def register(client, email="anna@example.com", password="correct-horse-battery", **extra):
    return client.post(REGISTER_URL, {"email": email, "password": password, **extra}, format="json")
