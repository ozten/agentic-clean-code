"""Golden accounting cases V01-V07 from the design doc. Artificial numbers, not measurements."""
import unittest
from decimal import Decimal

from harness.accounting import (AttemptUsage, PricingProfile, Usage, UsageError, aggregate, output_budget,
                                parse_usage, request_cost_usd, reserve_usd)

FICTIONAL = PricingProfile(id="fictional", snapshot_id="fictional", model="fictional", snapshot=None,
                           ordinary_input=Decimal("2"), cached_input=Decimal("0.20"), cache_write=Decimal("2.50"),
                           output=Decimal("10"), cache_write_category="priced", long_context_threshold=272_000,
                           context_window=400_000, reasoning_efforts=("medium",), doc_url="")
LEGACY = PricingProfile(id="legacy", snapshot_id="fictional", model="legacy", snapshot=None,
                        ordinary_input=Decimal("2"), cached_input=Decimal("0.20"), cache_write=Decimal("0"),
                        output=Decimal("10"), cache_write_category="none", long_context_threshold=None,
                        context_window=272_000, reasoning_efforts=("medium",), doc_url="")


def raw(I, C, W, O, R, T):
    return {"input_tokens": I, "input_tokens_details": {"cached_tokens": C, "cache_write_tokens": W},
            "output_tokens": O, "output_tokens_details": {"reasoning_tokens": R}, "total_tokens": T}


ONE = raw(1000, 600, 200, 200, 120, 1200)
TWO = raw(1500, 1000, 0, 300, 200, 1800)


class GoldenCases(unittest.TestCase):
    def test_v01_sums_without_double_counting(self):
        one, two = parse_usage(ONE, FICTIONAL), parse_usage(TWO, FICTIONAL)
        totals = aggregate([AttemptUsage("a", "solving", one), AttemptUsage("b", "solving", two)])
        self.assertEqual(totals.input_tokens, 2500)
        self.assertEqual(totals.output_tokens, 500)
        self.assertEqual(totals.exact_total, 3000)
        self.assertEqual(totals.cached_tokens, 1600)
        self.assertEqual(totals.cache_write_tokens, 200)
        self.assertEqual(totals.reasoning_tokens, 320)
        self.assertEqual(totals.ordinary_input, 700)
        self.assertEqual(totals.non_reasoning_output, 180)
        self.assertNotEqual(totals.exact_total, 5120)

    def test_v02_rate_card_costs(self):
        one, two = parse_usage(ONE, FICTIONAL), parse_usage(TWO, FICTIONAL)
        self.assertEqual(request_cost_usd(one, FICTIONAL), Decimal("0.00302"))
        self.assertEqual(request_cost_usd(two, FICTIONAL), Decimal("0.00420"))
        self.assertEqual(request_cost_usd(one, FICTIONAL) + request_cost_usd(two, FICTIONAL), Decimal("0.00722"))

    def test_v03_duplicate_ingestion_counts_once(self):
        one = parse_usage(ONE, FICTIONAL)
        totals = aggregate([AttemptUsage("a", "solving", one), AttemptUsage("a", "solving", one)])
        self.assertEqual(totals.exact_total, 1200)
        # Two genuine attempts with identical prompts remain two attempts.
        totals = aggregate([AttemptUsage("a", "solving", one), AttemptUsage("b", "solving", one)])
        self.assertEqual(totals.exact_total, 2400)

    def test_v04_timeout_without_usage_voids_exact_total(self):
        one = parse_usage(ONE, FICTIONAL)
        totals = aggregate([AttemptUsage("a", "solving", one, cost_usd=Decimal("0.00302")),
                            AttemptUsage("b", "solving", None, "timeout", None, Decimal("0.05"))])
        self.assertIsNone(totals.exact_total)
        self.assertEqual(totals.known_lower_bound, 1200)
        self.assertFalse(totals.usage_complete)
        self.assertEqual(totals.unresolved_reserve_usd, Decimal("0.05"))
        self.assertEqual(totals.missing_attempt_ids, ["b"])
        self.assertIsNone(totals.estimated_cost_usd)
        self.assertEqual(totals.known_cost_usd, Decimal("0.00302"))

    def test_v05_incomplete_and_refusal_still_consume(self):
        usage = parse_usage(raw(500, 0, 0, 8192, 8192, 8692), FICTIONAL)
        totals = aggregate([AttemptUsage("a", "solving", usage, "incomplete")])
        self.assertEqual(totals.exact_total, 8692)
        self.assertEqual(totals.non_reasoning_output, 0)

    def test_v06_invalid_usage_rejected(self):
        bad = [raw(-1, 0, 0, 1, 0, 0), raw(True, 0, 0, 1, 0, 2), raw(100, 80, 30, 10, 0, 110),
               raw(100, 0, 0, 10, 11, 110), raw(100, 0, 0, 10, 0, 111)]
        for case in bad:
            with self.subTest(case=case), self.assertRaises(UsageError):
                parse_usage(case, FICTIONAL)
        missing_total = {"input_tokens": 1, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                         "output_tokens": 1, "output_tokens_details": {"reasoning_tokens": 0}}
        with self.assertRaises(UsageError):
            parse_usage(missing_total, FICTIONAL)
        with self.assertRaises(UsageError):
            parse_usage(None, FICTIONAL)
        no_write = raw(100, 10, 0, 10, 0, 110)
        del no_write["input_tokens_details"]["cache_write_tokens"]
        with self.assertRaises(UsageError):
            parse_usage(no_write, FICTIONAL)          # unexplained absence
        with self.assertRaises(UsageError):
            parse_usage(no_write, None)

    def test_v06_verified_legacy_cache_write_branch(self):
        no_write = raw(100, 10, 0, 10, 0, 110)
        del no_write["input_tokens_details"]["cache_write_tokens"]
        usage = parse_usage(no_write, LEGACY)
        self.assertEqual(usage.cache_write_tokens, 0)
        self.assertTrue(usage.cache_write_normalized)
        self.assertEqual(request_cost_usd(usage, LEGACY), (Decimal(90) * 2 + Decimal(10) * Decimal("0.20") + Decimal(100)) / Decimal(1_000_000))

    def test_v07_output_budget(self):
        self.assertIsNone(output_budget(99_000, 500))
        self.assertEqual(output_budget(90_000, 2_000), 8_000)
        self.assertEqual(output_budget(0, 1_000), 8_192)
        self.assertIsNone(output_budget(0, 399_500, context_window=400_000))

    def test_reserve_uses_highest_input_rate(self):
        self.assertEqual(reserve_usd(1_000, 8_192, FICTIONAL), (Decimal(1000) * Decimal("2.50") + Decimal(8192) * 10) / Decimal(1_000_000))

    def test_long_context_bracket_rejected(self):
        usage = Usage(300_000, 0, 0, 10, 0, 300_010)
        with self.assertRaises(UsageError):
            request_cost_usd(usage, FICTIONAL)


if __name__ == "__main__":
    unittest.main()
