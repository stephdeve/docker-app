# 🐳 Docker & ☸️ Kubernetes — Guide Pratique Complet

> Projet d'apprentissage progressif des architectures de conteneurisation et DevOps/SRE,
> basé sur le déploiement d'une API Flask à travers huit couches de complexité croissante.

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis & Installation](#prérequis--installation)
3. [L'application commune](#lapplication-commune)
4. [Projet 1 — Docker](#projet-1--docker-)
5. [Projet 2 — Kubernetes](#projet-2--kubernetes-)
6. [Projet 3 — Monitoring avec Prometheus & Grafana](#projet-3--monitoring-avec-prometheus--grafana-)
7. [Projet 4 — CI/CD avec GitHub Actions](#projet-4--cicd-avec-github-actions-)
8. [Projet 5 — Variables d'environnement, ConfigMaps, Secrets & PostgreSQL](#projet-5--variables-denvironnement-configmaps-secrets--postgresql-)
9. [Projet 6 — Ingress Controller & HTTPS](#projet-6--ingress-controller--https-)
10. [Projet 7 — Helm](#projet-7--helm-)
11. [Projet 8 — CI/CD réel sur GKE](#projet-8--cicd-réel-sur-gke-)
12. [Problèmes rencontrés & Solutions](#problèmes-rencontrés--solutions)
13. [Comparaison Docker vs Kubernetes](#comparaison-docker-vs-kubernetes)
14. [Glossaire](#glossaire)

---

## Vue d'ensemble

Ce projet explore les grandes pratiques DevOps/SRE en déployant la **même application** (une API Python/Flask) à travers huit couches successives : conteneurisation Docker, orchestration Kubernetes, monitoring Prometheus/Grafana, CI/CD GitHub Actions, gestion des secrets, exposition sécurisée via Ingress HTTPS, packaging avec Helm, et déploiement cloud réel sur GKE.

```
ARCHITECTURE COMPLÈTE
──────────────────────────────────────────────────────────────
git push
  ↓
GitHub Actions
  ├── pytest (4 tests)
  ├── docker build + push → ghcr.io/stephdeve/docker-app/mon-api:sha-xxx
  └── helm upgrade → cluster Kubernetes (Minikube / GKE / Oracle / k3s)
          ↓
    Nginx Ingress (TLS)
          ├── /api/*     → Pods Flask × 3
          │               (ConfigMap + Secret)
          │                    ↓
          │               postgres-service
          │                    ↓
          │               Pod PostgreSQL
          └── /grafana/* → Pod Grafana
                               ↑
                           Prometheus (scrape /metrics)
```

---

## Prérequis & Installation

| Technologie | Rôle | Version testée |
|-------------|------|----------------|
| Python | Langage de l'API | 3.11 |
| Flask | Framework web | 3.1.0 |
| psycopg2-binary | Client PostgreSQL | 2.9.9 |
| prometheus-flask-exporter | Métriques | 0.23.1 |
| pytest | Tests automatisés | 8.x |
| Docker | Conteneurisation | 27.x |
| Docker Compose | Orchestration locale | 2.x |
| PostgreSQL | Base de données | 16-alpine |
| Minikube | Cluster Kubernetes local | 1.35.x |
| kubectl | CLI Kubernetes | 1.34.x |
| Helm | Gestionnaire de paquets K8s | 3.20.0 |
| Prometheus | Collecte de métriques | latest |
| Grafana | Visualisation | latest |
| Nginx Ingress | Reverse proxy + TLS | 1.14.x |
| GitHub Actions | CI/CD | — |

```bash
# Docker
sudo apt update && sudo apt install docker.io -y
sudo systemctl enable docker && sudo systemctl start docker
sudo usermod -aG docker $USER && newgrp docker

# Minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
minikube start

# kubectl
sudo snap install kubectl --classic

# Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

---

## L'application commune

### Structure du projet

```
docker-app/
├── app.py                        # API Flask complète
├── requirements.txt
├── test_app.py                   # Tests pytest
├── Dockerfile
├── docker-compose.yml            # Stack locale complète
├── prometheus.yml
├── configmap.yaml                # Objets K8s standalone
├── secret.yaml
├── deployment.yaml
├── service.yaml
├── postgres-deployment.yaml
├── ingress.yaml
├── mon-api-chart/                # Chart Helm (remplace tous les YAML standalone)
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── configmap.yaml
│       ├── secret.yaml
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       └── postgres.yaml
├── .github/
│   └── workflows/
│       └── ci-cd.yml
└── README.md
```

### app.py

```python
from flask import Flask, jsonify
import socket, os
import psycopg2
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
metrics = PrometheusMetrics(app)

hello_counter = metrics.counter(
    'hello_requests_total', 'Nombre total de requêtes sur /',
    labels={'pod': lambda: socket.gethostname()}
)

APP_ENV     = os.environ.get("APP_ENV", "development")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = os.environ.get("DB_PORT", "5432")
DB_NAME     = os.environ.get("DB_NAME", "appdb")
DB_USER     = os.environ.get("DB_USER", "appuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

@app.route("/")
@hello_counter
def hello():
    return f"Bonjour depuis {socket.gethostname()} [env: {APP_ENV}, v{APP_VERSION}]\n"

@app.route("/health")
def health():
    return {"status": "ok", "pod": socket.gethostname(), "env": APP_ENV}

@app.route("/config")
def config():
    return jsonify({
        "app_env": APP_ENV, "app_version": APP_VERSION,
        "db_host": DB_HOST, "db_port": DB_PORT,
        "db_name": DB_NAME, "db_user": DB_USER,
        "db_password": "***" if DB_PASSWORD else "NOT SET"
    })

@app.route("/db-test")
def db_test():
    if not DB_PASSWORD:
        return jsonify({"error": "DB_PASSWORD not configured"}), 500
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD, connect_timeout=3
        )
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        cur.close(); conn.close()
        return jsonify({"status": "connected", "postgres_version": version})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

### requirements.txt

```
Flask==3.1.0
prometheus-flask-exporter==0.23.1
psycopg2-binary==2.9.9
pytest==8.3.5
```

---

## Projet 1 — Docker 🐳

```dockerfile
FROM python:3.11-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout 100
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
```

```bash
docker build --network=host -t mon-api:v1 .
docker run -d -p 8081:5000 -e APP_ENV=production --name api1 mon-api:v1
docker ps && docker logs -f api1 && docker stats
```

---

## Projet 2 — Kubernetes ☸️

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mon-api-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mon-api
  template:
    metadata:
      labels:
        app: mon-api
    spec:
      containers:
      - name: mon-api
        image: mon-api:v1
        imagePullPolicy: Never
        ports:
        - containerPort: 5000
```

```bash
minikube image load mon-api:v1
kubectl apply -f deployment.yaml -f service.yaml
kubectl get pods -w
kubectl delete pod <nom>           # Résilience — Pod recréé automatiquement
kubectl scale deployment mon-api-deployment --replicas=5
```

---

## Projet 3 — Monitoring avec Prometheus & Grafana 📊

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'mon-api'
    static_configs:
      - targets: ['api1:5000', 'api2:5000', 'api3:5000']
```

```promql
rate(hello_requests_total[1m])
rate(flask_http_request_duration_seconds_sum[1m])
  / rate(flask_http_request_duration_seconds_count[1m]) * 1000
```

Grafana datasource : `http://prometheus:9090` (nom de service Docker, jamais localhost).

---

## Projet 4 — CI/CD avec GitHub Actions 🚀

Pipeline initiale — simulation locale du déploiement K8s.

```yaml
name: CI/CD Pipeline
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  IMAGE_NAME: ghcr.io/${{ github.repository }}/mon-api

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest test_app.py -v
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest,enable={{is_default_branch}}
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}

  cd:
    runs-on: ubuntu-latest
    needs: ci
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-kubectl@v3
      - run: |
          echo "✅ Image : ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}"
          echo "helm upgrade mon-app ./mon-api-chart --set app.image.tag=sha-${{ github.sha }}"
```

---

## Projet 5 — Variables d'environnement, ConfigMaps, Secrets & PostgreSQL 🗄️

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mon-api-config
data:
  APP_ENV: "production"
  APP_VERSION: "2.0.0"
  DB_HOST: "postgres-service"
  DB_PORT: "5432"
  DB_NAME: "appdb"
  DB_USER: "appuser"
```

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: mon-api-secret
type: Opaque
data:
  DB_PASSWORD: ZGV2c2VjcmV0MTIz   # echo -n "devsecret123" | base64
```

```bash
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f deployment.yaml -f service.yaml
kubectl port-forward service/mon-api-service 8080:5000
curl http://localhost:8080/db-test
```

---

## Projet 6 — Ingress Controller & HTTPS 🔒

```bash
minikube addons enable ingress
echo "$(minikube ip) monapp.local" | sudo tee -a /etc/hosts
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt -subj "/CN=monapp.local/O=DevOps Learning"
kubectl create secret tls monapp-tls --key tls.key --cert tls.crt
kubectl apply -f ingress.yaml
curl -k https://monapp.local/api/
```

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mon-api-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  tls:
  - hosts:
    - monapp.local
    secretName: monapp-tls
  rules:
  - host: monapp.local
    http:
      paths:
      - path: /api(/|$)(.*)
        pathType: Prefix
        backend:
          service:
            name: mon-api-service
            port:
              number: 5000
```

---

## Projet 7 — Helm 🎡

```
mon-api-chart/
├── Chart.yaml
├── values.yaml          ← toutes les valeurs paramétrables
└── templates/
    ├── configmap.yaml   ← {{ .Values.app.env }}
    ├── secret.yaml      ← {{ .Values.database.password | b64enc }}
    ├── deployment.yaml  ← {{ .Values.app.replicaCount }}
    ├── service.yaml
    ├── ingress.yaml     ← {{- if .Values.ingress.enabled }}
    └── postgres.yaml    ← {{- if .Values.postgresql.enabled }}
```

```bash
helm lint mon-api-chart/
helm template mon-api-chart/ --set database.password=secret123
helm install mon-app ./mon-api-chart --set database.password=secret123
helm list && helm history mon-app
helm upgrade mon-app ./mon-api-chart --set app.replicaCount=5 --set database.password=secret123
helm rollback mon-app 1
helm uninstall mon-app
```

Plusieurs environnements :

```bash
helm install mon-app-dev  ./mon-api-chart -f values-dev.yaml  --set database.password=devpass
helm install mon-app-prod ./mon-api-chart -f values-prod.yaml --set database.password=prodpass
```

---

## Projet 8 — CI/CD réel sur GKE ☁️

### Architecture du déploiement cloud

```
git push origin main
        ↓
GitHub Actions
        ├── Job CI : pytest → build → push ghcr.io:sha-xxx
        └── Job CD : Workload Identity → kubectl GKE → helm upgrade
                                                            ↓
                                              GKE Rolling Update
                                          (zero downtime deployment)
```

### Pourquoi Workload Identity Federation plutôt qu'une clé JSON

La plupart des tutoriels te disent de créer un Service Account, de télécharger une clé JSON, et de la coller dans les secrets GitHub. C'est une **mauvaise pratique** : une clé JSON qui fuite donne un accès permanent à ton cluster jusqu'à révocation manuelle, et elle ne tourne jamais automatiquement.

**Workload Identity Federation** est la solution moderne adoptée par toutes les grandes équipes DevOps. GitHub Actions prouve son identité à Google via un token OIDC éphémère valable quelques minutes — aucune clé long-terme n'est jamais créée. Google vérifie que la requête vient exactement de ton dépôt GitHub `stephdeve/docker-app`, et accorde un accès temporaire le temps du déploiement.

```
GitHub Actions                    Google Cloud
─────────────────                 ─────────────────────────────────
Job CD démarre
  ↓
Demande un token OIDC   ────────→ Vérifie : "vient-il de stephdeve/docker-app ?"
  ↓                               Oui → accorde impersonation temporaire
Reçoit token (5 min)   ←────────
  ↓
helm upgrade → GKE      ────────→ Cluster accepte (token valide)
  ↓
Job CD termine
Token expiré automatiquement ✅
```

### Prérequis

```bash
# Installer gcloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud auth login
gcloud config set project TON_PROJECT_ID

# Activer les APIs nécessaires
gcloud services enable container.googleapis.com
gcloud services enable iamcredentials.googleapis.com
```

### Créer le cluster GKE

```bash
# Cluster zonal — le plus économique (free tier GKE disponible)
gcloud container clusters create docker-app-cluster \
  --zone europe-west1-b \
  --num-nodes 2 \
  --machine-type e2-small \
  --no-enable-autoupgrade

# Configurer kubectl pour pointer vers GKE
gcloud container clusters get-credentials docker-app-cluster \
  --zone europe-west1-b

# Vérifier
kubectl get nodes
# NAME                                           STATUS   ROLES    AGE
# gke-docker-app-cluster-default-pool-xxx-xxx   Ready    <none>   2m
# gke-docker-app-cluster-default-pool-xxx-yyy   Ready    <none>   2m
```

### Configurer Workload Identity Federation

```bash
export PROJECT_ID=$(gcloud config get-value project)
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export GITHUB_REPO="stephdeve/docker-app"   # Remplace avec ton dépôt

# 1. Créer le Workload Identity Pool
gcloud iam workload-identity-pools create "github-pool" \
  --project=$PROJECT_ID \
  --location="global" \
  --display-name="GitHub Actions Pool"

# 2. Créer le Provider OIDC
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project=$PROJECT_ID \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"

# 3. Créer le Service Account
gcloud iam service-accounts create github-actions-sa \
  --project=$PROJECT_ID \
  --display-name="GitHub Actions Service Account"

# 4. Permissions sur GKE
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/container.developer"

# 5. Autoriser le Pool à impersonate le Service Account
gcloud iam service-accounts add-iam-policy-binding \
  "github-actions-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/$GITHUB_REPO"

# 6. Récupérer le Provider ID (à stocker dans les secrets GitHub)
gcloud iam workload-identity-pools providers describe github-provider \
  --project=$PROJECT_ID \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --format="value(name)"
# → projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

### Secrets GitHub à configurer

Dans **Settings → Secrets and variables → Actions** de ton dépôt :

| Nom du secret | Valeur |
|---|---|
| `GCP_PROJECT_ID` | `docker-app-devops` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/123.../providers/github-provider` |
| `GCP_SERVICE_ACCOUNT` | `github-actions-sa@docker-app-devops.iam.gserviceaccount.com` |
| `GKE_CLUSTER_NAME` | `docker-app-cluster` |
| `GKE_CLUSTER_ZONE` | `europe-west1-b` |
| `DB_PASSWORD` | `un-mot-de-passe-fort` |

### Le workflow CI/CD complet pour GKE

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline — GKE Production

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  IMAGE_NAME: ghcr.io/${{ github.repository }}/mon-api

# Permissions nécessaires pour Workload Identity Federation
permissions:
  contents: read
  id-token: write    # Permet de demander un token OIDC à Google
  packages: write    # Permet de pusher sur ghcr.io

jobs:
  ci:
    name: Test & Build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest test_app.py -v
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest,enable={{is_default_branch}}
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}

  cd:
    name: Deploy to GKE
    runs-on: ubuntu-latest
    needs: ci
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment: production

    steps:
      - uses: actions/checkout@v4

      # Authentification sans clé JSON via Workload Identity Federation
      - name: Authentifier vers Google Cloud
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      # Configure kubectl pour pointer vers le cluster GKE
      - name: Configurer kubectl vers GKE
        uses: google-github-actions/get-gke-credentials@v2
        with:
          cluster_name: ${{ secrets.GKE_CLUSTER_NAME }}
          location: ${{ secrets.GKE_CLUSTER_ZONE }}
          project_id: ${{ secrets.GCP_PROJECT_ID }}

      - name: Installer Helm
        uses: azure/setup-helm@v4

      # Créer le secret ghcr.io si nécessaire (idempotent)
      - name: Configurer le pull secret ghcr.io
        run: |
          kubectl create secret docker-registry ghcr-secret \
            --docker-server=ghcr.io \
            --docker-username=${{ github.actor }} \
            --docker-password=${{ secrets.GITHUB_TOKEN }} \
            --dry-run=client -o yaml | kubectl apply -f -

      # helm upgrade --install = crée si n'existe pas, met à jour sinon (idempotent)
      # --atomic = rollback automatique si le déploiement échoue
      - name: Déployer avec Helm
        run: |
          helm upgrade --install mon-app ./mon-api-chart \
            --set app.image.repository=ghcr.io/${{ github.repository }}/mon-api \
            --set app.image.tag=sha-${{ github.sha }} \
            --set app.image.pullPolicy=Always \
            --set database.password=${{ secrets.DB_PASSWORD }} \
            --set ingress.enabled=false \
            --atomic \
            --timeout 5m

      - name: Vérifier le déploiement
        run: |
          kubectl rollout status deployment/mon-app-deployment --timeout=120s
          echo " Déployé : ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}"
          kubectl get pods
```

### Le rolling update — zero downtime

La commande `helm upgrade --atomic` déclenche un **rolling update** dans Kubernetes : les nouveaux pods sont créés et passent en `Running` avant que les anciens soient supprimés. Aucune requête n'est perdue pendant la mise à jour.

```bash
# Observer le rolling update en temps réel depuis ta machine
kubectl get pods -w

# Tu verras :
# mon-app-deployment-OLD-xxx   Running   → Terminating
# mon-app-deployment-NEW-yyy   Pending   → ContainerCreating → Running
```

### Accéder à l'application sur GKE

```bash
# Sur GKE, utiliser un LoadBalancer pour obtenir une IP publique
kubectl patch service mon-app-service -p '{"spec":{"type":"LoadBalancer"}}'

# Attendre l'IP publique (1-2 minutes)
kubectl get service mon-app-service -w
# EXTERNAL-IP : 34.78.xxx.xxx

curl http://34.78.xxx.xxx:5000/health
```

### Nettoyage GKE — éviter les frais

```bash
# Supprimer le cluster
gcloud container clusters delete docker-app-cluster --zone europe-west1-b

# OU mettre à 0 nœuds (cluster reste, VMs s'arrêtent)
gcloud container clusters resize docker-app-cluster \
  --zone europe-west1-b --num-nodes 0
```

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry.k8s.io: i/o timeout` dans les conteneurs

Problème DNS/proxy réseau — les conteneurs Minikube/kind ne peuvent pas accéder à internet.

```bash
docker pull <image>
docker save <image> | docker exec -i minikube \
  ctr --namespace=k8s.io images import --all-platforms=false -
docker exec minikube crictl images | grep <nom>
```

### 2. `dial tcp 192.168.49.2:2376: connect: no route to host`

```bash
eval $(minikube docker-env --unset)
```

### 3. `ErrImageNeverPull`

```bash
minikube image load mon-api:v1
```

### 4. `ErrImagePull` / `ImagePullBackOff` sur les addons

```bash
docker pull <image>
docker save <image> | docker exec -i minikube \
  ctr --namespace=k8s.io images import --all-platforms=false -
kubectl delete pods -n ingress-nginx --all
```

### 5. Grafana ne se connecte pas à Prometheus

Utiliser `http://prometheus:9090` — jamais `http://localhost:9090`.

### 6. `failed calling webhook validate.nginx.ingress.kubernetes.io`

```bash
kubectl delete validatingwebhookconfiguration ingress-nginx-admission
```

### 7. `helm install` échoue — release en état `failed`

```bash
helm uninstall mon-app
helm install mon-app ./mon-api-chart --set database.password=secret123
```

### 8. Les Pods API démarrent avant PostgreSQL

Utiliser `depends_on` avec `condition: service_healthy` dans Docker Compose et un `healthcheck` avec `pg_isready`.

### 9. `ErrImagePull` sur GKE — image ghcr.io privée

```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=stephdeve \
  --docker-password=TON_GITHUB_TOKEN
# Ajouter imagePullSecrets dans le Deployment
```

### 10. kind vs Minikube

Kind est plus léger mais suppose un accès internet fluide. Minikube gère mieux les environnements avec restrictions réseau.

---

## Comparaison Docker vs Kubernetes

| Aspect | Docker | Kubernetes |
|--------|--------|------------|
| **Complexité** | Simple | Complexe mais puissant |
| **Scaling** | Manuel | Automatique |
| **Résilience** | Aucune | Controller-Manager recrée les Pods |
| **Config & Secrets** | `-e` ou `.env` | ConfigMap + Secret |
| **Exposition** | Port mapping | Service + Ingress + TLS |
| **Packaging** | docker-compose.yml | Helm chart |
| **Déploiement** | `docker run` | `helm upgrade --atomic` |
| **Mise à jour** | Arrêt + redémarrage | Rolling update (zero downtime) |
| **Philosophie** | **Impératif** | **Déclaratif** |

---

## Glossaire

| Terme | Définition |
|-------|------------|
| **Image** | Template immuable pour créer des conteneurs. |
| **Conteneur** | Instance en cours d'exécution d'une image. |
| **Dockerfile** | Recette pour construire une image instruction par instruction. |
| **Layer** | Couche immuable mise en cache créée par chaque instruction Dockerfile. |
| **Registry** | Stockage d'images Docker (Docker Hub, ghcr.io...). |
| **Pod** | Unité de base Kubernetes — un ou plusieurs conteneurs. |
| **Deployment** | Ressource K8s gérant la création, mise à jour et résilience des Pods. |
| **Service** | Expose des Pods avec une adresse stable et fait du load balancing. |
| **ClusterIP** | Service accessible uniquement à l'intérieur du cluster. |
| **NodePort** | Service exposé sur un port fixe de chaque nœud. |
| **LoadBalancer** | Service qui provisionne une IP publique via le cloud (GKE, EKS, AKS). |
| **Ingress** | Règles de routage HTTP/HTTPS vers les Services. |
| **Ingress Controller** | Reverse proxy (Nginx) qui implémente les règles Ingress. |
| **TLS Termination** | Déchiffrement du trafic HTTPS à l'entrée du cluster. |
| **cert-manager** | Automatise la gestion des certificats TLS (Let's Encrypt). |
| **ConfigMap** | Config non sensible stockée en clair dans Kubernetes. |
| **Secret** | Données sensibles encodées en base64 dans Kubernetes. |
| **envFrom** | Injecte toutes les clés d'un ConfigMap ou Secret comme variables d'env. |
| **Helm** | Gestionnaire de paquets Kubernetes. |
| **Chart** | Package Helm — templates + valeurs par défaut d'une application. |
| **Release** | Instance déployée d'un chart Helm (`helm install mon-app`). |
| **values.yaml** | Fichier central des valeurs par défaut d'un chart Helm. |
| **helm upgrade --atomic** | Déploie et rollback automatiquement si le déploiement échoue. |
| **Rolling Update** | Mise à jour progressive des Pods — zero downtime. |
| **GKE** | Google Kubernetes Engine — cluster Kubernetes managé par Google Cloud. |
| **Workload Identity Federation** | Authentification sans clé JSON via tokens OIDC éphémères. |
| **OIDC** | OpenID Connect — protocole d'identité utilisé par Workload Identity. |
| **Service Account** | Identité GCP utilisée par GitHub Actions pour déployer sur GKE. |
| **imagePullSecrets** | Secret K8s contenant les credentials pour pull une image privée. |
| **Master Node** | Cerveau du cluster — API Server, Scheduler, Controller-Manager, etcd. |
| **Worker Node** | Machine qui exécute les Pods. |
| **etcd** | Base de données clé-valeur de l'état du cluster. |
| **Controller-Manager** | Maintient l'état réel = état désiré en permanence. |
| **Prometheus** | Collecte les métriques via scraping (pull). |
| **Grafana** | Visualisation des métriques avec dashboards interactifs. |
| **PromQL** | Langage de requête Prometheus. |
| **rate()** | Calcule le taux de variation d'un Counter par seconde. |
| **CI** | Continuous Integration — tests et builds automatiques à chaque push. |
| **CD** | Continuous Deployment — déploiement automatique si CI réussit. |
| **GitHub Actions** | Plateforme CI/CD intégrée à GitHub. |
| **ghcr.io** | GitHub Container Registry. |
| **SHA du commit** | Tag unique d'une image pour garantir la traçabilité en production. |
| **kubeconfig** | Fichier de configuration kubectl avec adresse cluster et credentials. |
| **12-Factor App** | Méthodologie de référence pour les applications cloud-native. |
| **base64** | Encodage (pas chiffrement !) utilisé pour les valeurs de Secret K8s. |
| **healthcheck** | Vérification périodique qu'un service est prêt. |
| **port-forward** | Tunnel temporaire vers un Pod ou Service Kubernetes. |

---

*Projet réalisé sur Ubuntu 24 — Docker 27.x — Minikube 1.35.x — kubectl 1.34.x — Helm 3.20.0 — PostgreSQL 16 — Prometheus latest — Grafana latest — Nginx Ingress 1.14.x — GitHub Actions — GKE*