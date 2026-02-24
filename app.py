from flask import Flask
import socket

app = Flask(__name__)

@app.route("/")
def hello():
    # socket.gethostname() retourne le nom du conteneur — très utile pour voir quel conteneur répond
    return f"Bonjour depuis le conteneur : {socket.gethostname()}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
