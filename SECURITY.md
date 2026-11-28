# Security

## Supported versions

Only the current `world-class/v1` source line for **Vector Result Audit 0.2.2** is considered for fixes. Older snapshots are unsupported. This is a best-effort project with no SLA, production support, or guarantee that every reported issue will receive a fix.

## Reporting a vulnerability

Do not include credentials, private data, proprietary inputs, personal paths, or unreduced production artifacts in public issues. Report vulnerabilities privately through [GitHub Security Advisories](https://github.com/gedouluhui/vector-result-audit/security/advisories/new). Include the affected version or commit, operating system, runtime/dependency versions, a minimal sanitized reproduction, and the security impact you observed.

## Security boundaries

The CLI performs local JSON/HTML processing without network access or supplied-code execution. Python API callers supply trusted live objects; reports may retain identifiers and scores.

Hashes and fingerprints identify bytes or normalized inputs; they are not signatures or proof of trust. Review generated reports before sharing because metadata, names, prompts, queries, or previews may still be sensitive.
