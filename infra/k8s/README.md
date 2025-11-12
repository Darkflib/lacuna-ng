# Lacuna v2 - Kubernetes Deployment Guide

This directory contains Kubernetes manifests for deploying Lacuna v2 in production.

## Prerequisites

- Kubernetes cluster (1.24+)
- `kubectl` configured to access your cluster
- Container image pushed to GHCR: `ghcr.io/YOUR_REPO/lacuna-caddy:TAG`
- Compiled configuration files ready to be deployed

## Quick Start

### 1. Update Configuration

Edit `deployment.yaml` and update the image path:

```yaml
image: ghcr.io/YOUR_REPO/lacuna-caddy:latest
```

Replace `YOUR_REPO` with your actual GitHub repository path.

### 2. Create Namespace (Optional)

```bash
kubectl create namespace lacuna
kubectl config set-context --current --namespace=lacuna
```

### 3. Deploy Persistent Volume Claims

```bash
kubectl apply -f pvc.yaml
```

Verify PVCs are created:

```bash
kubectl get pvc
```

Expected output:
```
NAME                STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS
lacuna-acme-pvc     Bound    pvc-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx   1Gi        RWO            standard
lacuna-config-pvc   Bound    pvc-yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy   1Gi        RWO            standard
```

### 4. Upload Initial Configuration

Before deploying, upload your compiled configuration to the config PVC:

```bash
# Compile your configuration locally
uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config

# Create a temporary pod to upload config
kubectl run config-upload --image=busybox --restart=Never --rm -it -- sh

# In the pod shell:
# Copy your config files to the PVC
# (Use kubectl cp in another terminal)
```

Alternative method using a helper pod:

```bash
# Create a helper pod
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: config-helper
spec:
  containers:
  - name: busybox
    image: busybox
    command: ['sh', '-c', 'sleep 3600']
    volumeMounts:
    - name: config
      mountPath: /config
  volumes:
  - name: config
    persistentVolumeClaim:
      claimName: lacuna-config-pvc
EOF

# Wait for pod to be ready
kubectl wait --for=condition=ready pod/config-helper

# Copy config files
kubectl cp ./vol/config/config.active.json config-helper:/config/config.active.json
kubectl cp ./vol/config/config.lastgood.json config-helper:/config/config.lastgood.json

# Verify
kubectl exec config-helper -- ls -la /config/

# Clean up
kubectl delete pod config-helper
```

### 5. Deploy Application

```bash
# Deploy Caddy
kubectl apply -f deployment.yaml

# Deploy Service
kubectl apply -f service.yaml
```

### 6. Verify Deployment

Check pod status:

```bash
kubectl get pods -l app=lacuna
kubectl logs -l app=lacuna -f
```

Check service:

```bash
kubectl get svc lacuna-caddy
```

For LoadBalancer type, wait for external IP:

```bash
kubectl get svc lacuna-caddy -w
```

### 7. Test the Service

Once the external IP is assigned:

```bash
# Get the external IP
EXTERNAL_IP=$(kubectl get svc lacuna-caddy -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test HTTP (should redirect to HTTPS)
curl -v http://$EXTERNAL_IP

# Test HTTPS (if DNS is configured)
curl -v https://your-domain.com
```

## Updating Configuration in Production

### Method 1: Rolling Update with Config PVC

1. **Compile new configuration locally:**

   ```bash
   uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config
   ```

2. **Upload new configuration to config PVC:**

   ```bash
   # Start helper pod
   kubectl run config-update --image=busybox --restart=Never --rm -it \
     --overrides='
     {
       "spec": {
         "containers": [{
           "name": "busybox",
           "image": "busybox",
           "stdin": true,
           "tty": true,
           "command": ["sh"],
           "volumeMounts": [{
             "name": "config",
             "mountPath": "/config"
           }]
         }],
         "volumes": [{
           "name": "config",
           "persistentVolumeClaim": {"claimName": "lacuna-config-pvc"}
         }]
       }
     }' -- sh

   # In another terminal, copy files
   kubectl cp ./vol/config/config.next.json config-update:/config/config.next.json

   # Exit the pod
   exit
   ```

3. **Trigger Caddy reload:**

   Access admin API via port-forward:

   ```bash
   kubectl port-forward svc/lacuna-caddy-admin 2019:2019 &

   # Validate new config
   caddy validate --config ./vol/config/config.next.json

   # Reload Caddy (via admin API)
   curl -X POST http://localhost:2019/load \
     -H "Content-Type: application/json" \
     -d @./vol/config/config.next.json

   # Verify reload was successful
   curl http://localhost:2019/config/ | jq '._meta'
   ```

4. **Promote config (inside helper pod):**

   ```bash
   kubectl exec -it <pod-name> -- sh

   # Inside pod
   cd /config
   cp config.active.json config.lastgood.json
   cp config.next.json config.active.json

   # Verify
   ls -la
   exit
   ```

### Method 2: ConfigMap + Rolling Deployment (Alternative)

For gitops-style deployments, consider using ConfigMaps:

