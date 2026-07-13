"""Core: the single orchestrator plus provider/transport-independent contracts.

The core depends only on the ports (interfaces) in `ports.py` and the domain
models in `models.py`. It never imports a provider SDK, a vector-store client,
or a web framework.
"""
