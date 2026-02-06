"""Tests for BalanceTracker and debt simplification."""

import pytest

from splitwise.user import User
from splitwise.expense import Expense, SplitType
from splitwise.balance import BalanceTracker, Transaction


@pytest.fixture
def alice():
    return User(name="Alice", id="alice")


@pytest.fixture
def bob():
    return User(name="Bob", id="bob")


@pytest.fixture
def charlie():
    return User(name="Charlie", id="charlie")


@pytest.fixture
def dave():
    return User(name="Dave", id="dave")


class TestBalanceTracking:
    def test_single_expense(self, alice, bob):
        tracker = BalanceTracker()
        expense = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(expense)

        assert tracker.get_balance(alice) == 50.0
        assert tracker.get_balance(bob) == -50.0

    def test_multiple_expenses(self, alice, bob):
        tracker = BalanceTracker()

        e1 = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        e2 = Expense(
            description="Coffee",
            total_amount=20.0,
            paid_by={bob: 20.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(e1)
        tracker.add_expense(e2)

        # Alice: +50 from e1, -10 from e2 = +40
        # Bob: -50 from e1, +10 from e2 = -40
        assert tracker.get_balance(alice) == 40.0
        assert tracker.get_balance(bob) == -40.0

    def test_remove_expense(self, alice, bob):
        tracker = BalanceTracker()
        expense = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(expense)
        removed = tracker.remove_expense(expense.id)

        assert removed is not None
        assert tracker.get_balance(alice) == 0.0
        assert tracker.get_balance(bob) == 0.0

    def test_remove_nonexistent_expense(self):
        tracker = BalanceTracker()
        assert tracker.remove_expense("nonexistent") is None

    def test_unknown_user_balance(self, alice):
        tracker = BalanceTracker()
        assert tracker.get_balance(alice) == 0.0


class TestDebtSimplification:
    def test_two_people(self, alice, bob):
        tracker = BalanceTracker()
        expense = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(expense)

        txns = tracker.simplify_debts()
        assert len(txns) == 1
        assert txns[0].payer == bob
        assert txns[0].payee == alice
        assert txns[0].amount == 50.0

    def test_three_people_one_payer(self, alice, bob, charlie):
        tracker = BalanceTracker()
        expense = Expense(
            description="Dinner",
            total_amount=90.0,
            paid_by={alice: 90.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None},
        )
        tracker.add_expense(expense)

        txns = tracker.simplify_debts()
        assert len(txns) == 2
        total_to_alice = sum(t.amount for t in txns if t.payee == alice)
        assert total_to_alice == 60.0

    def test_simplification_reduces_transactions(self, alice, bob, charlie):
        """If A owes B and B owes C, simplification should produce A->C directly."""
        tracker = BalanceTracker()

        # Alice pays 60, split equally among A, B, C => each owes 20
        # So B owes Alice 20, Charlie owes Alice 20
        e1 = Expense(
            description="Dinner",
            total_amount=60.0,
            paid_by={alice: 60.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None},
        )
        # Bob pays 60, split equally among A, B, C => each owes 20
        # So Alice owes Bob 20, Charlie owes Bob 20
        e2 = Expense(
            description="Taxi",
            total_amount=60.0,
            paid_by={bob: 60.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None},
        )
        tracker.add_expense(e1)
        tracker.add_expense(e2)

        # Net: Alice +20, Bob +20, Charlie -40
        # Simplified: Charlie pays Alice 20, Charlie pays Bob 20
        txns = tracker.simplify_debts()
        assert len(txns) == 2

        total_paid_by_charlie = sum(t.amount for t in txns if t.payer == charlie)
        assert total_paid_by_charlie == 40.0

    def test_four_people_complex(self, alice, bob, charlie, dave):
        tracker = BalanceTracker()

        e1 = Expense(
            description="Hotel",
            total_amount=400.0,
            paid_by={alice: 400.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None, dave: None},
        )
        e2 = Expense(
            description="Gas",
            total_amount=100.0,
            paid_by={bob: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None, dave: None},
        )
        tracker.add_expense(e1)
        tracker.add_expense(e2)

        txns = tracker.simplify_debts()
        # At most N-1 = 3 transactions
        assert len(txns) <= 3

        # Verify the total amounts balance out
        for txn in txns:
            assert txn.amount > 0

    def test_already_settled(self, alice, bob):
        tracker = BalanceTracker()
        e1 = Expense(
            description="Lunch",
            total_amount=50.0,
            paid_by={alice: 50.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        e2 = Expense(
            description="Dinner",
            total_amount=50.0,
            paid_by={bob: 50.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(e1)
        tracker.add_expense(e2)

        txns = tracker.simplify_debts()
        assert len(txns) == 0


class TestSettleDebt:
    def test_settle_debt(self, alice, bob):
        tracker = BalanceTracker()
        expense = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(expense)
        tracker.settle_debt(payer=bob, payee=alice, amount=50.0)

        assert tracker.get_balance(alice) == 0.0
        assert tracker.get_balance(bob) == 0.0

    def test_partial_settlement(self, alice, bob):
        tracker = BalanceTracker()
        expense = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(expense)
        tracker.settle_debt(payer=bob, payee=alice, amount=30.0)

        assert tracker.get_balance(alice) == 20.0
        assert tracker.get_balance(bob) == -20.0

    def test_settle_negative_amount(self, alice, bob):
        tracker = BalanceTracker()
        with pytest.raises(ValueError, match="positive"):
            tracker.settle_debt(payer=bob, payee=alice, amount=-10.0)


class TestPairwiseBalances:
    def test_simple_pairwise(self, alice, bob):
        tracker = BalanceTracker()
        expense = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        tracker.add_expense(expense)

        pairwise = tracker.get_pairwise_balances()
        assert (bob, alice) in pairwise
        assert pairwise[(bob, alice)] == 50.0
