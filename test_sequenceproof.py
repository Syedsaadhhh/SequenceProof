import unittest
from sequenceproof import SAMPLE, analyze, prune_orphaned_steps, replay


class ReproductionTests(unittest.TestCase):
    def test_sample_reduction_preserves_exact_failure(self):
        result = analyze(SAMPLE)
        self.assertEqual(result["status"], "REPRODUCED")
        self.assertLess(len(result["reduced_steps"]), len(SAMPLE))
        self.assertEqual({trial["failure_id"] for trial in result["trials"]}, {"WRONG_CARD_CHARGED"})
        self.assertTrue(result["fixed_passes"])
        self.assertEqual(replay(result["reduced_steps"])["failure_id"], "WRONG_CARD_CHARGED")

    def test_second_trace_is_computed(self):
        trace = [{"action":"set_card","card":"card-B"},{"action":"add_item","item":"pen"},
                 {"action":"begin_checkout"},{"action":"view_catalog"},{"action":"set_card","card":"card-C"},
                 {"action":"retry_payment"}]
        result = analyze(trace)
        self.assertEqual(result["status"], "REPRODUCED")
        self.assertEqual(result["original"]["expected"], "card-C")
        self.assertEqual(result["original"]["actual"], "card-B")
        self.assertEqual(replay(result["reduced_steps"])["failure_id"], "WRONG_CARD_CHARGED")

    def test_invalid_or_passing_trace_cannot_fake_bug(self):
        invalid = analyze([{"action":"retry_payment"}])
        self.assertEqual(invalid["status"], "INVALID_TRACE")
        self.assertIsNone(invalid["reduced_steps"])
        passing = analyze([{"action":"add_item","item":"pen"},{"action":"begin_checkout"},
                           {"action":"retry_payment"}])
        self.assertEqual(passing["status"], "NOT_REPRODUCED")
        self.assertIsNone(passing["reduced_steps"])

    def test_deleted_parent_prunes_orphan_but_never_invents_steps(self):
        candidate = [{"action":"remove_item","item":"noise"},
                     {"action":"add_item","item":"pen"},
                     {"action":"begin_checkout"},
                     {"action":"set_card","card":"card-B"},
                     {"action":"retry_payment"}]
        repaired, pruned = prune_orphaned_steps(candidate)
        self.assertEqual(pruned, 1)
        self.assertEqual(repaired, candidate[1:])
        self.assertEqual(replay(repaired)["failure_id"], "WRONG_CARD_CHARGED")

    def test_repair_does_not_hide_bad_parameters_or_make_a_bug(self):
        malformed, count = prune_orphaned_steps([{"action":"set_card","card":"invalid"}])
        self.assertEqual(count, 0)
        self.assertEqual(replay(malformed)["status"], "INVALID_TRACE")
        no_bug, count = prune_orphaned_steps([{"action":"retry_payment"}])
        self.assertEqual(count, 1)
        self.assertEqual(replay(no_bug)["status"], "NOT_REPRODUCED")

    def test_reduction_accepts_valid_repaired_candidate(self):
        trace = [{"action":"add_item","item":"noise"},
                 {"action":"add_item","item":"pen"},
                 {"action":"remove_item","item":"noise"},
                 {"action":"begin_checkout"},
                 {"action":"set_card","card":"card-B"},
                 {"action":"retry_payment"}]
        result = analyze(trace)
        self.assertEqual(result["status"], "REPRODUCED")
        self.assertGreater(result["orphan_steps_pruned"], 0)
        self.assertEqual(len(result["reduced_steps"]), 4)
        self.assertTrue(result["fixed_passes"])


    def test_post_retry_set_card_is_not_a_false_positive(self):
        """A set_card that occurs AFTER retry_payment must not trigger WRONG_CARD_CHARGED.

        The bug is a stale-snapshot charge: pending_card != card at the moment
        retry_payment fires.  Changing the active card AFTER a correct retry does
        not constitute the bug; the oracle must not report REPRODUCED for such a
        trace, and the corrected implementation must also pass (fixed_passes=True).
        """
        # Trace: card-A used for checkout AND retry (correct charge), then
        # the user switches to card-B.  The retry was never wrong.
        correct_retry_then_switch = [
            {"action": "add_item", "item": "pen"},
            {"action": "begin_checkout"},          # pending_card = card-A
            {"action": "retry_payment"},            # charges card-A == current card-A: CORRECT
            {"action": "set_card", "card": "card-B"},  # card changes AFTER the charge
        ]
        # Before fix: oracle fires because final charged_card(A) != final card(B).
        # After fix: oracle must NOT fire; the charge was correct at retry time.
        result = analyze(correct_retry_then_switch)
        self.assertNotEqual(result["status"], "REPRODUCED",
                            "Post-retry card change must not be reported as WRONG_CARD_CHARGED")
        self.assertIsNone(result.get("reduced_steps"),
                          "A false-positive trace must yield no reduced evidence")
        # Sanity: direct replay must not report the bug either
        self.assertNotEqual(
            replay(correct_retry_then_switch)["status"], "REPRODUCED",
            "replay() must return NOT_REPRODUCED when the charge was correct at retry time")

    def test_adversarial_cascade_prune_not_reproduced_is_rejected(self):
        """Orphan-pruning that cascades through begin_checkout and retry_payment
        must produce a NOT_REPRODUCED result that reduce_trace rejects, not a
        spurious WRONG_CARD_CHARGED claim.

        Candidate after deleting the only add_item:
          [begin_checkout, set_card(B), retry_payment]
        Pruner drops begin_checkout (empty cart) then retry_payment (no pending).
        The surviving [set_card(B)] replays to NOT_REPRODUCED.
        """
        candidate = [
            {"action": "begin_checkout"},           # cart empty -> pruner drops
            {"action": "set_card", "card": "card-B"},
            {"action": "retry_payment"},             # pending None -> pruner drops
        ]
        repaired, pruned = prune_orphaned_steps(candidate)
        self.assertEqual(pruned, 2, "both orphaned steps should be pruned")
        result = replay(repaired)
        self.assertEqual(result["status"], "NOT_REPRODUCED",
                         "cascade-pruned trace must replay as NOT_REPRODUCED, not REPRODUCED")
        self.assertIsNone(result["failure_id"],
                          "failure_id must be None so reduce_trace rejects this candidate")


    def test_earlier_wrong_retry_is_not_hidden_by_later_correct_retry(self):
        """An earlier wrong charge must not be hidden when a later retry is correct.

        Trace:
          begin_checkout (pending=card-A)
          set_card(card-B)
          retry_payment  -> charges card-A while card-B is active: WRONG
          set_card(card-A)
          retry_payment  -> charges card-A while card-A is active: CORRECT

        The first attempt is wrong, so the trace must be REPRODUCED with
        expected=card-B, actual=card-A.  The scalar last-retry oracle would
        have reported NOT_REPRODUCED (false negative); the per-attempt oracle
        must catch it.
        """
        trace = [
            {"action": "add_item", "item": "pen"},
            {"action": "begin_checkout"},               # pending_card = card-A
            {"action": "set_card", "card": "card-B"},
            {"action": "retry_payment"},                # charges A, expected B: WRONG
            {"action": "set_card", "card": "card-A"},
            {"action": "retry_payment"},                # charges A, expected A: CORRECT
        ]
        r = replay(trace)
        self.assertEqual(r["status"], "REPRODUCED")
        self.assertEqual(r["failure_id"], "WRONG_CARD_CHARGED")
        self.assertEqual(r["expected"], "card-B",
                         "expected must come from the first wrong attempt, not the last correct one")
        self.assertEqual(r["actual"], "card-A")

        result = analyze(trace)
        self.assertEqual(result["status"], "REPRODUCED")
        self.assertEqual(result["failure_id"], "WRONG_CARD_CHARGED")
        self.assertIsNotNone(result["reduced_steps"],
                             "a real bug must produce reduced evidence")
        self.assertTrue(result["fixed_passes"],
                        "the corrected implementation must charge current card on every retry")

    def test_multiple_correct_retries_do_not_reproduce(self):
        """Several retries on the same card must all report NOT_REPRODUCED.

        Each retry charges the pending_card which equals the card active at
        checkout and at every retry (no card switch occurs).  No attempt is
        wrong, so the oracle must not fire.
        """
        trace = [
            {"action": "add_item", "item": "widget"},
            {"action": "begin_checkout"},               # pending_card = card-A
            {"action": "retry_payment"},                # charges A, expected A: CORRECT
            {"action": "retry_payment"},                # charges A, expected A: CORRECT
            {"action": "retry_payment"},                # charges A, expected A: CORRECT
        ]
        r = replay(trace)
        self.assertEqual(r["status"], "NOT_REPRODUCED")
        self.assertIsNone(r["failure_id"])

        result = analyze(trace)
        self.assertEqual(result["status"], "NOT_REPRODUCED")
        self.assertIsNone(result.get("reduced_steps"))

        # Fixed path: same result — correct on every retry
        r_fixed = replay(trace, fixed=True)
        self.assertEqual(r_fixed["status"], "NOT_REPRODUCED")


if __name__ == "__main__":
    unittest.main()
