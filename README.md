# 🐳 Docker & ☸️ Kubernetes — Guide Pratique Complet

> Projet d'apprentissage progressif des architectures de conteneurisation et DevOps/SRE,
> basé sur le déploiement d'une API Flask à travers sept couches de complexité croissante.

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
11. [Problèmes rencontrés & Solutions](#problèmes-rencontrés--solutions)
12. [Comparaison Docker vs Kubernetes](#comparaison-docker-vs-kubernetes)
13. [Glossaire](#glossaire)

---

## Vue d'ensemble

Ce projet explore les grandes pratiques DevOps/SRE en déployant la **même application** (une API Python/Flask) à travers sept couches successives : conteneurisation Docker, orchestration Kubernetes, monitoring Prometheus/Grafana, CI/CD GitHub Actions, gestion des secrets, exposition sécurisée via Ingress HTTPS, et packaging avec Helm.

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
    └── /grafana/*  → grafana-service → Pod Grafana
                                ↑
                            Prometheus (scrape /metrics)

CI/CD
──────────────────────────────────────────────────────────────
git push → Tests → Build → Push ghcr.io → helm upgrade

HELM
──────────────────────────────────────────────────────────────
helm install mon-app ./mon-api-chart --set database.password=xxx
  → ConfigMap + Secret + Deployment + Service + Ingress + PostgreSQL
     (tous les objets déployés en une seule commande)
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
| Helm | Gestionnaire de paquets K8s | 3.20.0 |
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
├── requirements.txt              # Dépendances Python
├── test_app.py                   # Tests pytest
├── Dockerfile                    # Build de l'image
├── docker-compose.yml            # Stack locale complète
├── prometheus.yml                # Config Prometheus
├── configmap.yaml                # Config non sensible K8s (standalone)
├── secret.yaml                   # Secrets K8s standalone
├── deployment.yaml               # Pods API K8s standalone
├── service.yaml                  # Service K8s standalone
├── postgres-deployment.yaml      # PostgreSQL K8s standalone
├── ingress.yaml                  # Ingress + TLS K8s standalone
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

### Dockerfile

```dockerfile
FROM python:3.11-alpine
WORKDIR /app
# requirements.txt avant app.py : optimise le cache Docker
# Si seul app.py change, pip install n'est pas réexécuté
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout 100
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
```

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
kubectl delete pod <nom>           # Résilience — Pod recréé automatiquement
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
rate(hello_requests_total[1m])
hello_requests_total
rate(flask_http_request_duration_seconds_sum[1m])
  / rate(flask_http_request_duration_seconds_count[1m]) * 1000
```

Grafana datasource URL : `http://prometheus:9090` (nom de service Docker, jamais localhost).

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
          echo "helm upgrade mon-app ./mon-api-chart --set app.image.tag=sha-${{ github.sha }}"
```

---

## Projet 5 — Variables d'environnement, ConfigMaps, Secrets & PostgreSQL 🗄️

### Le principe 12-Factor App

Toute configuration doit être lue depuis les variables d'environnement — jamais hardcodée. Kubernetes formalise ça avec deux objets : **ConfigMap** pour la config non sensible, **Secret** pour les données sensibles (base64, pas du chiffrement — utiliser Vault ou un secrets manager cloud en production réelle).

### Fichiers clés

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

```yaml
# Dans deployment.yaml — envFrom injecte tout d'un coup
envFrom:
- configMapRef:
    name: mon-api-config
- secretRef:
    name: mon-api-secret
```

### Déploiement dans le bon ordre

```bash
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl port-forward service/mon-api-service 8080:5000
curl http://localhost:8080/db-test
```

---

## Projet 6 — Ingress Controller & HTTPS 🔒

### Pourquoi l'Ingress est indispensable

Sans Ingress, chaque service est exposé via un NodePort avec une URL comme `http://192.168.49.2:30080`. L'Ingress Controller (Nginx) est un reverse proxy qui reçoit tout le trafic sur les ports 80/443 et le route intelligemment selon les règles déclarées.

```
AVANT (NodePort)                    APRÈS (Ingress)
──────────────────────────          ──────────────────────────────────
IP:30080 → API                      https://monapp.local
IP:30090 → Grafana                      ├── /api/*    → API
(un port exposé par service)            └── /grafana/* → Grafana
                                    (un seul point d'entrée HTTPS)
```

### Mise en place complète

```bash
# Activer l'addon Minikube
minikube addons enable ingress

# Configurer le domaine local
echo "$(minikube ip) monapp.local" | sudo tee -a /etc/hosts

# Générer un certificat TLS auto-signé (prod : cert-manager + Let's Encrypt)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=monapp.local/O=DevOps Learning"

kubectl create secret tls monapp-tls --key tls.key --cert tls.crt
kubectl apply -f ingress.yaml

# Tester
curl -k https://monapp.local/api/
curl -k https://monapp.local/api/health
```

### ingress.yaml

```yaml
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
      - path: /grafana(/|$)(.*)
        pathType: Prefix
        backend:
          service:
            name: grafana
            port:
              number: 3000
```

### cert-manager en production (référence)

```yaml
# ClusterIssuer Let's Encrypt — certificats gratuits et automatiques
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

---

## Projet 7 — Helm 🎡

### Pourquoi Helm change tout

Sans Helm, déployer cette application nécessite 6 commandes `kubectl apply` distinctes. Avec trois environnements (dev, staging, prod), ça devient 18 commandes sur des fichiers dupliqués. Helm résout ce problème en transformant les YAML en **templates paramétrables** regroupés dans un **chart**, déployable en une seule commande avec uniquement les valeurs qui changent.

```bash
# Avant Helm
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml

# Après Helm
helm install mon-app ./mon-api-chart --set database.password=secret123
```

### Structure du chart

```
mon-api-chart/
├── Chart.yaml          # Métadonnées : nom, version du chart, version de l'app
├── values.yaml         # Toutes les valeurs par défaut — c'est le fichier central
└── templates/          # Les YAML avec la syntaxe de templating Go {{ .Values.xxx }}
    ├── configmap.yaml
    ├── secret.yaml
    ├── deployment.yaml
    ├── service.yaml
    ├── ingress.yaml
    └── postgres.yaml
```

### Chart.yaml

```yaml
apiVersion: v2
name: mon-api-chart
description: API Flask avec PostgreSQL, Prometheus et Ingress
type: application
version: 0.1.0        # Version du chart (changer quand on modifie les templates)
appVersion: "2.0.0"   # Version de l'application
```

### values.yaml — le fichier central

```yaml
app:
  name: mon-api
  env: production
  version: "2.0.0"
  replicaCount: 3
  image:
    repository: mon-api
    tag: v1
    pullPolicy: Never

database:
  host: postgres-service
  port: 5432
  name: appdb
  user: appuser
  password: ""          # Toujours passé via --set, jamais commité dans Git

service:
  type: ClusterIP
  port: 5000

ingress:
  enabled: true
  host: monapp.local
  tlsSecret: monapp-tls

postgresql:
  enabled: true
  replicaCount: 1
  image: postgres:16-alpine
  database: appdb
  user: appuser
```

### Les templates — syntaxe Go

La syntaxe `{{ .Values.xxx }}` injecte les valeurs de `values.yaml`. `{{ .Release.Name }}` est le nom donné au déploiement (`mon-app`). Cette combinaison garantit que plusieurs releases du même chart peuvent coexister sans conflit de noms.

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-deployment
  labels:
    app: {{ .Values.app.name }}
    release: {{ .Release.Name }}
spec:
  replicas: {{ .Values.app.replicaCount }}
  selector:
    matchLabels:
      app: {{ .Values.app.name }}
      release: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app: {{ .Values.app.name }}
        release: {{ .Release.Name }}
    spec:
      containers:
      - name: {{ .Values.app.name }}
        image: "{{ .Values.app.image.repository }}:{{ .Values.app.image.tag }}"
        imagePullPolicy: {{ .Values.app.image.pullPolicy }}
        ports:
        - containerPort: 5000
        envFrom:
        - configMapRef:
            name: {{ .Release.Name }}-config
        - secretRef:
            name: {{ .Release.Name }}-secret
```

```yaml
# templates/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ .Release.Name }}-secret
type: Opaque
data:
  # b64enc encode automatiquement — plus besoin de echo -n "xxx" | base64
  DB_PASSWORD: {{ .Values.database.password | b64enc | quote }}
```

```yaml
# templates/ingress.yaml — la directive if permet de désactiver l'Ingress en dev
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Release.Name }}-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  tls:
  - hosts:
    - {{ .Values.ingress.host }}
    secretName: {{ .Values.ingress.tlsSecret }}
  rules:
  - host: {{ .Values.ingress.host }}
    http:
      paths:
      - path: /api(/|$)(.*)
        pathType: Prefix
        backend:
          service:
            name: {{ .Release.Name }}-service
            port:
              number: {{ .Values.service.port }}
{{- end }}
```

### Commandes Helm essentielles

```bash
# Valider le chart avant de déployer
helm lint mon-api-chart/

# Voir les YAML générés sans déployer (indispensable pour débugger)
helm template mon-api-chart/ --set database.password=secret123

# Déployer
helm install mon-app ./mon-api-chart --set database.password=secret123

# Voir toutes les releases actives
helm list

# Voir le statut détaillé d'une release
helm status mon-app

# Voir l'historique des révisions
helm history mon-app

# Mettre à jour (ex: passer à 5 réplicas)
helm upgrade mon-app ./mon-api-chart \
  --set app.replicaCount=5 \
  --set database.password=secret123

# Revenir à la révision précédente en cas de problème
helm rollback mon-app 1

# Désinstaller complètement (supprime tous les objets K8s)
helm uninstall mon-app
```

### Plusieurs environnements — la vraie puissance de Helm

```bash
# values-dev.yaml — environnement de développement
cat > values-dev.yaml << EOF
app:
  env: development
  replicaCount: 1
  image:
    pullPolicy: Never
ingress:
  enabled: false
EOF

# values-prod.yaml — environnement de production
cat > values-prod.yaml << EOF
app:
  env: production
  replicaCount: 5
  image:
    repository: ghcr.io/stephdeve/docker-app/mon-api
    tag: sha-abc1234
    pullPolicy: Always
ingress:
  enabled: true
  host: monapp.com
EOF

# Déployer les deux environnements — ils coexistent dans le cluster !
helm install mon-app-dev  ./mon-api-chart -f values-dev.yaml  --set database.password=devpass
helm install mon-app-prod ./mon-api-chart -f values-prod.yaml --set database.password=prodpass

helm list   # Les deux releases apparaissent
```

### Utiliser les charts publics Bitnami

Au lieu de maintenir ton propre déploiement PostgreSQL, tu peux utiliser le chart officiel qui gère la réplication, la persistence, les backups automatiques et le monitoring.

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Voir toutes les options configurables
helm show values bitnami/postgresql | head -50

# Déployer PostgreSQL production-ready en une commande
helm install postgres bitnami/postgresql \
  --set auth.database=appdb \
  --set auth.username=appuser \
  --set auth.password=secret123 \
  --set primary.persistence.size=10Gi
```

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry.k8s.io: i/o timeout` dans les conteneurs

Les conteneurs Docker (Minikube, kind) ne peuvent pas accéder à internet — problème DNS ou proxy réseau. La solution est de précharger les images sur la machine hôte puis de les injecter.

```bash
docker pull <image>
docker save <image> | docker exec -i minikube \
  ctr --namespace=k8s.io images import --all-platforms=false -
docker exec minikube crictl images | grep <nom>
```

### 2. `dial tcp 192.168.49.2:2376: connect: no route to host`

La variable `DOCKER_HOST` pointe encore vers Minikube.

```bash
eval $(minikube docker-env --unset)
```

### 3. `ErrImageNeverPull`

L'image n'est pas dans le registre Minikube.

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

Utiliser `http://prometheus:9090` et non `http://localhost:9090`.

### 6. `connection refused localhost:8080` dans GitHub Actions

La VM GitHub n'a pas de cluster Kubernetes. Simuler avec `echo` en local, utiliser un secret `KUBECONFIG` pour un vrai cluster cloud.

### 7. Les Pods API démarrent avant PostgreSQL

Utiliser `depends_on` avec `condition: service_healthy` dans Docker Compose, et un `healthcheck` avec `pg_isready` sur postgres.

### 8. `failed calling webhook validate.nginx.ingress.kubernetes.io`

Le webhook de validation Nginx Ingress est inaccessible (controller pas Running).

```bash
kubectl delete validatingwebhookconfiguration ingress-nginx-admission
```

### 9. `helm install` échoue avec `INSTALLATION FAILED`

Si le release est en état `failed`, le désinstaller avant de réessayer.

```bash
helm uninstall mon-app
helm install mon-app ./mon-api-chart --set database.password=secret123
```

### 10. kind vs Minikube

Kind est plus léger mais suppose un accès internet fluide depuis les conteneurs. Minikube est plus adapté aux environnements avec restrictions réseau grâce à son système d'addons et de préchargement d'images.

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
| **Ingress** | Règles de routage HTTP/HTTPS vers les Services. |
| **Ingress Controller** | Reverse proxy (Nginx) qui implémente les règles Ingress. |
| **TLS Termination** | Déchiffrement du trafic HTTPS à l'entrée du cluster. |
| **cert-manager** | Automatise la gestion des certificats TLS (Let's Encrypt). |
| **ConfigMap** | Config non sensible stockée en clair dans Kubernetes. |
| **Secret** | Données sensibles encodées en base64 dans Kubernetes (pas chiffrées !). |
| **envFrom** | Injecte toutes les clés d'un ConfigMap ou Secret comme variables d'env. |
| **Helm** | Gestionnaire de paquets Kubernetes — package les YAML en charts réutilisables. |
| **Chart** | Package Helm contenant les templates et valeurs par défaut d'une application. |
| **Release** | Instance déployée d'un chart Helm dans un cluster (`helm install mon-app`). |
| **values.yaml** | Fichier central des valeurs par défaut d'un chart Helm. |
| **helm template** | Génère les YAML finaux sans les déployer — indispensable pour débugger. |
| **helm lint** | Valide la syntaxe d'un chart avant déploiement. |
| **helm rollback** | Revient à une révision précédente en cas de problème. |
| **b64enc** | Fonction Helm qui encode automatiquement une valeur en base64. |
| **Master Node** | Cerveau du cluster — API Server, Scheduler, Controller-Manager, etcd. |
| **Worker Node** | Machine qui exécute les Pods. |
| **etcd** | Base de données clé-valeur de l'état du cluster. |
| **Controller-Manager** | Maintient l'état réel = état désiré en permanence. |
| **Prometheus** | Collecte les métriques via scraping (pull). |
| **Grafana** | Visualisation des métriques avec dashboards interactifs. |
| **PromQL** | Langage de requête Prometheus. |
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
| **rewrite-target** | Annotation Nginx Ingress pour réécrire le chemin URL. |
| **ssl-redirect** | Annotation Nginx Ingress pour forcer HTTP → HTTPS. |

---

*Projet réalisé sur Ubuntu 24 — Docker 27.x — Minikube 1.35.x — kubectl 1.34.x — Helm 3.20.0 — PostgreSQL 16 — Prometheus latest — Grafana latest — Nginx Ingress 1.14.x — GitHub Actions*