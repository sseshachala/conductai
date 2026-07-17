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

        # Merge dashboard picks — model returns kpis/charts/tables as string lists
        if r.get("ready") and (r.get("kpis") or r.get("charts") or r.get("tables")):
            if merged_spec is None:
                merged_spec = {"title": r.get("title", "Guard Overview"), "kpis": [], "charts": [], "tables": [], "month": r.get("month", "")}
            merged_spec["kpis"].extend(r.get("kpis", []))
            merged_spec["charts"].extend(r.get("charts", []))
            merged_spec["tables"].extend(r.get("tables", []))

    if merged_spec:
        # Deduplicate kpis by id field to prevent double-counting across subtask results
        if merged_spec["kpis"] and isinstance(merged_spec["kpis"][0], dict):
            merged_spec["kpis"] = list({item["id"]: item for item in merged_spec["kpis"] if "id" in item}.values()) or merged_spec["kpis"]

        if answers:
            merged_spec["summary"] = " ".join(answers)
        return {"skill": "report", "ready": True, **merged_spec}

    return {"skill": "analytics", "ready": False, "answer": "\n\n".join(answers)}
