# Tahseen Checker — OpenTelemetry + Grafana Observability Stack

A distributed async workload instrumented end-to-end with OpenTelemetry, deployed to Kubernetes via ArgoCD and Helm.

---

## Architecture

```
[Web UI] ──────────────────────────────────────────────────────────────────┐
                                                                            │
[Load script] ──► [API (Go)] ──► [Redis (queue + result store)] ──► [Worker (Python)]
                       │                                                    │
                       └──────────────── OTel SDK ──────────────────────────┘
                                              │
                                       OTel Collector
                                              │
                         ┌────────────────────┼────────────────────┐
                         │                    │                    │
                     Prometheus             Tempo                Loki
                         │                    │                    │
                         └────────────── Grafana ─────────────────┘
```

- **API (Go)**: `POST /check` pushes a job to Redis, returns a job ID. `GET /result/{id}` reads the result back.
- **Worker (Python)**: `BRPOP` consumes jobs, runs tajwid rule detection, writes result back to Redis.
- **Redis**: job queue and result store. Also the distributed tracing boundary — trace context is injected into the job payload by the API and extracted by the worker.
- **OTel Collector**: receives OTLP signals from both services, routes traces to Tempo, metrics to Prometheus, logs to Loki.
- **redis-exporter**: exposes Redis metrics (queue depth, memory, ops/sec) to Prometheus.

---

## Repo Structure

```
tahseen-opentelemetry/
├── apps/
│   ├── api/              # Go API — Dockerfile, source
│   ├── worker/           # Python worker — Dockerfile, src/
│   └── web-ui/           # nginx:alpine static UI — Dockerfile, index.html
├── charts/
│   └── tahseen-app/      # Helm chart: api, worker, redis, redis-exporter, web-ui
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
├── observability/
│   ├── otel-collector-config.yaml   # OTel Collector pipeline config
│   ├── prometheus.yaml              # Prometheus scrape config (compose)
│   ├── loki-config.yaml             # Loki config (compose)
│   ├── tempo-config.yaml            # Tempo config (compose)
│   ├── grafana-datasources.yaml     # Grafana datasource provisioning
│   └── values/                      # Helm values overrides for k8s
│       ├── otel-collector-values.yaml
│       ├── prometheus-values.yaml
│       ├── grafana-values.yaml
│       ├── loki-values.yaml
│       └── tempo-values.yaml
├── argocd/
│   ├── root-app.yaml                # App-of-Apps root — apply this once
│   └── apps/
│       ├── tahseen.yaml             # app chart
│       ├── otel-collector.yaml
│       ├── prometheus.yaml
│       ├── grafana.yaml
│       ├── loki.yaml
│       └── tempo.yaml
└── docker-compose.yml               # local dev stack
```

---

## Running Locally

```bash
docker compose up -d
```

Services:
- API: `http://localhost:8080`
- Web UI: `http://localhost:3001`
- Grafana: `http://localhost:3002` (admin/admin)
- Prometheus: `http://localhost:9090`

Send a request:

```bash
JOB_ID=$(curl -s -X POST http://localhost:8080/check \
  -H "Content-Type: application/json" \
  -d '{"text":"وَلَمْ يَكُنْ لَّهٗ كُفُوًا اَحَدٌ"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

curl -s http://localhost:8080/result/$JOB_ID | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])"
```

---

## Deploying to Kubernetes

### 1. Build and push images

```bash
IMAGE_TAG=$(git rev-parse --short HEAD)

docker build -t kandlagifari/tahseen-api:$IMAGE_TAG ./apps/api
docker build -t kandlagifari/tahseen-worker:$IMAGE_TAG ./apps/worker
docker build -t kandlagifari/tahseen-web-ui:$IMAGE_TAG ./apps/web-ui

docker push kandlagifari/tahseen-api:$IMAGE_TAG
docker push kandlagifari/tahseen-worker:$IMAGE_TAG
docker push kandlagifari/tahseen-web-ui:$IMAGE_TAG
```

Update `charts/tahseen-app/values.yaml` with the new tag.

### 2. Create prerequisite ConfigMaps

```bash
kubectl create namespace observability

kubectl create configmap otel-collector-config \
  --from-file=config.yaml=observability/otel-collector-config.yaml \
  -n observability

kubectl create configmap grafana-datasources \
  --from-file=datasources.yaml=observability/grafana-datasources.yaml \
  -n observability
```

### 3. Register repo with ArgoCD and apply root app

```bash
argocd repo add https://github.com/kandlagifari/tahseen-opentelemetry.git \
  --username kandlagifari \
  --password <PAT>

kubectl apply -f argocd/root-app.yaml
```

ArgoCD discovers all child Applications in `argocd/apps/` and syncs them automatically.

### 4. Watch sync progress

```bash
kubectl get applications -n argocd -w
```

### 5. Verify

```bash
kubectl port-forward svc/grafana 3000:80 -n observability &
kubectl port-forward svc/tahseen-api 8080:8080 -n tahseen-app &

curl -s -X POST http://localhost:8080/check \
  -H "Content-Type: application/json" \
  -d '{"text":"قُلْ هُوَ اللَّهُ أَحَدٌ"}'
```

Open Grafana at `http://localhost:3000`, go to Explore → Tempo, confirm the connected two-span trace.

---

## Incident Simulation

Inject a failure by setting `FAULT_MODE=true` on the worker. This causes every job to sleep 2 seconds and raise a `RuntimeError`, simulating a slow or broken downstream dependency:

```bash
kubectl set env deployment/tahseen-worker FAULT_MODE=true -n tahseen-app
```

Diagnose using the signal chain in Grafana: Prometheus p95 spike → exemplar dot → Tempo trace (worker span with `error=true`) → Loki logs (`job failed, error: fault mode enabled`).

Revert:

```bash
kubectl set env deployment/tahseen-worker FAULT_MODE=false -n tahseen-app
```

---

## AWS/EKS Portability

The Helm + ArgoCD setup is cluster-agnostic. On EKS:
- Change `destination.server` in the ArgoCD Application manifests to the EKS cluster endpoint.
- Use ECR instead of Docker Hub: `<account>.dkr.ecr.<region>.amazonaws.com/tahseen-api`.
- Add an `imagePullSecret` referencing ECR credentials if the cluster doesn't use IRSA for ECR access.

Everything else (chart structure, values overrides, App-of-Apps pattern) is unchanged.
