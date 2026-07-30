from unittest.mock import patch

import pytest

from app.auth.captcha import verify_captcha


class FakeRedis:
    def __init__(self, value):
        self.value = value
        self.deleted = []

    def get(self, _key):
        return self.value

    def delete(self, key):
        self.deleted.append(key)


@pytest.mark.parametrize("stored", ["ab3d", b"ab3d"])
def test_verify_captcha_accepts_redis_text_and_bytes(stored):
    redis = FakeRedis(stored)
    with patch("app.auth.captcha.get_redis", return_value=redis):
        assert verify_captcha("id", " AB3D ") is True
    assert redis.deleted == ["captcha:ans:id"]


def test_verify_captcha_consumes_wrong_answer_once():
    redis = FakeRedis("right")
    with patch("app.auth.captcha.get_redis", return_value=redis):
        assert verify_captcha("id", "wrong") is False
    assert redis.deleted == ["captcha:ans:id"]
