# Security Policy

## Supported Versions

We take security seriously and provide security updates for the following versions:

| Version | Supported          | End of Life |
| ------- | ------------------ | ----------- |
| 2.x     | ✅ Yes             | TBD         |
| 1.x     | ❌ No (deprecated) | N/A         |

**Recommendation**: Always use the latest version of Lacuna v2 for the most recent security patches and improvements.

## Reporting a Vulnerability

**Please do not open public issues for security vulnerabilities.**

### How to Report

Report security vulnerabilities privately using one of these methods:

1. **GitHub Security Advisories** (Preferred)
   - Go to the repository's Security tab
   - Click "Report a vulnerability"
   - Fill out the form with details

2. **Email** (If GitHub advisories unavailable)
   - Send to: [SECURITY_EMAIL_ADDRESS]
   - Include "SECURITY" in the subject line
   - Provide details as outlined below

### What to Include

Please include the following information in your report:

- **Description**: Brief description of the vulnerability
- **Impact**: What an attacker could achieve
- **Affected versions**: Which versions are affected
- **Steps to reproduce**: Detailed steps to reproduce the issue
- **Proof of concept**: Example exploit (if applicable)
- **Suggested fix**: If you have ideas for fixing it
- **Your contact info**: So we can follow up with questions

### Example Report

```markdown
## Vulnerability: [Brief Title]

**Severity**: [Critical/High/Medium/Low]
**Affected Versions**: 2.0.0 - 2.0.5

### Description
[Detailed description of the vulnerability]

### Impact
[What an attacker could do with this vulnerability]

### Steps to Reproduce
1. [Step 1]
2. [Step 2]
3. [Step 3]

### Proof of Concept
[Code or configuration that demonstrates the issue]

### Suggested Fix
[Your ideas for fixing it, if any]
```

### Response Timeline

- **Initial response**: Within 48 hours
- **Status update**: Within 1 week
- **Fix timeline**: Depends on severity
  - Critical: Within 7 days
  - High: Within 14 days
  - Medium: Within 30 days
  - Low: Next minor release

### What to Expect

1. **Acknowledgment**: We'll confirm receipt of your report
2. **Investigation**: We'll investigate and validate the issue
3. **Fix development**: We'll develop and test a fix
4. **Coordinated disclosure**: We'll coordinate release timing with you
5. **Public disclosure**: After the fix is released
6. **Credit**: You'll be credited in the security advisory (unless you prefer anonymity)

## Security Features

Lacuna v2 is designed with security as a core principle:

### Input Validation

#### Scheme Allowlist
- **Only `http://` and `https://` URLs allowed**
- Rejects dangerous schemes: `javascript:`, `data:`, `file:`, `ftp:`, etc.
- Prevents XSS and other injection attacks

```yaml
# ✅ Allowed
to: https://example.com

# ❌ Rejected
to: javascript:alert('XSS')
to: data:text/html,<script>alert('XSS')</script>
to: file:///etc/passwd
```

#### No Templating
- **Redirect targets cannot contain templating characters**
- Rejects `{`, `}`, `$` in target URLs
- Prevents server-side template injection

```yaml
# ✅ Allowed
to: https://example.com/user/123

# ❌ Rejected
to: https://example.com/user/{user_id}
to: https://example.com/user/${USER}
```

#### Rule ID Validation
- **Alphanumeric with limited special characters**
- Pattern: `^[a-z0-9][a-z0-9._-]*$`
- Prevents injection through identifiers

#### Path Validation
- **Must start with `/`**
- Prevents directory traversal
- Normalized before processing

### Configuration Safety

#### Atomic Updates
- **All config changes are atomic**
- Uses temp file + fsync + os.replace pattern
- No partial configurations possible
- Either success or rollback

#### Validation Before Deployment
- **Fail-fast approach**
- Validates with Caddy before applying
- Syntax errors caught before going live
- Optional health probes before promotion

#### Automatic Rollback
- **Instant rollback on any failure**
- Preserves last-known-good configuration
- No manual intervention needed for rollback
- Logs all rollback events

### Network Security

#### Admin API Binding
- **Caddy admin API bound to loopback (127.0.0.1:2019)**
- Not exposed to external networks
- Access via kubectl port-forward in Kubernetes
- Access via docker exec in Docker

#### HSTS Support
- **Per-host HTTP Strict Transport Security**
- Configured via `hsts: true` in YAML
- Header: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- Prevents SSL stripping attacks

#### TLS/ACME
- **Automatic HTTPS via Let's Encrypt**
- Caddy handles certificate renewal
- ACME cache persisted to volume
- Rate limit protection (staging environment support)

### No Open Redirects

- **All redirect targets explicitly configured**
- No user-driven redirect parameters
- No wildcard redirects
- Prevents open redirect abuse

### Observability for Security

#### Request Tracing
- **X-Lacuna-Rule header on all responses**
- Tracks which rule matched
- Enables audit trails
- Helps identify suspicious patterns

#### Structured Logging
- **All operations logged in JSON format**
- Includes timestamps, rule IDs, hosts, paths
- No sensitive data in logs (no query params logged)
- Tamper-evident log format

#### Metadata Tracking
- **All configs include metadata**
- Build timestamp, git hash, content SHA256
- Enables change auditing
- Verifies config integrity

