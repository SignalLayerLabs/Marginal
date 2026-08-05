# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Reporting a vulnerability

Do not open a public issue for vulnerabilities that could expose credentials, prompts,
private traces, budget bypasses, arbitrary execution, or supply-chain compromise.

Use GitHub private vulnerability reporting for this repository. Include:

- affected version and platform;
- minimal reproduction;
- impact and attack preconditions;
- suggested mitigation, when known.

The maintainers will acknowledge valid reports, assess severity, coordinate a fix, and
publish credit unless the reporter asks to remain anonymous.

## Security model

MARGINAL controls whether application-provided callables are invoked. It is not a sandbox,
credential vault, content filter, or authorization system. Applications remain responsible
for tool permissions, network controls, secret handling, and safe execution environments.
