"""Historical range check: z-score of a key metric vs prior results."""

from __future__ import annotations

import math

from reck.events import AgentResult, CheckResult, Verdict


def _extract(data: dict, dot_path: str) -> float | None:
    """Walk a dot-separated path into a nested dict, return float or None."""
    parts = dot_path.split(".")
    current: object = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    try:
        return float(current)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def historical_check(result: AgentResult, criteria: dict) -> CheckResult:
    """Compare a metric from structured_result to the distribution in prior_results."""
    metric_path: str = criteria.get("metric_path", "")
    sigma_threshold: float = criteria.get("sigma_threshold", 3.0)

    if not metric_path:
        return CheckResult(
            check_name="historical_range",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason="No metric_path in manifest criteria",
        )

    current_value = _extract(result.structured_result, metric_path)
    if current_value is None:
        return CheckResult(
            check_name="historical_range",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason=f"Metric {metric_path!r} not found in structured_result",
        )

    # Extract historical values
    prior_values = [v for pr in result.prior_results if (v := _extract(pr, metric_path)) is not None]

    if len(prior_values) < 2:
        return CheckResult(
            check_name="historical_range",
            verdict=Verdict.PASS,
            reason="Insufficient history for comparison",
            detail={"prior_count": len(prior_values)},
        )

    # Z-score (same approach as watch/detector.py)
    mean = sum(prior_values) / len(prior_values)
    variance = sum((v - mean) ** 2 for v in prior_values) / len(prior_values)
    stddev = math.sqrt(variance)

    if stddev == 0:
        return CheckResult(
            check_name="historical_range",
            verdict=Verdict.PASS,
            reason="Zero variance in history",
            detail={"mean": mean, "stddev": 0.0},
        )

    z_score = abs(current_value - mean) / stddev

    if z_score > sigma_threshold:
        return CheckResult(
            check_name="historical_range",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason=f"Metric {metric_path!r} z-score {z_score:.2f} exceeds threshold {sigma_threshold}",
            detail={
                "current": current_value,
                "mean": round(mean, 4),
                "stddev": round(stddev, 4),
                "z_score": round(z_score, 4),
                "threshold": sigma_threshold,
            },
        )

    return CheckResult(
        check_name="historical_range",
        verdict=Verdict.PASS,
        detail={
            "current": current_value,
            "mean": round(mean, 4),
            "stddev": round(stddev, 4),
            "z_score": round(z_score, 4),
            "threshold": sigma_threshold,
        },
    )
