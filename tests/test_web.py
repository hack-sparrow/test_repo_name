"""Tests for the Flask web application."""

import pytest

from splitwise.web import create_flask_app, splitwise_app


@pytest.fixture
def client():
    app = create_flask_app()
    app.config["TESTING"] = True

    # Reset the global state for each test
    splitwise_app._users.clear()
    splitwise_app._groups.clear()
    splitwise_app._balance_tracker._expenses.clear()
    splitwise_app._balance_tracker._net_balances.clear()

    with app.test_client() as client:
        yield client


def _login(client):
    return client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)


class TestAuth:
    def test_login_page(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data

    def test_login_success(self, client):
        resp = _login(client)
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_login_failure(self, client):
        resp = client.post("/login", data={"username": "bad", "password": "bad"}, follow_redirects=True)
        assert b"Invalid credentials" in resp.data

    def test_redirect_when_not_logged_in(self, client):
        resp = client.get("/")
        assert resp.status_code == 302

    def test_logout(self, client):
        _login(client)
        resp = client.get("/logout", follow_redirects=True)
        assert b"Login" in resp.data


class TestUserManagement:
    def test_add_user(self, client):
        _login(client)
        resp = client.post("/users/add", data={"name": "Alice"}, follow_redirects=True)
        assert b"Alice" in resp.data
        assert b"created" in resp.data

    def test_add_user_with_contact(self, client):
        _login(client)
        resp = client.post("/users/add", data={
            "name": "Bob",
            "email": "bob@example.com",
            "phone": "555-1234",
        }, follow_redirects=True)
        assert b"Bob" in resp.data
        assert b"bob@example.com" in resp.data

    def test_add_user_empty_name(self, client):
        _login(client)
        resp = client.post("/users/add", data={"name": ""}, follow_redirects=True)
        assert b"required" in resp.data

    def test_delete_user(self, client):
        _login(client)
        user = splitwise_app.add_user("ToDelete")
        resp = client.post(f"/users/{user.id}/delete", follow_redirects=True)
        assert b"removed" in resp.data

    def test_users_page(self, client):
        _login(client)
        splitwise_app.add_user("Alice")
        resp = client.get("/users")
        assert b"Alice" in resp.data


class TestGroupManagement:
    def test_create_group(self, client):
        _login(client)
        alice = splitwise_app.add_user("Alice")
        bob = splitwise_app.add_user("Bob")
        resp = client.post("/groups/add", data={
            "name": "Trip",
            "members": [alice.id, bob.id],
        }, follow_redirects=True)
        assert b"Trip" in resp.data
        assert b"created" in resp.data


class TestExpense:
    def test_expense_page(self, client):
        _login(client)
        resp = client.get("/expense")
        assert resp.status_code == 200
        assert b"Describe the expense" in resp.data

    def test_parse_complete_expense(self, client):
        _login(client)
        splitwise_app.add_user("Alice")
        splitwise_app.add_user("Bob")
        resp = client.post("/expense", data={
            "action": "parse",
            "text": "Alice paid 100 for dinner with Bob",
        })
        assert resp.status_code == 200
        assert b"Confirm" in resp.data

    def test_parse_incomplete_expense(self, client):
        _login(client)
        resp = client.post("/expense", data={
            "action": "parse",
            "text": "paid for dinner",
        })
        assert resp.status_code == 200
        # Should have a follow-up question
        assert b"answer" in resp.data

    def test_confirm_expense(self, client):
        _login(client)
        splitwise_app.add_user("Alice")
        splitwise_app.add_user("Bob")
        resp = client.post("/expense", data={
            "action": "confirm",
            "payer_name": "Alice",
            "amount": "100",
            "description": "Dinner",
            "participant_names": '["Alice", "Bob"]',
            "split_type": "equal",
            "split_details": "{}",
        }, follow_redirects=True)
        assert b"added" in resp.data


class TestHistory:
    def test_history_page_empty(self, client):
        _login(client)
        resp = client.get("/history")
        assert resp.status_code == 200
        assert b"No expenses" in resp.data

    def test_history_with_expenses(self, client):
        _login(client)
        alice = splitwise_app.add_user("Alice")
        bob = splitwise_app.add_user("Bob")
        splitwise_app.add_equal_expense("Lunch", 50.0, alice, [alice, bob])
        resp = client.get("/history")
        assert b"Lunch" in resp.data
        assert b"50.00" in resp.data

    def test_delete_expense(self, client):
        _login(client)
        alice = splitwise_app.add_user("Alice")
        bob = splitwise_app.add_user("Bob")
        exp = splitwise_app.add_equal_expense("Lunch", 50.0, alice, [alice, bob])
        resp = client.post(f"/expense/{exp.id}/delete", follow_redirects=True)
        assert b"removed" in resp.data


class TestLedger:
    def test_ledger_page_empty(self, client):
        _login(client)
        resp = client.get("/ledger")
        assert resp.status_code == 200

    def test_ledger_with_balances(self, client):
        _login(client)
        alice = splitwise_app.add_user("Alice")
        bob = splitwise_app.add_user("Bob")
        splitwise_app.add_equal_expense("Lunch", 100.0, alice, [alice, bob])
        resp = client.get("/ledger")
        assert b"Alice" in resp.data
        assert b"Bob" in resp.data
        assert b"50.00" in resp.data

    def test_settle_debt(self, client):
        _login(client)
        alice = splitwise_app.add_user("Alice")
        bob = splitwise_app.add_user("Bob")
        splitwise_app.add_equal_expense("Lunch", 100.0, alice, [alice, bob])
        resp = client.post("/settle", data={
            "payer_id": bob.id,
            "payee_id": alice.id,
            "amount": "50",
        }, follow_redirects=True)
        assert b"paid" in resp.data
