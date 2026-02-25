# 🐳 Docker & ☸️ Kubernetes — Guide Pratique Complet

> Projet d'apprentissage progressif des architectures de conteneurisation et DevOps/SRE,
> basé sur le déploiement d'une API Flask simple à travers quatre couches de complexité croissante.

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

Ce projet explore les grandes pratiques DevOps/SRE en déployant la **même application** (une API Python/Flask) avec Docker, Kubernetes, en la monitorant avec Prometheus & Grafana, et en automatisant tout avec GitHub Actions. Chaque couche s'appuie sur la précédente — Docker est la fondation, Kubernetes apporte la résilience, Prometheus & Grafana apportent la visibilité, et GitHub Actions automatise tout le cycle de vie.

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
       ↓                         ┌──────────────────────┐
  Prometheus ◄────────────────── │ Pods [📦][📦][📦]    │
  (scrape 15s)                   │ /metrics sur chaque  │
       ↓                         └──────────────────────┘
  Grafana                                   ↓
  (dashboards)                    Service Discovery
                                            ↓
                                      Running App

CI/CD (GitHub Actions)
──────────────────────────────────────────────────────
git push → Tests → Build Image → Push ghcr.io → kubectl deploy
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
| GitHub Actions | CI/CD automatisé | — |

### Installation de Docker

```bash
# Sur Ubuntu/Debian
sudo apt update && sudo apt install docker.io -y
sudo systemctl enable docker && sudo systemctl start docker

# Ajouter son utilisateur au groupe docker (évite de taper sudo à chaque fois)
sudo usermod -aG docker $USER
newgrp docker

# Vérifier l'installation
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
# Via snap (Ubuntu) — le --classic est obligatoire pour accéder au kubeconfig
sudo snap install kubectl --classic

# OU via alias Minikube (garantit la compatibilité de version)
echo "alias kubectl='minikube kubectl --'" >> ~/.bashrc
source ~/.bashrc

# Vérifier la connexion au cluster
kubectl get nodes
# NAME       STATUS   ROLES           AGE   VERSION
# minikube   Ready    control-plane   5m    v1.35.1
```

---

## L'application commune

Les quatre projets utilisent la même application Flask. C'est intentionnel : cela permet de se concentrer sur les **outils et l'infrastructure** plutôt que sur le code, et de comparer concrètement ce que chaque couche apporte.

### Structure du projet

```
docker-app/
├── app.py                        # API Flask avec métriques Prometheus
├── requirements.txt              # Dépendances Python
├── test_app.py                   # Tests automatisés (pytest)
├── Dockerfile                    # Instructions de build de l'image
├── docker-compose.yml            # Stack complète : API + Prometheus + Grafana
├── prometheus.yml                # Configuration du scraping Prometheus
├── deployment.yaml               # Déclaration Kubernetes — Pods & réplicas
├── service.yaml                  # Déclaration Kubernetes — Service Discovery
├── .github/
│   └── workflows/
│       └── ci-cd.yml             # Pipeline GitHub Actions (CI + CD)
└── README.md
```

### app.py — l'API Flask instrumentée

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

# Métrique "métier" personnalisée — un Counter ne fait que monter
# Le label 'pod' permet de distinguer quel pod répond dans Grafana
hello_counter = metrics.counter(
    'hello_requests_total',
    'Nombre total de requêtes sur /',
    labels={'pod': lambda: socket.gethostname()}
)

@app.route("/")
@hello_counter  # Chaque appel à / incrémente automatiquement le compteur
def hello():
    return f"Bonjour depuis le pod : {socket.gethostname()}\n"

# Endpoint de santé — Kubernetes s'en sert pour vérifier qu'un pod est vivant
@app.route("/health")
def health():
    return {"status": "ok", "pod": socket.gethostname()}

if __name__ == "__main__":
    # host="0.0.0.0" = écouter sur toutes les interfaces réseau
    # Sans ça, Flask n'est accessible que depuis l'intérieur du conteneur
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

### Le Dockerfile — chaque ligne compte