```bash
# Create ConfigMap from config file
kubectl create configmap lacuna-config \
  --from-file=config.active.json=./vol/config/config.active.json

# Update deployment to use ConfigMap (requires manifest changes)
# Then roll out:
kubectl rollout restart deployment/lacuna-caddy
```

## Rollback Procedures

### Quick Rollback (Deployment)

If new pods are failing:

```bash
# Check rollout status
kubectl rollout status deployment/lacuna-caddy

# Rollback to previous deployment
kubectl rollout undo deployment/lacuna-caddy

# Rollback to specific revision
kubectl rollout history deployment/lacuna-caddy
kubectl rollout undo deployment/lacuna-caddy --to-revision=2
```

### Config Rollback

If you need to rollback configuration:

```bash
# Access a pod
kubectl exec -it <pod-name> -- sh

# Inside pod, restore lastgood config
cd /srv/lacuna/config
cp config.lastgood.json config.active.json

# Reload Caddy
caddy reload --config /srv/lacuna/config/config.active.json
exit
```

Or use the admin API:

```bash
kubectl port-forward svc/lacuna-caddy-admin 2019:2019 &

# Load lastgood config
kubectl exec <pod-name> -- cat /srv/lacuna/config/config.lastgood.json | \
  curl -X POST http://localhost:2019/load \
    -H "Content-Type: application/json" \
    -d @-
```

## Monitoring and Debugging

### View Logs

```bash
# All pods
kubectl logs -l app=lacuna -f

# Specific pod
kubectl logs <pod-name> -f

# Previous container (if crashed)
kubectl logs <pod-name> --previous
```

### Access Admin API

```bash
# Port-forward to admin service
kubectl port-forward svc/lacuna-caddy-admin 2019:2019

# In another terminal:
# Get current config
curl http://localhost:2019/config/ | jq .

# Get metrics
curl http://localhost:2019/metrics
```

### Shell into Pod

```bash
kubectl exec -it <pod-name> -- sh
```

### Check Events

```bash
kubectl get events --sort-by='.lastTimestamp' | grep lacuna
```

### Resource Usage

```bash
kubectl top pods -l app=lacuna
kubectl top nodes
```

## Scaling

### Manual Scaling

```bash
# Scale to 3 replicas
kubectl scale deployment lacuna-caddy --replicas=3

# Verify
kubectl get pods -l app=lacuna
```

### Auto-scaling (HPA)

Create a HorizontalPodAutoscaler:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: lacuna-caddy-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: lacuna-caddy
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

Apply:

```bash
kubectl apply -f hpa.yaml
kubectl get hpa
```

## Security Considerations

### Image Pull Secrets

If using a private registry:

```bash
# Create secret
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_GITHUB_TOKEN \
  --docker-email=YOUR_EMAIL

# Update deployment to use the secret (already configured in deployment.yaml)
```

### Network Policies

Create network policies to restrict traffic:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: lacuna-netpol
spec:
  podSelector:
    matchLabels:
      app: lacuna
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 80
    - protocol: TCP
      port: 443
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 53  # DNS
    - protocol: UDP
      port: 53  # DNS
```

### RBAC

The deployment uses minimal permissions. For additional security, create a ServiceAccount:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: lacuna-caddy
---
# Add to deployment.yaml:
spec:
  template:
    spec:
      serviceAccountName: lacuna-caddy
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod <pod-name>

# Check events
kubectl get events --field-selector involvedObject.name=<pod-name>

# Common issues:
# - Image pull errors: Check image path and pull secrets
# - Config not found: Ensure config.active.json exists in PVC
# - Volume mount errors: Check PVC status
```

### Service Not Reachable

```bash
# Check service endpoints
kubectl get endpoints lacuna-caddy

# Check service details
kubectl describe svc lacuna-caddy

# Test from inside cluster
kubectl run curl-test --image=curlimages/curl -it --rm -- sh
# curl http://lacuna-caddy.lacuna.svc.cluster.local
```

### Configuration Issues

```bash
# Validate config syntax
kubectl exec <pod-name> -- caddy validate --config /srv/lacuna/config/config.active.json

# Check Caddy logs for errors
kubectl logs <pod-name> | grep -i error
```

## Production Checklist

- [ ] Update image tag to specific version (not `latest`)
- [ ] Configure resource limits based on load testing
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Configure log aggregation (Loki, ELK, etc.)
- [ ] Enable auto-scaling (HPA)
- [ ] Set up alerts for pod failures, high CPU/memory
- [ ] Configure backup for config PVC
- [ ] Set up DNS records pointing to LoadBalancer IP
- [ ] Configure TLS/ACME settings in Caddy config
- [ ] Test rollback procedures
- [ ] Document runbooks for common issues
- [ ] Set up CI/CD pipeline for automated deployments
- [ ] Configure network policies for security
- [ ] Review and harden RBAC permissions
- [ ] Enable pod security policies/standards

## Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Caddy Documentation](https://caddyserver.com/docs/)
- [Lacuna AGENTS.md](../../AGENTS.md) - Project specifications
- [Lacuna PROJECT_STRUCTURE.md](../../PROJECT_STRUCTURE.md) - Architecture overview
