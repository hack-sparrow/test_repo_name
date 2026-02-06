"""Tests for the SplitwiseApp facade."""

import pytest

from splitwise.app import SplitwiseApp
from splitwise.expense import SplitType


@pytest.fixture
def app():
    return SplitwiseApp()


class TestUserManagement:
    def test_add_user(self, app):
        user = app.add_user("Alice")
        assert user.name == "Alice"
        assert app.get_user(user.id) == user

    def test_add_user_with_contact(self, app):
        user = app.add_user("Alice", email="alice@example.com", phone="555-0001")
        assert user.email == "alice@example.com"
        assert user.phone == "555-0001"

    def test_get_all_users(self, app):
        app.add_user("Alice")
        app.add_user("Bob")
        assert len(app.get_all_users()) == 2

    def test_remove_user(self, app):
        user = app.add_user("Alice")
        removed = app.remove_user(user.id)
        assert removed == user
        assert app.get_user(user.id) is None

    def test_find_users_by_name(self, app):
        app.add_user("Alice")
        app.add_user("Bob")
        app.add_user("Alicia")

        results = app.find_users_by_name("ali")
        assert len(results) == 2


class TestGroupManagement:
    def test_create_group(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")
        group = app.create_group("Trip", members=[alice, bob])

        assert group.name == "Trip"
        assert len(group.members) == 2

    def test_add_remove_from_group(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")
        group = app.create_group("Trip", members=[alice])

        assert app.add_user_to_group(bob.id, group.id)
        assert bob in group.members

        assert app.remove_user_from_group(bob.id, group.id)
        assert bob not in group.members

    def test_add_invalid_user_to_group(self, app):
        group = app.create_group("Trip")
        assert not app.add_user_to_group("nonexistent", group.id)


class TestExpenseManagement:
    def test_add_equal_expense(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")

        expense = app.add_equal_expense(
            description="Lunch",
            total_amount=100.0,
            paid_by_user=alice,
            participants=[alice, bob],
        )

        assert expense.total_amount == 100.0
        assert app.get_balance(alice) == 50.0
        assert app.get_balance(bob) == -50.0

    def test_add_expense_with_split(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")
        charlie = app.add_user("Charlie")

        expense = app.add_expense(
            description="Dinner",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EXACT,
            split_data={alice: 50.0, bob: 30.0, charlie: 20.0},
        )

        assert app.get_balance(alice) == 50.0
        assert app.get_balance(bob) == -30.0
        assert app.get_balance(charlie) == -20.0

    def test_remove_expense(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")

        expense = app.add_equal_expense("Lunch", 100.0, alice, [alice, bob])
        app.remove_expense(expense.id)

        assert app.get_balance(alice) == 0.0
        assert app.get_balance(bob) == 0.0

    def test_get_expenses(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")

        app.add_equal_expense("Lunch", 50.0, alice, [alice, bob])
        app.add_equal_expense("Dinner", 80.0, bob, [alice, bob])

        assert len(app.get_expenses()) == 2


class TestGroupExpenses:
    def test_expense_in_group(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")
        group = app.create_group("Trip", members=[alice, bob])

        app.add_equal_expense("Hotel", 200.0, alice, [alice, bob], group_id=group.id)

        balances = app.get_group_balances(group.id)
        assert balances[alice] == 100.0
        assert balances[bob] == -100.0

    def test_simplify_group_debts(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")
        charlie = app.add_user("Charlie")
        group = app.create_group("Trip", members=[alice, bob, charlie])

        app.add_equal_expense("Hotel", 300.0, alice, [alice, bob, charlie], group_id=group.id)
        app.add_equal_expense("Food", 150.0, bob, [alice, bob, charlie], group_id=group.id)

        txns = app.simplify_group_debts(group.id)
        assert len(txns) >= 1

        # Charlie owes the most
        charlie_payments = sum(t.amount for t in txns if t.payer == charlie)
        assert charlie_payments == 150.0

    def test_nonexistent_group(self, app):
        assert app.get_group_balances("fake") == {}
        assert app.simplify_group_debts("fake") == []


class TestSettlement:
    def test_full_settlement(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")

        app.add_equal_expense("Lunch", 100.0, alice, [alice, bob])
        app.settle_debt(payer=bob, payee=alice, amount=50.0)

        assert app.get_balance(alice) == 0.0
        assert app.get_balance(bob) == 0.0

    def test_simplify_after_settlement(self, app):
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")

        app.add_equal_expense("Lunch", 100.0, alice, [alice, bob])
        app.settle_debt(payer=bob, payee=alice, amount=50.0)

        txns = app.simplify_debts()
        assert len(txns) == 0


class TestEndToEnd:
    def test_full_trip_scenario(self, app):
        """Simulate a realistic group trip scenario."""
        alice = app.add_user("Alice")
        bob = app.add_user("Bob")
        charlie = app.add_user("Charlie")
        dave = app.add_user("Dave")

        group = app.create_group("Weekend Trip", members=[alice, bob, charlie, dave])
        everyone = [alice, bob, charlie, dave]

        # Alice books the hotel
        app.add_equal_expense("Hotel", 400.0, alice, everyone, group_id=group.id)
        # Bob pays for gas
        app.add_equal_expense("Gas", 80.0, bob, everyone, group_id=group.id)
        # Charlie pays for dinner
        app.add_equal_expense("Dinner", 120.0, charlie, everyone, group_id=group.id)
        # Dave pays for activities
        app.add_equal_expense("Activities", 200.0, dave, everyone, group_id=group.id)

        # Total: 800, each person's share: 200
        balances = app.get_group_balances(group.id)
        assert balances[alice] == 200.0   # paid 400, owes 200
        assert balances[bob] == -120.0    # paid 80, owes 200
        assert balances[charlie] == -80.0 # paid 120, owes 200
        assert balances[dave] == 0.0      # paid 200, owes 200

        txns = app.simplify_group_debts(group.id)
        # bob and charlie both owe alice
        assert len(txns) == 2

        total_settled = sum(t.amount for t in txns)
        assert total_settled == 200.0