```dockerfile
# Image de base : Python 3.11 sur Alpine Linux (~5 Mo vs ~900 Mo pour python:3.11)
# En production, la taille de l'image impacte directement la vitesse de déploiement
FROM python:3.11-alpine

# Répertoire de travail à l'intérieur du conteneur
# Toutes les commandes COPY, RUN, CMD qui suivent s'exécutent depuis /app
WORKDIR /app

# ORDRE STRATÉGIQUE : requirements.txt avant app.py
# Docker met chaque couche en cache. Si on modifie app.py mais pas requirements.txt,
# Docker réutilise la couche "pip install" depuis le cache — build 10x plus rapide
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout 100

# Le code arrive en dernier pour maximiser l'utilisation du cache
COPY app.py .

# EXPOSE documente le port — c'est de la documentation, pas une ouverture réelle
EXPOSE 5000

CMD ["python", "app.py"]
```

La structure des couches Docker est un concept fondamental à bien comprendre. Chaque instruction crée une couche immuable qui est mise en cache. Docker compare le contenu de chaque couche à celle du build précédent : si rien n'a changé, il réutilise le cache. C'est pourquoi l'ordre des instructions n'est pas anodin — on va toujours du plus stable (image de base, dépendances) au plus changeant (code source).

```
IMAGE mon-api:v1
├── Couche 4 : COPY app.py           ← invalidée à chaque modif de code
├── Couche 3 : RUN pip install       ← réutilisée si requirements.txt inchangé
├── Couche 2 : COPY requirements.txt ← réutilisée si inchangé
├── Couche 1 : WORKDIR /app
└── Couche 0 : python:3.11-alpine    ← téléchargée une seule fois
```

### Construction et lancement

```bash
# Builder l'image (--network=host si problème DNS avec Minikube)
docker build --network=host -t mon-api:v1 .

# Lancer 3 conteneurs — chacun isolé avec sa propre identité réseau
docker run -d -p 8081:5000 --name api1 mon-api:v1
docker run -d -p 8082:5000 --name api2 mon-api:v1
docker run -d -p 8083:5000 --name api3 mon-api:v1

# Chaque réponse affiche un ID de conteneur différent — c'est l'isolation en action
curl http://localhost:8081   # Bonjour depuis le pod : a3f2c1b8d904
curl http://localhost:8082   # Bonjour depuis le pod : b7e9c2f1a203
curl http://localhost:8083   # Bonjour depuis le pod : c1d4e8b5f306
```

Le port mapping `-p 8081:5000` suit la logique `[port_machine_hôte]:[port_dans_le_conteneur]`. Flask écoute sur 5000 à l'intérieur du conteneur, mais on y accède via 8081 depuis l'extérieur. Trois conteneurs peuvent tous écouter sur 5000 en interne car ils sont isolés, mais ils doivent avoir des ports différents sur la machine hôte.

### Commandes Docker essentielles

```bash
docker ps                    # Conteneurs en cours d'exécution
docker ps -a                 # Tous les conteneurs, y compris arrêtés
docker logs -f api1          # Logs en temps réel (Ctrl+C pour quitter)
docker exec -it api1 sh      # Shell interactif à l'intérieur du conteneur
docker stats                 # CPU, mémoire, réseau en temps réel
docker stop api1 api2 api3   # Arrêter proprement
docker rm api1 api2 api3     # Supprimer les conteneurs arrêtés
docker rmi mon-api:v1        # Supprimer l'image
```

### Docker Compose — déclarer plutôt que commander

```yaml
# docker-compose.yml (version sans monitoring, pour référence)
version: "3.8"
services:
  api1:
    build: .
    ports:
      - "8081:5000"
  api2:
    build: .
    ports:
      - "8082:5000"
  api3:
    build: .
    ports:
      - "8083:5000"
```

```bash
docker compose up -d --build   # Démarrer avec rebuild
docker compose logs -f          # Logs de tous les services
docker compose ps               # État de chaque service
docker compose down             # Tout arrêter et supprimer
```

