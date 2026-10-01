"""Metadata-only token categories. Never infer a provider from a tool name."""
import re

FIELDS = ("uncached_input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", value):
        return None
    if value.lower().startswith(("sk-", "sk_", "cond_", "ghp_", "github_pat_", "xox", "akia")):
        return None
    return value


def categories(usage, family):
    if family == "codex":
        cached = usage.get("cached_input_tokens")
        if type(cached) is not int or type(usage.get("input_tokens")) is not int:
            return None
        values = [usage["input_tokens"] - cached, cached, 0, usage.get("output_tokens")]
    else:
        values = [usage.get("input_tokens"), usage.get("cache_read_input_tokens", 0),
                  usage.get("cache_creation_input_tokens", 0), usage.get("output_tokens")]
    if any(type(v) is not int or not 0 <= v <= 2**31 - 1 for v in values):
        return None
    result = dict(zip(FIELDS, values))
    reasoning = usage.get("reasoning_output_tokens")
    if type(reasoning) is int and 0 <= reasoning <= result["output_tokens"]:
        result["reasoning_output_tokens"] = reasoning
    return result


def add_delta(parts, current, previous, model=None, provider=None):
    if current is None or previous is None:
        return False
    delta = {k: current[k] - previous[k] for k in FIELDS}
    if any(v < 0 for v in delta.values()):
        return False
    if not any(delta.values()):
        return True
    previous_reasoning = previous.get("reasoning_output_tokens", 0 if not any(previous.values()) else None)
    reasoning = current.get("reasoning_output_tokens")
    if reasoning is not None and previous_reasoning is not None and 0 <= reasoning - previous_reasoning <= delta["output_tokens"]:
        delta["reasoning_output_tokens"] = reasoning - previous_reasoning
    model, provider = identifier(model), identifier(provider)
    for part in parts:
        if part["model"] == model and part["provider"] == provider:
            for key in FIELDS:
                part[key] += delta[key]
            if "reasoning_output_tokens" in part and "reasoning_output_tokens" in delta:
                part["reasoning_output_tokens"] += delta["reasoning_output_tokens"]
            else:
                part.pop("reasoning_output_tokens", None)
            return True
    if len(parts) >= 100:
        return False
    parts.append({"model": model, "provider": provider, **delta})
    return True
