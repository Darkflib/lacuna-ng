# AGENTS.md — Lacuna v2

A KISS redirection service: **Caddy** at the edge, static rules compiled from **YAML → Caddy JSON** by a small **Python** toolchain. No database. Exact and prefix matches only. External redirects allowed. Double-buffered config promotion with graceful reloads and instant rollback.

This document tells agents exactly what to build, how to test it, and when a task is “done”.

## Core principles

* **Simple, static, safe**: no runtime templating; only `http/https` targets.
* **Deterministic**: stable sort/order; reproducible builds; recorded metadata.
* **Fast failure**: validate early, refuse dangerous configs, keep last-known-good.
* **Observability by default**: log rule IDs, status, host, path, latency.

## Tech & conventions

* **Python**: 3.13 (3.12 OK). Dependency manager: **uv**.
* **Typing & style**: `mypy --strict`, `ruff`, `black`.
* **Data modelling**: **Pydantic v2**.
* **CLI**: **Typer** or stdlib `argparse` (already used in samples).
* **Testing**: `pytest`, coverage goal ≥ 85%.
* **Containers**: Podman/Docker; images to GHCR.
* **Edge**: **Caddy v2.8.x**, JSON config, admin bound to loopback.

## Repository layout (target)

```
.
├─ packages/
│  ├─ lacuna_schema/        # YAML models + validators
│  ├─ lacuna_compiler/      # YAML → Caddy JSON
│  └─ lacuna_promote/       # double-buffer, validate, reload, rollback
├─ tools/
│  └─ lacuna_sim/           # dry-run simulator (optional but desired)
├─ infra/
│  ├─ Dockerfile.caddy
│  ├─ compose.yaml
│  └─ k8s/                  # starter manifests
├─ examples/
│  └─ domainlist.yaml
├─ vol/                     # local dev volumes (gitignored)
│  ├─ config/
│  └─ caddy/
├─ .github/workflows/ci.yaml
├─ pyproject.toml
├─ .pre-commit-config.yaml
└─ AGENTS.md
```

## Task graph

```mermaid
graph TD
  S["Schema"]
  C["Compiler"]
  P["Promote"]
  I["Integration tests"]
  D["Infra & images"]
  R["R\"Retry/Fallback<br/>(re-route on timeout/error)\""]
  S --> C --> P --> I --> D
  P --> R
```

---

## Shared data contracts

### YAML schema (input)

```yaml
version: 1
defaults:
  hsts: true          # per-host override allowed
  keep_query: true
hosts:
  - host: example.com
    hsts: true
    rules:
      - id: home
        match: exact        # exact | prefix
        from: /
        to: https://www.example.org/
        status: 308
        keep_query: true
      - id: blog
        match: prefix
        from: /blog
        to: https://blog.example.org
        status: 308
        keep_query: true
  - host: parked.example.com
    hsts: false
    rules:
      - id: parked
        match: prefix
        from: /
        to: https://about.example.com/parked
        status: 302
```

Constraints:

* `id`: `^[a-z0-9][a-z0-9._-]*$`, unique per host.
* `match`: `exact` or `prefix`.
* `from`: absolute path, leading `/`.
* `to`: URL, **scheme in {http, https}**. No `{ }` or `$`.
* `status`: 301/302/303/307/308.
* `keep_query` defaults to `defaults.keep_query` (true unless overridden).
* `hsts` defaults to `defaults.hsts` (on for production, off for parked).

### Caddy JSON (output, excerpt)

* One HTTP 80 server: permanent redirect to HTTPS.
* One HTTPS 443 server: SNI+routing per host.
* For every rule, add response header `X-Lacuna-Rule: <id>`.
* For prefix rules, preserve remainder path, append query if `keep_query=true`.

---

## Sub-projects

### 1) `packages/lacuna_schema`

**Mission**: Validate YAML into typed models; run semantic checks; provide a tiny CLI checker.

**Inputs**: YAML file.
**Outputs**: `Config` object (Pydantic v2), or exit non-zero with actionable errors.

**Acceptance criteria**

* Detect invalid schemes, duplicate IDs, invalid statuses, templating chars in `to`, bad paths.
* Sorting helpers: exact rules ordered longest-path first; prefix rules longest-path first.
* Unit tests cover positive/negative golden cases and Hypothesis property tests for path shapes.

**CLI**

```bash
uv run python -m lacuna_schema.check examples/domainlist.yaml
# exit 0 on success; prints per-host/rule counts
```

