from flask import Flask
import socket
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

# PrometheusMetrics fait deux choses en une :
# 1. Il crée automatiquement l'endpoint GET /metrics
# 2. Il commence à mesurer chaque requête HTTP (durée, statut, méthode...)
# C'est le point d'entrée que Prometheus viendra "scraper" toutes les 15 secondes
metrics = PrometheusMetrics(app)

# On crée notre propre métrique "métier" — un compteur qui ne fait que monter
# Les compteurs sont parfaits pour mesurer des événements (requêtes, erreurs, paiements...)
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

# Endpoint de santé — très utilisé en production pour vérifier qu'un pod est vivant
# Kubernetes l'appellera automatiquement si on configure un "liveness probe"
@app.route("/health")
def health():
    return {"status": "ok", "pod": socket.gethostname()}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
