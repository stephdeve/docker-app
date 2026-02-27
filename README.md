# 🐳 Docker & ☸️ Kubernetes — Guide Pratique Complet

> Projet d'apprentissage progressif des architectures de conteneurisation et DevOps/SRE,
> basé sur le déploiement d'une API Flask à travers six couches de complexité croissante.

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
10. [Problèmes rencontrés & Solutions](#problèmes-rencontrés--solutions)
11. [Comparaison Docker vs Kubernetes](#comparaison-docker-vs-kubernetes)
12. [Glossaire](#glossaire)

---

## Vue d'ensemble

Ce projet explore les grandes pratiques DevOps/SRE en déployant la **même application** (une API Python/Flask) à travers six couches successives : conteneurisation Docker, orchestration Kubernetes, monitoring Prometheus/Grafana, CI/CD GitHub Actions, gestion des secrets, et exposition sécurisée via Ingress HTTPS.

```
ARCHITECTURE COMPLÈTE
──────────────────────────────────────────────────────────────
Internet
    ↓
https://monapp.local (port 443)
    ↓
Nginx Ingress Controller (terminaison TLS)
    ├── /api/*      → mon-api-service (ClusterIP)
    │                      ↓
    │               Pods Flask × 3
    │               (ConfigMap + Secret montés)
    │                      ↓
    │               postgres-service (ClusterIP)
    │                      ↓
    │               Pod PostgreSQL
    │
    └── /grafana/*  → grafana-service
                           ↓
                       Pod Grafana
                           ↑
                       Prometheus
                       (scrape /metrics)

CI/CD
──────────────────────────────────────────────────────────────
git push → Tests → Build → Push ghcr.io → kubectl deploy
```

---

## Prérequis & Installation

### Technologies utilisées

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
| Prometheus | Collecte de métriques | latest |
| Grafana | Visualisation | latest |
| Nginx Ingress | Reverse proxy + TLS | 1.14.x |
| GitHub Actions | CI/CD | — |

### Installation

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
kubectl get nodes
```

---

## L'application commune

### Structure du projet

```
docker-app/
├── app.py                        # API Flask complète
├── requirements.txt              # Dépendances Python
├── test_app.py                   # Tests pytest
├── Dockerfile                    # Build de l'image
├── docker-compose.yml            # Stack locale complète
├── prometheus.yml                # Config Prometheus
├── configmap.yaml                # Config non sensible K8s
├── secret.yaml                   # Secrets K8s (base64)
├── deployment.yaml               # Pods API K8s
├── service.yaml                  # Service K8s
├── postgres-deployment.yaml      # PostgreSQL K8s
├── ingress.yaml                  # Ingress + TLS K8s
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

### Dockerfile

```dockerfile
FROM python:3.11-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout 100
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
```

L'ordre des instructions optimise le cache Docker : `requirements.txt` avant `app.py` évite de réinstaller les dépendances à chaque modification du code.

### Commandes essentielles

```bash
docker build --network=host -t mon-api:v1 .
docker run -d -p 8081:5000 -e APP_ENV=production --name api1 mon-api:v1
docker ps && docker logs -f api1 && docker stats
docker exec -it api1 sh
docker stop api1 && docker rm api1
```

---

## Projet 2 — Kubernetes ☸️

### deployment.yaml et service.yaml

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

```yaml
# service.yaml (NodePort pour accès direct sans Ingress)
apiVersion: v1
kind: Service
metadata:
  name: mon-api-service
spec:
  type: NodePort
  selector:
    app: mon-api
  ports:
  - port: 5000
    targetPort: 5000
    nodePort: 30080
```

### Commandes essentielles

```bash
minikube image load mon-api:v1
kubectl apply -f deployment.yaml -f service.yaml
kubectl get pods -w
kubectl delete pod <nom>           # Test résilience — Pod recréé automatiquement
kubectl scale deployment mon-api-deployment --replicas=5
minikube service mon-api-service --url
minikube dashboard
```

---

## Projet 3 — Monitoring avec Prometheus & Grafana 📊

### prometheus.yml

```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'mon-api'
    static_configs:
      - targets: ['api1:5000', 'api2:5000', 'api3:5000']
```

### Requêtes PromQL essentielles

```promql
rate(hello_requests_total[1m])          # Requêtes/seconde par pod
hello_requests_total                    # Total depuis démarrage
rate(flask_http_request_duration_seconds_sum[1m])
  / rate(flask_http_request_duration_seconds_count[1m]) * 1000
```

Grafana datasource URL : `http://prometheus:9090` (nom de service Docker, pas localhost).

---

## Projet 4 — CI/CD avec GitHub Actions 🚀

### .github/workflows/ci-cd.yml

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
          echo "✅ ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}"
          echo "kubectl set image deployment/mon-api-deployment mon-api=..."
          echo "kubectl rollout status deployment/mon-api-deployment --timeout=120s"
```

---

## Projet 5 — Variables d'environnement, ConfigMaps, Secrets & PostgreSQL 🗄️

### Le principe 12-Factor App

Toute configuration doit être lue depuis les **variables d'environnement** — jamais hardcodée dans le code. Kubernetes formalise ça avec deux objets : **ConfigMap** pour la config non sensible, **Secret** pour les données sensibles (encodées en base64, jamais chiffrées — utiliser Vault ou un secrets manager cloud en production réelle).

### configmap.yaml

```yaml
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

### secret.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mon-api-secret
type: Opaque
data:
  DB_PASSWORD: ZGV2c2VjcmV0MTIz   # echo -n "devsecret123" | base64
```

### deployment.yaml avec envFrom

```yaml
spec:
  containers:
  - name: mon-api
    image: mon-api:v1
    imagePullPolicy: Never
    ports:
    - containerPort: 5000
    envFrom:
    - configMapRef:
        name: mon-api-config    # Toutes les clés → variables d'env
    - secretRef:
        name: mon-api-secret    # Idem pour les secrets
```

### postgres-deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:16-alpine
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_DB
          value: "appdb"
        - name: POSTGRES_USER
          value: "appuser"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: mon-api-secret
              key: DB_PASSWORD

---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
spec:
  type: ClusterIP
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

### docker-compose.yml avec PostgreSQL

```yaml
version: "3.8"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: devsecret123
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser -d appdb"]
      interval: 5s
      timeout: 3s
      retries: 5

  api1:
    build: .
    ports:
      - "8081:5000"
    environment:
      APP_ENV: development
      APP_VERSION: "2.0.0"
      DB_HOST: postgres
      DB_PORT: "5432"
      DB_NAME: appdb
      DB_USER: appuser
      DB_PASSWORD: devsecret123
    depends_on:
      postgres:
        condition: service_healthy

  api2:
    build: .
    ports:
      - "8082:5000"
    environment:
      APP_ENV: development
      APP_VERSION: "2.0.0"
      DB_HOST: postgres
      DB_PORT: "5432"
      DB_NAME: appdb
      DB_USER: appuser
      DB_PASSWORD: devsecret123
    depends_on:
      postgres:
        condition: service_healthy

  api3:
    build: .
    ports:
      - "8083:5000"
    environment:
      APP_ENV: development
      APP_VERSION: "2.0.0"
      DB_HOST: postgres
      DB_PORT: "5432"
      DB_NAME: appdb
      DB_USER: appuser
      DB_PASSWORD: devsecret123
    depends_on:
      postgres:
        condition: service_healthy

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command: ['--config.file=/etc/prometheus/prometheus.yml']
    depends_on: [api1, api2, api3]

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
    depends_on: [prometheus]

volumes:
  postgres-data:
  grafana-data:
```

### Déploiement dans le bon ordre

```bash
# Toujours dans cet ordre — les Pods ont besoin de la config au démarrage
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Inspecter sans exposer les valeurs sensibles
kubectl describe configmap mon-api-config
kubectl describe secret mon-api-secret

# Tester la connexion DB
kubectl port-forward service/mon-api-service 8080:5000
curl http://localhost:8080/db-test
# → {"status": "connected", "postgres_version": "PostgreSQL 16.x..."}

# Encoder/décoder base64
echo -n "monmotdepasse" | base64
echo "bW9ubW90ZGVwYXNzZQ==" | base64 --decode
```

---

## Projet 6 — Ingress Controller & HTTPS 🔒

### Pourquoi l'Ingress est indispensable en production

Sans Ingress, chaque service Kubernetes doit être exposé sur un NodePort avec une URL comme `http://192.168.49.2:30080` — peu utilisable et impossible à sécuriser avec HTTPS. L'Ingress Controller (Nginx) est un **reverse proxy** qui tourne dans le cluster, reçoit tout le trafic sur les ports 80/443, et le route vers le bon Service selon les règles déclarées.

```
AVANT (NodePort)                    APRÈS (Ingress)
──────────────────────────          ──────────────────────────────────
IP:30080 → API                      https://monapp.local
IP:30090 → Grafana                      ├── /api/*    → API
IP:30100 → Autre service                └── /grafana/* → Grafana
(un port par service)               (un seul point d'entrée HTTPS)
```

### Activation dans Minikube

```bash
# Minikube intègre Nginx Ingress comme addon — une seule commande
minikube addons enable ingress

# Vérifier que le controller est Running
kubectl get pods -n ingress-nginx
# ingress-nginx-controller-xxxx   1/1   Running   ✅

# Si les images ne peuvent pas être téléchargées (problème DNS réseau),
# les précharger manuellement — voir section Problèmes & Solutions
```

### Configurer un domaine local

```bash
# Récupérer l'IP du cluster
minikube ip   # ex: 192.168.49.2

# Ajouter le domaine dans /etc/hosts (simule un vrai DNS)
echo "$(minikube ip) monapp.local" | sudo tee -a /etc/hosts
```

### Créer un certificat TLS auto-signé

```bash
# Générer clé privée + certificat auto-signé (valable 365 jours)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key \
  -out tls.crt \
  -subj "/CN=monapp.local/O=DevOps Learning"

# Créer le Secret TLS dans Kubernetes
kubectl create secret tls monapp-tls \
  --key tls.key \
  --cert tls.crt

# En production : utiliser cert-manager + Let's Encrypt (certificats gratuits et automatiques)
```

### ingress.yaml

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mon-api-ingress
  annotations:
    # Redirection automatique HTTP → HTTPS
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    # Réécriture : /api/health devient /health pour le backend
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  tls:
  - hosts:
    - monapp.local
    secretName: monapp-tls    # Secret TLS créé ci-dessus

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

      - path: /grafana(/|$)(.*)
        pathType: Prefix
        backend:
          service:
            name: grafana
            port:
              number: 3000
```

### service.yaml mis à jour (ClusterIP avec Ingress)

```yaml
# Quand on utilise un Ingress, les Services n'ont plus besoin d'être NodePort
# L'Ingress gère l'accès externe — les Services redeviennent internes
apiVersion: v1
kind: Service
metadata:
  name: mon-api-service
spec:
  type: ClusterIP    # Plus de NodePort
  selector:
    app: mon-api
  ports:
  - port: 5000
    targetPort: 5000
```

### Déploiement et test

```bash
kubectl apply -f service.yaml     # ClusterIP maintenant
kubectl apply -f ingress.yaml

# Vérifier l'Ingress
kubectl get ingress
# NAME               HOSTS          ADDRESS          PORTS
# mon-api-ingress    monapp.local   192.168.49.2     80, 443

# HTTP doit rediriger vers HTTPS automatiquement
curl -v http://monapp.local/api/
# < HTTP/1.1 308 Permanent Redirect
# < Location: https://monapp.local/api/

# HTTPS — -k ignore l'avertissement du certificat auto-signé
curl -k https://monapp.local/api/
curl -k https://monapp.local/api/health
curl -k https://monapp.local/api/db-test
```

### Architecture finale avec Ingress

```
curl/Browser
      ↓
https://monapp.local:443
      ↓
Nginx Ingress Controller
(déchiffre TLS avec le Secret monapp-tls)
      ├── /api/*      → mon-api-service:5000 → Pods Flask
      └── /grafana/*  → grafana:3000 → Pod Grafana
```

### Note sur cert-manager en production

En production, on ne crée jamais un certificat auto-signé manuellement. **cert-manager** est l'outil standard qui automatise complètement la gestion des certificats TLS dans Kubernetes :

```bash
# Installation de cert-manager (gestionnaire de certificats)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

# ClusterIssuer Let's Encrypt (certificats gratuits et automatiques)
# cert-manager renouvelle les certificats automatiquement avant expiration
```

```yaml
# clusterissuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ton@email.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
```

```yaml
# Dans ingress.yaml — annotation pour déclencher la génération automatique du certificat
annotations:
  cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - monapp.com
    secretName: monapp-tls    # cert-manager crée et remplit ce Secret automatiquement
```

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry.k8s.io: i/o timeout` dans les conteneurs

Les conteneurs Docker (Minikube, kind) ne peuvent pas accéder à internet — problème DNS ou réseau proxy.

```bash
# Solution : précharger les images sur la machine hôte puis les injecter
docker pull registry.k8s.io/ingress-nginx/controller:v1.14.3
docker save registry.k8s.io/ingress-nginx/controller:v1.14.3 | \
  docker exec -i minikube ctr --namespace=k8s.io images import --all-platforms=false -

# Forcer imagePullPolicy: Never dans les manifests
sed -i 's/imagePullPolicy: IfNotPresent/imagePullPolicy: Never/g' manifest.yaml
```

### 2. `dial tcp 192.168.49.2:2376: connect: no route to host`

```bash
eval $(minikube docker-env --unset)
```

### 3. `ErrImageNeverPull`

```bash
minikube image load mon-api:v1
kubectl get pods -w
```

### 4. `ErrImagePull` / `ImagePullBackOff` sur les addons Minikube

Les images des addons ne peuvent pas être téléchargées depuis l'intérieur du cluster.

```bash
# Précharger l'image sur la machine hôte
docker pull <image>

# L'importer dans le runtime containerd du nœud Minikube
docker save <image> | docker exec -i minikube \
  ctr --namespace=k8s.io images import --all-platforms=false -

# Vérifier que crictl la voit (vue Kubernetes)
docker exec minikube crictl images | grep <nom>
```

### 5. Grafana ne se connecte pas à Prometheus

Utiliser `http://prometheus:9090` (nom de service Docker) et non `http://localhost:9090`.

### 6. `connection refused localhost:8080` dans GitHub Actions

La VM GitHub n'a pas de cluster Kubernetes. Simuler les commandes kubectl avec `echo` en local, et utiliser un secret `KUBECONFIG` pour un vrai cluster cloud.

### 7. Les Pods API démarrent avant PostgreSQL

Utiliser `depends_on` avec `condition: service_healthy` dans Docker Compose, et un `healthcheck` sur postgres avec `pg_isready`.

### 8. kind vs Minikube — lequel choisir ?

Kind est plus léger mais suppose un accès internet fluide depuis les conteneurs. Minikube est plus adapté aux environnements avec des restrictions réseau grâce à son système d'addons et de préchargement d'images.

---

## Comparaison Docker vs Kubernetes

| Aspect | Docker | Kubernetes |
|--------|--------|------------|
| **Complexité** | Simple | Complexe mais puissant |
| **Scaling** | Manuel | Automatique |
| **Résilience** | Aucune | Controller-Manager recrée les Pods |
| **Config & Secrets** | `-e` ou `.env` | ConfigMap + Secret |
| **Exposition** | Port mapping | Service + Ingress + TLS |
| **Réseau** | Bridge | CNI + DNS interne + Ingress |
| **Philosophie** | **Impératif** | **Déclaratif** |

---

## Glossaire

| Terme | Définition |
|-------|------------|
| **Image** | Template immuable pour créer des conteneurs. Analogue à une classe en POO. |
| **Conteneur** | Instance en cours d'exécution d'une image. |
| **Dockerfile** | Recette pour construire une image instruction par instruction. |
| **Layer** | Couche immuable mise en cache créée par chaque instruction Dockerfile. |
| **Registry** | Stockage d'images Docker (Docker Hub, ghcr.io...). |
| **Pod** | Unité de base Kubernetes — un ou plusieurs conteneurs partageant réseau et stockage. |
| **Deployment** | Ressource K8s gérant la création, mise à jour et résilience des Pods. |
| **Service** | Expose des Pods avec une adresse stable et fait du load balancing. |
| **ClusterIP** | Service accessible uniquement à l'intérieur du cluster. |
| **NodePort** | Service exposé sur un port fixe de chaque nœud (30000-32767). |
| **Ingress** | Règles de routage HTTP/HTTPS vers les Services — gérées par l'Ingress Controller. |
| **Ingress Controller** | Reverse proxy (Nginx) qui implémente les règles Ingress dans le cluster. |
| **TLS Termination** | Déchiffrement du trafic HTTPS à l'entrée du cluster par l'Ingress Controller. |
| **cert-manager** | Outil Kubernetes qui automatise la gestion des certificats TLS (Let's Encrypt). |
| **ConfigMap** | Config non sensible stockée en clair dans Kubernetes. |
| **Secret** | Données sensibles encodées en base64 dans Kubernetes (pas chiffrées !). |
| **envFrom** | Injecte toutes les clés d'un ConfigMap ou Secret comme variables d'environnement. |
| **Master Node** | Cerveau du cluster — API Server, Scheduler, Controller-Manager, etcd. |
| **Worker Node** | Machine qui exécute les Pods. |
| **Kubelet** | Agent sur chaque Worker Node. |
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
| **rewrite-target** | Annotation Nginx Ingress pour réécrire le chemin URL avant de router. |
| **ssl-redirect** | Annotation Nginx Ingress pour forcer la redirection HTTP → HTTPS. |

---

*Projet réalisé sur Ubuntu 24 — Docker 27.x — Minikube 1.35.x — kubectl 1.34.x — PostgreSQL 16 — Prometheus latest — Grafana latest — Nginx Ingress 1.14.x — GitHub Actions*