---

## Projet 2 — Kubernetes ☸️

### Architecture du cluster Minikube

Minikube crée un cluster Kubernetes complet sur ta machine. Même si tout tourne localement, l'architecture est identique à un vrai cluster de production.

```
Ta machine
└── Minikube (VM ou conteneur)
    ├── Master Node (control-plane)
    │   ├── API Server         → point d'entrée de toutes les commandes kubectl
    │   ├── etcd               → base de données clé-valeur (l'état du cluster)
    │   ├── Controller-Manager → surveille et corrige l'état en permanence
    │   └── Scheduler          → décide sur quel Worker Node placer chaque Pod
    └── Worker Node
        ├── Kubelet            → agent qui exécute les ordres du Master
        ├── Container Runtime  → fait tourner les conteneurs (containerd)
        └── Pods               → unité de base : un ou plusieurs conteneurs
```

### deployment.yaml — l'état désiré

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mon-api-deployment
spec:
  replicas: 3  # Je déclare vouloir 3 Pods — le Controller-Manager s'en assure en permanence
  selector:
    matchLabels:
      app: mon-api
  template:
    metadata:
      labels:
        app: mon-api  # Label appliqué à chaque Pod — le Service s'en sert pour router le trafic
    spec:
      containers:
      - name: mon-api
        image: mon-api:v1
        imagePullPolicy: Never  # Ne pas chercher l'image sur internet, utiliser le registre local
        ports:
        - containerPort: 5000
```

### service.yaml — le Service Discovery

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mon-api-service
spec:
  type: NodePort  # ClusterIP (interne) | NodePort (dev local) | LoadBalancer (cloud)
  selector:
    app: mon-api  # Route automatiquement vers tous les Pods portant ce label
  ports:
  - port: 5000
    targetPort: 5000
    nodePort: 30080  # Port fixe exposé sur le nœud (plage autorisée : 30000-32767)
```

### Déploiement, résilience et scaling

```bash
# Charger l'image dans le registre interne de Minikube (registres séparés !)
minikube image load mon-api:v1

# Envoyer les déclarations à l'API Server du Master Node
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Observer les Pods démarrer en temps réel
kubectl get pods -w

# ── TEST DE RÉSILIENCE ──────────────────────────────────────────────────────
# Supprimer un Pod volontairement — le Controller-Manager en recrée un immédiatement
kubectl delete pod <nom-du-pod>
kubectl get pods -w
# → STATUS : Terminating puis Pending puis Running en quelques secondes

# ── SCALING ─────────────────────────────────────────────────────────────────
kubectl scale deployment mon-api-deployment --replicas=5
kubectl get pods   # 5 pods actifs

# ── ACCÈS ───────────────────────────────────────────────────────────────────
minikube service mon-api-service --url
# Appeler plusieurs fois : le pod qui répond change → load balancing automatique
```

### Commandes kubectl de référence

```bash
kubectl get nodes/pods/deployments/services/all  # Lister les ressources
kubectl describe pod <nom>                        # Détails complets + historique des événements
kubectl logs -f <nom>                             # Logs en temps réel
kubectl exec -it <nom> -- sh                      # Shell interactif dans le Pod
kubectl apply -f fichier.yaml                     # Créer ou mettre à jour une ressource
kubectl delete -f fichier.yaml                    # Supprimer via fichier YAML
kubectl scale deployment <nom> --replicas=N       # Changer le nombre de réplicas
minikube dashboard                                # Interface web graphique complète
eval $(minikube docker-env)                       # Pointer Docker vers le registre Minikube
eval $(minikube docker-env --unset)               # Revenir au Docker local
```

---

## Projet 3 — Monitoring avec Prometheus & Grafana 📊

### Pourquoi le monitoring est fondamental en SRE

Un SRE (Site Reliability Engineer) ne déploie jamais à l'aveugle. Le monitoring répond à la question permanente : **"est-ce que ce que j'ai déployé fonctionne correctement en ce moment ?"**. Sans monitoring, un problème en production peut exister pendant des heures avant qu'un utilisateur ne le signale. Avec Prometheus & Grafana, on le détecte en secondes.

