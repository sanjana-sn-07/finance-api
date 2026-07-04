import os

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest

PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")

_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def get_plaid_client() -> plaid_api.PlaidApi:
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        raise ValueError("PLAID_CLIENT_ID and PLAID_SECRET must be set in .env")

    configuration = plaid.Configuration(
        host=_HOSTS.get(PLAID_ENV, plaid.Environment.Sandbox),
        api_key={"clientId": PLAID_CLIENT_ID, "secret": PLAID_SECRET},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def create_link_token(client_user_id: str) -> str:
    client = get_plaid_client()
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Finance API",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=client_user_id),
    )
    response = client.link_token_create(request)
    return response["link_token"]


def create_sandbox_public_token() -> str:
    client = get_plaid_client()
    request = SandboxPublicTokenCreateRequest(
        institution_id="ins_109508",
        initial_products=[Products("transactions")],
    )
    response = client.sandbox_public_token_create(request)
    return response["public_token"]


def exchange_public_token(public_token: str) -> tuple[str, str]:
    client = get_plaid_client()
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)
    return response["access_token"], response["item_id"]


def sync_transactions(access_token: str, cursor: str | None = None) -> dict:
    client = get_plaid_client()
    request = TransactionsSyncRequest(
        access_token=access_token,
        cursor=cursor or "",
    )
    response = client.transactions_sync(request)
    return {
        "added": response["added"],
        "modified": response["modified"],
        "removed": response["removed"],
        "has_more": response["has_more"],
        "next_cursor": response["next_cursor"],
    }
