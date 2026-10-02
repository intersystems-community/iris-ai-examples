"""Local Hugging Face LightDec adapter.

LightDec is a non-autoregressive, typed decision model published at
Falconsai/LightDec. It supports Choice, Score, and Noul questions, returns
calibrated probabilities/confidence, and emits no generated text.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPO = "Falconsai/LightDec"
DEFAULT_VARIANT = "int8"


class HFDecisionError(RuntimeError):
    """Raised when the local decision model cannot be loaded or queried."""


def _load_lightdec(repo: str, revision: str | None, variant: str):
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise HFDecisionError("Install huggingface_hub to use the LightDec backend") from exc

    try:
        root = Path(repo) if Path(repo).exists() else Path(snapshot_download(repo, revision=revision))
        path = root / "compact-int8" if variant == "int8" else root
        config_path = path / "falcondec_config.json"
        module_path = path / "falcondec_modeling.py"
        if not config_path.exists() or not module_path.exists():
            raise HFDecisionError(f"LightDec files missing in {path}")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        expected = config.get("weights", "model.safetensors")
        if not (path / expected).exists():
            candidates = sorted(path.glob("*.safetensors"))
            if not candidates:
                raise HFDecisionError(f"LightDec weights missing in {path}")
            local = Path("/tmp/lightdec_local") / variant
            shutil.copytree(path, local, dirs_exist_ok=True)
            shutil.copy(candidates[0], local / expected)
            path = local
            module_path = path / "falcondec_modeling.py"

        spec = importlib.util.spec_from_file_location("falcondec_modeling", module_path)
        if spec is None or spec.loader is None:
            raise HFDecisionError("Unable to import LightDec modeling module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from transformers import AutoTokenizer, PreTrainedTokenizerFast

        tokenizer_path = path / "tokenizer"
        try:
            tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path))
            model, _ = module.load_falcondec(str(path), device="cpu")
        except ValueError as exc:
            # The public checkpoint currently labels its tokenizer class as
            # TokenizersBackend, which newer Transformers versions do not
            # register. Construct the fast tokenizer from tokenizer.json and
            # inject it only for this loader call; no cache files are changed.
            if "TokenizersBackend" not in str(exc):
                raise
            tokenizer = PreTrainedTokenizerFast(
                tokenizer_file=str(tokenizer_path / "tokenizer.json"),
                cls_token="[CLS]",
                sep_token="[SEP]",
                mask_token="[MASK]",
                pad_token="[PAD]",
                unk_token="[UNK]",
            )
            original_loader = AutoTokenizer.from_pretrained
            AutoTokenizer.from_pretrained = lambda *args, **kwargs: tokenizer
            try:
                model, _ = module.load_falcondec(str(path), device="cpu")
            finally:
                AutoTokenizer.from_pretrained = original_loader
        return module, model, tokenizer
    except HFDecisionError:
        raise
    except Exception as exc:
        raise HFDecisionError(f"LightDec load failed: {exc}") from exc


@dataclass
class LightDecClient:
    repo: str = DEFAULT_REPO
    revision: str | None = None
    variant: str = DEFAULT_VARIANT
    _runtime: tuple[Any, Any, Any] | None = None

    def _ensure_loaded(self):
        if self._runtime is None:
            self._runtime = _load_lightdec(self.repo, self.revision, self.variant)
        return self._runtime

    def decide(self, *, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        module, model, tokenizer = self._ensure_loaded()
        try:
            return module.decide(model, tokenizer, state, questions)
        except Exception as exc:
            raise HFDecisionError(f"LightDec inference failed: {exc}") from exc


def _choice(answer: dict[str, Any]) -> tuple[str, float, dict[str, float], bool]:
    choice = answer.get("choice")
    probs = answer.get("probs") or answer.get("probabilities") or {}
    if not isinstance(choice, str) or not isinstance(probs, dict):
        raise HFDecisionError("LightDec action answer is missing choice/probs")
    confidence = float(answer.get("confidence", probs.get(choice, 0.0)))
    return choice, confidence, {str(k): float(v) for k, v in probs.items()}, bool(answer.get("defer", False))


def _score(answer: dict[str, Any]) -> tuple[float, dict[str, float]]:
    expected = answer.get("expected_level", answer.get("score"))
    probs = answer.get("probs") or answer.get("probabilities") or {}
    if expected is None or not isinstance(probs, dict):
        raise HFDecisionError("LightDec urgency answer is missing expected_level/probs")
    return float(expected), {str(k): float(v) for k, v in probs.items()}


def _noul(answer: dict[str, Any]) -> float:
    value = answer.get("p_true", answer.get("noul"))
    if value is None:
        raise HFDecisionError("LightDec consent answer is missing p_true")
    return float(value)


def render_lightdec_decision(patient_id: str, result: dict[str, Any], consent: str) -> str:
    answers = result.get("answers", {})
    action, confidence, probabilities, deferred = _choice(answers["action"])
    urgency, urgency_probs = _score(answers["urgency"])
    consent_probability = _noul(answers["has_consent"])
    action = action.upper()

    # Consent is an explicit application fact, not something the model is
    # allowed to infer into existence. LightDec's Noul remains visible for
    # audit/calibration, while the caller's literal consent value is the hard
    # boundary before a side effect.
    if consent.strip().lower() != "yes":
        decision = "ASK_HUMAN"
        reason = "patient consent is not explicitly confirmed"
    elif deferred:
        decision = "ASK_HUMAN"
        reason = "LightDec deferred the action"
    else:
        decision = action if action in {"EXECUTE", "SIMULATE", "ASK_HUMAN", "REJECT"} else "ASK_HUMAN"
        reason = f"LightDec selected {decision}"

    return "\n".join([
        f"Action Gate for {patient_id} (Hugging Face LightDec)",
        f"Decision: {decision}",
        f"LightDec action confidence: {confidence:.3f}",
        f"LightDec urgency expected level: {urgency:.3f}",
        f"LightDec consent probability: {consent_probability:.3f}",
        f"Action probabilities: {json.dumps(probabilities, sort_keys=True)}",
        f"Urgency probabilities: {json.dumps(urgency_probs, sort_keys=True)}",
        f"Reason: {reason}",
    ])


def decide_with_lightdec(
    patient_id: str,
    risk_assessment: str,
    proposed_action: str = "trigger_follow_up",
    consent: str = "no",
    *,
    client: LightDecClient | None = None,
    repo: str = DEFAULT_REPO,
    revision: str | None = None,
    variant: str = DEFAULT_VARIANT,
) -> str:
    if not patient_id:
        return "ERROR: patientId is required"
    if proposed_action != "trigger_follow_up":
        return f"Decision: REJECT\nReason: unsupported action '{proposed_action}'"
    client = client or LightDecClient(repo=repo, revision=revision, variant=variant)
    questions = {
        "action": {
            "type": "choice",
            "instructions": "What should happen next for this proposed care coordination action?",
            "criteria": {
                "EXECUTE": "Proceed with the proposed trigger_follow_up action when safe and appropriate.",
                "SIMULATE": "Prepare or simulate the action without causing a side effect.",
                "ASK_HUMAN": "Escalate to a human because the case is uncertain, sensitive, or needs review.",
                "REJECT": "Do not perform the proposed action.",
            },
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this care coordination action?",
            "criteria": ["routine; can wait for normal workflow timing", "high; should be handled promptly", "urgent; requires immediate attention"],
        },
        "has_consent": {
            "type": "noul",
            "instructions": "Does the patient_consent field explicitly confirm that the patient consented to this proposed action?",
            "labels": {
                "true": "The patient_consent field says consent is confirmed.",
                "false": "The patient_consent field does not say consent is confirmed.",
            },
        },
    }
    result = client.decide(
        state={
            "patient_id": patient_id,
            "risk_assessment": risk_assessment,
            "proposed_action": proposed_action,
            "patient_consent": consent,
        },
        questions=questions,
    )
    return render_lightdec_decision(patient_id, result, consent)