```
API Flask (/metrics)  →  Prometheus (scrape toutes 15s)  →  Grafana (dashboards)
```

### Les quatre types de métriques Prometheus

Il est important de choisir le bon type selon ce qu'on mesure. Un **Counter** ne fait que monter — c'est le bon choix pour compter les requêtes, les erreurs, les paiements traités. Une **Gauge** peut monter et descendre — parfaite pour le CPU, la mémoire, le nombre de connexions actives. Un **Histogram** mesure la distribution des valeurs dans des "buckets" — idéal pour les temps de réponse (combien de requêtes sous 100ms ? sous 500ms ?). Un **Summary** est similaire à l'Histogram mais calcule des quantiles côté client plutôt que côté serveur.

### PromQL — le langage de requête

PromQL est le langage qu'on utilise pour interroger Prometheus, que ce soit dans son interface ou dans Grafana. Sa fonction la plus importante est `rate()` qui calcule le taux de variation d'un Counter par seconde sur une fenêtre glissante. Par exemple, `rate(hello_requests_total[1m])` donne le nombre de requêtes par seconde sur la dernière minute — c'est la métrique fondamentale qu'un SRE surveille pour détecter un pic ou une chute de trafic.

```promql
# Taux de requêtes par seconde par pod (fenêtre glissante de 1 minute)
rate(hello_requests_total[1m])

# Nombre total de requêtes depuis le démarrage, par pod
hello_requests_total

# Temps de réponse moyen en millisecondes
rate(flask_http_request_duration_seconds_sum[1m])
/ rate(flask_http_request_duration_seconds_count[1m]) * 1000
```

### prometheus.yml

```yaml
global:
  scrape_interval: 15s  # Prometheus interroge chaque cible toutes les 15 secondes

scrape_configs:
  - job_name: 'mon-api'
    static_configs:
      # Ces noms sont les noms de services Docker Compose
      # Sur le réseau interne Docker, chaque service est joignable par son nom
      - targets: ['api1:5000', 'api2:5000', 'api3:5000']
```

### docker-compose.yml complet avec monitoring

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
      # On injecte notre fichier de config dans le conteneur
      # Syntaxe : [chemin sur la machine hôte]:[chemin dans le conteneur]
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
      # Volume nommé : les dashboards persistent entre les redémarrages
      - grafana-data:/var/lib/grafana
    depends_on:
      - prometheus

volumes:
  grafana-data:
```

### Lancement et exploration

```bash
# Démarrer tout le stack avec rebuild (important après modif de app.py)
docker compose up -d --build

# Générer du trafic pour alimenter les compteurs
for i in {1..20}; do
  curl -s http://localhost:8081
  curl -s http://localhost:8082
  curl -s http://localhost:8083
done

# Vérifier que les métriques sont exposées
curl http://localhost:8081/metrics | grep hello_requests
```

Dans **Prometheus** (`http://localhost:9090`), aller dans *Status → Targets* : les 3 APIs doivent être en vert avec le statut `UP`. C'est la confirmation que Prometheus scrape bien chaque pod.

Dans **Grafana** (`http://localhost:3000`, identifiants `admin/admin`), aller dans *Connections → Data sources → Add new data source → Prometheus*. L'URL doit être `http://prometheus:9090` et non `http://localhost:9090` — Grafana tourne dans un conteneur et doit joindre Prometheus par son **nom de service Docker**, pas par l'interface de la machine hôte. Après avoir cliqué *Save & test*, créer un dashboard avec la requête PromQL `rate(hello_requests_total[1m])` pour voir le trafic par pod en temps réel.

---

## Projet 4 — CI/CD avec GitHub Actions 🚀

### Le concept fondamental du CI/CD

**CI (Continuous Integration)** signifie que chaque push de code déclenche automatiquement des vérifications : les tests passent-ils ? L'image se build-elle ? L'objectif est de détecter les problèmes au plus tôt, avant qu'ils n'atteignent la production — le coût d'un bug augmente exponentiellement plus il est détecté tard.

