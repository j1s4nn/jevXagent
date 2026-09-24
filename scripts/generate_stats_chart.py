#!/usr/bin/env python3
"""Generate weekly statistics visualization chart

This script reads jevxagent_stats.jsonl and generates a PNG chart
showing performance metrics over time.

Usage:
    python scripts/generate_stats_chart.py [--input path/to/stats.jsonl] [--output statistics/weekly_stats.png]
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not installed. Install with: pip install matplotlib")


def load_stats(stats_file: Path) -> List[Dict]:
    """Load statistics from JSONL file"""
    stats = []
    if not stats_file.exists():
        print(f"Error: Stats file not found: {stats_file}")
        return stats

    with open(stats_file) as f:
        for line in f:
            if line.strip():
                stats.append(json.loads(line))

    return stats


def generate_chart(stats: List[Dict], output_file: Path):
    """Generate visualization chart"""
    if not MATPLOTLIB_AVAILABLE:
        print("Cannot generate chart: matplotlib not installed")
        return

    if not stats:
        print("No statistics data to visualize")
        return

    # Parse timestamps
    timestamps = [datetime.fromisoformat(s['timestamp'].replace('Z', '+00:00')) for s in stats]

    # Extract metrics
    jev_latencies = [s['jev_latency_ms'] for s in stats if s.get('jev_enabled')]
    agent_latencies = [s['agent_latency_ms'] for s in stats]
    total_latencies = [s['total_latency_ms'] for s in stats]
    output_tokens = [s.get('agent_output_tokens', 0) for s in stats]

    # Create figure with subplots
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('jevXagent Weekly Statistics', fontsize=16, fontweight='bold')

    # 1. Latency over time
    ax1.plot(timestamps, total_latencies, label='Total Latency', color='#0066cc', linewidth=2)
    if jev_latencies:
        ax1.plot(timestamps[:len(jev_latencies)], jev_latencies, label='Jev Latency',
                color='#ffc107', linewidth=2, linestyle='--')
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Latency (ms)')
    ax1.set_title('Response Time Trend')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))

    # 2. Token usage distribution
    if output_tokens:
        ax2.hist(output_tokens, bins=30, color='#28a745', alpha=0.7, edgecolor='black')
        ax2.axvline(sum(output_tokens)/len(output_tokens), color='red',
                   linestyle='--', linewidth=2, label=f'Avg: {sum(output_tokens)/len(output_tokens):.0f}')
        ax2.set_xlabel('Output Tokens')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Token Usage Distribution')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

    # 3. Request volume over time
    # Group by day
    daily_counts = {}
    for ts in timestamps:
        day = ts.date()
        daily_counts[day] = daily_counts.get(day, 0) + 1

    days = sorted(daily_counts.keys())
    counts = [daily_counts[d] for d in days]

    ax3.bar(days, counts, color='#667eea', alpha=0.8, edgecolor='black')
    ax3.set_xlabel('Date')
    ax3.set_ylabel('Request Count')
    ax3.set_title('Daily Request Volume')
    ax3.grid(True, alpha=0.3, axis='y')
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # 4. Summary statistics panel
    ax4.axis('off')
    total_requests = len(stats)
    jev_enabled = sum(1 for s in stats if s.get('jev_enabled'))
    bypassed = sum(1 for s in stats if s.get('bypass'))
    avg_latency = sum(total_latencies) / len(total_latencies) if total_latencies else 0
    avg_tokens = sum(output_tokens) / len(output_tokens) if output_tokens else 0

    summary_text = f"""
    SUMMARY STATISTICS
    {'='*40}

    Total Requests: {total_requests:,}
    Jev Enabled: {jev_enabled:,} ({jev_enabled/total_requests*100:.1f}%)
    Bypassed: {bypassed:,} ({bypassed/total_requests*100:.1f}%)

    Avg Total Latency: {avg_latency:.0f} ms
    Avg Jev Latency: {sum(jev_latencies)/len(jev_latencies):.0f} ms

    Avg Output Tokens: {avg_tokens:.0f}
    Total Output Tokens: {sum(output_tokens):,}

    Period: {timestamps[0].strftime('%Y-%m-%d')}
         to {timestamps[-1].strftime('%Y-%m-%d')}
    """

    ax4.text(0.1, 0.5, summary_text, fontsize=12, family='monospace',
             verticalalignment='center', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # Adjust layout and save
    plt.tight_layout()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_file}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='Generate jevXagent statistics chart')
    parser.add_argument('--input', type=Path, default='jevxagent_stats.jsonl',
                       help='Path to stats JSONL file (default: jevxagent_stats.jsonl)')
    parser.add_argument('--output', type=Path, default='statistics/weekly_stats.png',
                       help='Output PNG file (default: statistics/weekly_stats.png)')

    args = parser.parse_args()

    print(f"Loading statistics from: {args.input}")
    stats = load_stats(args.input)

    if not stats:
        print("No statistics found. Run jevXagent and collect some data first!")
        return

    print(f"Found {len(stats)} requests")
    print(f"Generating chart...")

    generate_chart(stats, args.output)

    print("\nDone! Upload the chart to your repository:")
    print(f"  git add {args.output}")
    print(f"  git commit -m 'Update weekly statistics'")
    print(f"  git push")


if __name__ == '__main__':
    main()
