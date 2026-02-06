"""Tests for Expense model."""

import pytest

from splitwise.user import User
from splitwise.expense import Expense, SplitType


@pytest.fixture
def alice():
    return User(name="Alice", id="alice")


@pytest.fixture
def bob():
    return User(name="Bob", id="bob")


@pytest.fixture
def charlie():
    return User(name="Charlie", id="charlie")


class TestEqualSplit:
    def test_equal_two_people(self, alice, bob):
        expense = Expense(
            description="Lunch",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None},
        )
        shares = expense.compute_shares()
        assert shares[alice] == 50.0
        assert shares[bob] == 50.0

    def test_equal_three_people(self, alice, bob, charlie):
        expense = Expense(
            description="Dinner",
            total_amount=90.0,
            paid_by={alice: 90.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None},
        )
        shares = expense.compute_shares()
        assert shares[alice] == 30.0
        assert shares[bob] == 30.0
        assert shares[charlie] == 30.0

    def test_equal_net_balances(self, alice, bob, charlie):
        expense = Expense(
            description="Dinner",
            total_amount=90.0,
            paid_by={alice: 90.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None},
        )
        balances = expense.compute_net_balances()
        assert balances[alice] == 60.0   # paid 90, owes 30
        assert balances[bob] == -30.0    # paid 0, owes 30
        assert balances[charlie] == -30.0


class TestExactSplit:
    def test_exact_split(self, alice, bob, charlie):
        expense = Expense(
            description="Groceries",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.EXACT,
            split_data={alice: 50.0, bob: 30.0, charlie: 20.0},
        )
        shares = expense.compute_shares()
        assert shares[alice] == 50.0
        assert shares[bob] == 30.0
        assert shares[charlie] == 20.0

    def test_exact_split_must_sum_to_total(self, alice, bob):
        with pytest.raises(ValueError, match="must equal total"):
            Expense(
                description="Bad",
                total_amount=100.0,
                paid_by={alice: 100.0},
                split_type=SplitType.EXACT,
                split_data={alice: 40.0, bob: 40.0},
            )


class TestPercentageSplit:
    def test_percentage_split(self, alice, bob):
        expense = Expense(
            description="Taxi",
            total_amount=50.0,
            paid_by={alice: 50.0},
            split_type=SplitType.PERCENTAGE,
            split_data={alice: 60.0, bob: 40.0},
        )
        shares = expense.compute_shares()
        assert shares[alice] == 30.0
        assert shares[bob] == 20.0

    def test_percentage_must_sum_to_100(self, alice, bob):
        with pytest.raises(ValueError, match="must sum to 100"):
            Expense(
                description="Bad",
                total_amount=50.0,
                paid_by={alice: 50.0},
                split_type=SplitType.PERCENTAGE,
                split_data={alice: 60.0, bob: 60.0},
            )


class TestSharesSplit:
    def test_shares_split(self, alice, bob, charlie):
        expense = Expense(
            description="Pizza",
            total_amount=120.0,
            paid_by={alice: 120.0},
            split_type=SplitType.SHARES,
            split_data={alice: 2, bob: 2, charlie: 2},
        )
        shares = expense.compute_shares()
        assert shares[alice] == 40.0
        assert shares[bob] == 40.0
        assert shares[charlie] == 40.0

    def test_unequal_shares(self, alice, bob):
        expense = Expense(
            description="Pizza",
            total_amount=100.0,
            paid_by={alice: 100.0},
            split_type=SplitType.SHARES,
            split_data={alice: 1, bob: 3},
        )
        shares = expense.compute_shares()
        assert shares[alice] == 25.0
        assert shares[bob] == 75.0


class TestMultiplePayers:
    def test_two_payers(self, alice, bob, charlie):
        expense = Expense(
            description="Dinner",
            total_amount=90.0,
            paid_by={alice: 60.0, bob: 30.0},
            split_type=SplitType.EQUAL,
            split_data={alice: None, bob: None, charlie: None},
        )
        balances = expense.compute_net_balances()
        assert balances[alice] == 30.0   # paid 60, owes 30
        assert balances[bob] == 0.0      # paid 30, owes 30
        assert balances[charlie] == -30.0


class TestValidation:
    def test_negative_amount(self, alice):
        with pytest.raises(ValueError, match="positive"):
            Expense(
                description="Bad",
                total_amount=-10.0,
                paid_by={alice: -10.0},
                split_type=SplitType.EQUAL,
                split_data={alice: None},
            )

    def test_payment_mismatch(self, alice, bob):
        with pytest.raises(ValueError, match="Sum of payments"):
            Expense(
                description="Bad",
                total_amount=100.0,
                paid_by={alice: 50.0},
                split_type=SplitType.EQUAL,
                split_data={alice: None, bob: None},
            )

    def test_empty_split_data(self, alice):
        with pytest.raises(ValueError, match="at least one"):
            Expense(
                description="Bad",
                total_amount=100.0,
                paid_by={alice: 100.0},
                split_type=SplitType.EQUAL,
                split_data={},
            )
