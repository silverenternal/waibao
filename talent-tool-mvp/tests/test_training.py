"""T3001: LoRA Fine-tuning (LLaMA-Factory) 测试.

覆盖:
  * dataset_prep — 业务记录/合成样本 → alpaca/sharegpt/jsonl 落盘
  * train — dry_run 产物骨架 + LLaMA-Factory 配置渲染
  * evaluate — 金标准指标 (accuracy / MAE / ROUGE-L) + 阈值判定
  * registry — 版本自增 / active / promote
  * deploy — vLLM 命令构造 + dry_run 注册
  * pipeline — 3 个 LoRA 端到端 (dry_run)
  * custom_lora provider — adapter 加载 + 本地 fallback 推理正确
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from services.training import (  # noqa: E402
    DEFAULT_THRESHOLD,
    LoRAConfig,
    LoRAModel,
    TaskKind,
    TrainingExample,
    TrainingJob,
    build_examples,
    build_vllm_command,
    evaluate,
    evaluate_gold,
    get_registry,
    gold_from_examples,
    instruction_for,
    prepare_dataset,
    render_configs,
    reset_registry,
    rouge_l,
    run_pipeline,
    synth_records,
    train,
    train_all,
    write_dataset,
)
from services.training.types import JobStatus  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def tmp_out(tmp_path):
    return str(tmp_path)


# ---------------------------------------------------------------------------
# dataset_prep
# ---------------------------------------------------------------------------
class TestDatasetPrep:
    def test_synth_records_count_and_shape(self):
        for task in TaskKind:
            recs = synth_records(task, 10)
            assert len(recs) == 10
            assert all(isinstance(r, dict) and r for r in recs)

    def test_build_examples_resume(self):
        recs = synth_records(TaskKind.RESUME_SCORING, 5)
        exs = build_examples(TaskKind.RESUME_SCORING, recs)
        assert len(exs) == 5
        ex = exs[0]
        assert isinstance(ex, TrainingExample)
        # output 是合法 JSON 且含 score
        out = json.loads(ex.output)
        assert "score" in out

    def test_build_examples_skips_empty(self):
        exs = build_examples(TaskKind.BIAS_REVIEW, [{}, None, {"text": "限男性", "label": "biased"}])
        assert len(exs) == 1

    def test_prepare_dataset_pads_to_min(self, tmp_out):
        path, exs = prepare_dataset(TaskKind.HRBP_SUMMARY, records=[], out_dir=tmp_out, min_samples=16)
        assert os.path.exists(path)
        assert len(exs) >= 16
        rows = json.load(open(path, encoding="utf-8"))
        assert len(rows) == len(exs)
        assert "instruction" in rows[0]

    def test_write_dataset_formats(self, tmp_out):
        exs = build_examples(TaskKind.BIAS_REVIEW, synth_records(TaskKind.BIAS_REVIEW, 4))
        p_alpaca = write_dataset(exs, os.path.join(tmp_out, "a.json"), fmt="alpaca")
        p_share = write_dataset(exs, os.path.join(tmp_out, "s.json"), fmt="sharegpt")
        p_jsonl = write_dataset(exs, os.path.join(tmp_out, "j.jsonl"), fmt="jsonl")
        assert "instruction" in json.load(open(p_alpaca))[0]
        assert "conversations" in json.load(open(p_share))[0]
        lines = open(p_jsonl).read().strip().splitlines()
        assert len(lines) == 4 and "instruction" in json.loads(lines[0])

    def test_instruction_for_all_tasks(self):
        for task in TaskKind:
            assert instruction_for(task)


# ---------------------------------------------------------------------------
# train (dry_run)
# ---------------------------------------------------------------------------
class TestTrain:
    def test_dry_run_produces_artifacts(self, tmp_out):
        path, _ = prepare_dataset(TaskKind.RESUME_SCORING, out_dir=tmp_out)
        job = TrainingJob(job_id="t1", task=TaskKind.RESUME_SCORING, config=LoRAConfig())
        job.output_dir = os.path.join(tmp_out, "out")
        train(job, path, dry_run=True)
        assert job.status is JobStatus.COMPLETED
        for fn in ("adapter_config.json", "adapter_model.safetensors", "trainer_state.json", "instruction.txt"):
            assert os.path.exists(os.path.join(job.output_dir, fn)), fn

    def test_adapter_config_matches_lora(self, tmp_out):
        path, _ = prepare_dataset(TaskKind.BIAS_REVIEW, out_dir=tmp_out)
        cfg = LoRAConfig(lora_rank=16, lora_alpha=32)
        job = TrainingJob(job_id="t2", task=TaskKind.BIAS_REVIEW, config=cfg)
        job.output_dir = os.path.join(tmp_out, "out2")
        train(job, path, dry_run=True)
        ac = json.load(open(os.path.join(job.output_dir, "adapter_config.json")))
        assert ac["r"] == 16 and ac["lora_alpha"] == 32
        assert ac["peft_type"] == "LORA"

    def test_render_configs_writes_yaml_and_dataset_info(self, tmp_out):
        path, _ = prepare_dataset(TaskKind.HRBP_SUMMARY, out_dir=tmp_out)
        job = TrainingJob(job_id="t3", task=TaskKind.HRBP_SUMMARY, config=LoRAConfig())
        job.output_dir = os.path.join(tmp_out, "out3")
        cfgs = render_configs(job, path)
        assert os.path.exists(cfgs["train_yaml"])
        info = json.load(open(cfgs["dataset_info"]))
        assert "hrbp_summary" in info
        yaml_txt = open(cfgs["train_yaml"]).read()
        assert "finetuning_type: lora" in yaml_txt
        assert "quantization_bit: 4" in yaml_txt

    def test_llamafactory_args_qlora(self):
        cfg = LoRAConfig()
        args = cfg.to_llamafactory_args(dataset="resume_scoring", output_dir="/tmp/x")
        assert args["finetuning_type"] == "lora"
        assert args["quantization_bit"] == 4
        assert args["lora_rank"] == 8 and args["lora_alpha"] == 16
        assert args["learning_rate"] == 2e-4


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------
class TestEvaluate:
    def test_rouge_l_identical_is_one(self):
        assert rouge_l("你好世界", "你好世界") == pytest.approx(1.0)

    def test_rouge_l_disjoint_is_zero(self):
        assert rouge_l("abc", "xyz") == 0.0

    def test_resume_scoring_perfect_infer(self):
        recs = synth_records(TaskKind.RESUME_SCORING, 10)
        exs = build_examples(TaskKind.RESUME_SCORING, recs)
        gold = gold_from_examples(exs)

        def perfect(instruction, input_text):
            # 回放期望 output → MAE=0
            for g in gold:
                if g["input"] == input_text:
                    return g["expected"]
            return "{}"

        res = evaluate_gold(TaskKind.RESUME_SCORING, gold, perfect)
        assert res.accuracy == 1.0
        assert res.mae == 0.0
        assert res.passed

    def test_bias_review_label_accuracy(self):
        gold = [
            {"input": "限男性", "expected": json.dumps({"label": "biased"})},
            {"input": "欢迎投递", "expected": json.dumps({"label": "clean"})},
        ]

        def infer(instruction, text):
            label = "biased" if "限" in text else "clean"
            return json.dumps({"label": label})

        res = evaluate_gold(TaskKind.BIAS_REVIEW, gold, infer)
        assert res.accuracy == 1.0 and res.passed

    def test_evaluate_attaches_threshold_and_evaluator(self):
        exs = build_examples(TaskKind.HRBP_SUMMARY, synth_records(TaskKind.HRBP_SUMMARY, 6))
        gold = gold_from_examples(exs)
        res = evaluate(TaskKind.HRBP_SUMMARY, gold, lambda i, x: x[:60])
        assert res.details["threshold"] == DEFAULT_THRESHOLD[TaskKind.HRBP_SUMMARY]
        assert res.rouge_l is not None

    def test_empty_gold_not_passed(self):
        res = evaluate_gold(TaskKind.BIAS_REVIEW, [], lambda i, x: "")
        assert res.n_samples == 0 and not res.passed


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
class TestRegistry:
    def _model(self, task, passed=True):
        return LoRAModel(
            model_id=f"{task.value}-v1",
            task=task,
            base_model="Qwen/Qwen2.5-7B-Instruct",
            adapter_path="/tmp/x",
            eval_passed=passed,
        )

    def test_register_and_get(self):
        reg = get_registry()
        m = reg.register(self._model(TaskKind.RESUME_SCORING))
        assert reg.get(m.model_id) is m

    def test_version_auto_increment(self):
        reg = get_registry()
        reg.register(self._model(TaskKind.BIAS_REVIEW))
        m2 = reg.register(self._model(TaskKind.BIAS_REVIEW))
        assert m2.version == 2
        assert reg.latest(TaskKind.BIAS_REVIEW).version == 2

    def test_active_prefers_promoted(self):
        reg = get_registry()
        m1 = reg.register(self._model(TaskKind.HRBP_SUMMARY))
        m2 = reg.register(self._model(TaskKind.HRBP_SUMMARY))
        assert reg.active(TaskKind.HRBP_SUMMARY).model_id == m2.model_id
        reg.promote(m1.model_id)
        assert reg.active(TaskKind.HRBP_SUMMARY).model_id == m1.model_id

    def test_failed_eval_not_activated(self):
        reg = get_registry()
        reg.register(self._model(TaskKind.RESUME_SCORING, passed=False), activate=True)
        assert reg.active(TaskKind.RESUME_SCORING) is None

    def test_list_filter_by_task(self):
        reg = get_registry()
        reg.register(self._model(TaskKind.RESUME_SCORING))
        reg.register(self._model(TaskKind.BIAS_REVIEW))
        assert len(reg.list(task=TaskKind.RESUME_SCORING)) == 1
        assert len(reg.list()) == 2


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------
class TestDeploy:
    def test_build_vllm_command_multi_lora(self):
        cmd = build_vllm_command(
            "Qwen/Qwen2.5-7B-Instruct",
            {"resume_scoring-v1": "/out/r", "bias_review-v1": "/out/b"},
        )
        assert "--enable-lora" in cmd
        joined = " ".join(cmd)
        assert "resume_scoring-v1=/out/r" in joined
        assert "bias_review-v1=/out/b" in joined

    @pytest.mark.asyncio
    async def test_deploy_dry_run_registers(self, tmp_out):
        from services.training.deploy import deploy

        job = TrainingJob(job_id="d1", task=TaskKind.RESUME_SCORING, config=LoRAConfig())
        job.output_dir = tmp_out
        from services.training.types import EvalResult

        job.eval = EvalResult(task=TaskKind.RESUME_SCORING, n_samples=5, accuracy=0.9, passed=True)
        model = await deploy(job, dry_run=True)
        assert model.served_url and model.served_url.endswith("/v1")
        assert get_registry().get(model.model_id) is not None


# ---------------------------------------------------------------------------
# pipeline (端到端, 3 个 LoRA)
# ---------------------------------------------------------------------------
class TestPipeline:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("task", list(TaskKind))
    async def test_run_pipeline_completes(self, task):
        job = await run_pipeline(task, dry_run=True)
        assert job.status is JobStatus.COMPLETED
        assert job.eval is not None and job.eval.passed
        assert job.model is not None
        assert get_registry().active(task) is not None

    @pytest.mark.asyncio
    async def test_train_all_three_loras(self):
        jobs = await train_all(dry_run=True)
        assert set(jobs.keys()) == set(TaskKind)
        assert all(j.status is JobStatus.COMPLETED for j in jobs.values())
        assert len(get_registry().list()) == 3


# ---------------------------------------------------------------------------
# custom_lora provider (加载 + 推理正确)
# ---------------------------------------------------------------------------
class TestCustomLoRAProvider:
    def _provider(self):
        from providers.llm.custom_lora import CustomLoRAProvider

        return CustomLoRAProvider()

    @pytest.mark.asyncio
    async def test_resolve_adapter_from_registry(self):
        await run_pipeline(TaskKind.RESUME_SCORING, dry_run=True)
        p = self._provider()
        model_id, url = p.resolve_adapter("resume_scoring")
        assert model_id == "resume_scoring-v1"

    @pytest.mark.asyncio
    async def test_score_resume_fallback(self):
        p = self._provider()
        out = await p.score_resume({"title": "backend"}, {"skills": ["Go", "K8s"], "years": 6})
        assert "score" in out and isinstance(out["score"], int)
        assert 0 <= out["score"] <= 100

    @pytest.mark.asyncio
    async def test_review_bias_detects(self):
        p = self._provider()
        out = await p.review_bias("限男性, 985 优先")
        assert out["label"] == "biased"
        assert "性别" in out["categories"] and "院校" in out["categories"]

    @pytest.mark.asyncio
    async def test_review_bias_clean(self):
        p = self._provider()
        out = await p.review_bias("欢迎有经验的后端工程师投递")
        assert out["label"] == "clean"

    @pytest.mark.asyncio
    async def test_summarize_ticket(self):
        p = self._provider()
        s = await p.summarize_ticket("候选人询问 offer 薪资与入职时间, HR 已确认 2 周内入职。" * 3)
        assert isinstance(s, str) and len(s) <= 60

    @pytest.mark.asyncio
    async def test_supported_models_reflects_registry(self):
        await train_all(dry_run=True)
        p = self._provider()
        models = p.supported_models
        assert "resume_scoring-v1" in models
        assert p.pricing["resume_scoring-v1"] == (0.0, 0.0)


# ---------------------------------------------------------------------------
# provider registry wiring
# ---------------------------------------------------------------------------
def test_registry_exposes_custom_lora(monkeypatch):
    from providers import registry as prov_reg
    from providers.llm.custom_lora import CustomLoRAProvider

    prov_reg._llm = None
    monkeypatch.setenv("LLM_PROVIDER", "custom_lora")
    p = prov_reg.get_llm_provider()
    assert isinstance(p, CustomLoRAProvider)
    prov_reg._llm = None
