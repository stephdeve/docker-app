# On part d'une image Python légère (alpine = très petite taille)
FROM python:3.11-alpine

# On définit le dossier de travail à l'intérieur du conteneur
WORKDIR /app

# On copie d'abord les dépendances (Docker met ça en cache si ça ne change pas)
COPY requirements.txt .
#RUN apk add --no-cache curl
RUN pip install --no-cache-dir -r requirements.txt --timeout 100

# Ensuite on copie le reste du code
COPY app.py .

# On expose le port sur lequel Flask écoute
EXPOSE 5000

CMD ["python", "app.py"]
