# 🐳 De Docker à Kubernetes en Production — Guide Narratif Complet

> Ce guide raconte une histoire : le parcours d'une application Flask simple qui grandit,
> rencontre des problèmes réels, et adopte les outils qui les résolvent.
> Chaque projet est autonome et se suffit à lui-même.
> Chaque transition vers le projet suivant est justifiée par un problème concret.

---

## 📋 Table des matières

1. [L'application — ce qu'on déploie](#lapplication--ce-quon-déploie)
2. [Projet 1 — Docker : isoler une application](#projet-1--docker--isoler-une-application-)
3. [Projet 2 — Docker Compose : orchestrer plusieurs conteneurs](#projet-2--docker-compose--orchestrer-plusieurs-conteneurs-)
4. [Projet 3 — Kubernetes : passer à la production](#projet-3--kubernetes--passer-à-la-production-)
5. [Projet 4 — Monitoring : savoir ce qui se passe](#projet-4--monitoring--savoir-ce-qui-se-passe-)
6. [Projet 5 — CI/CD : automatiser le déploiement](#projet-5--cicd--automatiser-le-déploiement-)
7. [Projet 6 — ConfigMaps, Secrets & PostgreSQL : séparer la config du code](#projet-6--configmaps-secrets--postgresql--séparer-la-config-du-code-)
8. [Projet 7 — Ingress & HTTPS : exposer proprement](#projet-7--ingress--https--exposer-proprement-)
9. [Projet 8 — Helm : packager et versionner](#projet-8--helm--packager-et-versionner-)
10. [Projet 9 — CI/CD cloud réel : GKE, OCI, k3s+ngrok](#projet-9--cicd-cloud-réel-)
11. [Problèmes rencontrés & Solutions](#problèmes-rencontrés--solutions)
12. [Glossaire](#glossaire)

---

## L'application — ce qu'on déploie

Avant de parler d'outils, parlons de ce qu'on déploie. L'application est une **API web en Python/Flask** — un serveur qui répond à des requêtes HTTP. C'est volontairement simple pour que l'application ne soit jamais le sujet. Le sujet, c'est comment on la déploie, comment on la rend fiable, comment on la monitore, et comment on l'automatise.

Au fil des projets, l'application s'enrichit de nouvelles fonctionnalités pour illustrer les concepts :

```python
# app.py — version finale complète

from flask import Flask, jsonify
import socket, os
import psycopg2
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
metrics = PrometheusMetrics(app)

# Compteur Prometheus — chaque requête sur / est enregistrée
hello_counter = metrics.counter(
    'hello_requests_total',
    'Nombre total de requêtes sur /',
    labels={'pod': lambda: socket.gethostname()}   # Quel pod a répondu ?
)

# Toute la configuration vient des variables d'environnement
# Jamais hardcodée dans le code — principe fondamental du 12-Factor App
APP_ENV     = os.environ.get("APP_ENV", "development")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = os.environ.get("DB_PORT", "5432")
DB_NAME     = os.environ.get("DB_NAME", "appdb")
DB_USER     = os.environ.get("DB_USER", "appuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD")   # Pas de valeur par défaut pour les secrets

@app.route("/")
@hello_counter
def hello():
    # socket.gethostname() retourne le nom du Pod dans Kubernetes
    # Ce qui permet de voir quel pod a répondu à chaque requête
    return f"Bonjour depuis {socket.gethostname()} [env: {APP_ENV}, v{APP_VERSION}]\n"

@app.route("/health")
def health():
    # Endpoint de santé — Kubernetes s'en sert pour savoir si le Pod est prêt
    return {"status": "ok", "pod": socket.gethostname(), "env": APP_ENV}

@app.route("/config")
def config():
    # Affiche la configuration active — utile pour débugger en production
    return jsonify({
        "app_env": APP_ENV,
        "app_version": APP_VERSION,
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_name": DB_NAME,
        "db_user": DB_USER,
        "db_password": "***" if DB_PASSWORD else "NOT SET"   # Ne jamais exposer les secrets !
    })

@app.route("/db-test")
def db_test():
    # Test de connexion PostgreSQL — vérifie que l'app communique bien avec la DB
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

```
# requirements.txt
Flask==3.1.0
prometheus-flask-exporter==0.23.1
psycopg2-binary==2.9.9
pytest==8.3.5
```

```python
# test_app.py — les tests automatisés
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_hello(client):
    response = client.get('/')
    assert response.status_code == 200

def test_health(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'

def test_config(client):
    response = client.get('/config')
    assert response.status_code == 200

def test_metrics(client):
    response = client.get('/metrics')
    assert response.status_code == 200
```

---

## Projet 1 — Docker : isoler une application 🐳

### Le problème que Docker résout

Avant Docker, déployer une application Python sur un serveur était une aventure. Le développeur travaille sur Ubuntu 22, le serveur de production tourne sur CentOS 7, le collègue est sur macOS. Chacun a une version différente de Python, des bibliothèques différentes, des chemins différents. La phrase redoutée : **"ça marchait sur ma machine"**.

Le problème fondamental est que l'application et son environnement d'exécution sont séparés. On livre le code, pas l'environnement.

**Docker résout ça en livrant les deux ensemble.** Une image Docker est un paquet autonome qui contient le code, le runtime Python, les bibliothèques, et la configuration système nécessaire. Elle s'exécute de façon identique sur n'importe quelle machine qui a Docker installé.

### Comment Docker fonctionne

Docker utilise les **namespaces** et les **cgroups** du kernel Linux pour isoler les processus. Un conteneur n'est pas une machine virtuelle — il n'y a pas de kernel séparé, pas de démarrage d'OS. C'est un processus Linux isolé qui croit qu'il est seul sur la machine. C'est pour ça que les conteneurs démarrent en millisecondes, contrairement aux VMs qui mettent des dizaines de secondes.

```
Ta machine Ubuntu
├── Kernel Linux (partagé)
├── Conteneur api1
│   ├── Python 3.11
│   ├── Flask + dépendances
│   └── app.py
├── Conteneur api2
│   ├── Python 3.11   (copie isolée, indépendante)
│   ├── Flask + dépendances
│   └── app.py
└── (les deux conteneurs ne se voient pas l'un l'autre)
```

### Le Dockerfile — la recette de l'image

```dockerfile
# On part d'une image de base officielle — Python 3.11 sur Alpine Linux
# Alpine est une distribution minimaliste (~5 Mo vs ~900 Mo pour Ubuntu)
# ce qui rend l'image finale beaucoup plus légère et plus sécurisée
FROM python:3.11-alpine

# Définir le répertoire de travail dans le conteneur
# Toutes les commandes suivantes s'exécutent depuis /app
WORKDIR /app

# IMPORTANT : on copie requirements.txt AVANT app.py
# Docker construit les images en couches (layers) — chaque instruction est une couche
# Si une couche n'a pas changé depuis le dernier build, Docker réutilise le cache
# En copiant requirements.txt en premier, pip install n'est réexécuté
# que si les dépendances changent — pas à chaque modification du code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout 100

# Copier le code — cette couche change souvent, mais c'est la dernière
# donc elle n'invalide pas le cache de pip install
COPY app.py .

# Indiquer que l'application écoute sur le port 5000
# (informatif — ne publie pas le port sur la machine hôte)
EXPOSE 5000

# Commande de démarrage du conteneur
CMD ["python", "app.py"]
```

**La stratégie de cache Docker est cruciale en pratique.** Un `pip install` peut prendre 30-60 secondes. En plaçant `requirements.txt` avant `app.py`, les 99% de builds où seul le code change prennent 2-3 secondes au lieu de 60.

### Construction et lancement

```bash
# Construire l'image
# -t mon-api:v1 = donner un nom (tag) à l'image
# . = le contexte de build est le répertoire courant
# --network=host = utiliser le réseau de la machine hôte pour pip install
#   (nécessaire si le réseau de l'environnement Docker est restreint)
docker build --network=host -t mon-api:v1 .

# Lancer un conteneur depuis cette image
# -d = détaché (tourne en arrière-plan)
# -p 8081:5000 = publier le port 5000 du conteneur sur le port 8081 de la machine
# -e APP_ENV=production = passer une variable d'environnement
# --name api1 = donner un nom au conteneur
docker run -d -p 8081:5000 -e APP_ENV=production --name api1 mon-api:v1

# Tester
curl http://localhost:8081
# Bonjour depuis <container_id> [env: production, v1.0.0]
```

### Commandes essentielles

```bash
docker ps                    # Conteneurs en cours d'exécution
docker ps -a                 # Tous les conteneurs (y compris arrêtés)
docker logs -f api1          # Logs en temps réel du conteneur api1
docker exec -it api1 sh      # Ouvrir un shell interactif dans le conteneur
docker stats                 # CPU, mémoire, réseau en temps réel
docker stop api1 && docker rm api1   # Arrêter et supprimer
docker images                # Lister les images disponibles localement
docker rmi mon-api:v1        # Supprimer une image
```

### Ce que Docker résout ✅

- Reproductibilité : même comportement partout
- Isolation : les applications ne se perturbent pas
- Portabilité : tourne sur n'importe quelle machine avec Docker
- Versioning des environnements : chaque image est taguée

### Les limites de Docker seul — pourquoi ça ne suffit pas

Docker gère **un** conteneur à la fois. Mais en pratique, une application n'est jamais seule. Notre API a besoin d'une base de données. Elle devrait tourner en plusieurs instances pour la performance. La base de données doit démarrer avant l'API. Si un conteneur plante, il faut le redémarrer manuellement.

Imagine devoir taper 10 commandes `docker run` dans le bon ordre avec tous les bons paramètres, à chaque déploiement. C'est là que Docker Compose entre en jeu.

---

## Projet 2 — Docker Compose : orchestrer plusieurs conteneurs 🔗

### Le problème que Docker Compose résout

Notre stack applicative réelle ressemble à ça :

```
Internet → [API Flask × 3 instances] → [PostgreSQL]
                                     ↓
                              [Prometheus] → [Grafana]
```

Lancer tout ça manuellement avec des commandes `docker run` séparées pose plusieurs problèmes. Il faut retenir les ports, les noms de réseau, les variables d'environnement pour chaque service. L'ordre de démarrage est critique — l'API ne peut pas démarrer avant que PostgreSQL soit prête. Si on relance tout, il faut retaper toutes les commandes. Partager la configuration avec un collègue devient difficile.

**Docker Compose résout ça avec un seul fichier YAML** qui décrit toute la stack. Une commande pour tout démarrer, une pour tout arrêter.

### Comment Docker Compose fonctionne

Docker Compose crée automatiquement un **réseau Docker dédié** pour tous les services définis dans le fichier. Dans ce réseau, chaque service est accessible par son **nom** — pas par son adresse IP. L'API peut donc se connecter à PostgreSQL via `postgres:5432` simplement parce que le service s'appelle `postgres` dans le fichier Compose.

```
Réseau Docker "docker-app_default"
├── service "postgres"   → accessible via postgres:5432
├── service "api1"       → accessible via api1:5000
├── service "api2"       → accessible via api2:5000
├── service "api3"       → accessible via api3:5000
├── service "prometheus" → accessible via prometheus:9090
└── service "grafana"    → accessible via grafana:3000
```

### docker-compose.yml

```yaml
version: "3.8"
services:

  # ── Base de données PostgreSQL ────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: devsecret123
    volumes:
      # Volume nommé = les données persistent même si le conteneur est supprimé
      # Sans ce volume, toutes les données sont perdues à chaque docker compose down
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    # Healthcheck : Compose attend que pg_isready retourne succès avant
    # de démarrer les services qui dépendent de postgres
    # Sans ça, l'API tente de se connecter à une DB pas encore prête → erreur
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser -d appdb"]
      interval: 5s
      timeout: 3s
      retries: 5

  # ── API Flask — instance 1 ────────────────────────────────────────────
  api1:
    build: .   # Construit l'image depuis le Dockerfile du répertoire courant
    container_name: api1
    ports:
      - "8081:5000"
    environment:
      APP_ENV: development
      APP_VERSION: "2.0.0"
      DB_HOST: postgres    # Nom du service Compose — résolution DNS automatique
      DB_PORT: "5432"
      DB_NAME: appdb
      DB_USER: appuser
      DB_PASSWORD: devsecret123
    depends_on:
      postgres:
        condition: service_healthy   # Attend que le healthcheck postgres soit vert

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

  # ── Prometheus — collecte les métriques des 3 instances API ──────────
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

  # ── Grafana — visualise les métriques Prometheus ──────────────────────
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

# Les volumes nommés sont gérés par Docker — les données persistent entre les sessions
volumes:
  postgres-data:
  grafana-data:
```

### Commandes essentielles

```bash
# Démarrer toute la stack (--build reconstruit les images si le code a changé)
docker compose up -d --build

# Voir l'état de tous les services
docker compose ps

# Voir les logs de toute la stack en temps réel
docker compose logs -f

# Voir les logs d'un service spécifique
docker compose logs -f api1

# Arrêter sans supprimer les données
docker compose stop

# Arrêter et supprimer les conteneurs (les volumes persistent)
docker compose down

# Arrêter et supprimer tout y compris les données
docker compose down -v

# Tester l'API
curl http://localhost:8081/db-test
# → {"status": "connected", "postgres_version": "PostgreSQL 16.x..."}
```

### Ce que Docker Compose résout ✅

- Stack multi-conteneurs décrite en un seul fichier
- Réseau interne automatique avec DNS par nom de service
- Ordre de démarrage garanti avec `depends_on` et `healthcheck`
- Volumes persistants pour les données
- Une commande pour tout démarrer, une pour tout arrêter

### Les limites de Docker Compose — pourquoi ça ne suffit pas en production

Docker Compose est excellent pour le développement local. Mais il présente des lacunes critiques pour la production.

**Pas de résilience.** Si un conteneur plante, Compose ne le redémarre pas automatiquement (sauf avec `restart: always`, mais ça reste limité). En production, on veut que l'application se répare elle-même.

**Pas de scaling dynamique.** Passer de 3 à 10 instances nécessite de modifier le fichier et de tout relancer. En production, on veut ajuster le nombre d'instances en une commande selon la charge.

**Une seule machine.** Compose tourne sur une seule machine. Si cette machine tombe, tout l'application tombe. En production, on distribue sur plusieurs machines.

**Pas de mises à jour sans coupure.** Mettre à jour l'image d'un service avec Compose arrête le conteneur puis repart — il y a une interruption de service. En production, on veut des mises à jour sans interruption (zero downtime).

C'est exactement pour répondre à ces quatre problèmes que Kubernetes a été créé.

---

## Projet 3 — Kubernetes : passer à la production ☸️

### Ce que Kubernetes est — et ce qu'il n'est pas

Kubernetes est souvent présenté comme "Docker à grande échelle" — ce n'est pas tout à fait ça. Kubernetes est un **système d'orchestration déclaratif**. La différence fondamentale avec Docker (et Compose) est philosophique : avec Docker, tu dis **comment** faire les choses. Avec Kubernetes, tu dis **ce que tu veux** comme état final, et Kubernetes fait tout pour y arriver et y rester.

Tu ne dis pas "démarre ce conteneur". Tu dis "je veux 3 réplicas de cette application qui tournent en permanence". Kubernetes crée les 3, les surveille, et en recrée un si l'un plante — sans aucune intervention humaine.

### Les composants du cluster

```
Ton ordinateur / Serveur Cloud
└── Cluster Kubernetes
    ├── Master Node (cerveau du cluster)
    │   ├── API Server     → Point d'entrée unique de kubectl et de tous les outils
    │   │                    Tout passe par là — c'est la "porte d'entrée" du cluster
    │   ├── etcd           → Base de données clé-valeur qui stocke TOUT l'état du cluster
    │   │                    Si etcd est perdu, le cluster est perdu
    │   ├── Scheduler      → Décide sur quel Worker Node placer un nouveau Pod
    │   │                    Prend en compte la mémoire disponible, les contraintes, etc.
    │   └── Controller-    → La boucle de contrôle fondamentale de Kubernetes
    │       Manager          Compare en permanence "état désiré" vs "état réel"
    │                        et prend les actions pour les réconcilier
    │
    └── Worker Node(s) (là où les applications tournent)
        ├── Kubelet        → Agent qui reçoit les ordres du Master et gère les Pods
        ├── kube-proxy     → Gère les règles réseau pour les Services
        └── Pods           → L'unité de base : un ou plusieurs conteneurs
```

**La boucle de contrôle du Controller-Manager** est le concept clé de Kubernetes. Elle tourne en permanence :

```
1. "État désiré" : 3 réplicas de mon-api doivent tourner
2. "État réel" : je compte les Pods qui tournent → il y en a 2 (un a planté)
3. Action : créer 1 nouveau Pod pour revenir à 3
4. Retour en 1. (recommencer en permanence)
```

C'est ça, la résilience automatique de Kubernetes.

### Les objets Kubernetes fondamentaux

**Le Pod** est l'unité de base. C'est un ou plusieurs conteneurs qui partagent le même réseau et le même stockage. On ne crée jamais de Pod directement — on passe par un Deployment.

**Le Deployment** déclare l'état désiré pour un ensemble de Pods identiques. Il gère la création, la mise à jour (rolling update) et la résilience.

**Le Service** est l'adresse stable d'un groupe de Pods. Les Pods ont des adresses IP éphémères qui changent à chaque recréation. Le Service a une adresse stable et fait du load balancing entre les Pods.

### Les fichiers de configuration

```yaml
# deployment.yaml
# "Je veux 3 réplicas de mon-api qui tournent en permanence"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mon-api-deployment
spec:
  replicas: 3    # L'état désiré — Kubernetes maintiendra toujours 3 Pods
  selector:
    matchLabels:
      app: mon-api   # Ce Deployment gère les Pods avec ce label
  template:
    metadata:
      labels:
        app: mon-api   # Label appliqué à chaque Pod créé
    spec:
      containers:
      - name: mon-api
        image: mon-api:v1
        imagePullPolicy: Never   # Ne pas chercher l'image sur Docker Hub — utiliser le registre local
        ports:
        - containerPort: 5000
```

```yaml
# service.yaml
# "Expose les Pods mon-api sur une adresse stable"
apiVersion: v1
kind: Service
metadata:
  name: mon-api-service
spec:
  type: NodePort   # Accessible depuis l'extérieur du cluster via un port fixe
  selector:
    app: mon-api   # Ce Service envoie le trafic vers les Pods avec ce label
  ports:
  - port: 5000        # Port du Service (interne au cluster)
    targetPort: 5000  # Port du conteneur
    nodePort: 30080   # Port exposé sur la machine hôte (entre 30000 et 32767)
```

### Déployer sur Minikube

Minikube crée un cluster Kubernetes complet (Master + Worker) dans une seule machine virtuelle sur ton ordinateur. C'est l'outil standard pour apprendre et développer avec Kubernetes localement.

```bash
# Démarrer Minikube
minikube start

# Minikube a son propre registre Docker, séparé de Docker local
# Il faut charger l'image dans le registre Minikube
minikube image load mon-api:v1

# Appliquer les fichiers de configuration
# "apply" = créer si n'existe pas, mettre à jour si existe (idempotent)
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Observer les Pods se créer
kubectl get pods -w
# NAME                                   READY   STATUS    RESTARTS
# mon-api-deployment-xxx-aaa             1/1     Running   0
# mon-api-deployment-xxx-bbb             1/1     Running   0
# mon-api-deployment-xxx-ccc             1/1     Running   0

# Accéder à l'application
minikube service mon-api-service --url
# http://192.168.49.2:30080
curl http://192.168.49.2:30080
```

### Tester la résilience — la vraie valeur de Kubernetes

```bash
# Supprimer un Pod manuellement (simule une panne)
kubectl delete pod mon-api-deployment-xxx-aaa

# Observer immédiatement — Kubernetes recrée le Pod automatiquement
kubectl get pods -w
# mon-api-deployment-xxx-aaa   Terminating
# mon-api-deployment-xxx-ddd   ContainerCreating   ← Kubernetes recrée !
# mon-api-deployment-xxx-ddd   Running

# Scaler à 5 réplicas en une commande
kubectl scale deployment mon-api-deployment --replicas=5
kubectl get pods   # 5 Pods Running
```

### Commandes kubectl essentielles

```bash
kubectl get pods                    # État des Pods
kubectl get pods -w                 # Surveiller en temps réel
kubectl describe pod <nom>          # Détails et événements d'un Pod
kubectl logs <nom>                  # Logs d'un Pod
kubectl logs -f <nom>               # Logs en temps réel
kubectl get services                # État des Services
kubectl get deployments             # État des Deployments
kubectl apply -f <fichier>          # Appliquer une configuration
kubectl delete -f <fichier>         # Supprimer des ressources
kubectl scale deployment <nom> --replicas=N   # Changer le nombre de réplicas
minikube dashboard                  # Interface web graphique
```

### Ce que Kubernetes résout ✅

- Résilience automatique : les Pods qui plantent sont recréés
- Scaling déclaratif : changer `replicas: N` suffit
- Rolling updates : mise à jour sans interruption de service
- Distribution sur plusieurs machines
- Service Discovery via DNS interne

### Les limites — ce qui manque encore

Notre application Kubernetes tourne, est résiliente, et se scale. Mais on déploie encore à la main. Chaque nouvelle version de l'API nécessite de rebuilder l'image, la charger dans Minikube, et relancer. Et surtout : **on ne sait pas ce qui se passe dans notre application**. Est-ce qu'elle répond vite ? Y a-t-il des erreurs ? Quel Pod reçoit le plus de trafic ? Sans monitoring, on déploie à l'aveugle.

---

## Projet 4 — Monitoring : savoir ce qui se passe 📊

### Pourquoi le monitoring est non-négociable

Un SRE (Site Reliability Engineer) a une règle fondamentale : **ne jamais déployer sans monitoring**. Voici pourquoi. Imagine que tu déploies une nouvelle version de l'API un vendredi soir. Le lundi matin, les utilisateurs se plaignent que l'application est lente depuis vendredi. Sans monitoring, tu ne sais pas si c'est lent depuis vendredi 18h00 précisément (donc à cause du déploiement) ou depuis samedi matin (donc peut-être une autre cause). Tu ne sais pas quel endpoint est lent. Tu ne sais pas si c'est une erreur ou juste de la lenteur.

**Avec le monitoring, tu aurais vu un graphe de temps de réponse monter en flèche vendredi à 18h03 — exactement 3 minutes après le déploiement.** Le diagnostic prend 30 secondes au lieu de 2 heures.

### L'architecture Prometheus + Grafana

Prometheus et Grafana sont deux outils distincts qui se complètent.

**Prometheus** est un système de monitoring qui fonctionne par **scraping** (pull) : il interroge périodiquement les endpoints `/metrics` de chaque application toutes les 15 secondes et stocke les valeurs dans une base de données temporelle. C'est l'approche inverse des systèmes push traditionnels — c'est Prometheus qui va chercher les données, pas l'application qui les envoie.

**Grafana** est un outil de visualisation. Il ne collecte rien — il se connecte à Prometheus (ou d'autres sources) et affiche les données sous forme de dashboards interactifs. On peut créer des graphes, des alertes, des tableaux de bord en temps réel.

```
Flux de données :

App Flask /metrics ←── Prometheus scrape toutes les 15s ──→ stocke en mémoire
                                                                    ↓
                                                             Grafana interroge
                                                                    ↓
                                                         Dashboard en temps réel
```

### Exposer les métriques depuis Flask

```python
# Dans app.py — ajouter prometheus-flask-exporter
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
metrics = PrometheusMetrics(app)   # Active automatiquement l'endpoint /metrics

# Créer un compteur custom — nombre de requêtes sur / par pod
hello_counter = metrics.counter(
    'hello_requests_total',          # Nom de la métrique
    'Nombre total de requêtes sur /',  # Description
    labels={'pod': lambda: socket.gethostname()}   # Dimension : quel pod ?
)

@app.route("/")
@hello_counter    # Chaque appel incrémente le compteur
def hello():
    ...
```

L'endpoint `/metrics` généré ressemble à ça :

```
# HELP hello_requests_total Nombre total de requêtes sur /
# TYPE hello_requests_total counter
hello_requests_total{pod="api1"} 42
hello_requests_total{pod="api2"} 38
hello_requests_total{pod="api3"} 45
# HELP flask_http_request_duration_seconds HTTP request duration
flask_http_request_duration_seconds_bucket{le="0.1",method="GET",path="/",status="200"} 120
...
```

### prometheus.yml

```yaml
global:
  scrape_interval: 15s   # Interroger les cibles toutes les 15 secondes

scrape_configs:
  - job_name: 'mon-api'
    static_configs:
      # Les trois instances de l'API — Prometheus interroge chacune séparément
      # Ce sont les noms de services Docker Compose — résolution DNS automatique
      - targets: ['api1:5000', 'api2:5000', 'api3:5000']
```

### Requêtes PromQL — le langage de Prometheus

PromQL est le langage de requête de Prometheus. Quelques exemples essentiels :

```promql
# Nombre de requêtes par seconde sur chaque pod (moyenne sur la dernière minute)
# rate() calcule le taux de variation d'un compteur — essentiel car les compteurs
# ne font que monter, c'est leur taux de variation qui est intéressant
rate(hello_requests_total[1m])

# Temps de réponse moyen en millisecondes
rate(flask_http_request_duration_seconds_sum[1m])
  / rate(flask_http_request_duration_seconds_count[1m]) * 1000

# Nombre total de requêtes depuis le démarrage
hello_requests_total
```

### Configuration dans Docker Compose

```yaml
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml

grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
```

### Configurer Grafana

1. Ouvrir `http://localhost:3000` (admin/admin)
2. **Connections → Data sources → Add → Prometheus**
3. URL : `http://prometheus:9090`
   - **IMPORTANT** : utiliser le nom de service Docker `prometheus`, pas `localhost`
   - `localhost` dans un conteneur désigne le conteneur lui-même, pas la machine hôte
4. **Save & Test** → vert
5. **Dashboards → New → Add visualization**
6. Saisir une requête PromQL et créer les graphes

### Ce que le monitoring résout ✅

- Visibilité en temps réel sur ce qui se passe
- Diagnostic rapide des problèmes et de leur moment d'apparition
- Alertes automatiques quand quelque chose dépasse un seuil
- Corrélation entre déploiements et dégradations de performance
- Base pour les décisions de scaling (quand ajouter des réplicas ?)

### Les limites — ce qui manque encore

On a une application résiliente, scalable, et monitorée. Mais chaque déploiement est encore manuel : modifier le code, rebuilder l'image, la charger dans Minikube, relancer. C'est lent, risqué (erreurs humaines), et non traçable. En équipe, comment savoir qui a déployé quoi et quand ? Comment garantir que les tests passent avant chaque déploiement ?

---

## Projet 5 — CI/CD : automatiser le déploiement 🚀

### Ce que CI/CD signifie vraiment

**CI — Intégration Continue** : à chaque fois qu'un développeur pousse du code, un système automatique vérifie que le code fonctionne (tests), que l'image Docker se construit sans erreur, et que rien n'est cassé. Si quelque chose échoue, le développeur est alerté immédiatement avant que le code ne parte en production.

**CD — Déploiement Continu** : si la CI réussit et que le code est sur la branche `main`, le déploiement en production est déclenché automatiquement — sans intervention humaine.

L'objectif combiné : **du code sur un laptop à une application mise à jour en production en quelques minutes, de façon fiable et traçable.**

### GitHub Actions — comment ça fonctionne

GitHub Actions est une plateforme CI/CD intégrée à GitHub. Un **workflow** est un fichier YAML dans `.github/workflows/` qui définit quand s'exécuter (trigger) et quoi faire (jobs et steps).

À chaque `git push`, GitHub Actions démarre une VM Ubuntu fraîche, exécute le workflow, et détruit la VM. Cette VM a accès à internet mais n'a pas accès à ton cluster Kubernetes local — ce qui est une limite qu'on résoudra dans les projets suivants.

### Le tag SHA — traçabilité en production

Une bonne pratique fondamentale : chaque image Docker déployée en production est taguée avec le **SHA du commit Git** qui l'a produite.

```
ghcr.io/stephdeve/docker-app/mon-api:sha-a3f8c21
```

Quand un problème survient en production, on peut immédiatement répondre à "quelle version tourne ?" avec le SHA exact, retrouver le commit dans Git, voir exactement quelles lignes ont changé, et décider si on doit rollback.

### Le workflow complet

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]      # Déclenché à chaque push sur main
  pull_request:
    branches: [main]      # ET à chaque Pull Request vers main

env:
  IMAGE_NAME: ghcr.io/${{ github.repository }}/mon-api

jobs:
  # ── Job 1 : Intégration Continue ──────────────────────────────────────
  ci:
    name: Test & Build
    runs-on: ubuntu-latest   # VM Ubuntu fraîche à chaque exécution

    steps:
      - name: Récupérer le code
        uses: actions/checkout@v4

      - name: Configurer Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Installer les dépendances
        run: pip install -r requirements.txt

      # Si un test échoue ici, tout s'arrête — le CD ne s'exécute JAMAIS
      - name: Lancer les tests
        run: pytest test_app.py -v

      - name: Se connecter à GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}   # Token automatique — pas besoin de créer un secret

      # Générer les tags : sha-abc123 + latest (si on est sur main)
      - name: Générer les tags Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build et Push l'image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}   # Ne pas pusher sur les PRs
          tags: ${{ steps.meta.outputs.tags }}

  # ── Job 2 : Déploiement Continu ───────────────────────────────────────
  # Ce job ne s'exécute que si le Job CI réussit ET seulement sur main
  cd:
    name: Deploy
    runs-on: ubuntu-latest
    needs: ci   # Dépendance explicite
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-kubectl@v3
      - run: |
          # Sans accès au cluster, on simule ici
          # Les projets suivants connectent ce job à un vrai cluster
          echo "✅ Image disponible : $IMAGE_NAME:sha-${{ github.sha }}"
          echo "→ helm upgrade mon-app ./mon-api-chart --set app.image.tag=sha-${{ github.sha }}"
```

### Ce que CI/CD résout ✅

- Les tests passent obligatoirement avant tout déploiement
- Chaque déploiement est traçable (SHA du commit)
- Plus d'erreurs humaines liées aux déploiements manuels
- Déploiements rapides et fréquents → moins de risque (petites modifications)
- Historique complet dans GitHub Actions

### Les limites — ce qui manque encore

La pipeline teste, construit et pousse l'image. Mais le déploiement est encore simulé — la VM GitHub Actions ne sait pas où est notre cluster. De plus, notre application a des identifiants de base de données hardcodés dans les fichiers YAML, ce qui est un problème de sécurité critique. Et l'URL d'accès reste `http://IP:30080` — peu professionnel pour une vraie application.

---

## Projet 6 — ConfigMaps, Secrets & PostgreSQL : séparer la config du code 🗄️

### Le principe 12-Factor App

Le **12-Factor App** est une méthodologie de référence publiée par les équipes de Heroku pour construire des applications cloud-native robustes. Le facteur III dit : **"Stocker la configuration dans l'environnement"**.

Concrètement : une configuration hardcodée dans le code ou dans les fichiers YAML crée trois problèmes graves. Les credentials finissent dans l'historique Git où ils sont visibles à tout le monde. La même image Docker ne peut pas être réutilisée entre dev, staging et prod car chaque environnement a des URLs et des mots de passe différents. Changer un paramètre de config nécessite de rebuilder l'image.

La solution est de lire **toute la configuration** depuis les variables d'environnement à l'exécution. L'image est identique dans tous les environnements — seules les variables changent.

### ConfigMap vs Secret — pourquoi deux objets séparés ?

Kubernetes distingue deux types de configuration selon leur sensibilité :

Un **ConfigMap** contient la configuration non sensible — URLs, noms, numéros de port, paramètres d'environnement. Ses valeurs sont stockées en clair et visibles avec `kubectl describe`. C'est normal — l'URL d'une base de données n'est pas un secret.

Un **Secret** contient les données sensibles — mots de passe, clés API, certificats. Ses valeurs sont stockées encodées en base64 dans etcd. **Important** : base64 n'est pas du chiffrement, c'est un encodage. N'importe qui avec accès au Secret peut le décoder. La vraie protection vient des permissions RBAC (contrôle d'accès) sur les Secrets. En production réelle, on utilise des solutions comme HashiCorp Vault ou les secrets managers cloud pour chiffrer vraiment les secrets.

```yaml
# configmap.yaml — configuration non sensible
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
# secret.yaml — données sensibles
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
# Dans deployment.yaml — envFrom injecte TOUTES les clés comme variables d'env
# Plus besoin de lister chaque variable individuellement
spec:
  containers:
  - name: mon-api
    envFrom:
    - configMapRef:
        name: mon-api-config
    - secretRef:
        name: mon-api-secret
```

### PostgreSQL dans Kubernetes

```yaml
# postgres-deployment.yaml
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
            secretKeyRef:           # Lire depuis le Secret — pas hardcodé !
              name: mon-api-secret
              key: DB_PASSWORD

---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
spec:
  type: ClusterIP    # Uniquement accessible à l'intérieur du cluster — voulu
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

### Déploiement dans le bon ordre

```bash
# Les Pods ont besoin de la config au démarrage — appliquer avant les Deployments
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Encoder/décoder base64
echo -n "monmotdepasse" | base64
echo "bW9ubW90ZGVwYXNzZQ==" | base64 --decode

# Tester
kubectl port-forward service/mon-api-service 8080:5000
curl http://localhost:8080/db-test
# → {"status": "connected", "postgres_version": "PostgreSQL 16.x..."}
```

---

## Projet 7 — Ingress & HTTPS : exposer proprement 🔒

### Le problème de l'exposition avec NodePort

Jusqu'ici, notre application est accessible via `http://192.168.49.2:30080` — une URL avec une adresse IP et un port non standard. C'est acceptable pour un cluster de dev, mais inutilisable en production pour trois raisons :

Les utilisateurs s'attendent à `https://monapp.com`, pas à une IP avec un port. Si on a plusieurs services (API, Grafana, admin...), il faudrait un NodePort différent pour chacun — ce qui devient ingérable. Et le HTTPS est obligatoire en production pour chiffrer les données.

### Ce qu'un Ingress Controller fait

Un **Ingress Controller** est un reverse proxy (Nginx dans notre cas) qui tourne dans le cluster comme un Pod. Il reçoit tout le trafic entrant sur les ports 80 et 443, déchiffre le TLS, et route vers le bon Service selon les règles déclarées dans des objets `Ingress`.

```
AVANT (NodePort — un port par service)     APRÈS (Ingress — un point d'entrée)
────────────────────────────────────       ──────────────────────────────────
http://IP:30080 → API Flask                https://monapp.local
http://IP:30090 → Grafana                      ├── /api/*    → API Flask
http://IP:30100 → Dashboard admin              ├── /grafana/* → Grafana
(3 ports, 3 URLs, HTTP seulement)              └── /admin/*   → Dashboard
                                           (1 URL, HTTPS, routage intelligent)
```

```bash
# Activer l'addon Ingress sur Minikube
minikube addons enable ingress

# Ajouter un faux domaine dans /etc/hosts pour simuler le DNS
echo "$(minikube ip) monapp.local" | sudo tee -a /etc/hosts

# Créer un certificat TLS auto-signé (production : cert-manager + Let's Encrypt)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt -subj "/CN=monapp.local/O=DevOps Learning"

# Créer un Secret TLS dans Kubernetes
kubectl create secret tls monapp-tls --key tls.key --cert tls.crt
```

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mon-api-ingress
  annotations:
    # Redirection automatique HTTP → HTTPS
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    # Réécriture des chemins : /api/health devient /health pour le backend
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  tls:
  - hosts:
    - monapp.local
    secretName: monapp-tls   # Nginx lit la clé et le certificat dans ce Secret
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

```bash
kubectl apply -f service.yaml   # Service en ClusterIP maintenant (plus besoin de NodePort)
kubectl apply -f ingress.yaml
curl -k https://monapp.local/api/health
```

**En production** : utiliser **cert-manager** avec Let's Encrypt pour des certificats gratuits, valides (pas auto-signés), et renouvelés automatiquement avant expiration.

---

## Projet 8 — Helm : packager et versionner 🎡

### Le problème que Helm résout

On a maintenant 7 fichiers YAML pour déployer notre application : configmap, secret, deployment, service, ingress, postgres-deployment, postgres-service. Si on veut déployer la même application dans trois environnements (dev, staging, prod) avec des valeurs différentes, ça devient 21 fichiers à maintenir. Changer le nombre de réplicas oblige à modifier un fichier. Passer d'une version à l'autre est manuel et risqué.

**Helm est le gestionnaire de paquets de Kubernetes.** Il transforme les fichiers YAML en templates paramétrables, les regroupe dans un **chart**, et permet de déployer toute l'application en une commande avec uniquement les valeurs qui changent.

```bash
# Avant Helm — 7 commandes dans le bon ordre
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml

# Après Helm — 1 commande
helm install mon-app ./mon-api-chart --set database.password=secret123
```

### La structure d'un chart

```
mon-api-chart/
├── Chart.yaml      # Métadonnées : nom, version du chart, version de l'app
├── values.yaml     # Toutes les valeurs par défaut — c'est LE fichier à modifier
└── templates/      # Les YAML avec la syntaxe de templating Go
    ├── configmap.yaml
    ├── secret.yaml
    ├── deployment.yaml
    ├── service.yaml
    ├── ingress.yaml
    └── postgres.yaml
```

### values.yaml — le fichier central

```yaml
app:
  name: mon-api
  env: production
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
  password: ""   # Toujours passé via --set, jamais commité dans Git

service:
  type: ClusterIP
  port: 5000

ingress:
  enabled: true   # Peut être désactivé en dev avec --set ingress.enabled=false
  host: monapp.local
  tlsSecret: monapp-tls

postgresql:
  enabled: true
  image: postgres:16-alpine
```

### La syntaxe de templating

```yaml
# Dans templates/deployment.yaml
# {{ .Values.app.replicaCount }} → injecte la valeur de values.yaml
# {{ .Release.Name }} → le nom donné au déploiement (ex: "mon-app")
# Ce mécanisme permet à plusieurs releases du même chart de coexister sans conflit
spec:
  replicas: {{ .Values.app.replicaCount }}
  ...
  containers:
  - image: "{{ .Values.app.image.repository }}:{{ .Values.app.image.tag }}"
```

```yaml
# Dans templates/secret.yaml
# b64enc encode automatiquement en base64 — plus besoin de le faire manuellement
data:
  DB_PASSWORD: {{ .Values.database.password | b64enc | quote }}
```

```yaml
# Dans templates/ingress.yaml
# La directive if permet de désactiver l'Ingress selon l'environnement
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
...
{{- end }}
```

### Commandes essentielles

```bash
helm lint mon-api-chart/           # Valider le chart avant de déployer
helm template mon-api-chart/ \     # Voir les YAML générés sans déployer
  --set database.password=test       (indispensable pour débugger)

helm install mon-app ./mon-api-chart --set database.password=secret123
helm list                           # Toutes les releases actives
helm history mon-app                # Historique des révisions
helm upgrade mon-app ./mon-api-chart --set app.replicaCount=5 --set database.password=secret123
helm rollback mon-app 1             # Revenir à la révision 1 en cas de problème
helm uninstall mon-app              # Désinstaller complètement
```

### Plusieurs environnements

```bash
# values-dev.yaml
cat > values-dev.yaml << EOF
app:
  env: development
  replicaCount: 1
ingress:
  enabled: false
EOF

# Les deux environnements coexistent dans le cluster
helm install dev  ./mon-api-chart -f values-dev.yaml  --set database.password=devpass
helm install prod ./mon-api-chart -f values-prod.yaml --set database.password=prodpass
```

---

## Projet 9 — CI/CD cloud réel 🌐

### Le dernier maillon — connecter la pipeline au cluster

Notre pipeline GitHub Actions teste, construit et pousse l'image. Il manque le dernier maillon : que GitHub Actions puisse réellement déployer sur un cluster Kubernetes. C'est ce projet qui transforme le CI/CD simulé en CI/CD réel.

Trois options selon le contexte :

### Option A — GKE (Google Kubernetes Engine)

La solution la plus robuste pour la production réelle. GKE est un cluster Kubernetes entièrement managé par Google — pas de nœuds à administrer, scaling automatique, load balancer cloud inclus.

**Workload Identity Federation** est la bonne pratique d'authentification. Au lieu de créer une clé JSON (qui ne tourne jamais et représente un risque si elle fuite), GitHub Actions prouve son identité à Google via un token OIDC éphémère valide quelques minutes uniquement.

```yaml
# Dans le workflow — authentification sans clé JSON
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
    service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

- uses: google-github-actions/get-gke-credentials@v2
  with:
    cluster_name: ${{ secrets.GKE_CLUSTER_NAME }}
    location: ${{ secrets.GKE_CLUSTER_ZONE }}

- run: |
    helm upgrade --install mon-app ./mon-api-chart \
      --set app.image.tag=sha-${{ github.sha }} \
      --set database.password=${{ secrets.DB_PASSWORD }} \
      --atomic --timeout 5m
```

> ⚠️ **Nécessite un compte Google Cloud avec carte bancaire** (même si le free tier ne débite pas, la carte est requise pour la vérification d'identité).

### Option B — Oracle Cloud (OCI)

Oracle offre le free tier le plus généreux : 2 VMs ARM avec 4 cœurs et 24 Go de RAM chacune, à vie. On y installe k3s pour avoir un vrai cluster Kubernetes.

> ⚠️ **Peut aussi demander une carte bancaire** selon le pays de résidence pour la vérification d'identité.

### Option C — k3s local + ngrok (100% gratuit, sans carte)

C'est la solution qui ne nécessite absolument rien de payant. **k3s** est une distribution Kubernetes certifiée CNCF qui tient en un binaire de 50 Mo. **ngrok** crée un tunnel HTTPS public vers ta machine locale, permettant à GitHub Actions (dans le cloud) de déployer sur ton cluster k3s (sur ta machine Ubuntu).

```
GitHub Actions (cloud) → https://xyz.ngrok-free.app → ngrok (ta machine) → k3s API Server
```

#### Installation de k3s

```bash
# k3s remplace Minikube — plus léger, plus proche de la production réelle
curl -sfL https://get.k3s.io | sh -

# Configurer kubectl
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
kubectl get nodes

# Charger les images locales dans k3s
# (k3s et Docker ont des registres séparés)
docker save mon-api:v1 | sudo k3s ctr images import -
docker save postgres:16-alpine | sudo k3s ctr images import -
```

#### Installation de ngrok

```bash
# Installer ngrok (compte gratuit sur ngrok.com — sans carte)
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update && sudo apt install ngrok

# Authentifier avec ton token (visible sur dashboard.ngrok.com)
ngrok config add-authtoken TON_TOKEN

# Créer le tunnel vers l'API Server k3s
ngrok tcp 6443
# → tcp://0.tcp.eu.ngrok.io:12345 (note cette adresse et ce port)
```

#### Préparer le kubeconfig pour GitHub Actions

```bash
# Remplacer localhost par l'adresse ngrok dans le kubeconfig
cat ~/.kube/config | \
  sed "s/127.0.0.1:6443/0.tcp.eu.ngrok.io:12345/g" \
  > /tmp/kubeconfig-ngrok.yaml

# Stocker dans les secrets GitHub : KUBECONFIG = contenu de ce fichier
```

#### Le workflow GitHub Actions pour k3s + ngrok

```yaml
name: CI/CD Pipeline — k3s local

on:
  push:
    branches: [main]

permissions:
  contents: read
  packages: write

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
          images: ghcr.io/${{ github.repository }}/mon-api
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

      - name: Configurer kubectl via ngrok
        run: |
          mkdir -p ~/.kube
          echo "${{ secrets.KUBECONFIG }}" > ~/.kube/config
          chmod 600 ~/.kube/config
          kubectl get nodes   # Vérifie que la connexion fonctionne

      - uses: azure/setup-helm@v4

      - name: Autoriser le pull depuis ghcr.io
        run: |
          kubectl create secret docker-registry ghcr-secret \
            --docker-server=ghcr.io \
            --docker-username=${{ github.actor }} \
            --docker-password=${{ secrets.GITHUB_TOKEN }} \
            --dry-run=client -o yaml | kubectl apply -f -

      - name: Déployer avec Helm
        run: |
          helm upgrade --install mon-app ./mon-api-chart \
            --set app.image.repository=ghcr.io/${{ github.repository }}/mon-api \
            --set app.image.tag=sha-${{ github.sha }} \
            --set app.image.pullPolicy=Always \
            --set database.password=${{ secrets.DB_PASSWORD }} \
            --set ingress.enabled=false \
            --atomic --timeout 5m

      - name: Vérifier
        run: |
          kubectl rollout status deployment/mon-app-deployment
          kubectl get pods
          echo "✅ Déployé : sha-${{ github.sha }}"
```

**Note sur ngrok free tier** : l'URL du tunnel change à chaque redémarrage. Pour une adresse permanente, utiliser un domaine TCP statique depuis le dashboard ngrok.com (disponible en free tier depuis 2023).

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry.k8s.io: i/o timeout`

Les conteneurs Docker (Minikube, kind) ne peuvent pas accéder à internet — problème DNS ou proxy réseau.

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

L'image n'est pas dans le registre Minikube ou k3s.

```bash
minikube image load mon-api:v1
# OU pour k3s :
docker save mon-api:v1 | sudo k3s ctr images import -
```

### 4. `failed calling webhook validate.nginx.ingress.kubernetes.io`

Le webhook de validation Nginx Ingress est inaccessible (controller pas encore Running).

```bash
kubectl delete validatingwebhookconfiguration ingress-nginx-admission
```

### 5. `helm install` échoue — release en état `failed`

```bash
helm uninstall mon-app
helm install mon-app ./mon-api-chart --set database.password=secret123
```

### 6. Grafana ne se connecte pas à Prometheus

Utiliser `http://prometheus:9090` (nom de service Docker) — jamais `http://localhost:9090`.

### 7. `ErrImagePull` sur GKE — image ghcr.io privée

```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=stephdeve \
  --docker-password=TON_GITHUB_TOKEN
```

### 8. k3s — images Docker locales non disponibles

k3s et Docker ont des registres séparés.

```bash
docker save <image> | sudo k3s ctr images import -
sudo k3s ctr images list | grep <nom>
```

### 9. ngrok — URL change à chaque redémarrage

Utiliser un domaine TCP statique depuis dashboard.ngrok.com et l'option `--remote-addr`.

### 10. Les Pods API démarrent avant PostgreSQL

Utiliser `depends_on` avec `condition: service_healthy` dans Docker Compose, et un `healthcheck` sur postgres avec `pg_isready`.

---

## Comparaison des options de déploiement

| Option | Coût | Carte bancaire | Adapté pour |
|--------|------|----------------|-------------|
| Minikube | Gratuit | Non | Apprentissage local |
| k3s local | Gratuit | Non | Dev local production-like |
| k3s + ngrok | Gratuit | Non | CI/CD réel sans cloud |
| Oracle OCI | Gratuit (free tier) | Parfois demandée | Homelab cloud |
| GKE | ~15$/mois | Oui | Production réelle |
| AWS EKS | ~75$/mois | Oui | Production enterprise |

---

## Glossaire

| Terme | Définition |
|-------|------------|
| **Image Docker** | Template immuable et portable contenant le code, le runtime et les dépendances. Analogue à une classe en POO. |
| **Conteneur** | Instance en cours d'exécution d'une image. Processus Linux isolé via namespaces et cgroups. |
| **Dockerfile** | Fichier recette pour construire une image, instruction par instruction. |
| **Layer (couche)** | Chaque instruction Dockerfile crée une couche immuable mise en cache. L'ordre des instructions impacte la vitesse de build. |
| **Registry** | Stockage d'images Docker (Docker Hub, ghcr.io, Google Container Registry...). |
| **Docker Compose** | Outil pour définir et lancer des applications multi-conteneurs via un fichier YAML. |
| **healthcheck** | Vérification périodique qu'un service est prêt — `pg_isready` pour PostgreSQL. |
| **depends_on** | Directive Compose qui ordonne le démarrage des services selon leurs dépendances. |
| **Pod** | Unité de base Kubernetes — un ou plusieurs conteneurs partageant réseau et stockage. |
| **Deployment** | Ressource K8s déclarant l'état désiré pour un ensemble de Pods. Gère la résilience et les rolling updates. |
| **Service** | Expose des Pods avec une adresse stable et fait du load balancing. Nécessaire car les Pods ont des IPs éphémères. |
| **ClusterIP** | Type de Service accessible uniquement à l'intérieur du cluster. |
| **NodePort** | Type de Service exposé sur un port fixe de chaque nœud (30000-32767). |
| **LoadBalancer** | Type de Service qui provisionne une IP publique via le cloud (GKE, EKS, AKS). |
| **Ingress** | Règles de routage HTTP/HTTPS vers les Services — géré par l'Ingress Controller. |
| **Ingress Controller** | Reverse proxy (Nginx) qui implémente les règles Ingress dans le cluster. |
| **TLS Termination** | Déchiffrement du trafic HTTPS à l'entrée du cluster par l'Ingress Controller. |
| **cert-manager** | Outil K8s qui automatise la gestion des certificats TLS via Let's Encrypt. |
| **ConfigMap** | Config non sensible stockée en clair dans Kubernetes (URLs, noms, paramètres). |
| **Secret** | Données sensibles encodées en base64 dans Kubernetes. Base64 ≠ chiffrement. |
| **envFrom** | Directive K8s qui injecte toutes les clés d'un ConfigMap ou Secret comme variables d'env. |
| **etcd** | Base de données clé-valeur distribuée qui stocke tout l'état du cluster Kubernetes. |
| **Controller-Manager** | Boucle de contrôle permanente qui maintient état réel = état désiré. |
| **Scheduler** | Composant K8s qui décide sur quel Worker Node placer un nouveau Pod. |
| **Kubelet** | Agent sur chaque Worker Node qui reçoit les ordres du Master et gère les Pods locaux. |
| **Prometheus** | Système de monitoring qui collecte les métriques par scraping (pull) toutes les N secondes. |
| **Grafana** | Outil de visualisation de métriques. Se connecte à Prometheus pour créer des dashboards. |
| **PromQL** | Langage de requête de Prometheus pour interroger et agréger les métriques. |
| **Counter** | Métrique Prometheus qui ne fait que monter (requêtes totales, erreurs totales...). |
| **rate()** | Fonction PromQL qui calcule le taux de variation d'un Counter par seconde. |
| **Scraping** | Mécanisme par lequel Prometheus interroge les endpoints /metrics des applications. |
| **CI** | Continuous Integration — vérification automatique que le code fonctionne à chaque push. |
| **CD** | Continuous Deployment — déploiement automatique en production si la CI réussit. |
| **GitHub Actions** | Plateforme CI/CD intégrée à GitHub, déclenchée par des événements Git. |
| **ghcr.io** | GitHub Container Registry — stockage d'images Docker intégré à GitHub. |
| **SHA du commit** | Identifiant unique d'un commit Git utilisé pour tagger les images en production. |
| **Helm** | Gestionnaire de paquets Kubernetes — package les YAML en charts réutilisables. |
| **Chart** | Package Helm contenant templates et valeurs par défaut d'une application. |
| **Release** | Instance déployée d'un chart Helm dans un cluster (ex: `helm install mon-app`). |
| **values.yaml** | Fichier central des valeurs par défaut d'un chart Helm. |
| **helm upgrade --atomic** | Déploie et rollback automatiquement si le déploiement échoue. |
| **Rolling Update** | Mise à jour progressive des Pods — les nouveaux démarrent avant que les anciens soient supprimés. Zero downtime. |
| **GKE** | Google Kubernetes Engine — cluster Kubernetes managé par Google Cloud. |
| **k3s** | Distribution Kubernetes certifiée CNCF ultra-légère — tient en un binaire de 50 Mo. |
| **ngrok** | Outil qui crée un tunnel HTTPS public vers un port local — permet l'accès depuis internet. |
| **Workload Identity Federation** | Authentification GKE sans clé JSON via tokens OIDC éphémères — la bonne pratique. |
| **OIDC** | OpenID Connect — protocole d'identité fédérée utilisé par Workload Identity. |
| **kubeconfig** | Fichier de configuration kubectl contenant l'adresse du cluster et les credentials d'accès. |
| **imagePullSecrets** | Secret K8s contenant les credentials pour pull une image depuis un registry privé. |
| **12-Factor App** | Méthodologie de référence pour construire des applications cloud-native robustes et portables. |
| **port-forward** | Commande kubectl qui crée un tunnel temporaire vers un Pod ou Service K8s. |

---

*Ubuntu 24 — Docker 27.x — Minikube 1.35.x — k3s latest — kubectl 1.34.x — Helm 3.20.0 — ngrok 3.x — PostgreSQL 16 — Prometheus latest — Grafana latest — Nginx Ingress 1.14.x — GitHub Actions*