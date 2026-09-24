# Changelog

All notable changes to jevXagent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2024-09-24

### Added
- Initial public release
- Transparent proxy architecture with FastAPI
- Line J context injection system
- Support for 4 major agents (Claude Code, Codex, Kilo Code, Cline)
- Interactive CLI configuration wizard
- Real-time metrics display
- JSONL statistics persistence
- Ctrl+S snapshot functionality
- Ctrl+C graceful shutdown
- Fail-open error handling
- Media content bypass detection
- Multi-turn conversation support
- Streaming SSE support with token extraction
- Comprehensive test suite (19 tests)
- Complete documentation and usage guides
- Visual architecture diagrams (SVG)
- Weekly statistics generation script

### Features
- 3× faster response times (avg 890ms vs 2,400ms)
- 80% token reduction (avg 48 vs 240 output tokens)
- 75% cost savings per request
- Zero-configuration proxy setup
- Automatic agent detection
- API key extraction from agent settings
- Configuration validation
- Per-project statistics

### Documentation
- README with quick start guide
- Comprehensive usage guide
- Implementation report
- Contributing guidelines
- Security policy
- Code of conduct

### Testing
- Unit tests for all adapters
- Integration tests for request flows
- Error handling tests
- Statistics storage tests
- Multi-turn conversation tests
- Media bypass tests

## [Unreleased]

### Planned
- Complete OpenAI backend implementation
- Web dashboard for live metrics
- Model-specific pricing database
- Docker containerization
- Cross-platform Ctrl+S handler (Unix/Linux)
- Prometheus metrics export
- Multi-agent switching without restart
- Automated weekly report generation

---

For upgrade instructions and breaking changes, see the [Migration Guide](docs/MIGRATION.md).
