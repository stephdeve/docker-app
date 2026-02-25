from flask import Flask, jsonify
import socket
import os  # os.environ permet de lire les variables d'environnement
import psycopg2  # Le client PostgreSQL pour Python
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
APP_ENV = os.environ.get("APP_ENV", "development")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

# Pour les credentials, on utilise os.environ.get sans valeur par défaut
# Si la variable est absente, on retourne None — l'app peut gérer ce cas
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "appdb")
DB_USER = os.environ.get("DB_USER", "appuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD")  # Pas de valeur par défaut pour les secrets !

@app.route("/")
@hello_counter
def hello():
    return f"Bonjour depuis {socket.gethostname()} [env: {APP_ENV}, v{APP_VERSION}]\n"

@app.route("/health")
def health():
    return {"status": "ok", "pod": socket.gethostname(), "env": APP_ENV}

@app.route("/config")
def config():
    # Cet endpoint expose la config NON sensible pour le debugging
    # Ne jamais exposer DB_PASSWORD ici !
    return jsonify({
        "app_env": APP_ENV,
        "app_version": APP_VERSION,
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_name": DB_NAME,
        "db_user": DB_USER,
        "db_password": "***" if DB_PASSWORD else "NOT SET"  # Masqué intentionnellement
    })

@app.route("/db-test")
def db_test():
    """Teste la connexion à PostgreSQL et retourne le résultat."""
    if not DB_PASSWORD:
        return jsonify({"error": "DB_PASSWORD not configured"}), 500
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=3  # Timeout rapide pour ne pas bloquer les health checks
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