## Known Limitations

Please be aware of these limitations:

### 1. Admin API Exposure
**Risk**: If admin API (port 2019) is exposed externally, attackers can modify Caddy configuration.

**Mitigation**:
- Bind admin API to loopback only (default)
- Use firewall rules to block port 2019
- Access via kubectl port-forward or docker exec

### 2. ACME Certificate Storage
**Risk**: Certificates stored in persistent volume. If volume is compromised, certificates are exposed.

**Mitigation**:
- Use encrypted persistent volumes
- Restrict access to volumes (filesystem permissions)
- Regular security audits of volume access
- Consider using separate certificate management

### 3. Request Path Logging
**Risk**: Request paths may contain PII (personally identifiable information).

**Mitigation**:
- Review log retention policies
- Redact sensitive paths if needed
- Use aggregated metrics instead of raw logs
- Consider privacy regulations (GDPR, CCPA)

### 4. Denial of Service
**Risk**: High volume of requests can overwhelm the server.

**Mitigation**:
- Use rate limiting (Caddy plugins or external)
- Deploy behind DDoS protection (e.g., Cloudflare)
- Configure resource limits (CPU, memory)
- Monitor and alert on anomalies

### 5. Config Repository Access
**Risk**: If Git repository is compromised, attackers can inject malicious configs.

**Mitigation**:
- Use branch protection rules
- Require code review for all changes
- Enable signed commits
- Use CI/CD to validate configs before deployment

## Best Practices

### Development

- **Run `mypy --strict`**: Catch type errors before runtime
- **Use pre-commit hooks**: Enforce code quality automatically
- **Write security tests**: Test validation and rejection of malicious inputs
- **Review dependencies**: Regularly update and audit dependencies
- **Follow principle of least privilege**: Minimize permissions

### Deployment

- **Use secrets management**: For sensitive configuration (if any)
- **Enable HSTS**: For production domains
- **Disable HSTS**: For development/testing domains
- **Use staging environment**: Test configs before production
- **Monitor logs**: Watch for suspicious patterns
- **Regular updates**: Keep Caddy and Python packages updated
- **Backup configs**: Maintain config backups for disaster recovery

### Operations

- **Audit logs regularly**: Review access and changes
- **Monitor metrics**: Track request patterns and anomalies
- **Test rollback**: Verify rollback works before emergencies
- **Document procedures**: Maintain runbooks for security incidents
- **Incident response plan**: Have a plan for security breaches

## Security Checklist

Use this checklist when deploying Lacuna v2:

### Configuration
- [ ] Only http/https schemes used in configs
- [ ] No templating characters in redirect targets
- [ ] Rule IDs follow pattern `^[a-z0-9][a-z0-9._-]*$`
- [ ] Paths start with `/`
- [ ] Status codes are valid (301/302/303/307/308)

### Deployment
- [ ] Caddy admin API bound to loopback (not 0.0.0.0)
- [ ] Ports 80 and 443 exposed only (not 2019)
- [ ] HSTS enabled for production hosts
- [ ] HSTS disabled for parked/dev domains
- [ ] Persistent volumes encrypted (if required)
- [ ] Resource limits configured
- [ ] Health checks enabled

### Monitoring
- [ ] Logs aggregated to secure location
- [ ] Metrics collected (Prometheus/Grafana)
- [ ] Alerts configured for failures
- [ ] X-Lacuna-Rule header logged
- [ ] Certificate expiry monitored

### Operations
- [ ] Rollback procedure tested
- [ ] Backup configs maintained
- [ ] Incident response plan documented
- [ ] Security contacts established
- [ ] Regular security audits scheduled

## Security Updates

We announce security updates through:

1. **GitHub Security Advisories**: Published for all security issues
2. **Release Notes**: Security fixes highlighted in CHANGELOG.md
3. **Git Tags**: Security releases tagged with version number

### Subscribing to Updates

- **Watch the repository**: Click "Watch" → "All Activity"
- **GitHub Notifications**: Enable security alert emails
- **RSS**: Subscribe to releases RSS feed

## Vulnerability Disclosure Policy

We follow coordinated vulnerability disclosure:

1. **Report received**: Vulnerability reported privately
2. **Initial triage**: Within 48 hours
3. **Investigation**: Validate and assess severity
4. **Fix development**: Develop and test fix
5. **Pre-release notification**: Notify reporter of fix timeline
6. **Public release**: Release fix with security advisory
7. **Public disclosure**: 7 days after fix release
8. **Credit**: Reporter credited (unless anonymous preference)

### Embargo Period

- Minimum 7 days after fix release
- Allows users time to update
- Can be extended for critical issues

## Security Hall of Fame

We recognize security researchers who responsibly disclose vulnerabilities:

(List will be added as vulnerabilities are reported and fixed)

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Caddy Security Documentation](https://caddyserver.com/docs/security)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)

## Contact

For security-related questions (not vulnerabilities):
- **Email**: [GENERAL_CONTACT_EMAIL]
- **GitHub Discussions**: Security category

For vulnerability reports:
- **GitHub Security Advisories** (preferred)
- **Email**: [SECURITY_EMAIL_ADDRESS] (Subject: SECURITY)

---

**Thank you for helping keep Lacuna v2 secure!**
