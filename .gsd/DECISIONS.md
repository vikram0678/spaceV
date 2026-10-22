# DECISIONS.md — Architecture Decision Records (ADR)

## ADR-001: Celesto MicroVM Isolation for Untrusted SpaceV Commands
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Autonomous agents executing shell commands directly on the host risk prompt-injection attacks and uncontained file modifications.
- **Decision**: Route all untrusted, shell, or remote payload executions through guest Firecracker microVMs with automated snapshot rollback on failure.
- **Consequences**: Guarantees host isolation; introduces microVM spin-up overhead managed via pre-warmed guest instances.
