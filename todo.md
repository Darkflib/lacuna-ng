## 1) `lacuna-schema` — config models and validation

**Goal**
Define the YAML schema (hosts, rules, defaults) with strict validation and semantic checks. No templating, only `http/https` targets. Expose a clean Python API.

**Deliverables**

* Python package `lacuna_schema/` with Pydantic v2 models: `Config`, `Host`, `Rule`.
* Loader `load_config(path: Path) -> Config`.
* Validators: scheme allow-list, rule ID syntax, no `{}`, `}`, `$` in `to`, longest-first sort helpers, duplicate ID detection.
* Unit tests with golden YAMLs (good/bad).
* Typed docs (README) with examples.

**Key tasks**

* Implement models, semantic validators, and ordering rules (exact then prefix, both longest-first).
* CLI check: `python -m lacuna_schema.check config.yaml` (exit non-zero on errors).
* Property-based tests for path edge cases (Hypothesis).

**Security**

* Disallow `javascript:`, `data:`, and anything non-`http/https`.
* Enforce `enabled: bool` default true; disabled rules don’t compile.

**Exit criteria**

* 100% of sample configs pass; all negative fixtures fail with clear messages.
* `mypy --strict` clean.

---

## 2) `lacuna-compiler` — YAML → Caddy JSON

**Goal**
Compile `Config` into deterministic Caddy JSON with exact and prefix redirects, response header `X-Lacuna-Rule: <id>`, and site-wide HSTS where enabled.

**Deliverables**

* Package `lacuna_compiler/` with `compile_to_caddy(cfg: Config) -> dict`.
* CLI: `lacuna-compiler config.yaml --out-dir /var/lib/lacuna/config --validate-only|--promote`.
* Deterministic output (stable ordering; embedded build metadata).

**Key tasks**

* Implement exact and prefix handlers:

  * Exact: path matcher → `static_response` with `Location` and status.
  * Prefix: `path: [from+"*"]` + `subroute` that `rewrite strip_path_prefix: from` then redirect to `to + {http.request.uri.path}` and, if `keep_query`, append `?{http.request.uri.query}` when query exists.
  * No user templating; string joins must be path-safe (`rstrip('/')` etc.).
* Inject `X-Lacuna-Rule`.
* Site-wide HSTS per host when enabled.
* JSON pretty-print with content SHA in a comment field (metadata node).

**Security**

* Reject any target containing `{`, `}`, or `$`.
* Optional loop guard: if `to.host == host` and `match == prefix` for `/`, refuse unless `allow_self_redirect: true` (hidden in v1; conservative).

**Exit criteria**

* Golden JSON fixtures stable across runs.
* Integration tests (see project 5) pass.

---

## 3) `lacuna-promote` — double buffer, validate, reload, rollback

**Goal**
Atomically write `config.next.json`, validate (`caddy validate`), reload (`caddy reload`), promote to `config.active.json`, keep `config.lastgood.json` for rollback.

**Deliverables**

* Module `lacuna_promote/` and CLI (already drafted in Step 3).
* Health probe hook (optional): GET a sentinel URL and verify expected 30x before committing; if it fails, roll back.

**Key tasks**

* Durable writes (`os.replace`), fsync, and clear logging.
* Optional admin API address support for health checks.
* Rollback on reload failure.

**Exit criteria**

* Chaos test: corrupt `config.next.json` → validation fails → no promotion; simulate failed reload → rollback to last good and log.

---

## 4) `lacuna-sim` — dry-run and coverage

**Goal**
Simulate requests against compiled config to surface dead rules, overlaps, and expected redirections. Post summary in CI.

**Deliverables**

* CLI `lacuna-sim --json config.active.json --requests cases.txt`.
* Output table: request → matched rule ID → status → location.
* Dead rule report (rules never matched by any sample input).

**Key tasks**

* Implement a tiny evaluator that mirrors our match ordering and handlers (only the subset we generate).
* Provide `cases.txt` generator based on rules (e.g., for each prefix `/foo`, generate `/foo`, `/foo/`, `/foo/bar`, `/foo?x=1`).

**Exit criteria**

* CI step comments the report on PRs; no “dead rules” for curated samples.

---

## 5) `lacuna-infra` — containers, volume layout, boot scripts

**Goal**
Package Caddy and provide a dev/ops-friendly layout with volumes for configs and ACME cache.

**Deliverables**

* `Dockerfile.caddy` (upstream caddy; config via JSON file on a RW volume).
* `compose.yaml` for local runs.
* K8s manifest (Deployment, Service, Config + PVCs) as a starting point.

**Volume layout**

```
/srv/lacuna/
  config/
    config.active.json
    config.lastgood.json
    config.next.json
  caddy/
    data/           # ACME cache
    logs/           # optional bind if you want file logs
```

**Sample `compose.yaml`**

