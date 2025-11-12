# Lacuna v2 - Infrastructure & Deployment Guide

This directory contains all infrastructure files needed to deploy Lacuna v2 in various environments.

## Overview

Lacuna v2 is a KISS (Keep It Simple, Stupid) redirection service that uses:
- **Caddy v2.8** as the edge server
- **Static JSON configuration** compiled from YAML
- **Double-buffered config promotion** for zero-downtime updates
- **HTTPS with automatic ACME/Let's Encrypt** certificate management

## Architecture

```
┌─────────────────────────────────────────┐
│         Client Requests (HTTP/S)        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         Load Balancer / Service         │
│    (Docker port mapping or K8s LB)      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         Caddy Edge Server(s)            │
│  • Reads: config.active.json            │
│  • ACME cache: /data                    │
│  • Admin API: localhost:2019            │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│     Static Redirect Rules (30x)        │
│  • Exact path matches                   │
│  • Prefix path matches                  │
│  • HSTS headers per host                │
│  • X-Lacuna-Rule tracking header        │
└─────────────────────────────────────────┘
```

## Deployment Options

| Option | Use Case | Complexity | HA Support |
|--------|----------|------------|------------|
| **Docker Compose** | Local dev, small deployments | Low | No |
| **Kubernetes** | Production, high availability | Medium | Yes |

## Quick Start

### Option 1: Docker Compose (Recommended for Dev/Testing)

**Prerequisites:**
- Docker or Podman with Compose support
- Compiled configuration files

**Steps:**

1. **Create volume directories:**

   ```bash
   mkdir -p vol/config vol/caddy
   ```

2. **Compile your configuration:**

   ```bash
   # Ensure you have the Python packages installed
   uv sync --all-extras --dev

   # Compile example configuration
   uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config
   ```

3. **Start the service:**

   ```bash
   cd infra
   docker compose up -d
   ```

4. **View logs:**

   ```bash
   docker compose logs -f caddy
   ```

5. **Test the service:**

   ```bash
   # Test HTTP redirect
   curl -v http://localhost

   # Test with specific host header
   curl -v http://localhost -H "Host: example.com"
   ```

6. **Stop the service:**

   ```bash
   docker compose down
   ```

**See [compose.yaml](./compose.yaml) for detailed configuration.**

---

### Option 2: Kubernetes (Recommended for Production)

**Prerequisites:**
- Kubernetes cluster (1.24+)
- kubectl configured
- Container image in registry

**Steps:**

1. **Build and push container image:**

   ```bash
   # Build image
   docker build -f infra/Dockerfile.caddy -t ghcr.io/YOUR_REPO/lacuna-caddy:v2.0.0 .

   # Push to registry
   docker push ghcr.io/YOUR_REPO/lacuna-caddy:v2.0.0
   ```

2. **Deploy to Kubernetes:**

   ```bash
   cd infra/k8s

   # Create PVCs
   kubectl apply -f pvc.yaml

   # Deploy application
   kubectl apply -f deployment.yaml
   kubectl apply -f service.yaml

   # Check status
   kubectl get pods,svc -l app=lacuna
   ```

3. **Upload initial configuration** (see [k8s/README.md](./k8s/README.md))

**See [k8s/README.md](./k8s/README.md) for comprehensive Kubernetes deployment guide.**

---

## Volume Layout

Lacuna uses two persistent volumes:

### 1. Configuration Buffer (`/srv/lacuna/config`)

Contains the double-buffered configuration files:

```
/srv/lacuna/config/
├── config.next.json      # Candidate config (being validated)
├── config.active.json    # Currently active config
└── config.lastgood.json  # Last known good config (for rollback)
```

**Lifecycle:**
1. Compiler writes `config.next.json`
2. Validation passes → reload Caddy with `next`
3. Success → promote `next` to `active`, backup `active` to `lastgood`
4. Failure → reload `lastgood`, abort promotion

**Access:**
- Docker Compose: `./vol/config` on host
- Kubernetes: `lacuna-config-pvc` PersistentVolumeClaim

### 2. ACME Cache (`/data`)

Caddy's default data directory containing:

```
/data/
├── caddy/
│   └── acme/
│       └── acme-v02.api.letsencrypt.org/
│           └── certificates/
│               └── *.crt, *.key, *.json
└── ... (other Caddy state)
```

