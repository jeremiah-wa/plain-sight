# 0002. Run the Postgres tests against a local ephemeral container, with no way to point them at a hosted database

- **Status:** Accepted
- **Date:** 2026-07-31

## Context and problem statement

The `postgres_conn` fixture drops and re-migrates every table around each test.
Until now the only `PLAIN_SIGHT_TEST_DATABASE_URL` on hand pointed at the hosted
Supabase instance, and `AGENTS.md` said so ("Postgres is hosted on Supabase;
there is no local Docker. Never run the destructive Postgres test against it"),
which put a loaded gun behind a house rule: a stray `uv run pytest` in a shell
with that variable exported destroys the schema of the project's only real
database. A convention that has to be remembered at exactly the wrong moment is
not a safeguard. The question is what the tests run against, and what stops them
running against anything else.

## Decision drivers

- Safety: the destructive fixture must not be *able* to reach a database anyone cares about.
- Speed: no per-statement round trip to `ap-southeast-1`.
- Independence: the suite passes offline, and on a machine that has never seen the Supabase credentials.
- Nothing is lost by moving off Supabase for tests: it has no separate dev role, and `PLAIN_SIGHT_DATABASE_URL` (what the app actually reads) is unset.
- One provisioning mechanism shared with CI, not a second one to keep honest.

## Considered options

- Keep Supabase as the test target, and keep the house rule.
- A `compose.yaml` service plus a structural refusal in the fixture.
- `testcontainers`, provisioning Postgres from inside the test suite.
- A guardrail with an opt-out (an env var or marker that permits a remote target).

## Decision outcome

Chosen option: "compose service plus a structural refusal", because it is the
only option where forgetting is harmless: the fixture resolves to a local
throwaway container by default, and refuses outright anything that is not both a
loopback host (`localhost`, `127.0.0.1`, `::1`) and a database named `*_test`.

Concretely:

- `compose.yaml` defines `db` on `postgres:17.6`, on host port `15432`, with `/var/lib/postgresql/data` on `tmpfs`, so no state survives a restart. (The port was `55432` as first written. Windows reserves blocks inside the 49152+ dynamic range for WinNAT and Hyper-V, and `55432` landed in one, so `docker compose up -d db` could not bind at all; `15432` sits below that range. The decision above is unaffected, only the number.)
- `tests/local_postgres.py` holds the refusal and the fallback. Unset means "the local container", not "skip".
- An explicitly configured database that is unreachable is an error; the implicit local default being unreachable is a skip that names `docker compose up -d db`.
- Version parity is with the deployment target, not with CI: Supabase reports 17.6, so local and CI both move to 17.6.
- Debian-based image, not Alpine: musl brings different ICU and collation behaviour, and the schema does text ordering and equality inside a GIST index.
- CI keeps its `services:` block rather than running compose. Its health-gated job start is worth more than deduplicating a version string; cross-referencing comments keep the two pins in step.

This reverses the `AGENTS.md` house rule and the `docs/ARCHITECTURE.md` line
"It is hosted on Supabase; there is no local Docker Postgres", both of which
are edited to describe the container and link here. Supabase remains the
deployment target and the system of record; only the tests move.

### Consequences

- Good, because the accident is now structurally impossible rather than forbidden by convention, and the refusal names the host and database it declined.
- Good, because the Postgres tests run offline, in RAM, without credentials.
- Bad, because the suite can no longer be pointed at Supabase **at all**, so Supabase-specific divergence (extension availability, pooler statement behaviour, managed-instance settings) is now caught first at deploy rather than by a test run.
- Bad, because contributors need Docker to run the `-m postgres` tests. Accepted: they skip cleanly with the fix in the message, and CI runs them on every push.

## Pros and cons of the options

### Keep Supabase as the test target

- Good, because it needs no new tooling and tests the exact managed instance the app deploys against.
- Bad, because the safety of the project's only real database rests on nobody having a variable exported. It is slow (round trips to `ap-southeast-1`) and needs credentials and a network.

### Compose service plus a structural refusal (chosen)

- Good, because safety stops being a rule and starts being a property; fast, offline, and shares one mechanism with CI's service container.
- Bad, because it requires Docker locally, and it gives up early warning of Supabase-specific divergence.

### `testcontainers`

- Good, because provisioning is automatic, with no "did you start the container" step.
- Bad, because it adds a Docker SDK dependency imported by the test suite, and a second provisioning mechanism alongside CI's `services:` block.

### A guardrail with an opt-out

- Good, because a deliberate run against Supabase stays possible for diagnosing managed-instance divergence.
- Bad, because the escape hatch is exactly the thing an agent or a tired human reaches for when a test errors, which returns the failure mode in full. A guardrail with an override is a house rule wearing a costume.
