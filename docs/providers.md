# Provider configuration

`ProviderSettings.from_env()` selects a provider from
`CONTEXT_HUB_PROVIDER`, defaulting to `nebius`. The factory supports `nebius`
and `nvidia`; an unsupported value raises `ProviderError`.

| Provider | API key | Default model | Default endpoint |
|---|---|---|---|
| `nebius` | `NEBIUS_API_KEY` | `nvidia/nemotron-3-super-120b-a12b` | `https://api.tokenfactory.nebius.com/v1` |
| `nvidia` | `NVIDIA_API_KEY` | `nvidia/nemotron-3-super-120b-a12b` | `https://integrate.api.nvidia.com/v1` |

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
