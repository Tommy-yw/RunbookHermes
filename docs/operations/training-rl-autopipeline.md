# RunbookAIOps training / RL / AutoPipeline

This layer turns RunbookAIOps incident handling into reusable model-improvement data. It follows the Hermes Agent idea of `dataset.jsonl -> batch_runner -> trajectories.jsonl -> trajectory_compressor -> compressed.jsonl`, while keeping external fine-tuning disabled by default.

## What is exported

`runbook_hermes.training` builds one run directory under `.runbook_hermes_store/training/runs/<run_id>/`:

- `datasets/dataset.jsonl`: prompt rows that can be passed to Hermes `batch_runner.py` for fresh model rollouts.
- `datasets/trajectories.jsonl`: Hermes-compatible `from/value` trajectories with tool calls, tool results, reward metadata and tool stats.
- `datasets/compressed.jsonl`: locally compressed trajectories, or the output of Hermes `trajectory_compressor.py` when explicitly requested.
- `datasets/sft.jsonl`: chat-style supervised fine-tuning records.
- `datasets/preference.jsonl`: chosen/rejected pairs for preference or DPO-style training.
- `datasets/rewards.jsonl`: scalar RCA/action/evidence/safety/learning reward labels.
- `alicloud/pai_dlc_job_spec.json`: Alibaba Cloud PAI DLC dry-run training-job handoff template.
- `alicloud/dashscope_finetune_template.json`: Alibaba Model Studio/DashScope dry-run fine-tuning handoff template.
- `manifest.json`: run metadata and file paths.

## API

```text
GET  /training/status
GET  /training/runs
GET  /training/datasets
POST /training/build-dataset
POST /training/compress
POST /training/export
POST /training/pipeline/run
```

Example:

```bash
curl -X POST http://127.0.0.1:8000/training/pipeline/run \
  -H 'content-type: application/json' \
  -d '{"include_incidents": true, "include_benchmark_cases": true, "dry_run": true}'
```

## Hermes RL handoff

The generated files are intentionally compatible with Hermes Agent training utilities:

```bash
python batch_runner.py --dataset_file=.runbook_hermes_store/training/runs/<run_id>/datasets/dataset.jsonl --run_name=runbook_aiops_<run_id>
python trajectory_compressor.py --input=.runbook_hermes_store/training/runs/<run_id>/datasets/trajectories.jsonl --output=.runbook_hermes_store/training/runs/<run_id>/datasets/compressed.jsonl
python rl_cli.py "Train a RunbookAIOps model using .runbook_hermes_store/training/runs/<run_id>/datasets/compressed.jsonl"
```

`runbook_training_compress` uses a deterministic local compressor by default. Set `use_hermes_compressor=true` only after your provider keys are configured for Hermes `trajectory_compressor.py`.

## Alibaba Cloud handoff

The AutoPipeline produces dry-run handoff files for Alibaba Cloud PAI/DashScope. It does not submit jobs unless all of the following are true:

```bash
RUNBOOK_ALICLOUD_AUTOPIPELINE_ENABLED=true
RUNBOOK_ALICLOUD_AUTOPIPELINE_EXECUTE=true
```

Recommended flow:

1. Run `/eval/run` against the current model and store the result.
2. Run `/training/pipeline/run` with `dry_run=true`.
3. Review `manifest.json`, `compressed.jsonl`, `sft.jsonl` and the generated `alicloud/*.json` files.
4. Upload the run directory to OSS.
5. Submit the reviewed job spec through your PAI/DashScope account workflow.
6. Run `/eval/run` again against the candidate model before any production route change.

## Safety notes

- The pipeline never includes API keys in generated files.
- External launch is disabled by default.
- Destructive incident actions remain protected by the existing approval/checkpoint policy.
- Reward labels are deterministic and transparent: RCA, action, evidence, safety and learning are reported separately.