**CD (Continuous Deployment)** va plus loin : si la CI réussit, le code est automatiquement déployé en production. En pratique, beaucoup d'équipes font du *Continuous Delivery* (une validation manuelle finale) plutôt que du déploiement totalement automatique pour les systèmes critiques.

La pipeline complète :

```
git push → GitHub Actions déclenché
    ↓
Job CI (ubuntu-latest, VM éphémère dans le cloud GitHub)
  ├── Checkout du code
  ├── Installation Python + dépendances
  ├── pytest (si échec → pipeline stoppée, CD ne s'exécute jamais)
  ├── Login vers ghcr.io (GitHub Container Registry)
  ├── Build de l'image Docker
  └── Push avec deux tags : latest + sha-<commit>
    ↓ (seulement si CI réussit ET branche main)
Job CD
  └── Simulation du déploiement Kubernetes avec les commandes kubectl
```

### test_app.py — les tests sont la fondation du CI

```python
import pytest
from app import app

# pytest.fixture crée un client de test Flask réutilisable dans tous les tests
# Flask simule les requêtes HTTP sans démarrer un vrai serveur — les tests sont rapides
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
    assert response.get_json()['status'] == 'ok'

def test_metrics_endpoint(client):
    """L'endpoint /metrics doit être accessible — Prometheus le scrape en permanence."""
    response = client.get('/metrics')
    assert response.status_code == 200
```

Pour lancer les tests localement avant de pousser :
```bash
pytest test_app.py -v
# 4 passed in 0.55s  ← si tout est vert, on peut pusher en confiance
```

### .github/workflows/ci-cd.yml — le workflow complet et corrigé

```yaml
name: CI/CD Pipeline

# Déclencheurs : à chaque push sur main ET sur les Pull Requests (pour valider avant merge)
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  # github.repository = "stephdeve/docker-app" — injecté automatiquement par GitHub
  IMAGE_NAME: ghcr.io/${{ github.repository }}/mon-api

jobs:
  # ──────────────────────────────────────────────────────────
  # JOB 1 — Intégration Continue
  # Tourne sur une VM Ubuntu fraîche dans les datacenters GitHub
  # ──────────────────────────────────────────────────────────
  ci:
    name: Build & Test
    runs-on: ubuntu-latest

    steps:
      - name: Checkout du code
        uses: actions/checkout@v4

      - name: Installer Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Installer les dépendances
        run: pip install -r requirements.txt

      # Si un seul test échoue ici, le job s'arrête et CD ne s'exécutera jamais
      - name: Lancer les tests pytest
        run: pytest test_app.py -v

      # secrets.GITHUB_TOKEN est automatiquement fourni par GitHub pour chaque workflow
      # Pas besoin de le créer manuellement — c'est un mécanisme de sécurité natif
      - name: Login vers GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # Cette action extrait les métadonnées Git pour créer des tags d'image cohérents
      # Elle génère deux tags : "latest" et "sha-<7 premiers chars du commit>"
      - name: Extraire les métadonnées Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build et Push de l'image Docker
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}

  # ──────────────────────────────────────────────────────────
  # JOB 2 — Déploiement Continu
  # S'exécute SEULEMENT si CI réussit ET SEULEMENT sur la branche main
  # (les Pull Requests ne déclenchent pas le déploiement — sécurité)
  # ──────────────────────────────────────────────────────────
  cd:
    name: Deploy
    runs-on: ubuntu-latest
    needs: ci                           # Dépendance explicite : attend que ci réussisse
    if: github.ref == 'refs/heads/main' # Guard : ne déploie que depuis main

    steps:
      - name: Checkout du code
        uses: actions/checkout@v4

      # kubectl est installé dans la VM pour valider la syntaxe des commandes
      - name: Installer kubectl
        uses: azure/setup-kubectl@v3

      # NOTE : En environnement local (Minikube), on simule le déploiement
      # car la VM GitHub n'a pas accès à notre cluster Minikube sur notre machine.
      # En production réelle, on remplacerait ce step par une connexion au cluster
      # via un secret KUBECONFIG stocké dans les secrets du dépôt GitHub.
      - name: Simuler le déploiement Kubernetes
        run: |
          echo "🚀 Pipeline CI/CD complète avec succès !"
          echo ""
          echo "✅ Image construite et poussée :"
          echo "   ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}"
          echo ""
          echo "📋 En production (cluster accessible), ces commandes s'exécuteraient :"
          echo "   kubectl set image deployment/mon-api-deployment \\"
          echo "     mon-api=ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}"
          echo "   kubectl rollout status deployment/mon-api-deployment --timeout=120s"
          echo ""
          echo "🔍 Le tag SHA garantit la traçabilité exacte en production."
```

