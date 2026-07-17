"""GLens Coordinator — assembles results from multiple agent instances into a final response."""
from app.modules.glens.prompts import KPI_META, CHART_META, TABLE_META, VALID_KPIS, VALID_CHARTS, VALID_TABLES


def coordinate(results: list[dict]) -> dict:
    """
    Merge results from one or more agent instances.
    Single result: pass through unchanged.
    Multiple results: merge into a combined response.
    """
    if not results:
        return {"skill": "report", "ready": False, "answer": "No results returned."}

    if len(results) == 1:
        return results[0]

    # Multiple results — merge by type
    answers = []
    merged_spec = None

    for r in results:
        skill = r.get("skill", "report")

        # Collect text answers
        text = r.get("answer") or r.get("question")
        if text:
            answers.append(f"[{skill.capitalize()}] {text}")

        # Merge dashboard specs — combine kpis/charts/tables
        if r.get("ready") and r.get("spec"):
            spec = r["spec"]
            if merged_spec is None:
                merged_spec = {"title": spec.get("title", "Guard Overview"), "kpis": [], "charts": [], "tables": []}
            merged_spec["kpis"].extend(spec.get("kpis", []))
            merged_spec["charts"].extend(spec.get("charts", []))
            merged_spec["tables"].extend(spec.get("tables", []))

    if merged_spec and answers:
        # Both dashboard + text answers — return dashboard, prepend summary
        merged_spec["summary"] = " ".join(answers)
        return {"skill": "report", "ready": True, "spec": merged_spec}

    if merged_spec:
        return {"skill": "report", "ready": True, "spec": merged_spec}

    return {"skill": "analytics", "ready": False, "answer": "\n\n".join(answers)}