```yaml
services:
  caddy:
    image: caddy:2.8
    command: ["caddy", "run", "--config", "/srv/lacuna/config/config.active.json", "--adapter", "caddyfile"]
    ports: ["80:80", "443:443"]
    volumes:
      - ./vol/config:/srv/lacuna/config
      - ./vol/caddy:/data       # caddy uses /data for ACME cache
    environment:
      - CADDY_ADMIN=0.0.0.0:2019
    healthcheck:
      test: ["CMD", "wget", "-qO-", "https://localhost:443", "--no-check-certificate"]  # adjust sentinel
      interval: 10s
      timeout: 2s
      retries: 6
```

*(You can run JSON directly without the Caddyfile adapter; the above keeps admin defaults explicit.)*

---

## 6) `lacuna-ci` — quality gates and build

**Goal**
Enforce standards, run unit/integration tests, build/push images, and publish artefacts.

**Deliverables**

* `.pre-commit-config.yaml` (ruff, black, end-of-file, yaml-lint).
* `pyproject.toml` for all packages, configured for `uv`.
* GH Actions workflow.

**Pre-commit (snippet)**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.2
    hooks: [{ id: ruff, args: ["--fix"] }, { id: ruff-format }]
  - repo: https://github.com/psf/black
    rev: 24.8.0
    hooks: [{ id: black }]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.1
    hooks: [{ id: mypy, additional_dependencies: ["pydantic>=2"] }]
  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks: [{ id: yamllint }]
```

**Workflow `.github/workflows/ci.yaml` (core steps)**

```yaml
name: ci
on:
  push: { branches: ["main"] }
  pull_request: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras --dev
      - run: uv run ruff check .
      - run: uv run black --check .
      - run: uv run mypy .
      - run: uv run pytest -q
      - name: Validate sample configs
        run: |
          uv run python -m lacuna_schema.check examples/domainlist.yaml
          uv run lacuna-compiler examples/domainlist.yaml --validate-only --out-dir ./out
  docker:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions: { contents: read, packages: write }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile.caddy
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ghcr.io/${{ github.repository }}/lacuna-caddy:latest
```

---

## 7) `lacuna-observability` — logs, labels, and dashboards

**Goal**
Ensure every redirect is observable; make it easy to answer “which rule redirected this request?”

**Deliverables**

* Caddy access log JSON with fields: `rule_id`, `host`, `request_path`, `status`, `duration`.
* Loki labels config example and a Grafana starter dashboard JSON.

**Tasks**

* Confirm our `X-Lacuna-Rule` header is set for all 30x responses.
* Add Caddy log custom fields via placeholders if needed (e.g., echo the header into logs using `log_format`).

**Alerting**

* Reload failures (non-zero from `lacuna-promote`).
* 5xx spikes.
* Certificate renewal failures from Caddy logs.

---

## Example inputs for agents

### Minimal sample `domainlist.yaml`

```yaml
version: 1
defaults:
  hsts: true
  keep_query: true
hosts:
  - host: prod.example.com
    hsts: true
    rules:
      - id: root
        match: exact
        from: /
        to: https://www.example.org/
        status: 308
      - id: blog
        match: prefix
        from: /blog
        to: https://blog.example.org
        status: 308
        keep_query: true
  - host: parked.example.com
    hsts: false
    rules:
      - id: park
        match: prefix
        from: /
        to: https://about.example.com/parked
        status: 302
```

### Makefile (dev ergonomics)

```makefile
.PHONY: fmt lint test compile run
fmt:
	uv run ruff check --fix .
	uv run ruff format .
	uv run black .
lint:
	uv run mypy .
test:
	uv run pytest -q
compile:
	uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config --validate-only
run:
	docker compose up --build
```

---

## Integration test harness (lightweight)

**Idea**
Spin up Caddy in CI against the compiled `config.next.json`, then probe a few URLs and assert `Location` and `status`.

**Pytest sketch**

```python
import os, subprocess, time, requests, json, tempfile, pathlib

def test_end_to_end(tmp_path: pathlib.Path):
    # Compile
    out = tmp_path/"config"
    out.mkdir()
    subprocess.check_call(["uv", "run", "lacuna-compiler", "examples/domainlist.yaml", "--out-dir", str(out), "--validate-only"])

    cfg = out/"config.next.json"
    p = subprocess.Popen(["caddy", "run", "--config", str(cfg)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(1.5)  # give it a moment
        r = requests.get("http://prod.example.com/", allow_redirects=False)
        assert r.status_code in (301,302,307,308)
        assert r.headers["location"].startswith("https://www.example.org")
    finally:
        p.terminate(); p.wait(timeout=5)
```

*(In CI, map host header or use `--adapter caddyfile` with a local bind. For speed, HTTP-only is fine for tests.)*

---

## Security notes (MVP, pragmatic)

* Only static rules; no user input in targets; classic open redirects don’t apply.
* Scheme allow-list enforced; templating characters rejected.
* Graceful reload with double buffer; `lastgood` for instant fallback.
* Parked domains: HSTS off by default; production vhosts: HSTS on (document why).
* Minimal attack surface: Caddy admin bound to loopback or protected network; no public admin.

---

## Ethics and privacy

* Logs can reveal user navigation patterns. Keep retention modest, prefer aggregation over raw where possible, and document the purpose of logging.
* Avoid per-user fingerprinting; stick to operational telemetry.
