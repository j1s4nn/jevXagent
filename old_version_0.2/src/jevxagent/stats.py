"""Statistics storage and management"""
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from .models import ProxyMetrics


class StatsStorage:
    """Persist request statistics"""

    def __init__(self, path: Optional[Path] = None):
        self.path = path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def save_metric(self, metric: ProxyMetrics) -> None:
        """Append metric to JSONL file"""
        if not self.path:
            return

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": metric.trace_id,
            "jev_enabled": metric.jev_enabled,
            "jev_status": metric.jev_status,
            "jev_latency_ms": metric.jev_latency_ms,
            "jev_input_tokens": metric.jev_input_tokens,
            "jev_output_tokens": metric.jev_output_tokens,
            "backend_latency_ms": metric.backend_latency_ms,
            "agent_called": metric.agent_called,
            "agent_ttft_ms": metric.agent_ttft_ms,
            "agent_latency_ms": metric.agent_latency_ms,
            "agent_input_tokens": metric.agent_input_tokens,
            "agent_output_tokens": metric.agent_output_tokens,
            "total_latency_ms": metric.total_latency_ms,
            "bypass": metric.bypass,
        }

        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def load_all(self) -> list[dict]:
        """Load all metrics from file"""
        if not self.path or not self.path.exists():
            return []

        metrics = []
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    metrics.append(json.loads(line))
        return metrics

    def get_summary(self) -> dict:
        """Calculate summary statistics"""
        metrics = self.load_all()
        if not metrics:
            return {}

        total_requests = len(metrics)
        jev_enabled_count = sum(1 for m in metrics if m["jev_enabled"])
        bypass_count = sum(1 for m in metrics if m["bypass"])

        # Calculate averages for Jev-enabled requests
        jev_metrics = [m for m in metrics if m["jev_enabled"] and m["jev_status"] == "success"]

        if jev_metrics:
            avg_jev_latency = sum(m["jev_latency_ms"] for m in jev_metrics) / len(jev_metrics)
            avg_total_latency = sum(m["total_latency_ms"] for m in jev_metrics) / len(jev_metrics)
        else:
            avg_jev_latency = 0
            avg_total_latency = 0

        return {
            "total_requests": total_requests,
            "jev_enabled_count": jev_enabled_count,
            "bypass_count": bypass_count,
            "avg_jev_latency_ms": avg_jev_latency,
            "avg_total_latency_ms": avg_total_latency,
        }
