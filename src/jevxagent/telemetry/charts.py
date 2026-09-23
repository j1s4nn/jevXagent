"""Terminal charts + SVG export. Uses only stored data — no fabricated values."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

_BLOCK = "█"


def bar(label: str, value: float, max_value: float, width: int = 24, suffix: str = "") -> str:
    if max_value <= 0:
        filled = 0
    else:
        filled = max(0, min(width, round(value / max_value * width)))
    return f"{label:<20} {_BLOCK * filled}{' ' * (width - filled)} {suffix}"


def pct(value: float, total: float) -> str:
    return f"{value / total * 100:.1f}%" if total else "n/a"


def routing_chart(stats: dict) -> str:
    total = stats["total_decisions"]
    lines = ["Routing distribution"]
    if not total:
        return "\n".join(lines) + "\n  (no data)"
    jev = stats["jev_handled"]
    claude = stats["claude_handled"]
    return "\n".join(
        [
            lines[0],
            bar("JEV", jev, total, suffix=pct(jev, total)),
            bar("Claude", claude, total, suffix=pct(claude, total)),
        ]
    )


def categories_chart(breakdown: dict) -> str:
    lines = ["Operations by category"]
    if not breakdown:
        return "\n".join(lines) + "\n  (no data)"
    max_total = max(entry["total"] for entry in breakdown.values())
    for name, entry in sorted(breakdown.items(), key=lambda kv: -kv[1]["total"]):
        suffix = f"{entry['total']} (JEV {entry['jev']})"
        lines.append(bar(name, entry["total"], max_total, suffix=suffix))
    return "\n".join(lines)


def latency_chart(stats: dict) -> str:
    lines = ["Latency comparison"]
    jev = stats.get("jev_avg_ms_measured")
    claude = stats.get("claude_avg_ms_measured")
    if jev is None and claude is None:
        return "\n".join(lines) + "\n  (no data)"
    max_ms = max([v for v in (jev, claude) if v is not None] or [1])
    if jev is not None:
        lines.append(bar("JEV (measured)", jev, max_ms, suffix=f"{jev} ms"))
    if claude is not None:
        lines.append(bar("Claude (measured)", claude, max_ms, suffix=f"{claude} ms"))
    return "\n".join(lines)


def _svg_hbar(title: str, items: list[tuple[str, float, str]], width: int = 520) -> str:
    import html

    row_h, gap, label_w, bar_x, bar_w, pad = 26, 10, 170, 180, 260, 30
    height = pad * 2 + len(items) * (row_h + gap)
    max_value = max([v for _, v, _ in items] or [1])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="Consolas, monospace" font-size="13">',
        f'<text x="10" y="20" font-weight="bold">{html.escape(title)}</text>',
    ]
    for i, (label, value, suffix) in enumerate(items):
        y = pad + 10 + i * (row_h + gap)
        parts.append(f'<text x="10" y="{y}" fill="#333">{html.escape(label)}</text>')
        filled = 0 if max_value <= 0 else round(value / max_value * bar_w)
        parts.append(f'<rect x="{bar_x}" y="{y - 12}" width="{bar_w}" height="16" fill="#eee"/>')
        if filled:
            parts.append(
                f'<rect x="{bar_x}" y="{y - 12}" width="{filled}" height="16" fill="#5c7cfa"/>'
            )
        parts.append(f'<text x="{bar_x + bar_w + 8}" y="{y}" fill="#333">{html.escape(suffix)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def save_charts(
    outdir: Path,
    stats: dict,
    breakdown: dict,
    series: list[dict],
    requests: list[dict],
    decisions: list[dict],
    timestamp: str | None = None,
) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
    files: list[Path] = []

    total = stats["total_decisions"]
    (outdir / f"routing_{stamp}.svg").write_text(
        _svg_hbar(
            "Routing distribution",
            [
                ("JEV handled", stats["jev_handled"], f"{stats['jev_handled']}"),
                ("Claude handled", stats["claude_handled"], f"{stats['claude_handled']}"),
                ("Fallback", stats["jev_fallback"], f"{stats['jev_fallback']}"),
            ],
        ),
        encoding="utf-8",
    )
    files.append(outdir / f"routing_{stamp}.svg")

    (outdir / f"latency_{stamp}.svg").write_text(
        _svg_hbar(
            "Average decision latency (ms)",
            [
                ("JEV (measured)", stats.get("jev_avg_ms_measured") or 0, f"{stats.get('jev_avg_ms_measured')}"),
                ("Claude (measured)", stats.get("claude_avg_ms_measured") or 0, f"{stats.get('claude_avg_ms_measured')}"),
            ],
        ),
        encoding="utf-8",
    )
    files.append(outdir / f"latency_{stamp}.svg")

    (outdir / f"categories_{stamp}.svg").write_text(
        _svg_hbar(
            "Operations by category",
            [
                (name, entry["total"], f"{entry['total']} (JEV {entry['jev']})")
                for name, entry in sorted(breakdown.items(), key=lambda kv: -kv[1]["total"])
            ],
        ),
        encoding="utf-8",
    )
    files.append(outdir / f"categories_{stamp}.svg")

    (outdir / f"statistics_{stamp}.json").write_text(
        json.dumps(
            {
                "generated": stamp,
                "stats": stats,
                "breakdown": breakdown,
                "series": series,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    files.append(outdir / f"statistics_{stamp}.json")

    if requests:
        csv_path = outdir / f"requests_{stamp}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted(requests[0].keys()))
            writer.writeheader()
            for row in requests:
                writer.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row.items()})
        files.append(csv_path)

    if decisions:
        csv_path = outdir / f"decisions_{stamp}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted(decisions[0].keys()))
            writer.writeheader()
            for row in decisions:
                writer.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row.items()})
        files.append(csv_path)

    return files
