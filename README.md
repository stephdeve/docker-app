# 🐳 Docker & ☸️ Kubernetes — Guide Pratique Complet

> Projet d'apprentissage progressif des architectures de conteneurisation et DevOps/SRE,
> basé sur le déploiement d'une API Flask à travers cinq couches de complexité croissante.

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
9. [Problèmes rencontrés & Solutions](#problèmes-rencontrés--solutions)
10. [Comparaison Docker vs Kubernetes](#comparaison-docker-vs-kubernetes)
11. [Glossaire](#glossaire)

---

## Vue d'ensemble

Ce projet explore les grandes pratiques DevOps/SRE en déployant la **même application** (une API Python/Flask) avec Docker, Kubernetes, en la monitorant avec Prometheus & Grafana, en automatisant tout avec GitHub Actions, et en séparant proprement la configuration du code.

```
DOCKER COMPOSE STACK
────────────────────────────────────────────────────
postgres ← api1, api2, api3 (via env vars)
               ↓
          prometheus → grafana

KUBERNETES STACK
────────────────────────────────────────────────────
ConfigMap + Secret
       ↓
postgres-deployment + postgres-service (ClusterIP)
       ↓
mon-api-deployment (lit les env vars depuis ConfigMap/Secret)
       ↓
mon-api-service (NodePort)
       ↓
/metrics → Prometheus → Grafana

CI/CD
────────────────────────────────────────────────────
git push → Tests → Build → Push ghcr.io → kubectl deploy
```

---

## Prérequis & Installation

### Technologies utilisées

| Technologie | Rôle | Version testée |
|-------------|------|----------------|
| Python | Langage de l'API | 3.11 |
| Flask | Framework web | 3.1.0 |
| psycopg2-binary | Client PostgreSQL pour Python | 2.9.9 |
| prometheus-flask-exporter | Exposition des métriques | 0.23.1 |
| pytest | Tests automatisés | 8.x |
| Docker | Conteneurisation | 27.x |
| Docker Compose | Orchestration locale multi-conteneurs | 2.x |
| PostgreSQL | Base de données relationnelle | 16-alpine |
| Minikube | Cluster Kubernetes local | 1.35.x |
| kubectl | CLI pour Kubernetes | 1.34.x |
| Prometheus | Collecte de métriques | latest |
| Grafana | Visualisation des métriques | latest |
| GitHub Actions | CI/CD automatisé | — |

### Installation de Docker

```bash
sudo apt update && sudo apt install docker.io -y
sudo systemctl enable docker && sudo systemctl start docker
sudo usermod -aG docker $USER && newgrp docker
docker --version
```

### Installation de Minikube

```bash
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
minikube start
minikube status
```

### Installation de kubectl

```bash
sudo snap install kubectl --classic
# OU via alias Minikube (garantit la compatibilité de version)
echo "alias kubectl='minikube kubectl --'" >> ~/.bashrc && source ~/.bashrc
kubectl get nodes
```

---

## L'application commune

### Structure du projet

```
docker-app/
├── app.py                        # API Flask avec métriques, DB et config via env vars
├── requirements.txt              # Dépendances Python
├── test_app.py                   # Tests automatisés (pytest)
├── Dockerfile                    # Instructions de build de l'image
├── docker-compose.yml            # Stack complète : API + Postgres + Prometheus + Grafana
├── prometheus.yml                # Configuration du scraping Prometheus
├── configmap.yaml                # Configuration non sensible pour Kubernetes
├── secret.yaml                   # Données sensibles pour Kubernetes (base64)
├── deployment.yaml               # Déclaration Kubernetes — Pods & réplicas
├── service.yaml                  # Déclaration Kubernetes — Service Discovery
├── postgres-deployment.yaml      # Déploiement PostgreSQL dans Kubernetes
├── .github/
│   └── workflows/
│       └── ci-cd.yml             # Pipeline GitHub Actions (CI + CD)
└── README.md
```

### app.py — l'API Flask complète

```python
from flask import Flask, jsonify
import socket
import os
import psycopg2
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
metrics = PrometheusMetrics(app)

hello_counter = metrics.counter(
    'hello_requests_total',
    'Nombre total de requêtes sur /',
    labels={'pod': lambda: socket.gethostname()}
)

# os.environ.get("NOM", "valeur_par_défaut") est le pattern standard
# La valeur par défaut permet à l'app de démarrer même sans la variable
APP_ENV     = os.environ.get("APP_ENV", "development")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = os.environ.get("DB_PORT", "5432")
DB_NAME     = os.environ.get("DB_NAME", "appdb")
DB_USER     = os.environ.get("DB_USER", "appuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD")   # Pas de défaut pour les secrets !

@app.route("/")
@hello_counter
def hello():
    return f"Bonjour depuis {socket.gethostname()} [env: {APP_ENV}, v{APP_VERSION}]\n"

@app.route("/health")
def health():
    return {"status": "ok", "pod": socket.gethostname(), "env": APP_ENV}

@app.route("/config")
def config():
    # Expose la config NON sensible pour le debugging — DB_PASSWORD est masqué
    return jsonify({
        "app_env": APP_ENV,
        "app_version": APP_VERSION,
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_name": DB_NAME,
        "db_user": DB_USER,
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
        cur.close()
        conn.close()
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

### Le Dockerfile

```dockerfile
FROM python:3.11-alpine
WORKDIR /app
# requirements.txt avant app.py : optimise le cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout 100
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
```

La stratégie de cache Docker est fondamentale : chaque instruction crée une couche immuable. Docker compare chaque couche avec le build précédent — si rien n'a changé, il réutilise le cache. En plaçant `requirements.txt` avant `app.py`, on évite de réinstaller toutes les dépendances à chaque modification du code.

### Construction et lancement

```bash
docker build --network=host -t mon-api:v1 .
docker run -d -p 8081:5000 -e APP_ENV=production --name api1 mon-api:v1
docker run -d -p 8082:5000 -e APP_ENV=production --name api2 mon-api:v1
docker run -d -p 8083:5000 -e APP_ENV=production --name api3 mon-api:v1
curl http://localhost:8081
```

### Commandes Docker essentielles

```bash
docker ps                    # Conteneurs en cours d'exécution
docker ps -a                 # Tous les conteneurs, y compris arrêtés
docker logs -f api1          # Logs en temps réel
docker exec -it api1 sh      # Shell interactif dans le conteneur
docker stats                 # CPU, mémoire, réseau en temps réel
docker stop api1 api2 api3 && docker rm api1 api2 api3
```

---

## Projet 2 — Kubernetes ☸️

### Architecture du cluster Minikube

```
Ta machine
└── Minikube
    ├── Master Node
    │   ├── API Server         → point d'entrée de kubectl
    │   ├── etcd               → état du cluster (clé-valeur)
    │   ├── Controller-Manager → maintient l'état désiré en permanence
    │   └── Scheduler          → place les Pods sur les Worker Nodes
    └── Worker Node
        ├── Kubelet            → agent qui exécute les ordres du Master
        ├── Container Runtime  → fait tourner les conteneurs
        └── Pods               → unité de base : un ou plusieurs conteneurs
```

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
# service.yaml
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

### Déploiement et commandes essentielles

```bash
minikube image load mon-api:v1
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl get pods -w
kubectl delete pod <nom>          # Test de résilience — Pod recréé automatiquement
kubectl scale deployment mon-api-deployment --replicas=5
minikube service mon-api-service --url
minikube dashboard                # Interface web graphique
```

---

## Projet 3 — Monitoring avec Prometheus & Grafana 📊

### Pourquoi monitorer ?

Un SRE ne déploie jamais à l'aveugle. Le monitoring répond à la question permanente : **"est-ce que ce que j'ai déployé fonctionne correctement en ce moment ?"** Prometheus collecte les métriques via un mécanisme de *scraping* (pull) — il interroge l'endpoint `/metrics` de chaque application toutes les 15 secondes. Grafana les visualise sous forme de dashboards interactifs.

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
rate(hello_requests_total[1m])                          # Requêtes/seconde par pod
hello_requests_total                                    # Total depuis le démarrage
rate(flask_http_request_duration_seconds_sum[1m])
  / rate(flask_http_request_duration_seconds_count[1m]) * 1000   # Temps de réponse moyen (ms)
```

Dans Grafana (`http://localhost:3000`), utiliser `http://prometheus:9090` comme URL de datasource — et non `localhost:9090`, car Grafana tourne dans un conteneur et doit joindre Prometheus par son nom de service Docker.

---

## Projet 4 — CI/CD avec GitHub Actions 🚀

### Le workflow complet

```yaml
# .github/workflows/ci-cd.yml
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
    name: Build & Test
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
    name: Deploy
    runs-on: ubuntu-latest
    needs: ci
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-kubectl@v3
      - name: Simuler le déploiement Kubernetes
        run: |
          echo "✅ Image : ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}"
          echo "kubectl set image deployment/mon-api-deployment mon-api=ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}"
          echo "kubectl rollout status deployment/mon-api-deployment --timeout=120s"
```

Le tag `sha-xxxxxxx` est fondamental en SRE : il garantit qu'on peut toujours identifier exactement quel commit tourne en production, et revenir en arrière en cas d'incident.

---

## Projet 5 — Variables d'environnement, ConfigMaps, Secrets & PostgreSQL 🗄️

### Le principe fondamental : séparer la configuration du code

C'est l'un des principes du [12-Factor App](https://12factor.net/fr/), la référence en matière d'applications cloud-native. Si on hardcode une URL de base de données ou un mot de passe dans le code, on crée trois problèmes graves : les credentials se retrouvent dans l'historique Git, l'image Docker ne peut pas être réutilisée entre les environnements (dev, staging, prod), et chaque changement de config nécessite un rebuild. La solution est de lire toute la configuration depuis les **variables d'environnement** à l'exécution.

Kubernetes formalise cette séparation avec deux objets distincts. Un **ConfigMap** contient la configuration non sensible (URLs, noms, paramètres) — ses valeurs sont visibles en clair avec `kubectl describe`. Un **Secret** contient les données sensibles (mots de passe, clés API, certificats) — ses valeurs sont stockées encodées en base64 dans etcd. Il faut noter que base64 n'est pas du chiffrement, c'est de l'encodage — en production réelle, on utilise des solutions comme HashiCorp Vault ou les secrets managers cloud pour chiffrer vraiment les secrets au repos.

### Docker Compose avec PostgreSQL

```yaml
# docker-compose.yml complet
version: "3.8"
services:
  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: devsecret123
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    # pg_isready vérifie que PostgreSQL est prêt à accepter des connexions
    # Les APIs ne démarrent pas tant que ce healthcheck n'est pas vert
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser -d appdb"]
      interval: 5s
      timeout: 3s
      retries: 5

  api1:
    build: .
    container_name: api1
    ports:
      - "8081:5000"
    environment:
      APP_ENV: development
      APP_VERSION: "2.0.0"
      DB_HOST: postgres       # Nom du service Docker — résolution DNS automatique
      DB_PORT: "5432"
      DB_NAME: appdb
      DB_USER: appuser
      DB_PASSWORD: devsecret123
    depends_on:
      postgres:
        condition: service_healthy

  api2:
    build: .
    container_name: api2
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
    container_name: api3
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
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    depends_on: [api1, api2, api3]

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
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

```bash
docker compose up -d --build
curl http://localhost:8081/db-test
# → {"status": "connected", "postgres_version": "PostgreSQL 16.x..."}
```

### ConfigMap et Secret Kubernetes

```yaml
# configmap.yaml — configuration non sensible, visible en clair
apiVersion: v1
kind: ConfigMap
metadata:
  name: mon-api-config
data:
  APP_ENV: "production"
  APP_VERSION: "2.0.0"
  DB_HOST: "postgres-service"   # Nom du Service Kubernetes qui expose PostgreSQL
  DB_PORT: "5432"
  DB_NAME: "appdb"
  DB_USER: "appuser"
```

```yaml
# secret.yaml — données sensibles, encodées en base64
apiVersion: v1
kind: Secret
metadata:
  name: mon-api-secret
type: Opaque
data:
  # Générer avec : echo -n "devsecret123" | base64
  DB_PASSWORD: ZGV2c2VjcmV0MTIz
```

```yaml
# deployment.yaml mis à jour — consomme ConfigMap et Secret
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
        # envFrom injecte TOUTES les clés d'un ConfigMap ou Secret comme variables d'env
        envFrom:
        - configMapRef:
            name: mon-api-config
        - secretRef:
            name: mon-api-secret
```

```yaml
# postgres-deployment.yaml — PostgreSQL dans Kubernetes
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
              key: DB_PASSWORD    # On ne prend que cette clé du Secret

---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
spec:
  type: ClusterIP    # Accessible uniquement à l'intérieur du cluster — voulu
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

### Déploiement dans le bon ordre

```bash
# 1. Les secrets et config d'abord (les Pods en ont besoin au démarrage)
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml

# 2. La base de données
kubectl apply -f postgres-deployment.yaml

# 3. L'API
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Inspecter (les valeurs du Secret sont masquées dans describe)
kubectl describe configmap mon-api-config
kubectl describe secret mon-api-secret

# Tester la connexion DB via port-forward
kubectl port-forward service/mon-api-service 8080:5000
curl http://localhost:8080/db-test
```

### Encoder et décoder les secrets base64

```bash
# Encoder une valeur pour la mettre dans secret.yaml
echo -n "monmotdepasse" | base64

# Décoder pour vérifier
echo "bW9ubW90ZGVwYXNzZQ==" | base64 --decode

# BONNE PRATIQUE : ne jamais commiter secret.yaml avec de vraies valeurs
# Ajouter secret.yaml à .gitignore en production
```

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry-1.docker.io: i/o timeout`

Docker ne peut pas télécharger les images depuis Docker Hub — le daemon utilise le DNS de Minikube qui ne route pas vers Internet.

```bash
sudo nano /etc/docker/daemon.json
# Contenu : { "dns": ["8.8.8.8", "8.8.4.4"] }
sudo systemctl restart docker
# Alternative immédiate : docker build --network=host -t mon-api:v1 .
```

### 2. `dial tcp 192.168.49.2:2376: connect: no route to host`

La variable `DOCKER_HOST` pointe encore vers Minikube suite à un `eval $(minikube docker-env)` non annulé.

```bash
eval $(minikube docker-env --unset)
docker info
```

### 3. `ErrImageNeverPull`

L'image existe dans le registre Docker local mais pas dans celui de Minikube — deux registres séparés.

```bash
minikube image load mon-api:v1
kubectl get pods -w    # Les Pods repassent en Running automatiquement
```

### 4. `kubectl : commande introuvable`

```bash
sudo snap install kubectl --classic
```

### 5. Grafana ne se connecte pas à Prometheus

Utiliser `http://prometheus:9090` (nom de service Docker) et non `http://localhost:9090` — `localhost` dans un conteneur désigne le conteneur lui-même, pas la machine hôte.

### 6. `connection refused localhost:8080` dans GitHub Actions

La VM GitHub n'a pas de cluster Kubernetes — `kubectl` ne trouve personne à qui parler. Pour l'environnement local (Minikube), simuler les commandes avec `echo`. Pour un vrai cluster, stocker le kubeconfig dans les secrets GitHub et configurer `kubectl` avant de déployer.

### 7. Les Pods API démarrent avant PostgreSQL

Utiliser `depends_on` avec `condition: service_healthy` dans Docker Compose, et un `healthcheck` sur le service postgres avec `pg_isready`. Dans Kubernetes, implémenter un `initContainer` ou des `readinessProbes` pour retarder le trafic jusqu'à ce que l'app soit prête.

---

## Comparaison Docker vs Kubernetes

| Aspect | Docker | Kubernetes |
|--------|--------|------------|
| **Complexité** | Simple, facile à démarrer | Complexe, courbe d'apprentissage importante |
| **Cas d'usage** | Dev local, petits projets | Production, applications à grande échelle |
| **Scaling** | Manuel | Automatique (`replicas: N`) |
| **Résilience** | Aucune — conteneur mort = mort | Automatique — Controller-Manager recrée les Pods |
| **Load balancing** | Manuel ou Docker Compose | Intégré dans les Services |
| **Config & Secrets** | Variables `-e` ou `.env` | ConfigMap + Secret (objets natifs) |
| **Réseau** | Bridge network par défaut | CNI + Services + DNS interne |
| **Philosophie** | **Impératif** — tu dis *comment* | **Déclaratif** — tu dis *quoi* tu veux |

---

## Glossaire

| Terme | Définition |
|-------|------------|
| **Image** | Template immuable à partir duquel on crée des conteneurs. Analogue à une classe en POO. |
| **Conteneur** | Instance en cours d'exécution d'une image. Analogue à un objet instancié. |
| **Dockerfile** | Fichier de recette pour construire une image, instruction par instruction. |
| **Layer (couche)** | Chaque instruction du Dockerfile crée une couche immuable mise en cache. |
| **Registry** | Stockage d'images Docker (Docker Hub, GitHub Container Registry ghcr.io...). |
| **Pod** | Unité de base dans Kubernetes — un ou plusieurs conteneurs partageant réseau et stockage. |
| **Deployment** | Ressource K8s qui gère la création, mise à jour et résilience d'un ensemble de Pods. |
| **Service** | Ressource K8s qui expose des Pods avec une adresse stable et fait du load balancing. |
| **ClusterIP** | Type de Service accessible uniquement à l'intérieur du cluster. |
| **NodePort** | Type de Service qui expose l'application sur un port fixe de chaque nœud. |
| **ConfigMap** | Objet Kubernetes pour stocker de la configuration non sensible (clé-valeur). |
| **Secret** | Objet Kubernetes pour stocker des données sensibles encodées en base64. |
| **envFrom** | Directive K8s qui injecte toutes les clés d'un ConfigMap ou Secret comme variables d'env. |
| **Master Node** | Cerveau du cluster K8s — API Server, Scheduler, Controller-Manager, etcd. |
| **Worker Node** | Machine qui exécute réellement les conteneurs (Pods). |
| **Kubelet** | Agent sur chaque Worker Node qui reçoit les ordres du Master et gère les Pods. |
| **etcd** | Base de données clé-valeur distribuée qui stocke tout l'état du cluster K8s. |
| **Controller-Manager** | Boucle de contrôle qui maintient l'état réel = état désiré en permanence. |
| **Scheduler** | Composant qui décide sur quel Worker Node placer un nouveau Pod. |
| **Prometheus** | Système de monitoring qui scrape les métriques des applications à intervalles réguliers. |
| **Grafana** | Outil de visualisation qui crée des dashboards interactifs à partir des données Prometheus. |
| **PromQL** | Langage de requête de Prometheus pour interroger et agréger les métriques. |
| **Counter** | Métrique Prometheus qui ne fait que monter (requêtes, erreurs...). |
| **Gauge** | Métrique Prometheus qui peut monter et descendre (CPU, mémoire...). |
| **Histogram** | Métrique Prometheus qui mesure la distribution des valeurs dans des buckets. |
| **rate()** | Fonction PromQL qui calcule le taux de variation d'un Counter par seconde. |
| **CI** | Continuous Integration — tests et builds automatiques à chaque push. |
| **CD** | Continuous Deployment — déploiement automatique si la CI réussit. |
| **GitHub Actions** | Plateforme CI/CD intégrée à GitHub, déclenchée par des événements Git. |
| **ghcr.io** | GitHub Container Registry — stockage d'images Docker intégré à GitHub. |
| **SHA du commit** | Identifiant unique d'un commit Git, utilisé pour tagger les images et garantir la traçabilité. |
| **kubeconfig** | Fichier de configuration kubectl contenant l'adresse du cluster et les credentials d'accès. |
| **kubectl rollout status** | Attend la fin d'un déploiement et échoue si les pods ne démarrent pas correctement. |
| **12-Factor App** | Méthodologie de référence pour construire des applications cloud-native fiables et scalables. |
| **base64** | Encodage (pas chiffrement !) utilisé par Kubernetes pour stocker les valeurs de Secret. |
| **healthcheck** | Vérification périodique qu'un service est prêt — `pg_isready` pour PostgreSQL. |
| **port-forward** | Commande kubectl qui crée un tunnel temporaire vers un Pod ou Service Kubernetes. |

---

*Projet réalisé sur Ubuntu 24 — Docker 27.x — Minikube 1.35.1 — kubectl 1.34.4 — PostgreSQL 16 — Prometheus latest — Grafana latest — GitHub Actions*