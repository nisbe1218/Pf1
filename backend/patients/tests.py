from django.test import SimpleTestCase
from unittest.mock import patch
import pandas as pd

from .views import (
	LLM_FOLLOWUP_REQUIRED_MESSAGE,
	_apply_llm_correction_plan,
	_build_preprocess_report,
	_build_deterministic_correction_plan,
	_merge_correction_plans,
	_normalize_correction_plan,
	_parse_llm_analysis_response,
	_sanitize_llm_limitations,
	_validate_preprocess_llm_output,
)


class LlmAnalysisParsingTests(SimpleTestCase):
	def test_truncated_dataset_summary_only_is_hard_fail(self):
		raw = '{"dataset_summary": {"rows": 1'

		parsed = _parse_llm_analysis_response(raw)

		self.assertIsInstance(parsed, dict)
		self.assertEqual(parsed.get('failure_type'), 'hard')
		self.assertFalse(parsed.get('trusted'))
		self.assertLess(parsed.get('domain_score', 1.0), 0.4)
		self.assertEqual(parsed.get('presence_score'), 0.333)
		self.assertEqual(parsed.get('completeness_score'), 0.333)

	def test_incomplete_structured_dataset_summary_only_is_hard_fail(self):
		raw = '{"dataset_summary": {"rows": 50}}'

		parsed = _parse_llm_analysis_response(raw)

		self.assertIsInstance(parsed, dict)
		self.assertEqual(parsed.get('failure_type'), 'hard')
		self.assertFalse(parsed.get('trusted'))
		self.assertEqual(parsed.get('structure_type'), 'object')
		self.assertEqual(parsed.get('presence_score'), 0.333)
		self.assertEqual(parsed.get('completeness_score'), 0.333)
		self.assertLess(parsed.get('domain_score', 1.0), 0.4)

	def test_meaningful_medical_content_passes_gate(self):
		raw = '{"dataset_summary": {"rows": 200, "columns": 8}, "medical_analysis": {"issues": ["x"]}}'

		parsed = _parse_llm_analysis_response(raw)

		self.assertIsInstance(parsed, dict)
		self.assertEqual(parsed.get('failure_type'), 'soft')
		self.assertTrue(parsed.get('trusted'))
		self.assertTrue(parsed.get('domain_gate'))
		self.assertGreaterEqual(parsed.get('domain_score', 0.0), 0.4)
		self.assertEqual(parsed.get('presence_score'), 0.667)
		self.assertEqual(parsed.get('completeness_score'), 0.667)

	def test_array_root_is_not_trusted_without_domain_content(self):
		raw = '[{"a":1}, {"b":2}]'

		parsed = _parse_llm_analysis_response(raw)

		self.assertIsInstance(parsed, dict)
		self.assertEqual(parsed.get('structure_type'), 'array_root')
		self.assertEqual(parsed.get('failure_type'), 'hard')
		self.assertFalse(parsed.get('domain_gate'))
		self.assertEqual(parsed.get('domain_score'), 0.0)
		self.assertIn('results', parsed)
		self.assertEqual(len(parsed['results']), 2)

	def test_noisy_json_with_real_content_stays_trusted(self):
		raw = 'Intro text... {"dataset_summary": {"rows": 10}, "medical_analysis": {"issues": ["x"]}} ... trailing text'

		parsed = _parse_llm_analysis_response(raw)

		self.assertIsInstance(parsed, dict)
		self.assertEqual(parsed.get('failure_type'), 'soft')
		self.assertTrue(parsed.get('domain_gate'))
		self.assertTrue(parsed.get('trusted'))
		self.assertEqual(parsed.get('presence_score'), 0.667)
		self.assertEqual(parsed.get('completeness_score'), 0.667)
		self.assertGreaterEqual(parsed.get('recovery_score', 0.0), 0.6)

	def test_fallback_invalid_json_is_hard_and_untrusted(self):
		with patch('patients.views._repair_json_text', return_value=None):
			parsed = _parse_llm_analysis_response('{"data_summary": {"columns_count": 85,')

		self.assertIsInstance(parsed, dict)
		self.assertEqual(parsed.get('failure_type'), 'hard')
		self.assertFalse(parsed.get('domain_gate'))
		self.assertFalse(parsed.get('trusted'))
		self.assertEqual(parsed.get('method_used'), 'fallback_invalid_json')
		self.assertIn('Le modele a repondu, mais le JSON est invalide.', parsed.get('limitations', []))

	def test_invalid_json_limitation_is_suppressed_after_recovery(self):
		limitations = _sanitize_llm_limitations(
			['Le modele a repondu, mais le JSON est invalide.', LLM_FOLLOWUP_REQUIRED_MESSAGE],
			suppress_invalid_json=True,
			suppress_followup=True,
		)

		self.assertEqual(limitations, [])


