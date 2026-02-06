#!/usr/bin/env python3
"""
Kroger API client for product search, store lookup, and cart management.

Usage:
    # Auth setup (one-time): generates OAuth URL, exchanges code for tokens
    python kroger_api.py auth

    # Find stores near a ZIP code
    python kroger_api.py stores --zip 48837

    # Search products at a store
    python kroger_api.py search --query "chicken breast" --location 01400943

    # Get product details
    python kroger_api.py product --id 0001111041700 --location 01400943

    # Add items to cart (requires user auth)
    python kroger_api.py cart-add --items '[{"upc":"0001111041700","quantity":2}]'

Environment:
    KROGER_CLIENT_ID       - App client ID from developer.kroger.com
    KROGER_CLIENT_SECRET   - App client secret
    KROGER_REDIRECT_URI    - OAuth redirect (default: http://localhost:8080/callback)
    KROGER_REFRESH_TOKEN   - User refresh token (for cart operations)
    KROGER_ZIP             - Default ZIP code (default: 48837)
    KROGER_LOCATION_ID     - Default store location ID
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import requests

BASE_URL = "https://api.kroger.com/v1"
AUTH_URL = "https://api.kroger.com/v1/connect/oauth2"


class KrogerAuth:
    """Handles OAuth2 for Kroger API (client credentials + authorization code)."""

    def __init__(self, client_id=None, client_secret=None, redirect_uri=None):
        self.client_id = client_id or os.getenv("KROGER_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("KROGER_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv(
            "KROGER_REDIRECT_URI", "http://localhost:8080/callback"
        )

        if not self.client_id or not self.client_secret:
            raise ValueError("KROGER_CLIENT_ID and KROGER_CLIENT_SECRET are required")

        self._app_token = None
        self._app_token_expires = 0
        self._user_token = None
        self._user_token_expires = 0
        self._refresh_token = os.getenv("KROGER_REFRESH_TOKEN")

        # Try loading saved tokens
        self._token_file = (
            Path(__file__).resolve().parent.parent / ".tmp" / "kroger_tokens.json"
        )
        self._load_tokens()

    def _basic_auth(self):
        creds = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        return f"Basic {creds}"

    def _save_tokens(self):
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if self._refresh_token:
            data["refresh_token"] = self._refresh_token
        if self._user_token:
            data["user_token"] = self._user_token
            data["user_token_expires"] = self._user_token_expires
        self._token_file.write_text(json.dumps(data))

    def _load_tokens(self):
        if self._token_file.exists():
            try:
                data = json.loads(self._token_file.read_text())
                if not self._refresh_token:
                    self._refresh_token = data.get("refresh_token")
                self._user_token = data.get("user_token")
                self._user_token_expires = data.get("user_token_expires", 0)
            except (json.JSONDecodeError, OSError):
                pass

    def get_app_token(self, scope="product.compact"):
        """Get client-credentials token for public endpoints (products, locations)."""
        if self._app_token and time.time() < self._app_token_expires:
            return self._app_token

        resp = requests.post(
            f"{AUTH_URL}/token",
            headers={
                "Authorization": self._basic_auth(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": scope},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        self._app_token = body["access_token"]
        self._app_token_expires = time.time() + body["expires_in"] - 60
        return self._app_token

    def get_authorize_url(self, scope="cart.basic:write profile.compact"):
        """Generate the URL the user must visit to authorize cart access."""
        params = {
            "scope": scope,
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        return f"{AUTH_URL}/authorize?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code):
        """Exchange authorization code for user tokens."""
        resp = requests.post(
            f"{AUTH_URL}/token",
            headers={
                "Authorization": self._basic_auth(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        self._user_token = body["access_token"]
        self._user_token_expires = time.time() + body["expires_in"] - 60
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        self._save_tokens()
        return body

    def get_user_token(self):
        """Get user token (refresh if expired). Required for cart operations."""
        if self._user_token and time.time() < self._user_token_expires:
            return self._user_token

        if not self._refresh_token:
            raise ValueError(
                "No refresh token. Run 'python kroger_api.py auth' to authorize."
            )

        resp = requests.post(
            f"{AUTH_URL}/token",
            headers={
                "Authorization": self._basic_auth(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        self._user_token = body["access_token"]
        self._user_token_expires = time.time() + body["expires_in"] - 60
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        self._save_tokens()
        return self._user_token

    @property
    def has_user_auth(self):
        return bool(self._refresh_token)


class KrogerClient:
    """High-level Kroger API client."""

    def __init__(self, auth=None):
        self.auth = auth or KrogerAuth()

    def _app_headers(self, scope="product.compact"):
        return {
            "Authorization": f"Bearer {self.auth.get_app_token(scope)}",
            "Accept": "application/json",
        }

    def _user_headers(self):
        return {
            "Authorization": f"Bearer {self.auth.get_user_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ── Locations ──────────────────────────────────────────────────────

    def find_stores(self, zip_code, radius_miles=10, limit=5):
        """Find Kroger stores near a ZIP code."""
        resp = requests.get(
            f"{BASE_URL}/locations",
            headers=self._app_headers("product.compact"),
            params={
                "filter.zipCode.near": zip_code,
                "filter.radiusInMiles": radius_miles,
                "filter.limit": limit,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Products ───────────────────────────────────────────────────────

    def search_products(self, query, location_id, limit=10, fulfillment=None):
        """Search products at a specific store."""
        params = {
            "filter.term": query,
            "filter.locationId": location_id,
            "filter.limit": limit,
        }
        if fulfillment:
            params["filter.fulfillment"] = fulfillment
        resp = requests.get(
            f"{BASE_URL}/products",
            headers=self._app_headers("product.compact"),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_product(self, product_id, location_id):
        """Get detailed product info including price and availability."""
        resp = requests.get(
            f"{BASE_URL}/products/{product_id}",
            headers=self._app_headers("product.compact"),
            params={"filter.locationId": location_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Cart ───────────────────────────────────────────────────────────

    def add_to_cart(self, items):
        """
        Add items to the user's cart. Requires user authorization.

        items: list of dicts with keys:
            - upc: product ID / UPC
            - quantity: int
            - modality: "PICKUP" or "DELIVERY" (optional, default PICKUP)
        """
        payload = {
            "items": [
                {
                    "upc": item["upc"],
                    "quantity": item["quantity"],
                    "modality": item.get("modality", "PICKUP"),
                }
                for item in items
            ]
        }
        resp = requests.put(
            f"{BASE_URL}/cart/add",
            headers=self._user_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        # Cart add returns 204 No Content on success
        return {"status": "ok", "items_added": len(items)}


# ── CLI ────────────────────────────────────────────────────────────────


def cmd_auth(args, client):
    """Interactive OAuth flow for cart access."""
    url = client.auth.get_authorize_url()
    print("Open this URL in your browser to authorize Kroger cart access:\n")
    print(url)
    print(
        "\nAfter authorizing, you'll be redirected to a URL containing a 'code' parameter."
    )
    code = input("\nPaste the authorization code here: ").strip()
    if not code:
        print("No code provided. Aborting.")
        sys.exit(1)
    result = client.auth.exchange_code(code)
    print(f"\nAuthorization successful! Tokens saved to {client.auth._token_file}")
    print(f"Refresh token: {result.get('refresh_token', 'N/A')[:20]}...")
    print("\nYou can now use cart operations.")


def cmd_stores(args, client):
    """Find stores near ZIP."""
    zip_code = args.zip or os.getenv("KROGER_ZIP", "48837")
    result = client.find_stores(zip_code, radius_miles=args.radius, limit=args.limit)
    stores = result.get("data", [])
    if not stores:
        print(f"No stores found near {zip_code}")
        return
    output = []
    for s in stores:
        addr = s.get("address", {})
        output.append(
            {
                "locationId": s["locationId"],
                "name": s.get("name", ""),
                "address": f"{addr.get('addressLine1', '')}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zipCode', '')}",
                "phone": s.get("phone", ""),
            }
        )
    print(json.dumps(output, indent=2))


def cmd_search(args, client):
    """Search products."""
    location_id = args.location or os.getenv("KROGER_LOCATION_ID")
    if not location_id:
        print("--location or KROGER_LOCATION_ID required")
        sys.exit(1)
    result = client.search_products(args.query, location_id, limit=args.limit)
    products = result.get("data", [])
    if not products:
        print(f"No products found for '{args.query}'")
        return
    output = []
    for p in products:
        item = p.get("items", [{}])[0]
        price_info = item.get("price", {})
        output.append(
            {
                "productId": p.get("productId"),
                "upc": p.get("upc", p.get("productId")),
                "description": p.get("description", ""),
                "brand": p.get("brand", ""),
                "size": item.get("size", ""),
                "regular_price": price_info.get("regular"),
                "promo_price": price_info.get("promo"),
                "in_stock": item.get("inventory", {}).get("stockLevel", ""),
                "fulfillment": item.get("fulfillment", {}),
            }
        )
    print(json.dumps(output, indent=2))


def cmd_product(args, client):
    """Get product details."""
    location_id = args.location or os.getenv("KROGER_LOCATION_ID")
    if not location_id:
        print("--location or KROGER_LOCATION_ID required")
        sys.exit(1)
    result = client.get_product(args.id, location_id)
    print(json.dumps(result.get("data", {}), indent=2))


def cmd_cart_add(args, client):
    """Add items to cart."""
    items = json.loads(args.items)
    result = client.add_to_cart(items)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Kroger API CLI")
    sub = parser.add_subparsers(dest="command")

    # auth
    sub.add_parser("auth", help="Interactive OAuth setup for cart access")

    # stores
    p_stores = sub.add_parser("stores", help="Find stores near ZIP")
    p_stores.add_argument("--zip", help="ZIP code")
    p_stores.add_argument("--radius", type=int, default=10, help="Radius in miles")
    p_stores.add_argument("--limit", type=int, default=5, help="Max results")

    # search
    p_search = sub.add_parser("search", help="Search products")
    p_search.add_argument("--query", required=True, help="Search term")
    p_search.add_argument("--location", help="Store location ID")
    p_search.add_argument("--limit", type=int, default=10, help="Max results")

    # product
    p_product = sub.add_parser("product", help="Get product details")
    p_product.add_argument("--id", required=True, help="Product ID")
    p_product.add_argument("--location", help="Store location ID")

    # cart-add
    p_cart = sub.add_parser("cart-add", help="Add items to cart")
    p_cart.add_argument(
        "--items", required=True, help='JSON array: [{"upc":"...","quantity":N}]'
    )

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    client = KrogerClient()

    commands = {
        "auth": cmd_auth,
        "stores": cmd_stores,
        "search": cmd_search,
        "product": cmd_product,
        "cart-add": cmd_cart_add,
    }
    commands[args.command](args, client)


if __name__ == "__main__":
    main()
