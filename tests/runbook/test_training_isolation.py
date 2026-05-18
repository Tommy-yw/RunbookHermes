from __future__ import annotations


def test_training_pipeline_never_launches_external_jobs(isolated_runbook_env, monkeypatch):
    monkeypatch.setenv("RUNBOOK_ALICLOUD_AUTOPIPELINE_ENABLED", "true")
    monkeypatch.setenv("RUNBOOK_ALICLOUD_AUTOPIPELINE_EXECUTE", "true")
    from runbook_hermes.training import external_launch_training, run_auto_pipeline, training_status

    status = training_status()
    assert status["pipeline_isolation"].startswith("pipeline_run_is_always")
    result = run_auto_pipeline(include_incidents=False, include_benchmark_cases=True, dry_run=False)
    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert result["requested_dry_run"] is False
    assert result["external_launch_isolated"] is True
    launch_step = [s for s in result["steps"] if s["name"] == "external_launch_isolated"][0]
    assert launch_step["result"]["executed"] is False

    rejected = external_launch_training(run_id=result["run_id"], confirmation_token="wrong")
    assert rejected["status"] == "rejected"
    assert rejected["executed"] is False