**Security gates**

* Refuse schemes not in {http, https}.
* Refuse any `to` containing `{`, `}`, or `$`.

---

### 2) `packages/lacuna_compiler`

**Mission**: Compile `Config` → Caddy JSON (deterministic), with headers and HSTS.

**Inputs**: `Config` from `lacuna_schema`.
**Outputs**: `dict` (Caddy JSON), serialised to `config.next.json` with metadata block:

```json
{
  "_meta": {
    "built_at": "2025-11-12T12:34:56Z",
    "git": "abc1234",
    "content_sha256": "…"
  },
  "apps": { "http": { … } }
}
```

**Behaviour**

* **Exact**: path matcher → `static_response` with `Location` and status.
* **Prefix**: `match: path [<from>*]` → `subroute`:

  * `rewrite strip_path_prefix: <from>`
  * redirect to `<to.rstrip('/')>/{http.request.uri.path}`
  * If `keep_query=true`, append `?{http.request.uri.query}` *only if query present*.
* Add `X-Lacuna-Rule` header for all rule-driven responses.
* Per-host HSTS header if `hsts=true`:

  ```
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
  ```

**Acceptance criteria**

* Golden-file tests: identical JSON across runs.
* Integration tests show correct `Location` for representative paths.

**CLI**

```bash
uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config --validate-only
```

---

### 3) `packages/lacuna_promote`

**Mission**: Double-buffer promotion with validation, reload, and rollback.

**Files in `/srv/lacuna/config` (or `--out-dir`):**

* `config.next.json` (candidate)
* `config.active.json` (current)
* `config.lastgood.json` (rollback)

**Algorithm**

1. Write `next` atomically (tmp + fsync + replace).
2. `caddy validate --config next` → abort on error.
3. *(Optional)* Probe sentinel URL(s) and expect known 30x.
4. `caddy reload --config next` → on failure, reload `lastgood` and abort.
5. Promote: atomically replace `active` with `next`.

**CLI**

```bash
uv run lacuna-compiler examples/domainlist.yaml --out-dir /srv/lacuna/config
# validates + reloads + promotes by default (see implementation flags)
```

**Acceptance criteria**

* Corrupted candidate refuses to promote.
* Simulated reload failure triggers rollback.
* Logs clearly indicate active/rollback states.

---

### 4) `tools/lacuna_sim` (nice-to-have for CI)

**Mission**: Offline simulator to find dead rules and verify expected outcomes.

**Input**: `config.active.json` or YAML; optional `cases.txt`.
**Output**: Table `request → rule_id → status → location`; “dead rules” list.

**CLI**

```bash
uv run lacuna-sim --json ./vol/config/config.active.json --cases ./examples/cases.txt
```

**Acceptance criteria**

* Reports rule coverage; no false positives against golden cases.

---

### 5) `infra` (images, compose, k8s)

**Mission**: Make it trivial to run locally and to ship a minimal prod deploy.

* `Dockerfile.caddy`: use `caddy:2.8`, run with JSON config from `/srv/lacuna/config/config.active.json`. Persist ACME cache at `/data`.
* `compose.yaml`: map ports `80:80`, `443:443`; bind volumes:

  * `./vol/config:/srv/lacuna/config`
  * `./vol/caddy:/data`
* `k8s/`: starter Deployment/Service; PVC for `/data` and `/srv/lacuna/config`.

**Acceptance criteria**

* `docker compose up` serves examples with HTTPS termination once DNS is mapped (HTTP in dev is fine).
* Healthcheck returns 30x or 200 for sentinel paths.

---

## Running locally

```bash
# 1) Setup
uv sync --all-extras --dev
pre-commit install

# 2) Validate + compile (no reload)
uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config --validate-only

# 3) Run Caddy (HTTP dev)
caddy run --config ./vol/config/config.next.json

# 4) Promote (reload Caddy if running)
uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config
```

---

## CI (GitHub Actions)

**Gates**

1. `ruff`, `black --check`, `mypy --strict`, `pytest -q`.
2. `lacuna_schema.check` on examples and real domain list.
3. `lacuna-compiler --validate-only` to produce JSON artifact.
4. *(Optional)* Spin up Caddy and probe a handful of URLs.
5. Build multi-arch `lacuna-caddy` image and push to GHCR on `main`.

---

## Logging & metrics

