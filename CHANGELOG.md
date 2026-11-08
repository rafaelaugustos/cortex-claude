# Changelog

## 0.14.0

- Add an isolated, cross-process memory proof to the recovery CLI and Mavis dashboard. Test results never mark real client hooks active.
- Show capture, durable save, and context delivery separately for Claude and Codex.
- Extract a bounded static project map, including Vue script blocks, with file/line evidence and explicit coverage limits.
- Reuse unchanged analysis, remove obsolete code evidence, and queue source-dependent conclusions for review without automatically confirming them.
- Sample service health every minute and retain a bounded history of incidents and recovery.
- Close SQLite handles explicitly after health checks, backups and HTTP requests, preventing long-running dashboards from exhausting file descriptors. Retry transient launchd registration failures during service installation.
- Evaluate Codex and Claude using independent task graders, separate stores and actual provider token counters. Preserve neutral and regressing token results.
- Verify reproducible wheels, bundled dashboard assets, and 0.13.0 → 0.14.0 → 0.13.0 → 0.14.0 compatibility in an isolated installation.

Client-side Codex hook authorization remains a separate user-controlled step. Local backups do not protect against loss of the disk. Static analysis, model recall, and measured token savings remain bounded by their reported evidence.
