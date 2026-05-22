from django.test import SimpleTestCase

from patients.views import _parse_llm_analysis_response


class RepairContractTests(SimpleTestCase):
    def assertContract(self, raw, *, failure_type, domain_gate, trusted, score_min=None, score_max=None, structure_type=None):
        parsed = _parse_llm_analysis_response(raw)

        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get('failure_type'), failure_type)
        self.assertEqual(parsed.get('domain_gate'), domain_gate)
        self.assertEqual(parsed.get('trusted'), trusted)

        if score_min is not None:
            self.assertGreaterEqual(parsed.get('recovery_score', 0.0), score_min)
        if score_max is not None:
            self.assertLessEqual(parsed.get('recovery_score', 0.0), score_max)
        if structure_type is not None:
            self.assertEqual(parsed.get('structure_type'), structure_type)

        return parsed

    def test_truncated_object_ultra_short_is_hard_fail(self):
        self.assertContract(
            '{"dataset_',
            failure_type='hard',
            domain_gate=False,
            trusted=False,
            score_max=0.0,
        )

    def test_dataset_summary_only_is_hard_fail(self):
        parsed = self.assertContract(
            '{"dataset_summary": {"rows": 50}}',
            failure_type='hard',
            domain_gate=False,
            trusted=False,
            score_min=0.0,
            score_max=0.6,
        )
        self.assertEqual(parsed.get('presence_score'), 0.333)
        self.assertEqual(parsed.get('completeness_score'), 0.333)

    def test_array_root_broken_is_hard_fail(self):
        parsed = self.assertContract(
            '[{"a":1}, {"b":2',
            failure_type='hard',
            domain_gate=False,
            trusted=False,
            structure_type='array_root',
        )
        self.assertEqual(parsed.get('domain_score'), 0.0)
        self.assertIn('results', parsed)

    def test_garbage_prefix_valid_json_is_soft_and_trusted(self):
        parsed = self.assertContract(
            'Sure! here is result:\n{"dataset_summary": {"rows": 10}, "medical_analysis": {"issues": ["x"]}}\nBut note: truncated',
            failure_type='soft',
            domain_gate=True,
            trusted=True,
            score_min=0.4,
        )
        self.assertEqual(parsed.get('presence_score'), 0.667)
        self.assertEqual(parsed.get('completeness_score'), 0.667)

    def test_python_literal_is_soft_and_trusted(self):
        parsed = self.assertContract(
            "{'dataset_summary': {'rows': 10}, 'medical_analysis': {'issues': ['x']}}",
            failure_type='soft',
            domain_gate=True,
            trusted=True,
            score_min=0.6,
        )
        self.assertEqual(parsed.get('presence_score'), 0.667)
        self.assertEqual(parsed.get('completeness_score'), 0.667)

    def test_noisy_multi_prefix_variant_is_soft_and_trusted(self):
        parsed = self.assertContract(
            'Noise prefix Some commentary... Some commentary... {"dataset_summary": {"rows": 40}, "medical_analysis": {"issues": ["i1"]}}',
            failure_type='soft',
            domain_gate=True,
            trusted=True,
            score_min=0.6,
        )
        self.assertEqual(parsed.get('domain_score'), 0.667)

    def test_valid_incomplete_is_soft_and_trusted(self):
        parsed = self.assertContract(
            '{"dataset_summary": {"rows": 200, "columns": 8}, "medical_analysis": {"issues": []}}',
            failure_type='soft',
            domain_gate=True,
            trusted=True,
            score_min=0.5,
        )
        self.assertEqual(parsed.get('presence_score'), 0.667)
        self.assertEqual(parsed.get('completeness_score'), 0.333)

    def test_bad_escape_json_is_hard_fail(self):
        parsed = self.assertContract(
            '{"dataset_summary": {"rows": 20, "notes": "contains "quotes" and unfinished"',
            failure_type='hard',
            domain_gate=False,
            trusted=False,
            score_max=0.6,
        )
        self.assertLess(parsed.get('domain_score', 1.0), 0.4)
