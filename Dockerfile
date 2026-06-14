# syntax=docker/dockerfile:1

# Image légère et officielle (Python 3.11, requis par le projet).
FROM python:3.11-slim

# Bonnes pratiques d'exécution Python en conteneur :
# - pas de fichiers .pyc, sortie non bufferisée (logs en temps réel),
# - pip silencieux et sans cache (image plus légère).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) Dépendances d'abord : cette couche n'est reconstruite que si
#    requirements.txt change (cache Docker -> builds plus rapides).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Code applicatif.
COPY app/ ./app/
COPY static/ ./static/

# 3) Sécurité : exécution sous un utilisateur non-root. Le dossier /app doit
#    rester accessible en écriture (création de subtext.db au démarrage).
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Le backend FastAPI écoute sur le port 8000.
EXPOSE 8000

# Vérification de disponibilité via l'endpoint /health (sans dépendance externe).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# Démarrage : bind sur 0.0.0.0 pour être joignable hors du conteneur.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