**Purpose:**
- HTTPS certificate storage (Let's Encrypt)
- Certificate renewal state
- Caddy internal state

**Important:**
- Must persist across restarts to avoid rate limits
- Should be backed up regularly in production

**Access:**
- Docker Compose: `./vol/caddy` on host
- Kubernetes: `lacuna-acme-pvc` PersistentVolumeClaim

---

## Configuration Management

### Local Development

```bash
# 1. Edit YAML
vim examples/domainlist.yaml

# 2. Validate
uv run python -m lacuna_schema.check examples/domainlist.yaml

# 3. Compile (validation only)
uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config --validate-only

# 4. Compile and promote (reload Caddy)
uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config
```

### Docker Compose

```bash
# Update config
uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config

# Reload Caddy (option 1: restart container)
docker compose restart caddy

# Reload Caddy (option 2: admin API)
docker compose exec caddy caddy reload --config /srv/lacuna/config/config.active.json

# Or via admin API:
curl -X POST http://localhost:2019/load \
  -H "Content-Type: application/json" \
  -d @./vol/config/config.active.json
```

### Kubernetes

See [k8s/README.md - Updating Configuration](./k8s/README.md#updating-configuration-in-production) for detailed procedures.

---

## Security Model

### Admin API Binding

The Caddy admin API is bound to **loopback only** (127.0.0.1:2019) for security:

- **Docker Compose:** Access via `docker compose exec` or port mapping (use with caution)
- **Kubernetes:** Access via `kubectl port-forward` or internal service

**Do NOT expose port 2019 externally in production.**

### HTTPS & ACME

Caddy automatically obtains and renews HTTPS certificates using ACME (Let's Encrypt):

1. **HTTP-01 Challenge:** Requires port 80 accessible from internet
2. **Automatic Renewal:** Caddy handles renewals (30 days before expiry)
3. **Rate Limits:** Let's Encrypt has rate limits (50 certs/domain/week)

**Production tips:**
- Use staging environment first to avoid rate limits
- Ensure DNS is properly configured before deploying
- Monitor certificate expiry dates
- Backup ACME cache regularly

### Security Best Practices

- ✅ Admin API on loopback only
- ✅ HSTS enabled for production hosts
- ✅ No templating in redirect targets (prevents injection)
- ✅ Only `http/https` schemes allowed
- ✅ Containers run as non-root user
- ✅ Read-only root filesystem (where possible)
- ✅ Resource limits configured
- ✅ Health checks enabled

---

## Monitoring & Observability

### Health Checks

All deployments include health checks:

- **Liveness:** Is Caddy running? (Admin API `/config/`)
- **Readiness:** Is Caddy ready to serve traffic? (Admin API `/config/`)
- **Startup:** Has Caddy completed initialization?

### Logging

Caddy logs in structured format (JSON):

```json
{
  "level": "info",
  "ts": 1699999999.999,
  "msg": "handled request",
  "request": {
    "remote_ip": "1.2.3.4",
    "proto": "HTTP/2.0",
    "method": "GET",
    "host": "example.com",
    "uri": "/blog/post",
    "headers": {...}
  },
  "status": 308,
  "duration": 0.001234
}
```

**Access logs:**
- Docker: `docker compose logs caddy`
- Kubernetes: `kubectl logs -l app=lacuna`

### Metrics

Caddy exposes metrics on the admin API:

```bash
# Docker Compose
curl http://localhost:2019/metrics

# Kubernetes (via port-forward)
kubectl port-forward svc/lacuna-caddy-admin 2019:2019
curl http://localhost:2019/metrics
```

**Integrate with Prometheus:**
- Scrape endpoint: `http://localhost:2019/metrics`
- Format: OpenMetrics/Prometheus

### Custom Headers

All redirects include tracking headers:

```
X-Lacuna-Rule: <rule-id>
```

Use this header for:
- Rule hit tracking
- Debugging which rule matched
- Analytics and reporting

---

## Rollback Procedures

### Docker Compose

```bash
# Option 1: Restore previous config
cp vol/config/config.lastgood.json vol/config/config.active.json
docker compose restart caddy

# Option 2: Roll back to previous image
docker compose down
docker tag ghcr.io/YOUR_REPO/lacuna-caddy:v2.0.0-previous \
  ghcr.io/YOUR_REPO/lacuna-caddy:latest
docker compose up -d
```

### Kubernetes

```bash
# Option 1: Rollback deployment
kubectl rollout undo deployment/lacuna-caddy

# Option 2: Restore config from lastgood
kubectl exec <pod> -- cp /srv/lacuna/config/config.lastgood.json \
  /srv/lacuna/config/config.active.json
kubectl exec <pod> -- caddy reload --config /srv/lacuna/config/config.active.json

# Option 3: Rollback to specific revision
kubectl rollout history deployment/lacuna-caddy
kubectl rollout undo deployment/lacuna-caddy --to-revision=2
```

See [k8s/README.md - Rollback Procedures](./k8s/README.md#rollback-procedures) for details.

---

## Troubleshooting

### Common Issues

#### 1. Config file not found

**Symptom:** Caddy fails to start, logs show "config file not found"

**Solution:**
- Ensure `config.active.json` exists in the config volume
- Run compiler to generate initial config
- Check volume mounts are correct

```bash
# Docker Compose
ls -la vol/config/
docker compose exec caddy ls -la /srv/lacuna/config/

# Kubernetes
kubectl exec <pod> -- ls -la /srv/lacuna/config/
```

#### 2. ACME challenge failures

**Symptom:** HTTPS certificate not obtained, logs show ACME errors

**Solutions:**
- Ensure port 80 is accessible from internet (for HTTP-01 challenge)
- Check DNS records point to correct IP
- Verify firewall rules allow inbound 80/443
- Check rate limits (use staging first)

```bash
# Test from external source
curl -v http://your-domain.com/.well-known/acme-challenge/test
```

#### 3. Admin API not accessible

**Symptom:** Cannot access admin API on 2019

**Cause:** API bound to loopback for security

**Solutions:**
```bash
# Docker Compose: Use exec
docker compose exec caddy caddy reload --config /srv/lacuna/config/config.active.json

# Kubernetes: Use port-forward
kubectl port-forward svc/lacuna-caddy-admin 2019:2019
curl http://localhost:2019/config/
```

#### 4. Redirects not working

**Symptom:** Getting 404 or unexpected responses

**Debug steps:**
```bash
# 1. Check config is loaded
curl http://localhost:2019/config/ | jq '._meta'

# 2. Check rule matches
curl -v http://your-domain.com/path

# 3. Check logs for errors
docker compose logs caddy | grep -i error
kubectl logs -l app=lacuna | grep -i error

# 4. Validate config syntax
caddy validate --config vol/config/config.active.json
```

### Debug Mode

Enable debug logging:

```bash
# Docker Compose: Add to environment
services:
  caddy:
    environment:
      - CADDY_DEBUG=1

# Kubernetes: Add to deployment env
env:
  - name: CADDY_DEBUG
    value: "1"
```

### Getting Help

1. Check logs for errors
2. Validate configuration syntax
3. Test with curl including `-v` flag
4. Review [AGENTS.md](../AGENTS.md) for specifications
5. Check [Caddy documentation](https://caddyserver.com/docs/)

---

## Performance Tuning

### Resource Limits

**Docker Compose** (optional, uncomment in compose.yaml):
```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 512M
    reservations:
      cpus: '0.5'
      memory: 128M
```

**Kubernetes** (configured in deployment.yaml):
```yaml
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

Adjust based on:
- Number of domains
- Traffic volume
- Number of rules
- TLS session cache size

### Scaling

**Horizontal scaling** (Kubernetes only):
```bash
# Manual
kubectl scale deployment lacuna-caddy --replicas=5

# Auto-scaling (HPA)
kubectl apply -f hpa.yaml
```

**Vertical scaling** (adjust resource limits):
- More CPU → faster TLS handshakes
- More memory → larger TLS session cache

---

## Production Deployment Checklist

### Pre-deployment

- [ ] Configuration validated and tested in staging
- [ ] DNS records configured and propagated
- [ ] Container image built and pushed to registry
- [ ] Image tagged with version (not `latest` for production)
- [ ] Resource limits configured appropriately
- [ ] Health checks tested and tuned
- [ ] Monitoring and alerting configured
- [ ] Backup procedures for PVCs documented
- [ ] Rollback procedure tested

### Post-deployment

- [ ] Health checks passing
- [ ] HTTPS certificates obtained successfully
- [ ] All redirect rules tested and working
- [ ] Logs aggregated and searchable
- [ ] Metrics collected in Prometheus/Grafana
- [ ] Alerts configured for failures
- [ ] Documentation updated with production specifics
- [ ] Team trained on operations procedures
- [ ] Runbooks created for common issues

---

## File Reference

```
infra/
├── README.md              # This file - deployment overview
├── Dockerfile.caddy       # Container image for Caddy
├── compose.yaml           # Docker Compose configuration
└── k8s/                   # Kubernetes manifests
    ├── README.md          # Detailed K8s deployment guide
    ├── pvc.yaml           # Persistent volume claims
    ├── deployment.yaml    # Caddy deployment
    └── service.yaml       # LoadBalancer service
```

---

## Additional Resources

- [Lacuna AGENTS.md](../AGENTS.md) - Technical specifications
- [Lacuna PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md) - Architecture overview
- [Caddy Documentation](https://caddyserver.com/docs/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)

---

## Support

For issues related to:
- **Configuration:** See [packages/lacuna_compiler/README.md](../packages/lacuna_compiler/README.md)
- **Kubernetes:** See [k8s/README.md](./k8s/README.md)
- **Caddy:** See [Caddy docs](https://caddyserver.com/docs/)

---

**Next Steps:**
1. Choose your deployment method (Compose or K8s)
2. Follow the Quick Start guide above
3. Compile your configuration
4. Deploy and test
5. Set up monitoring and alerts
6. Document your production setup
