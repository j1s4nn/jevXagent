"""Generate the conceptual figures used in README.md.

These figures are schematic diagrams that explain *what jevXagent is* and *how
it routes decisions*. They contain no measured numbers and make no performance
claims — the real numbers live in the telemetry store and the statistics CLI.

Run:

    python scripts/generate_readme_figures.py

Requires matplotlib (installed with the `dev` extra: pip install -e ".[dev]").
Output: docs/images/*.png
"""

from __future__ import annotations

from pathlib import Path

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon
except ImportError:
    raise SystemExit('matplotlib is required: pip install -e ".[dev]"')

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "images"

# ---- palette -------------------------------------------------------------
BG = "#FFFFFF"
INK = "#1F2933"
MUTED = "#5B6B7B"
FAINT = "#9AA7B4"

AGENT_FC, AGENT_EC = "#EEF2FF", "#4F46E5"
PROXY_FC, PROXY_EC = "#E0F2FE", "#0284C7"
CLAUDE_FC, CLAUDE_EC = "#F3E8FF", "#7C3AED"
JEV_FC, JEV_EC = "#FFEDD5", "#EA580C"
OK_FC, OK_EC = "#DCFCE7", "#16A34A"
WARN_FC, WARN_EC = "#FEF3C7", "#D97706"
GREY_FC, GREY_EC = "#F1F5F9", "#94A3B8"
ARROW = "#475569"


def canvas(width: float, height: float):
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.axis("off")
    return fig, ax


def title(ax, x, y, text, size=17):
    ax.text(x, y, text, ha="center", va="center", fontsize=size,
            fontweight="bold", color=INK)


def box(ax, x, y, w, h, text, fc, ec, fs=10.5, tc=INK, weight="bold",
        radius=0.55, lw=1.6, align="center"):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.15,rounding_size={radius}",
        linewidth=lw, edgecolor=ec, facecolor=fc, mutation_aspect=1.0,
    )
    ax.add_patch(patch)
    ha = "center" if align == "center" else "left"
    tx = x + w / 2 if align == "center" else x + 0.8
    ax.text(tx, y + h / 2, text, ha=ha, va="center", fontsize=fs,
            color=tc, fontweight=weight, linespacing=1.45)


def diamond(ax, cx, cy, w, h, text, fc, ec, fs=9.5):
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor=ec, linewidth=1.6))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            color=INK, fontweight="bold", linespacing=1.35)


def arrow(ax, p1, p2, color=ARROW, lw=1.8, ls="-", rad=0.0, style="-|>",
          ms=15):
    ax.add_patch(
        FancyArrowPatch(
            p1, p2, arrowstyle=style, mutation_scale=ms, lw=lw, color=color,
            linestyle=ls, shrinkA=1, shrinkB=1,
            connectionstyle=f"arc3,rad={rad}",
        )
    )


def label(ax, x, y, text, fs=8.8, color=MUTED, ha="center", va="center",
          weight="normal"):
    ax.text(x, y, text, ha=ha, va=va, fontsize=fs, color=color,
            fontweight=weight)


# ---- figure 1: system architecture --------------------------------------
def figure_architecture():
    fig, ax = canvas(13, 7.6)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 60)

    title(ax, 50, 56.5, "jevXagent — where it sits in the stack")

    # agent
    box(ax, 2.5, 33, 17, 12,
        "LLM Agent\n(Claude Code)\n\nspeaks the\nAnthropic API", AGENT_FC, AGENT_EC,
        fs=10)

    # proxy container
    ax.add_patch(FancyBboxPatch(
        (29, 6), 38, 46, boxstyle="round,pad=0.3,rounding_size=1.0",
        linewidth=2.2, edgecolor=PROXY_EC, facecolor="#F8FBFF", mutation_aspect=1.0))
    label(ax, 48, 49, "jevXagent  (local proxy · 127.0.0.1:8787)", fs=11,
          color=PROXY_EC, weight="bold")

    box(ax, 32, 38.5, 32, 7.5,
        "/v1/messages\nverbatim relay (JSON + SSE)", "#DBEAFE", PROXY_EC, fs=9.3)
    box(ax, 32, 28.5, 32, 7.5,
        "/v1/decision\nrouter: classifier → policy → executor", "#DBEAFE", PROXY_EC, fs=9)
    box(ax, 32, 18.5, 32, 7.5,
        "observes tool_use\n→ detects decision events", "#DBEAFE", PROXY_EC, fs=9.3)
    box(ax, 32, 9, 32, 7.5,
        "telemetry (SQLite) → statistics CLI", "#DBEAFE", PROXY_EC, fs=9.3)

    # providers
    box(ax, 74, 32, 24, 13,
        "Claude API\nprimary model\n\nglobal context +\ndeep reasoning", CLAUDE_FC, CLAUDE_EC,
        fs=10)
    box(ax, 74, 11, 24, 13,
        "JEV\ndecision coprocessor\n\nfast typed decisions\n(choice / noul / score)",
        JEV_FC, JEV_EC, fs=9.3)

    arrow(ax, (19.5, 41), (32, 42.2))
    label(ax, 25.5, 44.3, "/v1/messages", fs=8.4)

    arrow(ax, (64, 42.2), (74, 40))
    label(ax, 69, 44.6, "relay", fs=8.4)

    arrow(ax, (64, 32.2), (74, 20))
    label(ax, 70.5, 30.5, "route", fs=8.4)

    arrow(ax, (86, 24), (86, 32), ls="--", color=WARN_EC)
    label(ax, 90.5, 28, "fallback\n(uncertain /\ntimeout)", fs=8.2, color=WARN_EC)

    fig.savefig(OUT_DIR / "architecture.png", bbox_inches="tight",
                facecolor=BG, pad_inches=0.25)
    plt.close(fig)


