from __future__ import annotations

from pathlib import Path

from akf_workshop.akf_search.pipeline import SearchPipeline
from akf_workshop.akf_skills import KumoPredictionSkill, RetrievalSkill, SkillRegistry

from .trace import Trace


class AgentHarness:
    def __init__(self, sample_box_root: Path):
        self.pipeline = SearchPipeline(sample_box_root)
        self.registry = SkillRegistry()
        self.registry.register("retrieval", RetrievalSkill(self.pipeline))
        self.registry.register("kumo_prediction", KumoPredictionSkill(sample_box_root, adapter=self.pipeline.adapter))

    def ingest(self) -> dict:
        return self.pipeline.ingest()

    def ask(self, query: str, user: str, groups: set[str]) -> dict:
        trace = Trace()
        trace.add("plan", query=query, skills=self.registry.names())
        if _needs_prediction(query):
            prediction = self.registry.call("kumo_prediction", query=query, user=user, groups=groups)
            trace.add("skill", skill="kumo_prediction", status=prediction["status"], trace_ms=prediction["trace_ms"])
            retrieval = self.registry.call("retrieval", query=query, user=user, groups=groups)
            trace.add("skill", skill="retrieval", status=retrieval["status"], trace_ms=retrieval["trace_ms"])
            answer = _combine_prediction_and_retrieval(prediction, retrieval)
            return {
                "answer": answer,
                "citations": retrieval.get("evidence", []),
                "skill_evidence": prediction.get("evidence", []),
                "status": _combined_status(prediction, retrieval),
                "trace": trace.as_dict(),
            }

        retrieval = self.registry.call("retrieval", query=query, user=user, groups=groups)
        trace.add("skill", skill="retrieval", status=retrieval["status"], trace_ms=retrieval["trace_ms"])
        return {
            "answer": retrieval["answer"],
            "citations": retrieval.get("evidence", []),
            "skill_evidence": [],
            "status": retrieval["status"],
            "trace": trace.as_dict(),
        }


def _needs_prediction(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in ["predict", "prediction", "risk", "forecast", "likely"])


def _combine_prediction_and_retrieval(prediction: dict, retrieval: dict) -> str:
    if prediction["status"] != "ok":
        return prediction["answer"]
    if retrieval["status"] != "ok":
        return f"{prediction['answer']} I could not find permitted Box policy context to cite."
    return f"{prediction['answer']} Policy context: {retrieval['answer']}"


def _combined_status(prediction: dict, retrieval: dict) -> str:
    if prediction["status"] == "denied":
        return "denied"
    if prediction["status"] == "ok" and retrieval["status"] == "ok":
        return "ok"
    return "partial"