class LlmCorrectionPlanSafetyTests(SimpleTestCase):
	def _base_analysis_result(self):
		return {
			'dataset_summary': {},
			'medical_analysis': {},
			'missing_values_analysis': {},
			'outliers_analysis': {},
			'duplicate_analysis': {},
			'corrections_applied': [],
			'suspect_values': [],
			'remaining_risks': [],
			'recommendations': [],
			'cleaned_dataset_preview': [],
			'processing_statistics': {},
			'quality_score': {},
			'summary': 'ok',
			'correction_plan': {},
		}

	def test_normalization_forces_drop_columns_to_empty(self):
		analysis_result = self._base_analysis_result()
		analysis_result['correction_plan'] = {
			'drop_columns': ['age_annees'],
			'fill_missing': {'sexe': {'strategy': 'mode'}},
		}

		normalized = _normalize_correction_plan(analysis_result, available_columns=['age_annees', 'sexe'])

		self.assertEqual(normalized['correction_plan'].get('drop_columns'), [])

	def test_validation_rejects_non_empty_drop_columns(self):
		analysis_result = self._base_analysis_result()
		analysis_result['correction_plan'] = {
			'rename_columns': {},
			'drop_columns': ['age_annees'],
			'value_mappings': {},
			'fill_missing': {},
			'type_casts': {},
			'parse_dates': [],
			'trim_whitespace_columns': [],
			'default_values': {},
		}

		is_valid, _status, issues = _validate_preprocess_llm_output(
			analysis_result,
			stage_name='test',
			available_columns=['age_annees', 'sexe'],
		)

		self.assertFalse(is_valid)
		self.assertTrue(any('drop_columns non autorise' in issue for issue in issues))

	def test_validation_rejects_unsafe_fill_missing_strategy(self):
		analysis_result = self._base_analysis_result()
		analysis_result['correction_plan'] = {
			'rename_columns': {},
			'drop_columns': [],
			'value_mappings': {},
			'fill_missing': {'age_annees': {'strategy': 'magic_guess'}},
			'type_casts': {},
			'parse_dates': [],
			'trim_whitespace_columns': [],
			'default_values': {},
		}

		is_valid, _status, issues = _validate_preprocess_llm_output(
			analysis_result,
			stage_name='test',
			available_columns=['age_annees', 'sexe'],
		)

		self.assertFalse(is_valid)
		self.assertTrue(any('strategie non autorisee' in issue for issue in issues))

	def test_normalization_sets_notes_and_severity(self):
		analysis_result = self._base_analysis_result()
		analysis_result['correction_plan'] = {
			'drop_columns': ['age_annees'],
			'fill_missing': {'age_annees': {'strategy': 'median'}},
		}

		normalized = _normalize_correction_plan(analysis_result, available_columns=['age_annees'])

		self.assertIn('normalization_notes', normalized)
		self.assertIn('normalization_severity_score', normalized)
		self.assertGreaterEqual(int(normalized.get('normalization_severity_score', 0)), 1)

	def test_report_exposes_normalization_metadata(self):
		df = pd.DataFrame([{'age_annees': '45'}])
		technical_profile = {
			'rows': 1,
			'columns': 1,
			'missing_cells': 0,
			'missing_pct': 0.0,
			'duplicate_rows': 0,
			'duplicate_pct': 0.0,
		}
		llm_analysis = self._base_analysis_result()
		llm_analysis['normalization_notes'] = ['drop_columns_forced_empty_by_medical_policy']
		llm_analysis['normalization_severity_score'] = 2

		report = _build_preprocess_report(df, technical_profile, llm_analysis=llm_analysis, corrected_df=df, applied_actions=[])

		self.assertEqual(report.get('normalization_notes'), ['drop_columns_forced_empty_by_medical_policy'])
		self.assertEqual(report.get('normalization_severity_score'), 2)
		internal = report.get('llm_internal_status') or {}
		self.assertEqual(internal.get('normalization_severity_score'), 2)
		self.assertEqual(internal.get('normalization_notes'), ['drop_columns_forced_empty_by_medical_policy'])

	def test_applied_corrections_include_file_change_details(self):
		df = pd.DataFrame([
			{'Sexe': ' M ', 'age': '45'},
			{'Sexe': ' F ', 'age': None},
		])
		llm_analysis = {
			'correction_plan': {
				'rename_columns': {'Sexe': 'sexe'},
				'drop_columns': [],
				'value_mappings': {'sexe': {'M': 'homme', 'F': 'femme'}},
				'fill_missing': {'age': {'strategy': 'constant', 'value': '0'}},
				'type_casts': {},
				'parse_dates': [],
				'trim_whitespace_columns': ['sexe'],
				'default_values': {},
			}
		}

		_corrected, applied_actions = _apply_llm_correction_plan(df, llm_analysis)

		rename_action = next(item for item in applied_actions if item.get('action') == 'rename_columns')
		trim_action = next(item for item in applied_actions if item.get('action') == 'trim_whitespace')
		mapping_action = next(item for item in applied_actions if item.get('action') == 'value_mappings')
		fill_action = next(item for item in applied_actions if item.get('action') == 'fill_missing')

		self.assertEqual(rename_action.get('details', {}).get('columns'), [{'from': 'Sexe', 'to': 'sexe'}])
		self.assertEqual(trim_action.get('cells_changed'), 2)
		self.assertEqual(mapping_action.get('cells_changed'), 2)
		self.assertEqual(fill_action.get('cells_changed'), 1)

	def test_merge_correction_plans_adds_missing_deterministic_actions(self):
		llm_plan = {
			'rename_columns': {},
			'drop_columns': [],
			'value_mappings': {},
			'fill_missing': {'age_annees': {'strategy': 'mode'}},
			'type_casts': {},
			'parse_dates': [],
			'trim_whitespace_columns': [],
			'default_values': {},
		}
		deterministic_plan = _build_deterministic_correction_plan({
			'columns_profile': [
				{'name': 'age_annees', 'dtype': 'float64', 'missing_count': 1},
				{'name': 'date_debut_dialyse', 'dtype': 'object', 'missing_count': 0},
				{'name': 'sexe', 'dtype': 'int64', 'missing_count': 0},
			],
		})

		merged = _merge_correction_plans(llm_plan, deterministic_plan)

		self.assertEqual(merged.get('fill_missing', {}).get('age_annees', {}).get('strategy'), 'mode')
		self.assertIn('date_debut_dialyse', merged.get('parse_dates', []))
		self.assertIn('sexe', merged.get('type_casts', {}))
