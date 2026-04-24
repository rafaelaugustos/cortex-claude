# Contributing to Cortex Claude

Thanks for your interest in contributing! Here's how to get started.

## Setup

```bash
git clone https://github.com/your-user/cortex-claude.git
cd cortex-claude
uv venv --python python3.13
uv sync --all-extras
uv run python -m spacy download en_core_web_sm
uv run python -m spacy download pt_core_news_sm  # optional, for Portuguese
```

## Running Tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/unit/test_facts.py

# Verbose output
uv run pytest -v

# Run benchmarks
uv run python scripts/benchmark.py
```

## Project Structure

```
src/cortex_claude/
├── core/           # Engine, scope manager, token budget, decay
├── storage/        # SQLite + sqlite-vec repositories
├── embeddings/     # Sentence-transformers wrapper, tokenizer
├── facts/          # spaCy fact extraction, normalization
├── summarizer/     # Extractive summarization
├── server/         # MCP server, tool handlers
└── models/         # Pydantic data models
```

## How to Contribute

### Bug Reports

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version, OS

### Feature Requests

Open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Why it belongs in Cortex (vs. being a separate tool)

### Pull Requests

1. Fork the repo and create a branch from `main`
2. Write tests for any new functionality
3. Make sure all tests pass: `uv run pytest`
4. Keep PRs focused — one feature/fix per PR
5. Update documentation if needed

### Code Style

- Type hints on all public functions
- No excessive comments — code should be self-explanatory
- Tests go in `tests/unit/` (no external deps) or `tests/integration/` (needs SQLite, models)
- Follow existing patterns in the codebase

### Adding a New MCP Tool

1. Create handler in `src/cortex_claude/server/tools/your_tool.py`
2. Add method to `CortexEngine` in `src/cortex_claude/core/engine.py`
3. Register in `src/cortex_claude/server/app.py` with `@mcp.tool()`
4. Add tests in `tests/integration/`

### Adding a New Language

1. Add model name to `LANG_MODELS` in `src/cortex_claude/facts/spacy_extract.py`
2. Add detection markers to `_detect_lang()` in the same file
3. Add the same to `src/cortex_claude/summarizer/extractive.py`
4. Add stop words to `STOP_WORDS` in `src/cortex_claude/facts/normalizer.py`
5. Document in README

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical specification.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
