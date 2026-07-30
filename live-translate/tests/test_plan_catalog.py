import os
import unittest
from pathlib import Path

from app.billing.plans import DEFAULT_PLANS


class PlanCatalogTest(unittest.TestCase):
    def test_pack_small_uses_production_price(self):
        small = next(plan for plan in DEFAULT_PLANS if plan["code"] == "pack_small")

        self.assertEqual(990, small["price_cents"])

    def test_miniprogram_does_not_override_pack_small_to_test_price(self):
        repo_root = Path(
            os.environ.get("VI_TRANSLATE_ROOT", Path(__file__).resolve().parents[2])
        )
        pricing_js = (
            repo_root / "miniprogram" / "pages" / "pricing" / "pricing.js"
        ).read_text(encoding="utf-8")

        self.assertIn("{ id: 'pack_small', name: '小包', price_cents: 990", pricing_js)
        self.assertNotIn("return { ...p, price_cents: 10 };", pricing_js)


if __name__ == "__main__":
    unittest.main()
