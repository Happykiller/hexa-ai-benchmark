"""Hexa-AI Benchmark auditor package.

CLI entrypoint and audit pipeline that scores an agent deliverable. Run via
``python auditor/main.py analyze <deliverable>`` (see README.md / CLAUDE.md).

Modules are imported flat (``main``, ``modules.*``, ``scoring_config``, ``challenges``)
with ``auditor/`` on ``sys.path``; pytest wires this through ``pythonpath`` in
pyproject.toml. This file intentionally exports nothing to avoid import side effects.
"""
