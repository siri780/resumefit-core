from app import evaluate


def test_evaluation_runs_and_core_checks_hold(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "REPORT", tmp_path / "REPORT.md")
    report = evaluate.run()
    assert set(report) == set(evaluate.RULES)
    # these must never regress
    for check in ("posting_guard", "email_reader", "applied_match"):
        assert report[check]["pass"], (check, report[check]["misses"])
    assert report["edit_guard"]["all"]["wrongly blocked"] == 0
    assert report["letter_guard"]["all"]["wrongly removed"] == 0
    path = evaluate.write_report(report)
    text = path.read_text(encoding="utf-8")
    assert "| Check |" in text and "Known limitations" in text


def test_every_case_is_labelled_and_split():
    import json
    cases = json.loads(evaluate.CASES.read_text(encoding="utf-8"))
    for check, items in cases.items():
        ids = [c["id"] for c in items]
        assert len(ids) == len(set(ids)), check
        assert all(c["split"] in ("dev", "holdout") and "expect" in c for c in items), check
        assert any(c["split"] == "holdout" for c in items), check


def test_magnitudes_count_as_different_numbers():
    from app.guard import check_length, numbers_in
    assert numbers_in("3 million patients across 14M users") == {"3m", "14m"}
    assert numbers_in("raised 3 metrics") == {"3"}
    assert check_length("Built dashboards.", "Built dashboards for leadership reviews.") == []
