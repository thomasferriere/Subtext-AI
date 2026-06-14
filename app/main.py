import json
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.parser import SRTParseError, parse_srt_to_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subtext.main")

# Chemins (résolus depuis la racine du projet, indépendamment du cwd de lancement)
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"
OLLAMA_TIMEOUT = 60.0

app = FastAPI(
    title="Subtext AI",
    description="Analyse psychologique de dialogues issus de fichiers SRT",
    version="1.0.0",
)

# Service des fichiers statiques (CSS, JS, assets) sous /static.
# Le répertoire est créé s'il n'existe pas pour éviter une erreur au démarrage.
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    """Sert l'interface web (single-page) depuis static/index.html."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="Interface introuvable : static/index.html est manquant.",
        )
    return FileResponse(index_file)


@app.get("/health", tags=["monitoring"])
async def health():
    """Sonde de disponibilité simple."""
    return {"status": "ok"}


@app.post("/analyze", tags=["analysis"])
async def analyze(file: UploadFile = File(...)):
    """
    Endpoint POST asynchrone : accepte un fichier .srt, en extrait les dialogues
    et envoie le premier bloc (chunk) à un modèle Ollama local pour une analyse
    psychologique.
    """
    # 1. Validation de l'extension du fichier
    if not file.filename or not file.filename.lower().endswith(".srt"):
        raise HTTPException(
            status_code=400,
            detail="Le fichier fourni doit avoir l'extension .srt.",
        )

    # 2. Lecture asynchrone du fichier et décodage en UTF-8
    try:
        file_bytes = await file.read()
    except Exception as exc:  # erreur de transfert / lecture du flux
        logger.exception("Échec de la lecture du fichier uploadé.")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la lecture du fichier : {exc}",
        ) from exc

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Le fichier fourni est vide.")

    try:
        file_content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Le fichier fourni doit être encodé en UTF-8 valide.",
        )

    # 3. Extraction et division des dialogues du fichier SRT en chunks
    try:
        chunks = await parse_srt_to_chunks(file_content)
    except SRTParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Fichier SRT mal formé : {exc}",
        ) from exc

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="Aucun dialogue valide n'a pu être extrait du fichier SRT.",
        )

    # 4. Pour cette V1 de test : on n'analyse que le premier bloc.
    first_chunk = chunks[0]

    # 5. Préparation du prompt et du payload JSON pour Ollama
    prompt = (
        "Tu es un profileur psychologique. Analyse le dialogue suivant et renvoie "
        "STRICTEMENT un objet JSON valide avec les clés 'tension_score' (int de 1 à 10), "
        "'dominant_emotion' (string) et 'manipulation_detected' (bool). Dialogue : "
        + first_chunk
    )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    # 6. Envoi de la requête asynchrone à l'API locale d'Ollama
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        try:
            response = await client.post(OLLAMA_API_URL, json=payload)
            response.raise_for_status()
            ollama_response = response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail="Ollama n'a pas répondu dans le délai imparti.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Ollama a retourné une erreur : {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Impossible de se connecter à Ollama à l'adresse "
                    f"{OLLAMA_API_URL}. Le service est-il démarré ? ({exc})"
                ),
            ) from exc

    # 7. Extraction et validation de l'analyse renvoyée par le modèle.
    # Ollama renvoie le contenu généré dans la clé "response" (chaîne JSON ici).
    raw_analysis = ollama_response.get("response")
    if raw_analysis is None:
        raise HTTPException(
            status_code=502,
            detail="Réponse inattendue d'Ollama : champ 'response' absent.",
        )

    try:
        analysis = json.loads(raw_analysis)
    except (json.JSONDecodeError, TypeError):
        # Le modèle n'a pas respecté le format JSON : on renvoie la sortie brute.
        logger.warning("Réponse d'Ollama non parsable en JSON, renvoi brut.")
        analysis = {"raw_response": raw_analysis}

    return {"chunks_total": len(chunks), "analysis": analysis}
