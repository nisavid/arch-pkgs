# python-fastapi-openai-compat

Arch package for the FastAPI router factory used by Hayhooks to expose
OpenAI-compatible endpoints.

## Maintenance Baseline

- `authoritative_reference`: upstream
  [`fastapi-openai-compat` PyPI source and metadata](https://pypi.org/project/fastapi-openai-compat/1.2.0/);
  no same-name Arch or AUR recipe was available at the 2026-08 refresh.
- `advisory_references`: upstream
  [`fastapi-openai-compat` source](https://github.com/deepset-ai/fastapi-openai-compat)
  and Hayhooks release metadata.
- `divergence_notes`: the current recipe packages upstream `1.2.0` from its
  source distribution with pacman-owned FastAPI, Pydantic, and multipart
  dependencies; this remains the selected supporting version for Hayhooks
  `1.23.0`.
- `update_notes`: verify the immutable source, clean-build and inspect the
  package on Python 3.14, then prove request and response compatibility through
  the deferred Hayhooks REST and OpenAI-compatible API gate before publication.
