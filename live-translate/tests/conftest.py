import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Plan, User


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def test_user(db_session):
    user = User(email="user@example.test", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def test_plan(db_session):
    plan = Plan(
        code="pack_small",
        name="小包",
        interval="payg",
        price_cents=990,
        chars_per_period=72_000,
        duration_days=0,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan
