from unittest.mock import patch


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Finance API is running"}


def test_register_success(client):
    response = client.post(
        "/register",
        json={"username": "alice", "password": "password123"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "User alice created successfully"}


def test_register_duplicate(client):
    payload = {"username": "alice", "password": "password123"}
    client.post("/register", json=payload)
    response = client.post("/register", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists"


def test_login_success(client):
    client.post("/register", json={"username": "bob", "password": "password123"})
    response = client.post(
        "/token",
        data={"username": "bob", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_login_invalid_credentials(client):
    client.post("/register", json={"username": "bob", "password": "password123"})
    response = client.post(
        "/token",
        data={"username": "bob", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_summary_requires_auth(client):
    response = client.get("/summary")
    assert response.status_code == 401


def test_transactions_requires_auth(client):
    response = client.get("/transactions")
    assert response.status_code == 401


def test_budget_requires_auth(client):
    response = client.get("/budget")
    assert response.status_code == 401


def test_report_requires_auth(client):
    response = client.get("/report")
    assert response.status_code == 401


def test_summary_empty(client, auth_headers):
    response = client.get("/summary", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_spending_category": None,
    }


def test_create_transaction(client, auth_headers, mock_openai):
    response = client.post(
        "/transactions",
        headers=auth_headers,
        json={"description": "coffee shop", "amount": 12.5, "category": "uncategorized"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "coffee shop"
    assert data["amount"] == 12.5
    assert data["category"] == "food"
    mock_openai.chat.completions.create.assert_called_once()


def test_create_transaction_with_category(client, auth_headers):
    response = client.post(
        "/transactions",
        headers=auth_headers,
        json={"description": "rent", "amount": 1500.0, "category": "utilities"},
    )
    assert response.status_code == 200
    assert response.json()["category"] == "utilities"


def test_get_transactions_list(client, auth_headers):
    client.post("/transactions", headers=auth_headers,
                json={"description": "groceries", "amount": 30.0, "category": "food"})
    client.post("/transactions", headers=auth_headers,
                json={"description": "bus", "amount": 5.0, "category": "transport"})
    response = client.get("/transactions", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_transaction_by_id(client, auth_headers):
    created = client.post(
        "/transactions",
        headers=auth_headers,
        json={"description": "lunch", "amount": 20.0, "category": "food"},
    ).json()
    response = client.get(f"/transactions/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["description"] == "lunch"


def test_get_transaction_not_found(client, auth_headers):
    response = client.get("/transactions/999", headers=auth_headers)
    assert response.status_code == 404


def test_report_empty(client, auth_headers):
    response = client.get("/report", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "No transactions found"


def test_report_with_transactions(client, auth_headers):
    client.post("/transactions", headers=auth_headers,
                json={"description": "groceries", "amount": 40.0, "category": "food"})
    client.post("/transactions", headers=auth_headers,
                json={"description": "uber", "amount": 15.0, "category": "transport"})
    response = client.get("/report", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_transactions"] == 2
    assert data["total_spent"] == 55.0
    assert len(data["top_categories"]) == 2
    assert len(data["monthly_breakdown"]) == 2


def test_budget_and_summary(client, auth_headers):
    client.post(
        "/transactions",
        headers=auth_headers,
        json={"description": "groceries", "amount": 40.0, "category": "food"},
    )
    client.post(
        "/transactions",
        headers=auth_headers,
        json={"description": "uber", "amount": 15.0, "category": "transport"},
    )

    budget = client.get("/budget", headers=auth_headers)
    assert budget.status_code == 200
    categories = {row["category"]: row for row in budget.json()}
    assert categories["food"]["total"] == 40.0
    assert categories["transport"]["total"] == 15.0

    summary = client.get("/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json() == {
        "total_spent": 55.0,
        "transaction_count": 2,
        "top_spending_category": "food",
    }


def test_summary_cache(client, auth_headers, mock_redis):
    client.post(
        "/transactions",
        headers=auth_headers,
        json={"description": "groceries", "amount": 20.0, "category": "food"},
    )

    first = client.get("/summary", headers=auth_headers)
    assert first.status_code == 200
    assert "summary:testuser" in mock_redis

    cached_value = mock_redis["summary:testuser"]
    second = client.get("/summary", headers=auth_headers)
    assert second.status_code == 200
    assert second.json() == cached_value

    client.post(
        "/transactions",
        headers=auth_headers,
        json={"description": "gas", "amount": 30.0, "category": "transport"},
    )
    assert "summary:testuser" not in mock_redis


def test_get_transactions_empty(client, auth_headers):
    response = client.get("/transactions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_budget_empty(client, auth_headers):
    response = client.get("/budget", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_report_top_categories_order(client, auth_headers):
    client.post("/transactions", headers=auth_headers,
                json={"description": "rent", "amount": 1500.0, "category": "utilities"})
    client.post("/transactions", headers=auth_headers,
                json={"description": "coffee", "amount": 5.0, "category": "food"})
    response = client.get("/report", headers=auth_headers)
    assert response.status_code == 200
    top = response.json()["top_categories"]
    assert top[0]["category"] == "utilities"
    assert top[0]["total"] == 1500.0


def test_create_multiple_transactions_summary(client, auth_headers):
    for i in range(5):
        client.post("/transactions", headers=auth_headers,
                    json={"description": f"item {i}", "amount": 10.0, "category": "shopping"})
    summary = client.get("/summary", headers=auth_headers)
    assert summary.json()["transaction_count"] == 5
    assert summary.json()["total_spent"] == 50.0


def test_invalid_token(client):
    response = client.get("/transactions", headers={"Authorization": "Bearer invalidtoken"})
    assert response.status_code == 401


def test_plaid_link_token(client, auth_headers):
    with patch("main.create_link_token", return_value="link-sandbox-test-token"):
        response = client.post("/plaid/link-token", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["link_token"] == "link-sandbox-test-token"


def test_plaid_link_token_error(client, auth_headers):
    with patch("main.create_link_token", side_effect=ValueError("Plaid error")):
        response = client.post("/plaid/link-token", headers=auth_headers)
    assert response.status_code == 500


def test_plaid_exchange_token(client, auth_headers):
    with patch("main.exchange_public_token", return_value=("access-sandbox-xxx", "item-xxx")):
        response = client.post(
            "/plaid/exchange-token",
            headers=auth_headers,
            json={"public_token": "public-sandbox-test"},
        )
    assert response.status_code == 200
    assert response.json()["item_id"] == "item-xxx"


def test_plaid_exchange_token_error(client, auth_headers):
    with patch("main.exchange_public_token", side_effect=Exception("exchange failed")):
        response = client.post(
            "/plaid/exchange-token",
            headers=auth_headers,
            json={"public_token": "bad-token"},
        )
    assert response.status_code == 400


def test_plaid_sandbox_setup(client, auth_headers):
    with patch("main.create_sandbox_public_token", return_value="public-sandbox-xxx"), \
         patch("main.exchange_public_token", return_value=("access-sandbox-xxx", "item-xxx")):
        response = client.post("/plaid/sandbox/setup", headers=auth_headers)
    assert response.status_code == 200
    assert "item_id" in response.json()


def test_plaid_sync_no_account(client, auth_headers):
    response = client.post("/plaid/sync", headers=auth_headers)
    assert response.status_code == 400
    assert "Link a Plaid account first" in response.json()["detail"]
