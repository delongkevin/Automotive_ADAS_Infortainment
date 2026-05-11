# Automotive ADAS Workspace Instructions

## Core Principles

This workspace follows an **automation-first, complete-implementation workflow**. When implementing features, fixing issues, or enhancing code, follow these principles without waiting for confirmation:

### 1. **Automatically Fix All Problems Found**

When you discover any issues (errors, compliance problems, bugs, syntax errors), fix them immediately without asking:

- Markdown linting violations → Fix with `replace_string_in_file`
- JSON syntax errors → Correct and validate
- Test failures → Debug and resolve
- Code quality issues → Refactor proactively
- Missing dependencies or imports → Add automatically

Verify all fixes with appropriate validation tools (`get_errors()`, `run_in_terminal` with linters/validators).

### 2. **Complete Implementation Pattern**

Never implement features partially. Follow this **code → test → document → commit** sequence:

1. **Code**: Implement the feature using established patterns from the codebase
2. **Test**: Write tests immediately; run them to verify 100% pass rate
3. **Document**: Create comprehensive documentation with examples, API reference, troubleshooting
4. **Commit**: Stage, commit with descriptive message, and push to GitHub

Each step must be completed before moving to the next.

### 3. **Automatic Testing**

- After implementing or modifying code, always run relevant tests
- Use `pytest` for Python code; aim for 100% pass rate
- Include scenario-based validation where appropriate (MIL framework)
- Report test results and fix any failures before committing

### 4. **Comprehensive Documentation**

Create documentation that includes:

- **API Reference**: Signatures, parameters, return values, types
- **Configuration**: All configurable settings with examples
- **Integration Examples**: How to use within the broader ADAS ecosystem
- **Scenarios**: Real-world usage examples (driving scenarios, test cases)
- **Troubleshooting**: Edge cases, common errors, solutions
- **Performance Metrics**: Latency, accuracy, resource requirements

### 5. **Automatic Git Integration**

- After implementing, testing, and documenting features: **always commit and push**
- Commit messages must be descriptive:
  - Start with conventional prefix: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
  - Include feature name and brief description
  - Example: `feat: Add Traffic Sign Recognition with city/highway scenarios`
- Push to the default branch (`main`) without asking

### 6. **Codebase Pattern Compliance**

When implementing new features, follow established patterns:

- **ADAS Feature Class Structure**: Inherit patterns from LDW, ACC, AEB, BSD
  - `__init__()` with config, vehicle state initialization
  - `update()` method processing sensor data
  - `enable()` / `disable()` methods
  - Status dictionary with feature-specific fields
- **JSON Scenario Format**: Follow structure in `scenarios/*.json`
  - Events array with timestamps, event_type, parameters
  - Validation checkpoints with field, operator, expected_value
- **Test Organization**: Use `tests/test_mil.py` pattern
  - Feature-specific test classes
  - Scenario-based validation methods
  - Clear assertion messages

### 7. **Multi-Step Work Management**

For complex tasks requiring multiple steps, use `manage_todo_list` to:
- Break work into actionable tasks
- Mark tasks in-progress before starting
- Mark tasks completed immediately after finishing
- Provide visibility into progress

## When These Instructions Apply

✅ **Always apply to:**
- Feature implementations (new ADAS features, sensors, capabilities)
- Bug fixes and error resolution
- Test suite improvements
- Code refactoring
- Documentation updates
- Compliance fixes

✅ **Apply unless user explicitly says "just analyze" or "just explain"**
- Architectural discussions
- Code reviews
- Exploratory tasks

❌ **Don't apply to:**
- Conceptual questions ("How does LDW work?")
- One-off code snippets without project context
- Tool-only operations (file reads, searches with no changes)

## Success Metrics

A complete implementation in this workspace should result in:

- ✅ All code changes tested and passing (100% test pass rate)
- ✅ Zero linting/compliance errors
- ✅ Comprehensive documentation created
- ✅ Git commit with descriptive message
- ✅ Changes pushed to GitHub `main` branch
- ✅ Related tests passing in CI (if applicable)

## Example Workflow

**User Request:** "Add Pedestrian Detection System with urban scenario"

**Agent Implementation:**
1. Create `pedestrian_detection.py` in `core/adas_features/` following BSD/AEB patterns
2. Add to simulator initialization in `simulator.py`
3. Create detection methods, status dictionary, thresholds
4. Write unit tests in `tests/test_mil.py`
5. Create `pedestrian_detection_urban.json` scenario with validation points
6. Run: `pytest ADAS_SIL_System/tests/test_mil.py -v` → verify all passing
7. Create `PEDESTRIAN_DETECTION.md` documentation (1000+ lines)
8. Add feature to `core/adas_features/__init__.py` exports
9. Run final: `get_errors()` → verify zero compliance issues
10. Commit: `git add -A && git commit -m "feat: Add Pedestrian Detection with urban scenario"`
11. Push: `git push origin main`

## Configuration Override

If a user explicitly requests a different approach (e.g., "just show me the code", "don't auto-commit"), respect that request for that specific task only. The default workflow remains automation-first.
