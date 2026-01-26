# Project: widget-helper

## Stack
- Language: python
- Frameworks: None
- Tools: None

## Code Standards
- New files: aim 200-300 lines, split at 400
- Existing files: don't refactor unless >500 lines
- Working god files: leave alone (one responsibility > line count)
- Max function size: 25 lines (40+ ok if one clear purpose)
- Full type hints required
- Use dataclasses/pydantic for structured data
- pathlib over os.path

## Testing
- pytest for all tests
- No mocks unless external service
- Test file mirrors source: src/foo.py → tests/test_foo.py
