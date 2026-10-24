# Security and configuration audit

Audit scope: Context Hub Phase 11.4, reviewed 2026-10-24. This is an evidence-based engineering audit, not a security certification or a substitute for deployment-specific review.

## Trust boundaries reviewed

The review covered repository scanning and parsing, SQLite-backed indexing and retrieval, context packet assembly, MCP tools, the read-only agent tool executor, provider configuration and HTTP clients, patch proposal validation, subprocess-backed validation, packaging metadata, CI configuration, and existing security tests.

## Confirmed findings and remediation

| Severity | Component | Finding | Remediation | Verification |
|---|---|---|---|---|
| High | Scanner/indexing | A file symlink could be read after resolving outside the repository root. | Scanner now rejects files whose resolved target is outside the root. | `tests/test_security_audit.py::test_scanner_does_not_follow_file_symlink_outside_root` |
| Medium | Scanner/indexing | Scanner exclusions did not cover common credential variants such as `credentials.json` and `secrets.yaml`, although tool exposure was already blocked. | Scanner now excludes names beginning with `credentials.` or `secrets.`. | `tests/test_security_audit.py::test_scanner_excludes_sensitive_variants` |
| Medium | Provider configuration | Provider endpoints accepted arbitrary URL schemes and embedded URL credentials. | Configuration now requires an absolute HTTP(S) URL without embedded credentials. | `tests/test_security_audit.py::test_provider_url_rejects_non_http_and_embedded_credentials` |
| Medium | Validation/provider errors | Captured validation output and provider error details could preserve secret-shaped values supplied by an external process or response. | Secret assignments and bearer values are redacted before reports/errors are returned. | `tests/test_security_audit.py::test_validation_output_redacts_secret_like_text`; existing MCP redaction tests |

No credential values are reproduced in this report. Repository examples and tests use nonfunctional placeholders.

## Potential risks and limitations

- Provider responses are external input. Error detail is bounded and redacted, but provider-specific formats may contain sensitive material that does not match the current secret-shaped patterns.
- The scanner skips binary and undecodable files, but it is not a full DLP system. Source code itself may contain business-sensitive data.
- Gitignore handling is intentionally small and does not implement every gitignore pattern semantic. Sensitive-name and suffix protections are independent of gitignore rules.
- MCP is a local stdio service by default. The caller still controls the repository root and should run it with least privilege.
- Tool execution is read-only and uses fixed subprocess commands with `shell=False`; it does not apply patches. This does not protect against vulnerabilities in approved tools or imported project code.
- Dependency audit and remote CI execution were not run in this environment. No vulnerability claim is made from their absence.

## Checks not performed

- No live provider calls, network scans, or credential rotation were performed.
- The configured `uv` workflow could not be executed because the local `uv` cache was inaccessible and the shell had no `python` executable. Therefore focused tests and package/dependency audit results remain environment blockers, not passes.
- No full repository or remote GitHub Actions verification was run.

## Safe configuration assumptions

Use a repository root selected by the operator, keep provider credentials in environment variables outside the repository, and treat generated context packets, MCP responses, logs, and validation artifacts as potentially sensitive. Provider-backed operations require explicit credentials; deterministic/offline tests should use mocks.

## Reproducing the focused checks

From the repository root:

```text
uv run --locked --with pytest==8.3.5 pytest tests/test_security_audit.py tests/test_mcp_security.py tests/test_validation.py tests/test_providers.py
```

The command was not runnable in the audit environment because `uv` could not initialize its configured cache. It is recorded here as the intended reproducible check, not as an observed pass.