# ---- figure 2: request + decision flow ----------------------------------
def figure_request_flow():
    fig, ax = canvas(13, 7.8)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 60)

    title(ax, 50, 56.5, "One Claude Code turn, through jevXagent")

    # transport lane
    label(ax, 2, 50.5, "TRANSPORT  (always on)", fs=9.5, color=PROXY_EC,
          ha="left", weight="bold")
    ax.plot([2, 98], [48.7, 48.7], color="#E2E8F0", lw=1.2)

    nodes = [
        (2, "1", "Claude Code", "POST /v1/messages"),
        (21.5, "2", "Proxy relay", "forwards verbatim"),
        (41, "3", "Claude API", "streams the answer"),
        (60.5, "4", "Proxy relay", "streams back unchanged"),
        (80, "5", "Claude Code", "receives the answer"),
    ]
    for x, num, head, sub in nodes:
        box(ax, x, 36, 17, 9, f"{num}.  {head}\n{sub}", "#EFF6FF", PROXY_EC, fs=9.0)
    for x in (19, 38.5, 58, 77.5):
        arrow(ax, (x, 40.5), (x + 2.2, 40.5), ms=13)

    # decision lane
    label(ax, 2, 28, "DECISION  (background, non-blocking)", fs=9.5,
          color=JEV_EC, ha="left", weight="bold")
    ax.plot([2, 98], [26.2, 26.2], color="#E2E8F0", lw=1.2)

    dnodes = [
        (2, "A", "Observe", "response has tool_use?"),
        (21.5, "B", "Classify", "type + complexity\n(no model call)"),
        (41, "C", "Policy", "routable &\nsimple enough?"),
        (60.5, "D", "JEV or Claude", "structured decision\nor fallback"),
        (80, "E", "Verify + record", "agree/disagree →\ntelemetry store"),
    ]
    for x, tag, head, sub in dnodes:
        box(ax, x, 13.5, 17, 9.5, f"{tag}.  {head}\n{sub}", "#FFF7ED", JEV_EC, fs=8.8)
    for x in (19, 38.5, 58, 77.5):
        arrow(ax, (x, 18.25), (x + 2.2, 18.25), ms=13)

    # link transport to decision
    arrow(ax, (69, 35.8), (69, 23.2), ls="--", color=FAINT, rad=-0.25)
    label(ax, 84, 29.5, "detected from the\nsame response", fs=8.3)

    label(ax, 50, 6, "The /v1/messages path is never blocked or rewritten; "
                     "decision routing runs beside it.", fs=8.8, color=MUTED)
    label(ax, 50, 3, "Statistics CLI reports everything the decision lane recorded.",
          fs=8.8, color=MUTED)

    fig.savefig(OUT_DIR / "request-flow.png", bbox_inches="tight",
                facecolor=BG, pad_inches=0.25)
    plt.close(fig)


