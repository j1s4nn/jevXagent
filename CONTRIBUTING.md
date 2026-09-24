# Contributing to jevXagent

Thank you for your interest in contributing to jevXagent! This document provides guidelines and instructions for contributing.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:

1. **Clear title** describing the issue
2. **Steps to reproduce** the problem
3. **Expected behavior** vs actual behavior
4. **Environment details** (OS, Python version, agent type)
5. **Logs or error messages** (sanitize any API keys)

### Suggesting Features

Feature requests are welcome! Please include:

1. **Use case** - What problem does this solve?
2. **Proposed solution** - How should it work?
3. **Alternatives considered** - Other approaches you thought about
4. **Impact** - Who benefits from this feature?

### Submitting Pull Requests

1. **Fork the repository** and create a new branch
2. **Make your changes** with clear, focused commits
3. **Add tests** for new functionality
4. **Update documentation** if needed
5. **Ensure tests pass** (`pytest tests/ -v`)
6. **Submit a pull request** with a clear description

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/jevXagent-v0.2.git
cd jevXagent-v0.2

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Coding Standards

### Style Guidelines

- Follow **PEP 8** for Python code style
- Use **type hints** for function parameters and returns
- Write **docstrings** for modules, classes, and functions
- Keep functions **focused and small** (< 50 lines preferred)

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add OpenAI streaming support
fix: handle Jev timeout correctly
docs: update installation instructions
test: add integration test for bypass flow
```

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_proxy.py -v

# Run with coverage
pytest tests/ --cov=src/jevxagent
```

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Assume good intentions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

- **GitHub Discussions** for general questions
- **GitHub Issues** for bug reports and features
- **Email** myprojectjisan@gmail.com for private inquiries

Thank you for helping make jevXagent better!
