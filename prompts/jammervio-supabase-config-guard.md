Implement the isolated JammerVIO backlog task: add a fail-fast Supabase configuration guard.

Read and obey the repository AGENTS.md and CLAUDE.md before editing. Work only in the current task worktree. Do not commit, push, open a request, access devices, read credential files, or run Gradle on this host.

Current behavior: app/src/main/java/com/nuvio/tv/core/di/SupabaseModule.kt passes BuildConfig.SUPABASE_URL and SUPABASE_ANON_KEY directly to createSupabaseClient. Add a small non-secret validation path that runs before client construction.

Acceptance criteria:

1. Blank or whitespace-only URL values fail immediately with an actionable message naming the missing URL configuration.
2. Blank or whitespace-only anonymous-key values fail immediately with an actionable message naming the missing key configuration.
3. Valid nonblank values pass through unchanged.
4. No exception, log, test name, snapshot, or diagnostic output contains the actual key value.
5. Add focused pure unit tests for blank URL, blank key, whitespace-only values, and valid values, following existing project test conventions.
6. Keep the change minimal and do not alter unrelated dependency-injection behavior or configuration sources.

You may run repository-safe non-Gradle checks, but leave Android compilation/unit verification to the orchestrator's sanctioned remote ./scripts/verify.sh and MR pipeline. At the end, report files changed, exact checks attempted, unresolved risks, and whether the task is complete. Do not claim tests passed unless you observed them.