### Pourquoi le tag SHA est fondamental en SRE

Le tag `sha-xxxxxxx` est l'une des pratiques les plus importantes du déploiement fiable. Il permet de répondre à tout moment à la question "quelle version exacte tourne en production ?" avec une certitude absolue. Si un incident se produit, on peut immédiatement identifier le commit responsable et revenir en arrière avec `kubectl set image` en pointant vers le SHA du commit précédent. `latest` est pratique mais dangereux en production car il ne dit pas *quelle* version est déployée.

### Ce que ça donne en production réelle

Pour connecter le job CD à un vrai cluster, on ajouterait le kubeconfig du cluster dans les secrets GitHub (*Settings → Secrets → New repository secret*), puis on modifierait le step de déploiement ainsi :

```yaml
- name: Configurer kubectl vers le cluster de production
  run: |
    mkdir -p ~/.kube
    echo "${{ secrets.KUBECONFIG }}" > ~/.kube/config

- name: Déployer sur le cluster
  run: |
    kubectl set image deployment/mon-api-deployment \
      mon-api=ghcr.io/${{ github.repository }}/mon-api:sha-${{ github.sha }}
    # rollout status attend la fin du déploiement et échoue si les pods ne démarrent pas
    # C'est le filet de sécurité : si la nouvelle version plante, la pipeline échoue
    kubectl rollout status deployment/mon-api-deployment --timeout=120s
```

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry-1.docker.io: i/o timeout`

Docker ne peut pas télécharger les images depuis Docker Hub. La cause est que le daemon Docker utilise le DNS de Minikube (`192.168.49.1`) qui ne route pas vers Internet. La solution est d'éditer `/etc/docker/daemon.json` pour forcer les DNS publics de Google :

```bash
sudo nano /etc/docker/daemon.json
# Contenu : { "dns": ["8.8.8.8", "8.8.4.4"] }
sudo systemctl restart docker

# Alternative immédiate sans modifier la config permanente :
docker build --network=host -t mon-api:v1 .
```

### 2. `dial tcp 192.168.49.2:2376: connect: no route to host`

Docker essaie de se connecter à Minikube au lieu du Docker local. La cause est que la variable `DOCKER_HOST` pointe encore vers Minikube suite à un `eval $(minikube docker-env)` non annulé dans la session shell.

```bash
eval $(minikube docker-env --unset)
docker info   # Doit afficher le Docker local, pas celui de Minikube
```

### 3. `ErrImageNeverPull`

Les Pods Kubernetes restent en erreur faute d'image. La cause est que Docker et Minikube ont des registres d'images séparés — builder localement ne rend pas l'image disponible dans Minikube.

```bash
minikube image load mon-api:v1        # Transférer l'image
minikube image ls | grep mon-api      # Vérifier le transfert
kubectl get pods -w                   # Les pods passent automatiquement en Running
```

### 4. `kubectl : commande introuvable`

```bash
sudo snap install kubectl --classic
# OU via alias (garantit la compatibilité de version avec Minikube)
echo "alias kubectl='minikube kubectl --'" >> ~/.bashrc && source ~/.bashrc
```

### 5. Grafana ne se connecte pas à Prometheus

L'URL `http://localhost:9090` ne fonctionne pas depuis Grafana car Grafana tourne dans un conteneur Docker. `localhost` dans un conteneur désigne le conteneur lui-même, pas la machine hôte. Il faut utiliser le nom de service Docker : `http://prometheus:9090`.

