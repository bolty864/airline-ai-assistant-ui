"""Test setup: env vars, import path and a fake Azure OpenAI client (no network, no cost)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATABASE_URL", os.getenv("TEST_DATABASE_URL", "postgresql://postgres@localhost/aerocomply_test"))
os.environ["LOCAL_STORAGE_ROOT"] = tempfile.mkdtemp(prefix="aerocomply_blobs_")   # stands in for Azure Blob
os.environ["ENTERPRISE_LOCAL_PATH"] = str(BACKEND / "sample_data" / "enterprise")
os.environ["AGENT3_WORKER_ENABLED"] = "false"
os.environ["WATCHDOG_ENABLED"] = "false"          # tests call /api/watchdog/scan explicitly
os.environ["HEAL_RETRY_SECONDS"] = "300"
os.environ["LOG_JSON"] = "false"
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://fake.openai.azure.com/")
os.environ.setdefault("AZURE_OPENAI_KEY", "fake")


def fake_vec(text: str) -> list[float]:
    """Deterministic bag-of-words vector so similarity is meaningful in tests."""
    v = np.zeros(1536, dtype=np.float32)
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) > 2:
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 1536] += 1.0
    n = np.linalg.norm(v)
    return (v / n if n else v + 1e-3).tolist()


_TYPE_KEYWORDS = [("retain", "Data Retention"), ("encrypt", "Cyber Security"), ("access review", "Access Control"),
                  ("report", "Incident Management"), ("training", "Training Compliance"),
                  ("produce", "Record Keeping"), ("transmit", "Data Privacy")]


class FakeOpenAI:
    """Handles both Agent 2 (obligation_extraction) and Agent 3 (obligation_mapping) schemas."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.embedding_inputs = 0
        self.embeddings = SimpleNamespace(create=self._embed)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))

    async def _embed(self, model, input):
        self.embedding_inputs += len(input)
        data = [SimpleNamespace(index=i, embedding=fake_vec(t)) for i, t in enumerate(input)]
        return SimpleNamespace(data=data, usage=SimpleNamespace(total_tokens=sum(len(t.split()) for t in input)))

    async def _chat(self, model, messages, response_format, **kw):
        schema = response_format["json_schema"]["name"]
        self.calls.append((schema, model))
        prompt = messages[-1]["content"]
        if schema == "obligation_extraction":
            body = self._extract(prompt)
        elif schema == "gap_assessment":
            body = self._gap(prompt)
        else:
            body = self._map(prompt)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=len(prompt) // 4, completion_tokens=150),
        )

    @staticmethod
    def _extract(prompt: str) -> dict:
        number = re.search(r"Clause number: (\S+)", prompt).group(1)
        text = prompt.split('"""')[1].strip()
        text = re.sub(r"^\d+(\.\d+)*\s+", "", text)
        out = []
        for sentence in re.split(r"(?<=\.)\s+", text):
            if not re.search(r"\b(shall|must|required)\b", sentence, re.I):
                continue
            ob_type = next((t for k, t in _TYPE_KEYWORDS if k in sentence.lower()), "Other")
            citation = sentence.rstrip(".")
            if number == "4.1":
                citation = "Operators must send API data to the authority"  # paraphrase: must be repaired
            out.append({"clause_number": number, "requirement": "The operator shall " + sentence.split(" shall ")[-1]
                        if " shall " in sentence else sentence, "obligation_type": ob_type,
                        "owner_function": "whatever", "severity": "LOW", "citation": citation,
                        "confidence_score": 0.92, "target_system": "APIS" if "API" in sentence else ""})
        return {"obligations": out}

    @staticmethod
    def _gap(prompt: str) -> dict:
        """Rule-based stand-in for GPT-4o: compares '<N> years' in the requirement with the control description."""
        requirement = re.search(r"Requirement: (.+)", prompt).group(1)
        req_words = set(re.findall(r"[a-z]{4,}", requirement.lower()))
        controls = re.findall(r"\[(C\d+)\] (\S+) (.+?)\nDescription: (.*?)\n", prompt)
        match = next(((k, code, desc) for k, code, _n, desc in controls
                      if len(req_words & set(re.findall(r"[a-z]{4,}", desc.lower()))) >= 2), None)
        base = {"supporting_refs": [], "gap_types": [], "primary_ref": "", "parameters": []}
        if match is None:
            return {**base, "applicable_control_found": False, "coverage": 5, "confidence": 0.9,
                    "observation": "No supplied control performs this activity.", "recommendation": ""}
        key, code, desc = match
        need = re.search(r"(\d+) years?", requirement)
        have = re.search(r"[^.]*?(\d+) years?[^.]*", desc)
        quote = (have.group(0) if have else desc.split(".")[0]).strip()
        if "UNVERIFIED" in requirement:
            quote = "an invented sentence the control never contained"
        met = not (need and have and int(have.group(1)) < int(need.group(1)))
        param = {"parameter": "Retention period" if need else "Activity",
                 "required": f"{need.group(0)}" if need else "As described",
                 "actual": have.group(0).strip() if have else "Described", "met": met,
                 "source_ref": key, "actual_quote": quote}
        return {**base, "applicable_control_found": True, "parameters": [param], "primary_ref": key,
                "coverage": 92 if met else 55, "gap_types": [] if met else ["Partial Coverage"], "confidence": 0.9,
                "observation": f"{code}: {'meets' if met else 'does not meet'} the requirement.",
                "recommendation": "" if met else f"Update {code} to meet the required period."}

    @staticmethod
    def _map(prompt: str) -> dict:
        ob_words = set(re.findall(r"[a-z]{4,}", prompt.split("CANDIDATES")[0].lower()))
        mappings = []
        for key, body in re.findall(r"\[([PCS]\d+)\] (.+?)(?=\n\[[PCS]\d+\]|\Z)", prompt, re.S):
            overlap = len(ob_words & set(re.findall(r"[a-z]{4,}", body.lower())))
            if overlap >= 3:
                content = body.split("\n", 1)[-1]
                sentence = next((s.strip() for s in re.split(r"(?<=\.)\s(?=\d|[A-Z])", content) if "retained" in s), "")
                mappings.append({"candidate_id": key, "link_type": "DIRECT" if key[0] == "P" else "SUPPORTING",
                                 "relevance": min(0.5 + overlap / 10, 0.95), "current_provision": sentence,
                                 "rationale": f"{overlap} overlapping terms"})
        mappings.append({"candidate_id": "P99", "link_type": "DIRECT", "relevance": 0.99,
                         "current_provision": "", "rationale": "hallucinated id, must be dropped"})
        return {"mappings": mappings, "unmapped_reason": ""}
