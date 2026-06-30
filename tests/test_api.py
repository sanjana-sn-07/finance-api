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


def test_get_transaction_not_found(client, auth_headers):
    response = client.get("/transactions/999", headers=auth_headers)
    assert response.status_code == 404


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