# ---- figure 3: routing + fallback decision tree -------------------------
def figure_decision_routing():
    fig, ax = canvas(8.8, 11.6)
    ax.set_xlim(0, 92)
    ax.set_ylim(0, 116)

    title(ax, 46, 112, "How a decision is routed", size=15)

    cx = 38
    box(ax, cx - 17, 100, 34, 8, "Decision event\n(/v1/decision · intercept · MCP)",
        GREY_FC, GREY_EC, fs=9.4)
    arrow(ax, (cx, 100), (cx, 94.5))

    box(ax, cx - 22, 86, 44, 8,
        "Classifier: infer type + complexity\n(regex / length heuristics — no model call)",
        PROXY_FC, PROXY_EC, fs=9.0)
    arrow(ax, (cx, 86), (cx, 80.5))

    diamond(ax, cx, 72, 60, 17,
            "JEV enabled & routing on\n& type routable\n& complexity ≤ threshold ?",
            WARN_FC, WARN_EC, fs=9.0)

    # "no" branch: straight to fallback (right side rail)
    ax.plot([68, 85], [72, 72], color=FAINT, lw=1.8)
    ax.plot([85, 85], [72, 16.5], color=FAINT, lw=1.8)
    arrow(ax, (85, 16.5), (81, 16.5), color=FAINT)
    label(ax, 88, 45, "NO", fs=9.5, color=FAINT, weight="bold")
    label(ax, 77, 74.5, "always safe", fs=8.2, color=MUTED)

    # "yes" branch
    arrow(ax, (cx, 63.5), (cx, 58))
    label(ax, cx + 3.5, 60.8, "YES", fs=9.5, color=OK_EC, weight="bold")

    box(ax, cx - 20, 49, 40, 9,
        "Call JEV Decisions API\n(typed choice / noul / score)", JEV_FC, JEV_EC, fs=9.2)
    arrow(ax, (cx, 49), (cx, 43.5))

    diamond(ax, cx, 34.5, 56, 18,
            "valid structured answer\n& confidence ≥ threshold\n& arrived in time ?",
            WARN_FC, WARN_EC, fs=8.8)

    # terminal nodes side by side (no overlap)
    box(ax, 4, 12, 30, 9, "Return JEV decision\n(recorded as routed_jev)",
        OK_FC, OK_EC, fs=9.2)
    box(ax, 50, 12, 30, 9, "Fallback to Claude\n(recorded as fallback_claude)",
        CLAUDE_FC, CLAUDE_EC, fs=9.0)

    # "yes" -> JEV result (down then left)
    ax.plot([cx, cx], [25.5, 23.2], color=OK_EC, lw=1.8)
    ax.plot([cx, 19], [23.2, 23.2], color=OK_EC, lw=1.8)
    arrow(ax, (19, 23.2), (19, 21), color=OK_EC)
    label(ax, cx - 6, 25.9, "YES", fs=9.5, color=OK_EC, weight="bold")

    # "no" -> fallback (down then right)
    ax.plot([cx, 65], [25.5, 25.5], color=WARN_EC, lw=1.8)
    arrow(ax, (65, 25.5), (65, 21), color=WARN_EC)
    label(ax, 60, 27.2, "NO", fs=9.5, color=WARN_EC, weight="bold")

    label(ax, 46, 5, "Quality first: any uncertainty, timeout, malformed output or\n"
                     "complex task always falls back to Claude.",
          fs=9, color=MUTED)

    fig.savefig(OUT_DIR / "decision-routing.png", bbox_inches="tight",
                facecolor=BG, pad_inches=0.25)
    plt.close(fig)


# ---- figure 4: getting started pipeline ---------------------------------
def figure_getting_started():
    fig, ax = canvas(13, 4.4)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 34)

    title(ax, 50, 29.5, "From zero to a routed Claude Code session", size=15)

    steps = [
        ("1", "Clone", "git clone\n…/jevXagent.git"),
        ("2", "Install", "python -m venv .venv\npip install -e \".[dev]\""),
        ("3", "Configure", "copy .env.example .env\nadd CLAUDE_API_KEY"),
        ("4", "Run proxy", "jevXagent serve\n→ 127.0.0.1:8787"),
        ("5", "Point Claude Code", "ANTHROPIC_BASE_URL\n→ http://127.0.0.1:8787"),
    ]
    w, gap, start = 17.4, 3.0, 0.5
    x = start
    for i, (num, head, sub) in enumerate(steps):
        fc, ec = ("#FFF7ED", JEV_EC) if i == 4 else ("#EFF6FF", PROXY_EC)
        box(ax, x, 9, w, 15, f"{num}\n{head}\n{sub}", fc, ec, fs=8.6)
        if i < len(steps) - 1:
            arrow(ax, (x + w + 0.3, 16.5), (x + w + gap - 0.4, 16.5),
                  color="#94A3B8", ms=13)
        x += w + gap

    label(ax, 50, 4, "Optional: add a JEV key to turn on decision routing, "
                     "then run  jevXagent statistics  to see the evidence.",
          fs=9, color=MUTED)

    fig.savefig(OUT_DIR / "getting-started.png", bbox_inches="tight",
                facecolor=BG, pad_inches=0.25)
    plt.close(fig)


