"""Unit tests for core/state_model.py (FR 4.0).

The tests cover:
  - Reading the bundled Order state machine.
  - Each of the three coverage strategies producing the expected counts.
  - Output shape compatibility with the rest of the pipeline (every test
    case must carry the fields the optimiser / exporter / runner depend on).
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import state_model  # noqa: E402


REQUIRED_TC_FIELDS = (
    "test_case_id", "requirement_id", "feature", "title", "description",
    "test_design_technique", "coverage_item", "coverage_type",
    "preconditions", "test_data", "steps", "expected_result", "priority",
    "risk_level", "risk_score", "traceability", "review_status",
    "need_manual_review",
)


class TestStateModel(unittest.TestCase):

    def setUp(self):
        self.model = state_model.load_default_order_model()

    # --- model loading ---------------------------------------------------

    def test_default_model_has_three_states(self):
        self.assertEqual(set(self.model.states),
                         {"pending", "completed", "cancelled"})
        self.assertEqual(self.model.initial, "pending")
        self.assertEqual(set(self.model.terminal),
                         {"completed", "cancelled"})

    def test_default_model_distinguishes_valid_and_invalid_transitions(self):
        self.assertEqual(len(self.model.valid_transitions()), 2)
        self.assertEqual(len(self.model.invalid_transitions()), 2)

    # --- algorithms ------------------------------------------------------

    def test_all_states_visits_every_state(self):
        result = state_model.generate_state_test_cases(
            self.model, strategy="all_states")
        ending_states = {tc["coverage_item"].split("--> ")[-1]
                          for tc in result["test_cases"]}
        ending_states.add(self.model.initial)
        self.assertEqual(ending_states, set(self.model.states))

    def test_all_transitions_emits_one_case_per_valid_edge(self):
        result = state_model.generate_state_test_cases(
            self.model, strategy="all_transitions")
        self.assertEqual(len(result["test_cases"]),
                         len(self.model.valid_transitions()))

    def test_guards_strategy_includes_invalid_transitions(self):
        result = state_model.generate_state_test_cases(
            self.model, strategy="all_transitions+guards")
        invalid_cases = [tc for tc in result["test_cases"]
                         if tc["coverage_type"] == "negative"]
        self.assertEqual(len(invalid_cases),
                         len(self.model.invalid_transitions()))

    # --- pipeline compatibility -----------------------------------------

    def test_test_cases_carry_all_required_fields(self):
        result = state_model.generate_state_test_cases(
            self.model, strategy="all_transitions+guards")
        for tc in result["test_cases"]:
            for field in REQUIRED_TC_FIELDS:
                self.assertIn(field, tc, f"missing field: {field}")

    def test_summary_counts_match_cases(self):
        result = state_model.generate_state_test_cases(
            self.model, strategy="all_transitions+guards")
        self.assertEqual(result["summary"]["total"],
                         len(result["test_cases"]))
        by_technique = result["summary"]["by_technique"]
        self.assertEqual(by_technique[state_model.TECHNIQUE],
                         len(result["test_cases"]))

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            state_model.generate_state_test_cases(
                self.model, strategy="nonsense")


if __name__ == "__main__":
    unittest.main()
