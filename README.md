# 🐳 Docker & ☸️ Kubernetes — Guide Pratique Complet

> Projet d'apprentissage progressif des deux architectures de conteneurisation, basé sur le déploiement d'une API Flask simple.

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis & Installation](#prérequis--installation)
3. [L'application commune](#lapplication-commune)
4. [Projet 1 — Docker](#projet-1--docker-)
5. [Projet 2 — Kubernetes](#projet-2--kubernetes-)
6. [Problèmes rencontrés & Solutions](#problèmes-rencontrés--solutions)
7. [Comparaison Docker vs Kubernetes](#comparaison-docker-vs-kubernetes)
8. [Glossaire](#glossaire)

---

## Vue d'ensemble

Ce projet explore les deux grandes architectures de conteneurisation en déployant la **même application** (une API Python/Flask) avec Docker puis Kubernetes. L'objectif est de comprendre concrètement le flux illustré dans le schéma ci-dessous :

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
                                            ↓
                                      Worker Node
                                  ┌──────────────────┐
                                  │ Kubelet           │
                                  │ Container Runtime │
                                  │ Pods [📦][📦][📦] │
                                  └──────────┬───────┘
                                             ↓
                                   Service Discovery
                                             ↓
                                       Running App
```

---

## Prérequis & Installation

### Technologies utilisées

| Technologie | Rôle | Version testée |
|-------------|------|----------------|
| Python | Langage de l'API | 3.11 |
| Flask | Framework web | 3.x |
| Docker | Conteneurisation | 27.x |
| Minikube | Cluster Kubernetes local | 1.35.x |
| kubectl | CLI pour Kubernetes | 1.34.x |

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

Les deux projets utilisent exactement la même application Flask. C'est intentionnel : cela permet de **comparer les deux approches** sur une base identique.

### Structure du projet

```
docker-app/
├── app.py              # Le code de l'API Flask
├── requirements.txt    # Dépendances Python
├── Dockerfile          # Instructions de build de l'image
├── docker-compose.yml  # Orchestration Docker locale
├── deployment.yaml     # Déclaration Kubernetes — Pods & réplicas
└── service.yaml        # Déclaration Kubernetes — Service Discovery
```

### app.py

```python
from flask import Flask
import socket

app = Flask(__name__)

@app.route("/")
def hello():
    # socket.gethostname() retourne le nom du conteneur ou du pod
    # C'est très utile pour identifier qui répond lors du load balancing
    return f"Bonjour depuis le conteneur : {socket.gethostname()}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

> **Pourquoi `host="0.0.0.0"` ?**
> Par défaut Flask écoute sur `127.0.0.1` (localhost), ce qui signifie que seuls les processus à l'intérieur du même conteneur peuvent y accéder. `0.0.0.0` signifie "écoute sur toutes les interfaces réseau disponibles", ce qui permet au trafic externe d'atteindre Flask.

### requirements.txt

```
flask
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
RUN pip install -r requirements.txt

# On copie le code ensuite (l'ordre est important pour le cache !)
COPY app.py .

# On documente que le conteneur écoute sur le port 5000
# EXPOSE ne publie pas réellement le port — c'est de la documentation
EXPOSE 5000

# La commande qui s'exécute quand le conteneur démarre
CMD ["python", "app.py"]
```

### Construction de l'image

```bash
# Syntaxe : docker build -t <nom>:<tag> <chemin-du-Dockerfile>
docker build -t mon-api:v1 .

# Si problème de DNS (réseau d'entreprise, VPN, conflit Minikube) :
docker build --network=host -t mon-api:v1 .
```

Ce que Docker fait en coulisses :
1. Lit le Dockerfile instruction par instruction
2. Pour chaque instruction, crée une **couche** (layer) en lecture seule
3. Met chaque couche en cache pour les builds futurs
4. Empile toutes les couches pour former l'image finale

```
IMAGE mon-api:v1
├── Couche 4 : COPY app.py          [nouvelle à chaque modif du code]
├── Couche 3 : RUN pip install      [en cache si requirements.txt inchangé]
├── Couche 2 : COPY requirements.txt [en cache si inchangé]
├── Couche 1 : WORKDIR /app
└── Couche 0 : python:3.11-alpine   [téléchargée une seule fois]
```

Vérifier que l'image est bien créée :
```bash
docker images
# REPOSITORY   TAG   IMAGE ID       CREATED         SIZE
# mon-api      v1    90d97d03bd49   2 minutes ago   58MB
```

### Lancer des conteneurs

```bash
# -d = detached (arrière-plan), -p = port mapping, --name = nom lisible
docker run -d -p 8080:5000 --name api1 mon-api:v1
docker run -d -p 8081:5000 --name api2 mon-api:v1
docker run -d -p 8082:5000 --name api3 mon-api:v1
```

> **Comprendre le port mapping `-p 8080:5000`**
>
> `[port_machine_hôte]:[port_dans_le_conteneur]`
>
> Flask écoute sur le port 5000 **à l'intérieur** du conteneur. Depuis l'extérieur, tu accèdes via le port 8080 de ta machine. Trois conteneurs peuvent tous écouter sur le port 5000 en interne — ils sont isolés — mais ils doivent avoir des ports différents sur la machine hôte.

Tester :
```bash
curl http://localhost:8080   # Réponse : Bonjour depuis le conteneur : a3f2c1b8d904
curl http://localhost:8081   # Réponse : Bonjour depuis le conteneur : b7e9c2f1a203
curl http://localhost:8082   # Réponse : Bonjour depuis le conteneur : c1d4e8b5f306
```

Chaque réponse affiche un ID différent — c'est l'**isolation des conteneurs** en action.

### Commandes Docker essentielles

```bash
# Lister les conteneurs en cours d'exécution
docker ps

# Lister tous les conteneurs (y compris arrêtés)
docker ps -a

# Voir les logs d'un conteneur
docker logs api1
docker logs -f api1   # -f = follow (temps réel)

# Entrer dans un conteneur (shell interactif)
docker exec -it api1 sh

# Arrêter et supprimer des conteneurs
docker stop api1 api2 api3
docker rm api1 api2 api3

# Supprimer une image
docker rmi mon-api:v1

# Voir l'utilisation des ressources en temps réel
docker stats
```

### Docker Compose — orchestrer plusieurs conteneurs

Au lieu de taper plusieurs `docker run`, on déclare tout dans un fichier YAML :

```yaml
# docker-compose.yml
version: "3"
services:
  api1:
    build: .
    ports:
      - "8080:5000"
  api2:
    build: .
    ports:
      - "8081:5000"
  api3:
    build: .
    ports:
      - "8082:5000"
```

```bash
# Démarrer tous les services
docker compose up -d

# Voir les logs de tous les services
docker compose logs -f

# Arrêter et supprimer tout
docker compose down
```

---

## Projet 2 — Kubernetes ☸️

### Architecture du cluster Minikube

Minikube crée un cluster Kubernetes complet sur ta machine. Même si tout tourne localement, il respecte parfaitement l'architecture réelle :

```
Ta machine
└── Minikube (VM ou conteneur)
    ├── Master Node (control-plane)
    │   ├── API Server        → point d'entrée de toutes les commandes kubectl
    │   ├── etcd              → base de données clé-valeur (l'état du cluster)
    │   ├── Controller-Manager → surveille et corrige l'état du cluster
    │   └── Scheduler         → décide sur quel Worker Node placer chaque Pod
    └── Worker Node
        ├── Kubelet           → agent qui exécute les ordres du Master
        ├── Container Runtime → (Docker ou containerd) fait tourner les conteneurs
        └── Pods              → groupes de conteneurs (unité de base dans K8s)
```

### Étape 1 — Préparer l'image pour Minikube

**Le problème clé :** Minikube a son propre registre d'images Docker, séparé de celui de ta machine. Il y a deux solutions :

**Solution A — Charger l'image depuis ta machine (recommandée)**

```bash
# S'assurer qu'on est bien sur le Docker local (pas celui de Minikube)
eval $(minikube docker-env --unset)

# Vérifier que l'image existe localement
docker images | grep mon-api

# Transférer l'image dans le registre de Minikube
minikube image load mon-api:v1

# Vérifier qu'elle est bien arrivée
minikube image ls | grep mon-api
```

**Solution B — Builder directement dans Minikube**

```bash
# Rediriger le client Docker vers le daemon interne de Minikube
eval $(minikube docker-env)

# Builder (l'image ira directement dans le registre de Minikube)
docker build --network=host -t mon-api:v1 .

# Pour revenir au Docker local ensuite :
eval $(minikube docker-env --unset)
```

> ⚠️ **Attention** : `eval $(minikube docker-env)` modifie des variables d'environnement dans ta session shell. Toutes tes commandes `docker` iront dans Minikube jusqu'à ce que tu fasses `--unset`. C'est une source classique de confusion !

### Étape 2 — Le Deployment (deployment.yaml)

Le Deployment est la ressource Kubernetes qui dit **ce que tu veux** (état désiré). Le Controller-Manager s'assure que la réalité correspond toujours à cette déclaration.

```yaml
apiVersion: apps/v1        # Version de l'API Kubernetes pour cette ressource
kind: Deployment           # Type de ressource
metadata:
  name: mon-api-deployment # Nom unique du Deployment dans le cluster
spec:
  replicas: 3              # Je veux exactement 3 Pods en permanence
  selector:
    matchLabels:
      app: mon-api         # Ce Deployment gère les Pods avec ce label
  template:                # Modèle pour créer chaque Pod
    metadata:
      labels:
        app: mon-api       # Label appliqué à chaque Pod créé
    spec:
      containers:
      - name: mon-api
        image: mon-api:v1
        imagePullPolicy: Never  # Ne pas essayer de télécharger depuis internet
        ports:
        - containerPort: 5000
```

### Étape 3 — Le Service (service.yaml)

Sans Service, les Pods sont inaccessibles de l'extérieur et n'ont pas d'adresse stable. Le Service est le **Service Discovery** du schéma.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mon-api-service
spec:
  type: NodePort           # Expose le service en dehors du cluster
  selector:
    app: mon-api           # Route le trafic vers tous les Pods avec ce label
  ports:
  - port: 5000             # Port du Service à l'intérieur du cluster
    targetPort: 5000       # Port sur lequel le conteneur écoute
    nodePort: 30080        # Port exposé sur le nœud (30000-32767)
```

> **Types de Service :**
>
> `ClusterIP` → accessible uniquement à l'intérieur du cluster (défaut)
>
> `NodePort` → expose un port sur chaque nœud du cluster (pour le dev local)
>
> `LoadBalancer` → crée un load balancer externe (cloud AWS/GCP/Azure)

### Étape 4 — Déployer et observer

```bash
# Envoyer les déclarations à l'API Server du Master Node
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Observer les Pods créés dans le Worker Node (-w = watch, temps réel)
kubectl get pods -w
```

Résultat attendu :
```
NAME                                  READY   STATUS    RESTARTS   AGE
mon-api-deployment-54bb58689b-24jkd   1/1     Running   0          15s
mon-api-deployment-54bb58689b-tpbtm   1/1     Running   0          15s
mon-api-deployment-54bb58689b-vxzlk   1/1     Running   0          23s
```

Accéder à l'application :
```bash
# Obtenir l'URL d'accès
minikube service mon-api-service --url

# Tester plusieurs fois — le pod qui répond change à chaque fois !
curl http://192.168.49.2:30080
curl http://192.168.49.2:30080
curl http://192.168.49.2:30080
```

### Étape 5 — Tester la résilience (le vrai pouvoir de Kubernetes)

```bash
# Supprimer volontairement un Pod
kubectl delete pod mon-api-deployment-54bb58689b-24jkd

# Observer immédiatement : le Controller-Manager recrée un nouveau Pod !
kubectl get pods -w
```

Ce que tu vas voir :
```
NAME                                  READY   STATUS        RESTARTS
mon-api-deployment-54bb58689b-24jkd   1/1     Terminating   0        ← Pod supprimé
mon-api-deployment-54bb58689b-x9pq2   0/1     Pending       0        ← Nouveau Pod créé
mon-api-deployment-54bb58689b-x9pq2   1/1     Running       0        ← Pod prêt
```

C'est le **Controller-Manager** en action : il surveille en permanence que l'état réel (2 pods) = état désiré (3 pods) et corrige automatiquement.

### Étape 6 — Scaling (montée en charge)

```bash
# Passer à 5 réplicas en une commande
kubectl scale deployment mon-api-deployment --replicas=5
kubectl get pods   # 5 pods actifs

# Redescendre à 2
kubectl scale deployment mon-api-deployment --replicas=2
kubectl get pods   # 2 pods actifs (les autres sont terminés proprement)
```

### Commandes kubectl essentielles

```bash
# ── INFORMATIONS ──────────────────────────────────────────────────
kubectl get nodes                          # État des nœuds du cluster
kubectl get pods                           # Lister les Pods
kubectl get pods -o wide                   # Avec plus de détails (IP, nœud)
kubectl get deployments                    # Lister les Deployments
kubectl get services                       # Lister les Services
kubectl get all                            # Tout voir d'un coup

# ── DEBUGGING ─────────────────────────────────────────────────────
kubectl describe pod <nom-du-pod>          # Détails complets + événements
kubectl logs <nom-du-pod>                  # Logs du conteneur
kubectl logs -f <nom-du-pod>               # Logs en temps réel
kubectl exec -it <nom-du-pod> -- sh        # Shell interactif dans le Pod

# ── ACTIONS ───────────────────────────────────────────────────────
kubectl apply -f fichier.yaml              # Créer ou mettre à jour une ressource
kubectl delete -f fichier.yaml             # Supprimer via fichier YAML
kubectl delete pod <nom-du-pod>            # Supprimer un Pod spécifique
kubectl scale deployment <nom> --replicas=5  # Changer le nombre de réplicas

# ── MINIKUBE ──────────────────────────────────────────────────────
minikube start                             # Démarrer le cluster
minikube stop                              # Arrêter le cluster
minikube status                            # État du cluster
minikube dashboard                         # Interface web graphique !
minikube service <nom-service> --url       # Obtenir l'URL d'un service
minikube image load <image:tag>            # Charger une image locale
minikube image ls                          # Lister les images disponibles
eval $(minikube docker-env)                # Pointer Docker vers Minikube
eval $(minikube docker-env --unset)        # Revenir au Docker local
```

---

## Problèmes rencontrés & Solutions

### 1. `lookup registry-1.docker.io: i/o timeout`

**Symptôme :** Docker ne peut pas télécharger les images depuis Docker Hub.

**Cause :** Le daemon Docker utilise un serveur DNS défaillant ou celui de Minikube (`192.168.49.1`).

**Solution :**
```bash
# Éditer la config du daemon Docker
sudo nano /etc/docker/daemon.json

# Ajouter les DNS publics Google
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}

# Redémarrer Docker
sudo systemctl restart docker

# Ou utiliser --network=host lors du build
docker build --network=host -t mon-api:v1 .
```

---

### 2. `dial tcp 192.168.49.2:2376: connect: no route to host`

**Symptôme :** La commande `docker` essaie de se connecter à l'adresse de Minikube au lieu du Docker local.

**Cause :** La variable d'environnement `DOCKER_HOST` pointe encore vers Minikube suite à un `eval $(minikube docker-env)` précédent.

**Solution :**
```bash
# Annuler la redirection vers Minikube
eval $(minikube docker-env --unset)

# Vérifier que Docker local répond
docker info
```

---

### 3. `ErrImageNeverPull`

**Symptôme :** Les Pods Kubernetes sont en erreur, ils ne trouvent pas l'image.

**Cause :** L'image a été buildée dans le registre Docker local, mais Kubernetes cherche dans son propre registre interne.

**Solution :**
```bash
# Transférer l'image du Docker local vers le registre Minikube
minikube image load mon-api:v1

# Vérifier la présence de l'image
minikube image ls | grep mon-api

# Les Pods vont automatiquement réessayer et passer en Running
kubectl get pods -w
```

---

### 4. `kubectl : commande introuvable`

**Symptôme :** `kubectl` n'est pas installé.

**Solution :**
```bash
# Via snap
sudo snap install kubectl --classic

# OU via alias Minikube (plus simple, toujours compatible)
echo "alias kubectl='minikube kubectl --'" >> ~/.bashrc
source ~/.bashrc
```

---

## Comparaison Docker vs Kubernetes

| Aspect | Docker | Kubernetes |
|--------|--------|------------|
| **Complexité** | Simple, facile à démarrer | Complexe, courbe d'apprentissage importante |
| **Cas d'usage** | Dev local, petits projets | Production, applications à grande échelle |
| **Scaling** | Manuel (`docker run` plusieurs fois) | Automatique (`replicas: 5` dans le YAML) |
| **Résilience** | Aucune — si un conteneur meurt, il reste mort | Automatique — le Controller-Manager recrée les Pods |
| **Load balancing** | Manuel ou via Docker Compose | Intégré dans les Services |
| **Service Discovery** | Manuel ou via Docker Compose | Natif avec les Services et labels |
| **Configuration** | `docker run` ou `docker-compose.yml` | Fichiers YAML déclaratifs |
| **Monitoring** | `docker stats`, `docker logs` | `kubectl describe`, dashboard, Prometheus... |
| **Réseau** | Bridge network par défaut | CNI (Container Network Interface) |
| **Philosophie** | **Impératif** — tu dis *comment* faire | **Déclaratif** — tu dis *quoi* tu veux |

### La différence philosophique fondamentale

Avec Docker, tu **commandes** : "lance ce conteneur sur ce port avec ces paramètres".

Avec Kubernetes, tu **déclares** : "je veux 3 instances de mon API accessibles sur ce port, toujours". Kubernetes s'occupe du *comment* et maintient cet état en permanence, même si des pods plantent ou si des nœuds tombent.

---

## Glossaire

| Terme | Définition |
|-------|------------|
| **Image** | Template immuable (lecture seule) à partir duquel on crée des conteneurs. Analogue à une classe en POO. |
| **Conteneur** | Instance en cours d'exécution d'une image. Analogue à un objet instancié. |
| **Dockerfile** | Fichier de recette pour construire une image, instruction par instruction. |
| **Layer (couche)** | Chaque instruction du Dockerfile crée une couche en cache. |
| **Registry** | Stockage d'images Docker (Docker Hub, GitHub Container Registry...). |
| **Pod** | Unité de base dans Kubernetes — un ou plusieurs conteneurs partageant réseau et stockage. |
| **Deployment** | Ressource K8s qui gère la création et mise à jour d'un ensemble de Pods. |
| **Service** | Ressource K8s qui expose des Pods avec une adresse stable et fait du load balancing. |
| **Master Node** | Cerveau du cluster K8s — contient l'API Server, Scheduler, Controller-Manager, etcd. |
| **Worker Node** | Machine qui exécute réellement les conteneurs (Pods). |
| **Kubelet** | Agent sur chaque Worker Node qui reçoit les ordres du Master et gère les Pods. |
| **etcd** | Base de données clé-valeur distribuée qui stocke tout l'état du cluster K8s. |
| **Controller-Manager** | Boucle de contrôle qui surveille l'état réel et le corrige pour correspondre à l'état désiré. |
| **Scheduler** | Composant qui décide sur quel Worker Node placer un nouveau Pod. |
| **kubectl** | Outil en ligne de commande pour interagir avec l'API Server de Kubernetes. |
| **Minikube** | Outil qui crée un cluster Kubernetes complet en local pour le développement. |
| **YAML** | Format de fichier de configuration utilisé par Kubernetes pour décrire les ressources. |
| **Label** | Paire clé-valeur attachée à une ressource K8s pour l'organisation et la sélection. |
| **Selector** | Filtre qui sélectionne des ressources K8s par leurs labels. |
| **NodePort** | Type de Service qui expose l'application sur un port fixe de chaque nœud. |
| **imagePullPolicy: Never** | Directive K8s pour ne jamais tenter de télécharger l'image depuis internet. |

---

*Projet réalisé sur Ubuntu 24 — Docker 27.x — Minikube 1.35.1 — kubectl 1.34.4*
