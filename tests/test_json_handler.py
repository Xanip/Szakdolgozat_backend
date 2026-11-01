from tests.prediction_analization.json_handler import (
	default_result_paths,
	has_complete_prediction_window,
	load_json,
	merge_prediction_results,
	rebuild_best_model_document,
	write_json_atomic,
)


def test_atomic_json_round_trip_creates_parent_directory(tmp_path):
	path = tmp_path / "results" / "data.json"
	document = {"metadata": {"models": ["PROPHET"]}, "results": {}}

	write_json_atomic(path, document)

	assert load_json(path) == document


def test_merge_replaces_a_complete_window_without_touching_other_models():
	existing = {
		"metadata": {},
		"results": {
			"EUR/USD": {
				"PROPHET": {"2026-09": {"2026-09-01": {"actual_rate": 1.1}}},
				"ARIMA": {"2026-09": {"2026-09-01": {"actual_rate": 1.2}}},
			}
		},
	}
	updated = merge_prediction_results(
		existing,
		{"EUR/USD": {"PROPHET": {"2026-09": {"2026-09-02": {"actual_rate": 1.3}}}}},
	)

	assert updated["results"]["EUR/USD"]["PROPHET"]["2026-09"] == {
		"2026-09-02": {"actual_rate": 1.3}
	}
	assert "ARIMA" in updated["results"]["EUR/USD"]
	assert has_complete_prediction_window(
		updated, "EUR/USD", "PROPHET", "2026-09", ["2026-09-02"]
	)


def test_best_model_is_rebuilt_from_90_day_mapes_deterministically():
	summary = {
		"metadata": {"models": ["PROPHET", "ARIMA"]},
		"results": {
			"EUR/USD": {
				"PROPHET": {"90_days": {"summary_metrics": {"mape": 2.0}}},
				"ARIMA": {"90_days": {"summary_metrics": {"mape": 3.0}}},
			},
			"GBP/USD": {
				"PROPHET": {"90_days": {"summary_metrics": {"mape": 4.0}}},
				"ARIMA": {"90_days": {"summary_metrics": {"mape": 1.0}}},
			},
		},
	}

	best = rebuild_best_model_document(summary)

	assert best["results"]["EUR/USD"]["best_model"] == "PROPHET"
	assert best["results"]["GBP/USD"]["best_model"] == "ARIMA"
	assert best["global_best_model"] == "PROPHET"
	assert best["global_model_average_mapes"] == {"ARIMA": 2.0, "PROPHET": 3.0}


def test_default_result_paths_use_documented_filenames(tmp_path):
	paths = default_result_paths(tmp_path)

	assert paths["predictions"].name == "AllPredictionTestsData.json"
	assert paths["summary"].name == "SummaryTestsData.json"