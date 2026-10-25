# Provider configuration

`ProviderSettings.from_env()` selects a provider from
`CONTEXT_HUB_PROVIDER`, defaulting to `nebius`. The factory supports `nebius`
and `nvidia`; an unsupported value raises `ProviderError`.

| Provider | API key | Default model | Default endpoint |
|---|---|---|---|
| `nebius` | `NEBIUS_API_KEY` | `nvidia/nemotron-3-super-120b-a12b` | `https://api.tokenfactory.nebius.com/v1` |
| `nvidia` | `NVIDIA_API_KEY` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | `https://integrate.api.nvidia.com/v1` |

Override provider-specific model and URL with `NEBIUS_MODEL`/
`NEBIUS_BASE_URL` or `NVIDIA_MODEL`/`NVIDIA_BASE_URL`. General settings are
`CONTEXT_HUB_TIMEOUT`, `CONTEXT_HUB_TEMPERATURE`, `CONTEXT_HUB_MAX_TOKENS`,
`CONTEXT_HUB_MAX_CONTEXT_CHARS`, and `CONTEXT_HUB_RETRIES`.

The HTTP providers send JSON chat-completion requests and require the matching
API key. Missing keys raise a provider error when generation is attempted;
they are not needed for indexing, retrieval, inspection, graph operations,
proposal structural validation, or `ctx pack --no-llm`. Keep keys in the
process environment or a secret manager, never in the repository. `ctx provider
status` reports only `configured` or `missing` for the key.

## NVIDIA API Catalog (Windows)

In Command Prompt, select NVIDIA explicitly and set the endpoint, model, and
key in the current shell:

```bat
set CONTEXT_HUB_PROVIDER=nvidia
set NVIDIA_API_KEY=your-nvidia-api-key
set NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
set NVIDIA_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b
uv run ctx provider status
uv run ctx analyze "Explain the project architecture, identify the main modules, and trace how data flows between them."
```

In PowerShell:

```powershell
$env:CONTEXT_HUB_PROVIDER = "nvidia"
$env:NVIDIA_API_KEY = "your-nvidia-api-key"
$env:NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
$env:NVIDIA_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
uv run ctx provider status
uv run ctx analyze "Explain the project architecture, identify the main modules, and trace how data flows between them."
```

`ctx provider status` is local-only and prints the selected provider, model,
endpoint, and only whether the selected provider's key is configured. If the
key is missing, analysis stops with an NVIDIA-specific diagnostic and makes no
request. Nebius remains available by setting `CONTEXT_HUB_PROVIDER=nebius`,
`NEBIUS_API_KEY`, and optionally `NEBIUS_BASE_URL` and `NEBIUS_MODEL`.

If NVIDIA returns `Function ... Not found for account`, the endpoint is
reachable, but the account-scoped 404 may reflect model availability,
entitlement, or an endpoint/model mismatch. Confirm the exact `NVIDIA_MODEL`,
the `NVIDIA_BASE_URL`, and that the model is enabled for the account. This is
different from a missing key or a network failure.