### 6. `connection refused` sur `localhost:8080` dans GitHub Actions

Le job CD essaie d'exécuter `kubectl` sur la VM GitHub qui n'a pas de cluster Kubernetes. La VM est une machine vierge — sans Minikube, sans kubeconfig. La solution pour l'environnement local est de simuler les commandes kubectl avec `echo`. Pour un vrai cluster, il faudrait stocker le kubeconfig dans les secrets GitHub et configurer `kubectl` avant de déployer.

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

La différence philosophique fondamentale : avec Docker, tu **commandes** ("lance ce conteneur sur ce port avec ces paramètres"). Avec Kubernetes, tu **déclares** ("je veux 3 instances de mon API toujours disponibles") et le système s'occupe du *comment* en permanence, même si des pods plantent ou si des nœuds tombent.

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
| **Master Node** | Cerveau du cluster K8s — contient l'API Server, Scheduler, Controller-Manager, etcd. |
| **Worker Node** | Machine qui exécute réellement les conteneurs (Pods). |
| **Kubelet** | Agent sur chaque Worker Node qui reçoit les ordres du Master et gère les Pods. |
| **etcd** | Base de données clé-valeur distribuée qui stocke tout l'état du cluster K8s. |
| **Controller-Manager** | Boucle de contrôle qui maintient l'état réel = état désiré en permanence. |
| **Scheduler** | Composant qui décide sur quel Worker Node placer un nouveau Pod. |
| **Prometheus** | Système de monitoring qui scrape les métriques des applications à intervalles réguliers. |
| **Grafana** | Outil de visualisation qui crée des dashboards interactifs à partir des données Prometheus. |
| **PromQL** | Langage de requête de Prometheus pour interroger et agréger les métriques. |
| **Scraping** | Mécanisme pull de Prometheus : il va chercher les métriques plutôt qu'elles lui soient poussées. |
| **Counter** | Métrique Prometheus qui ne fait que monter (requêtes, erreurs, paiements...). |
| **Gauge** | Métrique Prometheus qui peut monter et descendre (CPU, mémoire, connexions actives...). |
| **Histogram** | Métrique Prometheus qui mesure la distribution des valeurs dans des buckets (temps de réponse). |
| **rate()** | Fonction PromQL qui calcule le taux de variation d'un Counter par seconde sur une fenêtre glissante. |
| **CI (Continuous Integration)** | Automatisation des tests et builds à chaque push de code. |
| **CD (Continuous Deployment)** | Déploiement automatique en production si la CI réussit. |
| **GitHub Actions** | Plateforme CI/CD intégrée à GitHub, déclenchée par des événements Git (push, PR...). |
| **ghcr.io** | GitHub Container Registry — stockage d'images Docker intégré à GitHub. |
| **SHA du commit** | Identifiant unique d'un commit Git, utilisé pour tagger les images et garantir la traçabilité en production. |
| **kubeconfig** | Fichier de configuration kubectl contenant l'adresse du cluster et les credentials d'accès. |
| **kubectl rollout status** | Commande qui attend la fin d'un déploiement et échoue si les pods ne démarrent pas. |
| **liveness probe** | Vérification périodique par Kubernetes qu'un Pod est toujours vivant (via /health). |
| **imagePullPolicy: Never** | Directive K8s pour ne jamais télécharger l'image depuis internet — utiliser le registre local. |
| **NodePort** | Type de Service qui expose l'application sur un port fixe de chaque nœud (30000-32767). |
| **Label** | Paire clé-valeur attachée à une ressource K8s pour l'organisation et la sélection par les Services. |

---

*Projet réalisé sur Ubuntu 24 — Docker 27.x — Minikube 1.35.1 — kubectl 1.34.4 — Prometheus latest — Grafana latest — GitHub Actions*