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


if __name__ == "__main__":
    unittest.main()
