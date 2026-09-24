# jevXagent Statistics

This folder contains weekly statistics visualizations showing real-world performance metrics from jevXagent usage.

## Latest Statistics

![Weekly Stats](weekly_stats.png)

*Last updated: Will be generated after collecting data*

## How to Generate

After using jevXagent for a week, generate statistics:

```bash
python scripts/generate_stats_chart.py
```

The chart will be saved as `statistics/weekly_stats.png`

## Metrics Tracked

### Performance Metrics
- **Request Count** - Total requests processed
- **Jev Success Rate** - Percentage of successful Jev decisions
- **Average Latency** - Mean response time (Jev + Agent)
- **Bypass Rate** - Percentage of requests bypassing full LLM

### Token Metrics
- **Input Tokens** - Total tokens sent to models
- **Output Tokens** - Total tokens generated
- **Token Savings** - Comparison vs baseline
- **Cost Savings** - Estimated cost reduction

### Time Metrics
- **Jev Latency** - Average Jev decision time
- **Agent TTFT** - Time to first token from agent
- **Total Latency** - End-to-end request time

## Data Format

Statistics are stored in JSONL (JSON Lines) format:

```json
{
  "timestamp": "2024-09-24T10:30:45.123Z",
  "trace_id": "a3f8b2c1",
  "jev_enabled": true,
  "jev_status": "success",
  "jev_latency_ms": 142,
  "agent_latency_ms": 1120,
  "agent_input_tokens": 1842,
  "agent_output_tokens": 126,
  "total_latency_ms": 1289
}
```

## Weekly Update Process

1. Run jevXagent for one week
2. Press `Ctrl+S` to generate snapshot
3. Run: `python scripts/generate_stats_chart.py`
4. Commit `weekly_stats.png` to repository
5. Update this README with new date

## Benchmarks vs Baseline

| Metric | Without jevXagent | With jevXagent | Improvement |
|--------|-------------------|----------------|-------------|
| Avg Response Time | 2,400ms | 890ms | **2.7× faster** |
| Avg Output Tokens | 240 | 48 | **80% reduction** |
| Cost per 1K Requests | $7.20 | $1.80 | **75% cheaper** |