# ---- figure 5: evidence model -------------------------------------------
def figure_evidence_model():
    fig, ax = canvas(12, 4.6)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 38)

    title(ax, 50, 33.5, "The honesty rule behind every number", size=15)

    cols = [
        (2, "MEASURED", OK_FC, OK_EC,
         "read straight from real\nprovider calls\n\n• latency (ms)\n"
         "• API-reported tokens\n• routes, fallbacks, errors"),
        (34.5, "ESTIMATED", WARN_FC, WARN_EC,
         "projected from history or\nconfigured baselines\n\n"
         "• Claude tokens avoided\n• latency avoided\n• cost avoided"),
        (67, "UNAVAILABLE", GREY_FC, GREY_EC,
         "shown as n/a\n\n• anything the API does\n  not report\n\n"
         "never invented, never guessed"),
    ]
    for x, head, fc, ec, body in cols:
        box(ax, x, 6, 31, 22, "", fc, ec, radius=0.7)
        ax.text(x + 15.5, 24.5, head, ha="center", va="center", fontsize=11.5,
                color=ec, fontweight="bold")
        ax.text(x + 15.5, 14.5, body, ha="center", va="center", fontsize=9.2,
                color=INK, linespacing=1.5)

    fig.savefig(OUT_DIR / "evidence-model.png", bbox_inches="tight",
                facecolor=BG, pad_inches=0.25)
    plt.close(fig)


def figure_why_routing():
    fig, ax = canvas(12, 5.6)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 44)

    title(ax, 50, 41, "The main goal: give low-complexity decisions a cheaper path",
          size=15)

    panels = [
        (3, "Today (no routing)", "#F8FAFC", "#CBD5E1",
         ["Claude"] * 8,
         "every micro-decision is handled by\nthe primary (most expensive) model"),
        (52, "With jevXagent", "#FFFBF5", JEV_EC,
         ["JEV", "Claude", "JEV", "JEV", "Claude", "JEV", "JEV", "JEV"],
         "low-complexity decisions go to JEV;\ncomplex ones still go to Claude"),
    ]

    chip_h, chip_gap = 2.0, 0.7
    for x0, head, panel_fc, panel_ec, labels, cap in panels:
        ax.add_patch(FancyBboxPatch(
            (x0, 8), 45, 28, boxstyle="round,pad=0.3,rounding_size=0.8",
            linewidth=1.8, edgecolor=panel_ec, facecolor=panel_fc, mutation_aspect=1.0))
        ax.text(x0 + 22.5, 33.4, head, ha="center", va="center", fontsize=11.5,
                color=JEV_EC if panel_ec == JEV_EC else INK, fontweight="bold")
        y = 29.4
        for lab in labels:
            is_jev = lab == "JEV"
            ax.add_patch(FancyBboxPatch(
                (x0 + 11, y), 23, chip_h,
                boxstyle="round,pad=0.05,rounding_size=0.5",
                linewidth=1.1, edgecolor=JEV_EC if is_jev else CLAUDE_EC,
                facecolor=JEV_FC if is_jev else CLAUDE_FC, mutation_aspect=1.0))
            ax.text(x0 + 22.5, y + chip_h / 2, lab, ha="center", va="center",
                    fontsize=8.2, color=INK, fontweight="bold")
            y -= chip_h + chip_gap
        ax.text(x0 + 22.5, 5, cap, ha="center", va="center", fontsize=8.6,
                color=MUTED, linespacing=1.4)

    label(ax, 50, 1, "Illustrative only — the real split is measured, not assumed.",
          fs=8.4, color=FAINT)

    fig.savefig(OUT_DIR / "why-routing.png", bbox_inches="tight",
                facecolor=BG, pad_inches=0.25)
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    figure_architecture()
    figure_request_flow()
    figure_decision_routing()
    figure_getting_started()
    figure_evidence_model()
    figure_why_routing()
    for path in sorted(OUT_DIR.glob("*.png")):
        print(f"wrote {path.relative_to(OUT_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