* **Access logs**: JSON; include `rule_id` (from response header), `host`, `path`, `status`, `duration`.
  Configure Loki labels: `{app="lacuna", host, rule_id, status}`.
* **Headers**: Always set `X-Lacuna-Rule` on redirect responses.
* **Alerts**: reload failures, 5xx spikes, ACME renewal errors.

---

## Security posture

* Only `http/https` targets; no templating in v1; reject `{`, `}`, `$` in `to`.
* No user-driven redirects → classic open redirect abuse not applicable.
* Admin API bound to loopback (or internal network only).
* HSTS off for parked domains; on for production vhosts.
* Double-buffered promotion with instant rollback.

---

## PR checklist (agents must enforce)

* [ ] Code formatted (`ruff`, `black`), typed (`mypy --strict`), tested (`pytest`).
* [ ] New/changed YAML passes `lacuna_schema.check`.
* [ ] Compiler golden JSON updated intentionally (review diff carefully).
* [ ] Integration probe(s) added/updated for new rules.
* [ ] Security rules unchanged (no templating, schemes allowed).
* [ ] Documentation updated (README for the affected package).

---

## Interfaces (importable APIs)

```python
# packages/lacuna_schema/api.py
from pathlib import Path
from pydantic import BaseModel
from typing import List

class Rule(BaseModel): ...
class Host(BaseModel): ...
class Config(BaseModel): ...

def load_config(path: Path) -> Config: ...
def sort_rules(host: Host) -> Host: ...

# packages/lacuna_compiler/api.py
from lacuna_schema.api import Config
from typing import Dict, Any

def compile_to_caddy(cfg: Config) -> Dict[str, Any]: ...
def write_candidate(cfg: Config, out_dir: Path) -> Path: ...  # returns config.next.json path

# packages/lacuna_promote/api.py
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class PromoteOptions:
    out_dir: Path
    caddy_bin: str = "caddy"
    validate_only: bool = False

def compile_and_promote(yaml_path: Path, opts: PromoteOptions) -> Path: ...
```

---

## Failure handling & retries

* **Validate-time errors**: exit non-zero with precise messages; do **not** touch `active`/`lastgood`.
* **Reload failure**: log stdout/stderr; attempt rollback to `lastgood`; exit non-zero.
* **Partial writes**: use temp file + `fsync` + `os.replace` for atomicity.
* **Timeouts**: if using admin probes, retry once with backoff (250 ms → 1 s).

---

## Prompts for code agents

**Schema agent**

* *“Implement Pydantic v2 models for Lacuna YAML. Enforce scheme allow-list, forbid templating characters in `to`, validate IDs and statuses, and provide `python -m lacuna_schema.check <yaml>` CLI. Include unit tests with both valid and invalid fixtures and property tests for paths.”*

**Compiler agent**

* *“Implement YAML→Caddy JSON compiler with exact and prefix support as specified. Preserve path remainders for prefix; append query when `keep_query=true`. Insert `X-Lacuna-Rule`. Generate deterministic JSON with a `_meta` block. Provide CLI `lacuna-compiler` supporting `--validate-only` and defaulting to promote by calling `lacuna_promote`.”*

**Promote agent**

* *“Implement double-buffer promotion: write candidate with atomic replace, `caddy validate`, optional probe, `caddy reload`, then promote candidate to active; keep `lastgood` for rollback. On any failure, roll back and exit non-zero.”*

**Infra agent**

* *“Produce `Dockerfile.caddy`, `compose.yaml`, and starter K8s manifests. Persist `/data` (ACME) and `/srv/lacuna/config` (configs). Healthcheck returns expected 30x/200.”*

**Sim agent (optional)**

* *“Implement `lacuna-sim` that evaluates our generated subset of Caddy routes and prints which rule matches for given requests, highlighting dead rules.”*

---

## Example Make targets

```makefile
.PHONY: fmt lint test compile promote run
fmt: ; uv run ruff check --fix . && uv run ruff format . && uv run black .
lint: ; uv run mypy .
test: ; uv run pytest -q
compile: ; uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config --validate-only
promote: ; uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config
run:
\tdocker compose up --build
```

---

## Done definition (MVP)

* Exact/prefix redirects functional with correct `Location` and status.
* `X-Lacuna-Rule` present on all redirects.
* HSTS per policy (on for production, off for parked).
* Double-buffer promotion works; rollback verified.
* CI green; image builds published; `compose up` works locally with example config.

