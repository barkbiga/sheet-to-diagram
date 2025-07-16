# Image de base légère avec Python 3.11
FROM python:3.11-slim

# Empêche les fichiers .pyc
ENV PYTHONDONTWRITEBYTECODE=1
# Active le mode unbuffered (utile pour logs)
ENV PYTHONUNBUFFERED=1

# Crée un dossier pour l'app
WORKDIR /app

# Copie les fichiers nécessaires
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Commande de lancement par défaut
CMD ["python", "main.py"]
