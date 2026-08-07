# Simple Architecture & Clean Code Rules

- **No Over-engineering**: Keep code flat, linear, and human-readable in under 5 minutes.
- **Functions over Heavy Abstractions**: Do not introduce interface hierarchies or design patterns (Abstract Factory, Strategy, DAO) unless strictly necessary.
- **Guard Clauses**: Avoid nesting `if` blocks deeper than 2 levels. Return early.
- **Dependency Management**: Use `uv` (`uv sync`, `uv run`) for all Python operations in `backend/`.
- **Hardware Fallback**: All hardware interfaces (ESP32 Serial, Camera trigger) must support automatic Mock Mode.
