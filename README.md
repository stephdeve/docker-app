# 🐳 Docker & ☸️ Kubernetes — Guide Pratique Complet

> Projet d'apprentissage progressif des architectures de conteneurisation et DevOps, basé sur le déploiement d'une API Flask simple.

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis & Installation](#prérequis--installation)
3. [L'application commune](#lapplication-commune)
4. [Projet 1 — Docker](#projet-1--docker-)
5. [Projet 2 — Kubernetes](#projet-2--kubernetes-)
6. [Projet 3 — Monitoring avec Prometheus & Grafana](#projet-3--monitoring-avec-prometheus--grafana-)
7. [Projet 4 — CI/CD avec GitHub Actions](#projet-4--cicd-avec-github-actions-)
8. [Problèmes rencontrés & Solutions](#problèmes-rencontrés--solutions)
9. [Comparaison Docker vs Kubernetes](#comparaison-docker-vs-kubernetes)
10. [Glossaire](#glossaire)

---

## Vue d'ensemble

Ce projet explore les grandes pratiques DevOps/SRE en déployant la **même application** (une API Python/Flask) avec Docker, Kubernetes, en la monitorant avec Prometheus & Grafana, et en automatisant tout avec GitHub Actions.

```
DOCKER                          KUBERNETES
──────────────────────────      ──────────────────────────────────────
App Code + Dependencies         App Code + Dependencies
       ↓                                ↓
   Dockerfile                       Dockerfile
       ↓                                ↓
  Build Image                      Build Image
       ↓                                ↓
Container Runtime               Container Runtime
       ↓                                ↓
  Host Machine                    Master Node
  [🐳][🐳][🐳]                  ┌─────────────────────┐
  [🐳][🐳][🐳]                  │ API Server           │
       ↓                         │ Key-Value Store      │
  Networking                     │ Controller-Manager   │
       ↓                         │ Scheduler            │
  Running App                    └──────────┬──────────┘
       ↓                                    ↓
  /metrics                           Worker Node
       ↓                         ┌──────────────────┐
  Prometheus                     │ Kubelet           │
  (scrape 15s)                   │ Container Runtime │
       ↓                         │ Pods [📦][📦][📦] │
  Grafana                        └──────────┬───────┘
  (dashboards)                              ↓
                                  Service Discovery
                                            ↓
                                      Running App
                                            ↓
                                     /metrics endpoint
                                            ↓
                             Prometheus (scrape toutes 15s)
                                            ↓
                                 Grafana (visualisation)
```

---

## Prérequis & Installation

### Technologies utilisées

| Technologie | Rôle | Version testée |
|-------------|------|----------------|
| Python | Langage de l'API | 3.11 |
| Flask | Framework web | 3.1.0 |
| prometheus-flask-exporter | Exposition des métriques | 0.23.1 |
| pytest | Tests automatisés | 8.x |
| Docker | Conteneurisation | 27.x |
| Docker Compose | Orchestration locale multi-conteneurs | 2.x |
| Minikube | Cluster Kubernetes local | 1.35.x |
| kubectl | CLI pour Kubernetes | 1.34.x |
| Prometheus | Collecte de métriques | latest |
| Grafana | Visualisation des métriques | latest |
| GitHub Actions | CI/CD automatisé | - |

### Installation de Docker

```bash
# Sur Ubuntu/Debian
sudo apt update
sudo apt install docker.io -y
sudo systemctl enable docker
sudo systemctl start docker

# Ajouter ton utilisateur au groupe docker (évite de taper sudo à chaque fois)
sudo usermod -aG docker $USER
newgrp docker

# Vérifier l'installation
docker --version
docker info
```

### Installation de Minikube

```bash
# Télécharger Minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Démarrer le cluster
minikube start

# Vérifier le statut
minikube status
```

### Installation de kubectl

```bash
# Via snap (Ubuntu)
sudo snap install kubectl --classic

# OU via alias Minikube (évite les problèmes de compatibilité de version)
echo "alias kubectl='minikube kubectl --'" >> ~/.bashrc
source ~/.bashrc

# Vérifier la connexion au cluster
kubectl get nodes
```

Résultat attendu :
```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   5m    v1.35.1
```

---

## L'application commune

### Structure du projet

```
docker-app/
├── app.py                        # API Flask avec métriques Prometheus
├── requirements.txt              # Dépendances Python
├── test_app.py                   # Tests automatisés (pytest)
├── Dockerfile                    # Instructions de build de l'image
├── docker-compose.yml            # Orchestration Docker locale (API + Prometheus + Grafana)
├── prometheus.yml                # Configuration du scraping Prometheus
├── deployment.yaml               # Déclaration Kubernetes — Pods & réplicas
├── service.yaml                  # Déclaration Kubernetes — Service Discovery
├── .github/
│   └── workflows/
│       └── ci-cd.yml             # Pipeline GitHub Actions
└── README.md
```

### app.py

```python
from flask import Flask
import socket
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

# PrometheusMetrics fait deux choses en une :
# 1. Il crée automatiquement l'endpoint GET /metrics
# 2. Il mesure chaque requête HTTP (durée, statut, méthode...)
# C'est ce endpoint que Prometheus "scrape" toutes les 15 secondes
metrics = PrometheusMetrics(app)

# Métrique "métier" personnalisée — un compteur qui ne fait que monter
# Le label 'pod' permet de distinguer quel pod répond dans Grafana
hello_counter = metrics.counter(
    'hello_requests_total',
    'Nombre total de requêtes sur /',
    labels={'pod': lambda: socket.gethostname()}
)

@app.route("/")
@hello_counter  # Chaque appel à / incrémente notre compteur
def hello():
    return f"Bonjour depuis le pod : {socket.gethostname()}\n"

# Endpoint de santé — utilisé par Kubernetes pour vérifier qu'un pod est vivant
@app.route("/health")
def health():
    return {"status": "ok", "pod": socket.gethostname()}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

### requirements.txt

```
Flask==3.1.0
prometheus-flask-exporter==0.23.1
pytest==8.3.5
```

---

## Projet 1 — Docker 🐳

### Le Dockerfile expliqué ligne par ligne

```dockerfile
# On part d'une image de base officielle — Python 3.11 sur Alpine Linux
# Alpine est une distribution minimaliste (~5 Mo) parfaite pour les conteneurs
FROM python:3.11-alpine

# On définit le répertoire de travail à l'intérieur du conteneur
# Toutes les commandes suivantes s'exécuteront depuis /app
WORKDIR /app

# ASTUCE : on copie d'abord SEULEMENT requirements.txt
# Docker met chaque étape en cache. Si app.py change mais pas requirements.txt,
# Docker réutilise le cache de pip install — le build est beaucoup plus rapide
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout 100

# On copie le code ensuite (l'ordre est important pour le cache !)
COPY app.py .

# EXPOSE documente le port — il ne publie pas réellement le port
EXPOSE 5000

CMD ["python", "app.py"]
```

Ce que Docker fait en coulisses lors du build : il lit chaque instruction, crée une couche en cache en lecture seule, et empile toutes les couches pour former l'image finale. L'ordre des instructions est donc stratégique.

```
IMAGE mon-api:v1
├── Couche 4 : COPY app.py           [nouvelle à chaque modif du code]
├── Couche 3 : RUN pip install       [en cache si requirements.txt inchangé]
├── Couche 2 : COPY requirements.txt [en cache si inchangé]
├── Couche 1 : WORKDIR /app
└── Couche 0 : python:3.11-alpine    [téléchargée une seule fois]
```

### Construction et lancement

```bash
# Builder l'image (--network=host si problème DNS)
docker build --network=host -t mon-api:v1 .

# Lancer 3 conteneurs sur des ports différents
docker run -d -p 8081:5000 --name api1 mon-api:v1
docker run -d -p 8082:5000 --name api2 mon-api:v1
docker run -d -p 8083:5000 --name api3 mon-api:v1

# Tester — chaque réponse affiche un ID de conteneur différent
curl http://localhost:8081
curl http://localhost:8082
curl http://localhost:8083
```

### Commandes Docker essentielles

```bash
docker ps                          # Conteneurs en cours d'exécution
docker ps -a                       # Tous les conteneurs (y compris arrêtés)
docker logs -f api1                # Logs en temps réel
docker exec -it api1 sh            # Shell interactif dans le conteneur
docker stop api1 api2 api3         # Arrêter des conteneurs
docker rm api1 api2 api3           # Supprimer des conteneurs
docker stats                       # Utilisation des ressources en temps réel
```

---

## Projet 2 — Kubernetes ☸️

### Architecture du cluster Minikube

```
Ta machine
└── Minikube (VM ou conteneur)
    ├── Master Node (control-plane)
    │   ├── API Server         → point d'entrée de toutes les commandes kubectl
    │   ├── etcd               → base de données clé-valeur (l'état du cluster)
    │   ├── Controller-Manager → surveille et corrige l'état du cluster
    │   └── Scheduler          → décide sur quel Worker Node placer chaque Pod
    └── Worker Node
        ├── Kubelet            → agent qui exécute les ordres du Master
        ├── Container Runtime  → fait tourner les conteneurs
        └── Pods               → unité de base : un ou plusieurs conteneurs
```

### deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mon-api-deployment
spec:
  replicas: 3              # Controller-Manager maintient toujours 3 Pods actifs
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
        imagePullPolicy: Never  # Utiliser l'image locale de Minikube
        ports:
        - containerPort: 5000
```

### service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mon-api-service
spec:
  type: NodePort           # Expose le service en dehors du cluster
  selector:
    app: mon-api           # Route vers tous les Pods avec ce label
  ports:
  - port: 5000
    targetPort: 5000
    nodePort: 30080        # Port exposé sur le nœud (plage 30000-32767)
```

### Déploiement et commandes essentielles

```bash
# Charger l'image dans le registre de Minikube
minikube image load mon-api:v1

# Déployer
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Observer en temps réel
kubectl get pods -w

# Tester la résilience — Kubernetes recrée le Pod automatiquement !
kubectl delete pod <nom-du-pod>
kubectl get pods -w

# Scaler
kubectl scale deployment mon-api-deployment --replicas=5

# Accéder à l'application
minikube service mon-api-service --url
```

### Commandes kubectl essentielles

```bash
kubectl get nodes/pods/deployments/services/all    # Lister les ressources
kubectl describe pod <nom>                         # Détails + événements
kubectl logs -f <nom>                              # Logs en temps réel
kubectl exec -it <nom> -- sh                       # Shell dans le Pod
kubectl apply -f fichier.yaml                      # Créer ou mettre à jour
kubectl delete -f fichier.yaml                     # Supprimer via YAML
minikube dashboard                                 # Interface web graphique
```

---

## Projet 3 — Monitoring avec Prometheus & Grafana 📊

### Pourquoi monitorer ?

Un SRE ne déploie jamais à l'aveugle. Le monitoring répond à la question fondamentale : **"est-ce que ce que j'ai déployé fonctionne correctement en production ?"**. Prometheus collecte les métriques, Grafana les visualise. Ce duo est le standard industriel dans les équipes DevOps/SRE.

```
API Flask (/metrics)  →  Prometheus (scrape toutes 15s)  →  Grafana (dashboards)
```

### Concepts clés à comprendre

**Le scraping** est le mécanisme central de Prometheus : au lieu que les applications *poussent* leurs métriques, Prometheus vient les *tirer* (pull) à intervalles réguliers depuis l'endpoint `/metrics`. C'est plus fiable car Prometheus détecte immédiatement si une cible ne répond plus.

Les **types de métriques Prometheus** sont au nombre de quatre. Un *Counter* ne fait que monter — parfait pour compter les requêtes ou les erreurs. Une *Gauge* peut monter et descendre — parfaite pour le CPU, la mémoire, le nombre de connexions actives. Un *Histogram* mesure la distribution des valeurs — parfait pour les temps de réponse. Un *Summary* est similaire mais calcule des quantiles côté client.

**PromQL** est le langage de requête de Prometheus. Sa fonction la plus utile est `rate()` qui calcule le taux de variation d'un compteur par seconde sur une fenêtre glissante. Par exemple, `rate(hello_requests_total[1m])` donne le nombre de requêtes par seconde sur la dernière minute — c'est la métrique qu'un SRE surveille pour détecter un pic ou une chute de trafic.

### prometheus.yml

```yaml
global:
  scrape_interval: 15s     # Prometheus interroge chaque cible toutes les 15s

scrape_configs:
  - job_name: 'mon-api'
    static_configs:
      # Ces noms sont les noms des services Docker Compose
      # Docker Compose crée un réseau interne où chaque service est joignable par son nom
      - targets: ['api1:5000', 'api2:5000', 'api3:5000']
```

### docker-compose.yml complet (avec monitoring)

```yaml
version: "3.8"

services:
  api1:
    build: .
    ports:
      - "8081:5000"
    container_name: api1

  api2:
    build: .
    ports:
      - "8082:5000"
    container_name: api2

  api3:
    build: .
    ports:
      - "8083:5000"
    container_name: api3

  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      # On injecte notre fichier de config dans le conteneur Prometheus
      # Le ":" sépare [chemin sur ta machine]:[chemin dans le conteneur]
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    depends_on:
      - api1
      - api2
      - api3

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      # Volume nommé pour que tes dashboards persistent si tu redémarres Compose
      - grafana-data:/var/lib/grafana
    depends_on:
      - prometheus

# Déclaration du volume nommé — Docker le gère et il survit aux `docker compose down`
volumes:
  grafana-data:
```

### Lancement et vérification

```bash
# Démarrer tout le stack (--build pour reconstruire l'image après modif de app.py)
docker compose up -d --build

# Générer du trafic pour alimenter les métriques
for i in {1..20}; do
  curl -s http://localhost:8081
  curl -s http://localhost:8082
  curl -s http://localhost:8083
done

# Vérifier que les métriques sont bien exposées
curl http://localhost:8081/metrics | grep hello_requests
```

### Explorer Prometheus (http://localhost:9090)

Dans *Status → Targets*, les 3 APIs doivent être en vert avec le statut `UP`. C'est la confirmation que Prometheus scrape bien tes pods.

Requêtes PromQL utiles à essayer dans l'interface :

```promql
# Taux de requêtes par seconde par pod (sur 1 minute glissante)
rate(hello_requests_total[1m])

# Nombre total de requêtes par pod depuis le démarrage
hello_requests_total

# Temps de réponse moyen en millisecondes
rate(flask_http_request_duration_seconds_sum[1m])
/ rate(flask_http_request_duration_seconds_count[1m]) * 1000
```

### Configurer Grafana (http://localhost:3000)

Les identifiants par défaut sont `admin` / `admin`. Pour connecter Prometheus, aller dans *Connections → Data sources → Add new data source → Prometheus*. Dans le champ URL, entrer **`http://prometheus:9090`** et non `http://localhost:9090`. Cette distinction est importante : Grafana tourne dans un conteneur et doit joindre Prometheus par son **nom de service Docker**, pas par l'interface de la machine hôte. Cliquer *Save & test* — le message "Successfully queried the Prometheus API" confirme que tout est connecté.

Pour créer un dashboard : *Dashboards → New → Add visualization*, puis coller la requête PromQL. Chaque pod apparaît avec une couleur différente grâce au label `pod` défini dans `app.py`.

---

## Projet 4 — CI/CD avec GitHub Actions 🚀

### Qu'est-ce que le CI/CD et pourquoi est-ce central en DevOps/SRE ?

**CI (Continuous Integration)** signifie que chaque fois qu'un développeur pousse du code, une série de vérifications automatiques s'exécute immédiatement : les tests passent-ils ? L'image Docker se build-elle correctement ? L'objectif est de détecter les problèmes au plus tôt, avant qu'ils n'atteignent la production.

**CD (Continuous Deployment)** va plus loin : si la CI réussit, le code est automatiquement déployé en production sans intervention humaine. En pratique, beaucoup d'équipes font du *Continuous Delivery* (une validation manuelle finale avant le déploiement) plutôt que du déploiement totalement automatique.

La pipeline complète qu'on a construite :

```
git push
    ↓
GitHub Actions déclenché automatiquement
    ↓
Job 1 — CI :
  ├── Checkout du code
  ├── Installation des dépendances Python
  ├── Exécution des tests (pytest)
  ├── Build de l'image Docker
  └── Push vers GitHub Container Registry (ghcr.io)
    ↓
Job 2 — CD (si CI réussit, sur branche main uniquement) :
  ├── kubectl set image (déploiement de la nouvelle image)
  └── kubectl rollout status (vérification du déploiement)
    ↓
Prometheus détecte les nouveaux pods
    ↓
Grafana affiche les métriques en temps réel
```

### test_app.py — les tests automatisés

```python
import pytest
from app import app

# pytest.fixture crée un "client de test" Flask réutilisable dans tous les tests
# Flask simule des requêtes HTTP sans démarrer un vrai serveur
@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_hello_returns_200(client):
    """L'endpoint principal doit répondre avec un statut HTTP 200."""
    response = client.get('/')
    assert response.status_code == 200

def test_hello_contains_bonjour(client):
    """La réponse doit contenir le mot 'Bonjour'."""
    response = client.get('/')
    assert b'Bonjour' in response.data

def test_health_endpoint(client):
    """L'endpoint /health doit retourner status: ok."""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ok'

def test_metrics_endpoint(client):
    """L'endpoint /metrics doit être accessible (Prometheus le scrape en permanence)."""
    response = client.get('/metrics')
    assert response.status_code == 200
```

### .github/workflows/ci-cd.yml — le workflow complet

```yaml
name: CI/CD Pipeline

# Déclencheurs : à chaque push sur main et sur les Pull Requests
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  # ghcr.io = GitHub Container Registry
  # ${{ github.repository }} = "ton-username/docker-app" (automatique)
  IMAGE_NAME: ghcr.io/${{ github.repository }}/mon-api

jobs:
  # ─────────────────────────────────────────────────
  # JOB 1 : Intégration Continue
  # ─────────────────────────────────────────────────
  ci:
    name: Build & Test
    runs-on: ubuntu-latest   # GitHub fournit une VM Ubuntu gratuite

    steps:
      # Étape 1 : récupérer le code du dépôt dans la VM
      - name: Checkout du code
        uses: actions/checkout@v4

      # Étape 2 : installer Python dans la VM
      - name: Installer Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      # Étape 3 : installer les dépendances
      - name: Installer les dépendances
        run: pip install -r requirements.txt

      # Étape 4 : lancer les tests — si un test échoue, la pipeline s'arrête ici
      - name: Lancer les tests pytest
        run: pytest test_app.py -v

      # Étape 5 : se connecter au GitHub Container Registry
      # ${{ secrets.GITHUB_TOKEN }} est fourni automatiquement par GitHub
      - name: Login vers GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # Étape 6 : extraire les métadonnées pour tagger l'image
      # Le tag SHA du commit permet de tracer exactement quelle version tourne en prod
      - name: Extraire les métadonnées Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest,enable={{is_default_branch}}

      # Étape 7 : builder ET pousser l'image vers le registry
      - name: Build et Push de l'image Docker
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}

  # ─────────────────────────────────────────────────
  # JOB 2 : Déploiement Continu
  # S'exécute seulement si CI réussit, seulement sur main
  # ─────────────────────────────────────────────────
  cd:
    name: Deploy
    runs-on: ubuntu-latest
    needs: ci                           # Attend que ci réussisse
    if: github.ref == 'refs/heads/main' # Ne déploie que depuis main

    steps:
      - name: Checkout du code
        uses: actions/checkout@v4

      - name: Déploiement sur Kubernetes
        run: |
          echo "✅ Image déployée : ${{ env.IMAGE_NAME }}:sha-${{ github.sha }}"
          echo "📋 Commandes exécutées sur un vrai cluster :"
          echo "   kubectl set image deployment/mon-api-deployment mon-api=${{ env.IMAGE_NAME }}:sha-${{ github.sha }}"
          echo "   kubectl rollout status deployment/mon-api-deployment"
```

### Pousser sur GitHub et observer la pipeline

```bash
# Initialiser Git si ce n'est pas encore fait
git init
git add .
git commit -m "feat: add monitoring and CI/CD pipeline"

# Connecter au dépôt GitHub (remplace avec ton URL)
git remote add origin https://github.com/ton-username/docker-app.git
git branch -M main
git push -u origin main
```

Dans l'onglet **Actions** de ton dépôt GitHub, tu verras le workflow s'exécuter en temps réel. Si un test échoue, la pipeline s'arrête et tu reçois une notification — c'est exactement le comportement attendu d'un vrai système CI/CD.

### Vérifier l'image dans le registry

Une fois la pipeline terminée, va dans *Packages* sur ton profil GitHub. L'image `mon-api` sera présente avec deux tags : `latest` et `sha-xxxxxxx`. Ce tag par SHA est fondamental en SRE : il permet de savoir **exactement quel commit tourne en production** à n'importe quel moment, et de revenir en arrière en cas de problème.

```bash
# Utiliser l'image depuis n'importe quelle machine
docker pull ghcr.io/ton-username/docker-app/mon-api:latest
```

### Le flux de travail DevOps complet

À partir de maintenant, ton workflow ressemble à ceci : tu modifies `app.py`, tu écris le test correspondant dans `test_app.py`, tu fais `git push`. GitHub Actions exécute les tests, construit la nouvelle image, la pousse avec un tag unique, et déploie sur Kubernetes — sans que tu aies rien fait manuellement. Prometheus détecte les nouveaux pods. Grafana affiche les métriques. C'est le cœur du métier DevOps/SRE : **l'automatisation au service de la fiabilité**.

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry-1.docker.io: i/o timeout`

**Symptôme :** Docker ne peut pas télécharger les images depuis Docker Hub. **Cause :** Le daemon Docker utilise le DNS de Minikube (`192.168.49.1`) qui ne route pas vers Internet.

```bash
sudo nano /etc/docker/daemon.json
# Contenu : { "dns": ["8.8.8.8", "8.8.4.4"] }
sudo systemctl restart docker

# Alternative immédiate sans modifier la config :
docker build --network=host -t mon-api:v1 .
```

### 2. `dial tcp 192.168.49.2:2376: connect: no route to host`

**Symptôme :** `docker` essaie de se connecter à Minikube au lieu du Docker local. **Cause :** La variable `DOCKER_HOST` pointe encore vers Minikube suite à un `eval $(minikube docker-env)` non annulé.

```bash
eval $(minikube docker-env --unset)
docker info   # Doit afficher le Docker local
```

### 3. `ErrImageNeverPull`

**Symptôme :** Les Pods Kubernetes restent en erreur. **Cause :** L'image existe dans le registre Docker local mais pas dans celui de Minikube — ce sont deux registres séparés.

```bash
minikube image load mon-api:v1
minikube image ls | grep mon-api
kubectl get pods -w   # Les pods passent automatiquement en Running
```

### 4. `kubectl : commande introuvable`

```bash
sudo snap install kubectl --classic
# OU
echo "alias kubectl='minikube kubectl --'" >> ~/.bashrc && source ~/.bashrc
```

### 5. Grafana ne se connecte pas à Prometheus

**Cause :** Utilisation de `localhost` au lieu du nom de service Docker dans l'URL. Dans un réseau Docker Compose, les conteneurs se joignent par leur **nom de service**, pas par localhost.

```
❌ http://localhost:9090
✅ http://prometheus:9090
```

---

## Comparaison Docker vs Kubernetes

| Aspect | Docker | Kubernetes |
|--------|--------|------------|
| **Complexité** | Simple, facile à démarrer | Complexe, courbe d'apprentissage importante |
| **Cas d'usage** | Dev local, petits projets | Production, applications à grande échelle |
| **Scaling** | Manuel (`docker run` plusieurs fois) | Automatique (`replicas: 5` dans le YAML) |
| **Résilience** | Aucune — conteneur mort = mort | Automatique — Controller-Manager recrée les Pods |
| **Load balancing** | Manuel ou via Docker Compose | Intégré dans les Services |
| **Service Discovery** | Manuel ou via Docker Compose | Natif avec les Services et labels |
| **Configuration** | `docker run` ou `docker-compose.yml` | Fichiers YAML déclaratifs |
| **Monitoring** | `docker stats`, `docker logs` | `kubectl describe`, Prometheus, Grafana |
| **Réseau** | Bridge network par défaut | CNI (Container Network Interface) |
| **Philosophie** | **Impératif** — tu dis *comment* faire | **Déclaratif** — tu dis *quoi* tu veux |

La différence philosophique fondamentale est celle-ci : avec Docker, tu **commandes** ("lance ce conteneur sur ce port"). Avec Kubernetes, tu **déclares** ("je veux 3 instances toujours disponibles") et le système s'occupe du reste en permanence, même si des pods plantent ou si des nœuds tombent.

---

## Glossaire

| Terme | Définition |
|-------|------------|
| **Image** | Template immuable à partir duquel on crée des conteneurs. Analogue à une classe en POO. |
| **Conteneur** | Instance en cours d'exécution d'une image. Analogue à un objet instancié. |
| **Dockerfile** | Fichier de recette pour construire une image, instruction par instruction. |
| **Layer (couche)** | Chaque instruction du Dockerfile crée une couche mise en cache. |
| **Registry** | Stockage d'images Docker (Docker Hub, GitHub Container Registry...). |
| **Pod** | Unité de base dans Kubernetes — un ou plusieurs conteneurs partageant réseau et stockage. |
| **Deployment** | Ressource K8s qui gère la création et mise à jour d'un ensemble de Pods. |
| **Service** | Ressource K8s qui expose des Pods avec une adresse stable et fait du load balancing. |
| **Master Node** | Cerveau du cluster K8s — API Server, Scheduler, Controller-Manager, etcd. |
| **Worker Node** | Machine qui exécute réellement les conteneurs (Pods). |
| **Kubelet** | Agent sur chaque Worker Node qui reçoit les ordres du Master et gère les Pods. |
| **etcd** | Base de données clé-valeur distribuée qui stocke tout l'état du cluster K8s. |
| **Controller-Manager** | Boucle de contrôle qui maintient l'état réel = état désiré en permanence. |
| **Scheduler** | Composant qui décide sur quel Worker Node placer un nouveau Pod. |
| **Prometheus** | Système de monitoring qui scrape les métriques des applications à intervalles réguliers. |
| **Grafana** | Outil de visualisation qui crée des dashboards à partir des données Prometheus. |
| **PromQL** | Langage de requête de Prometheus pour interroger et agréger les métriques. |
| **Scraping** | Mécanisme pull de Prometheus : il va chercher les métriques plutôt qu'elles lui soient poussées. |
| **Counter** | Métrique Prometheus qui ne fait que monter (requêtes, erreurs...). |
| **Gauge** | Métrique Prometheus qui peut monter et descendre (CPU, mémoire...). |
| **CI (Continuous Integration)** | Automatisation des tests et builds à chaque push de code. |
| **CD (Continuous Deployment)** | Déploiement automatique en production si la CI réussit. |
| **GitHub Actions** | Plateforme CI/CD intégrée à GitHub, déclenchée par des événements Git. |
| **ghcr.io** | GitHub Container Registry — stockage d'images Docker intégré à GitHub. |
| **SHA du commit** | Identifiant unique d'un commit Git, utilisé pour tagger les images Docker en production. |
| **kubectl** | CLI pour interagir avec l'API Server de Kubernetes. |
| **Minikube** | Outil qui crée un cluster Kubernetes complet en local pour le développement. |
| **YAML** | Format de fichier de configuration utilisé par Kubernetes et GitHub Actions. |
| **Label** | Paire clé-valeur attachée à une ressource K8s pour l'organisation et la sélection. |
| **NodePort** | Type de Service qui expose l'application sur un port fixe de chaque nœud. |
| **imagePullPolicy: Never** | Directive K8s pour ne jamais télécharger l'image depuis internet. |
| **liveness probe** | Vérification périodique par Kubernetes qu'un Pod est toujours vivant (via /health). |
| **rate()** | Fonction PromQL qui calcule le taux de variation d'un compteur par seconde. |

---

*Projet réalisé sur Ubuntu 24 — Docker 27.x — Minikube 1.35.1 — kubectl 1.34.4 — Prometheus latest — Grafana latest — GitHub Actions*