"""Tests for User model."""

from splitwise.user import User


def test_user_creation():
    user = User(name="Alice")
    assert user.name == "Alice"
    assert user.id is not None
    assert user.email is None
    assert user.phone is None


def test_user_with_contact_info():
    user = User(name="Bob", email="bob@example.com", phone="555-1234")
    assert user.email == "bob@example.com"
    assert user.phone == "555-1234"


def test_user_unique_ids():
    u1 = User(name="Alice")
    u2 = User(name="Alice")
    assert u1.id != u2.id
    assert u1 != u2


def test_user_equality_by_id():
    u1 = User(name="Alice", id="same_id")
    u2 = User(name="Bob", id="same_id")
    assert u1 == u2


def test_user_hashable():
    u1 = User(name="Alice")
    u2 = User(name="Bob")
    s = {u1, u2}
    assert len(s) == 2


def test_user_repr():
    user = User(name="Alice", id="abc123")
    assert "Alice" in repr(user)
    assert "abc123" in repr(user)
