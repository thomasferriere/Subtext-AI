import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import database
from app.parser import SRTParseError, parse_srt_to_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subtext.main")

# Chemins (résolus depuis la racine du projet, indépendamment du cwd de lancement)
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"
OLLAMA_TIMEOUT = 60.0

# Taille maximale d'un upload (anti-DoS mémoire) : un .srt de sous-titres reste
# très léger ; 5 Mo est largement suffisant.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# --- Sécurité : clé API optionnelle + rate limiting ---------------------------
# Authentification désactivée par défaut (usage local). Définir la variable
# d'environnement SUBTEXT_API_KEY active la protection : les requêtes doivent
# alors présenter l'en-tête `X-API-Key`.
API_KEY = os.environ.get("SUBTEXT_API_KEY")

# Fenêtre glissante : au plus RATE_LIMIT_MAX requêtes par IP sur RATE_LIMIT_WINDOW
# secondes. En mémoire (mono-processus) — suffisant pour un déploiement simple.
RATE_LIMIT_MAX = 20
RATE_LIMIT_WINDOW = 60.0


class RateLimiter:
    """Limiteur de débit à fenêtre glissante, par clé (IP), sûr en asynchrone."""

    def __init__(self, max_requests: int, window_seconds: float):
        self._max = max_requests
        self._window = window_seconds
        self._hits: defaultdict = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str):
        """Retourne (autorisé: bool, retry_after_secondes: float)."""
        now = time.monotonic()
        async with self._lock:
            hits = self._hits[key]
            # Purge des horodatages sortis de la fenêtre.
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._max:
                return False, self._window - (now - hits[0])
            hits.append(now)
            return True, 0.0


_rate_limiter = RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW)


async def verify_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """Exige l'en-tête X-API-Key uniquement si SUBTEXT_API_KEY est configurée."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Clé API invalide ou manquante.")


async def rate_limit(request: Request):
    """Applique le limiteur de débit par adresse IP cliente."""
    client = request.client.host if request.client else "unknown"
    allowed, retry_after = await _rate_limiter.check(client)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Trop de requêtes. Merci de patienter avant de réessayer.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

# --- Ingénierie de prompt -----------------------------------------------------
# System prompt : définit le rôle, le schéma JSON strict et les consignes
# d'analyse des rapports de pouvoir (qui domine, intention).
SYSTEM_PROMPT = (
    "Tu es un profileur psychologique et analyste narratif expert. "
    "Ta mission est d'analyser un extrait de dialogue et d'en révéler le sous-texte.\n\n"
    "RÈGLES D'ANALYSE :\n"
    "1. DOMINATION : identifie qui mène la conversation. Le dominant est "
    "généralement celui qui POSE LES QUESTIONS, oriente le sujet ou impose le "
    "rythme ; le dominé est celui qui répond, se justifie ou subit.\n"
    "2. INTENTION : déduis l'objectif réel de l'interaction en analysant les "
    "verbes d'action et de volonté (vouloir, exiger, convaincre, obtenir, "
    "cacher, protéger...). Distingue l'intention affichée de l'intention réelle.\n"
    "3. CONFLIT : qualifie la nature de la tension (pouvoir, jalousie, "
    "trahison, séduction, négociation, aucun...).\n"
    "4. MANIPULATION : détecte culpabilisation, chantage affectif, "
    "déformation des faits ou double discours.\n\n"
    "FORMAT DE SORTIE : tu réponds STRICTEMENT et UNIQUEMENT avec un objet JSON "
    "valide, sans texte avant ou après, sans bloc de code markdown."
)

# Few-shot : un exemple concret guide le modèle vers un formatage strict et une
# analyse plus profonde (schéma complet attendu en sortie).
FEW_SHOT_EXAMPLE_INPUT = (
    "- Où étais-tu hier soir ?\n"
    "- Je te l'ai déjà dit, au bureau.\n"
    "- Curieux, j'ai appelé le bureau. Personne.\n"
    "- ... Tu me surveilles maintenant ?"
)
FEW_SHOT_EXAMPLE_OUTPUT = json.dumps(
    {
        "tension_score": 8,
        "conflict_type": "trahison",
        "dominant_emotion": "méfiance",
        "dominant_trait": "contrôle",
        "power_dynamics": {
            "who_dominates": "Le premier interlocuteur",
            "reason": "Il pose toutes les questions et confronte l'autre à une "
            "contradiction, plaçant son vis-à-vis en position de justification.",
        },
        "intention": "Confondre l'autre et obtenir un aveu de mensonge.",
        "manipulation_detected": True,
    },
    ensure_ascii=False,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialise la base de données au démarrage de l'application."""
    await database.init_db()
    yield


app = FastAPI(
    title="Subtext AI",
    description="Analyse psychologique de dialogues issus de fichiers SRT",
    version="1.0.0",
    lifespan=lifespan,
)

# Service des fichiers statiques (CSS, JS, assets) sous /static.
# Le répertoire est créé s'il n'existe pas pour éviter une erreur au démarrage.
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _parse_ollama_analysis(raw_text):
    """
    Tente de transformer la sortie textuelle d'Ollama en dictionnaire Python.

    Robuste face à un modèle qui ne respecte pas parfaitement le format JSON :
    1. Essai d'un parsing JSON direct.
    2. À défaut, extraction du premier objet ``{...}`` repérable dans le texte
       (cas fréquent où le modèle ajoute du texte autour du JSON).

    Returns:
        tuple[dict | None, bool] : (analyse parsée, format_valide). En cas
        d'échec total, renvoie (None, False) sans jamais lever d'exception.
    """
    if isinstance(raw_text, dict):
        return raw_text, True

    if not isinstance(raw_text, str):
        return None, False

    # 1. Parsing direct
    try:
        return json.loads(raw_text), True
    except json.JSONDecodeError:
        pass

    # 2. Extraction du premier bloc JSON présent dans la chaîne
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0)), True
        except json.JSONDecodeError:
            pass

    return None, False


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


@app.get(
    "/history",
    tags=["analysis"],
    dependencies=[Depends(verify_api_key), Depends(rate_limit)],
)
async def history():
    """
    Retourne la liste des analyses précédemment sauvegardées, de la plus récente
    à la plus ancienne, afin d'alimenter l'historique du dashboard.
    """
    try:
        entries = await database.get_history()
    except Exception as exc:
        logger.exception("Lecture de l'historique impossible.")
        raise HTTPException(
            status_code=500,
            detail=f"Impossible de récupérer l'historique : {exc}",
        ) from exc

    return {"count": len(entries), "history": entries}


@app.post(
    "/analyze",
    tags=["analysis"],
    dependencies=[Depends(verify_api_key), Depends(rate_limit)],
)
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

    # 2. Lecture asynchrone du fichier (nécessaire avant le cache : l'indexation
    # se fait sur le hash du CONTENU, pas sur le nom de fichier).
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

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "Fichier trop volumineux : la taille maximale autorisée est de "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} Mo."
            ),
        )

    # 2bis. Empreinte MD5 du contenu : deux fichiers identiques (même contenu)
    # partagent le même hash et donc le même cache ; deux fichiers homonymes au
    # contenu différent produisent des hash distincts et sont traités séparément.
    # usedforsecurity=False : le MD5 sert de clé de cache, pas de garantie crypto.
    content_hash = hashlib.md5(file_bytes, usedforsecurity=False).hexdigest()

    # 2ter. Cache : si ce contenu a déjà été analysé, on renvoie le résultat
    # sauvegardé sans solliciter Ollama. Une panne de la base ne doit pas
    # empêcher une nouvelle analyse : on log et on poursuit.
    try:
        cached = await database.get_analysis_by_hash(content_hash)
    except Exception:
        logger.exception("Lecture du cache impossible ; analyse normale poursuivie.")
        cached = None

    if cached is not None:
        logger.info(
            "Cache hit (hash=%s, analyse #%s, fichier d'origine '%s').",
            content_hash, cached["id"], cached["filename"],
        )
        return {**cached["result"], "cached": True, "cached_at": cached["timestamp"]}

    # 3. Décodage UTF-8 du contenu.
    try:
        file_content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Le fichier fourni doit être encodé en UTF-8 valide.",
        )

    # 4. Extraction et division des dialogues du fichier SRT en chunks
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

    # Pour cette V1 de test : on n'analyse que le premier bloc.
    first_chunk = chunks[0]

    # 5. Construction du prompt Few-Shot (exemple résolu + dialogue à analyser).
    prompt = (
        "Voici un exemple d'analyse attendue.\n\n"
        f"### Dialogue exemple :\n{FEW_SHOT_EXAMPLE_INPUT}\n\n"
        f"### Analyse JSON attendue :\n{FEW_SHOT_EXAMPLE_OUTPUT}\n\n"
        "Analyse maintenant le dialogue ci-dessous en respectant EXACTEMENT le "
        "même schéma JSON (mêmes clés, mêmes types).\n\n"
        f"### Dialogue à analyser :\n{first_chunk}\n\n"
        "### Analyse JSON :"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "system": SYSTEM_PROMPT,
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

    # 7. Extraction et validation robuste de l'analyse renvoyée par le modèle.
    # Ollama place le contenu généré dans la clé "response" (chaîne JSON ici).
    raw_analysis = ollama_response.get("response")
    analysis, format_valid = _parse_ollama_analysis(raw_analysis)

    # Le modèle a échoué à produire un JSON exploitable : on dégrade proprement
    # (réponse 200 structurée) au lieu de propager une erreur 502 au client.
    if not format_valid:
        logger.warning("Le modèle n'a pas renvoyé de JSON valide ; renvoi dégradé.")
        analysis = {
            "error": "Le modèle n'a pas respecté le format JSON attendu.",
            "raw_response": raw_analysis,
        }

    result = {
        "chunks_total": len(chunks),
        "format_valid": format_valid,
        "analysis": analysis,
    }

    # 8. Persistance : on sauvegarde l'analyse (indexée par hash de contenu) pour
    # servir le cache et l'historique. Un échec d'écriture ne doit pas priver le
    # client de son résultat.
    try:
        meta = await database.save_analysis(file.filename, content_hash, result)
        result["id"] = meta["id"]
        result["timestamp"] = meta["timestamp"]
    except Exception:
        logger.exception("Sauvegarde de l'analyse impossible ; résultat renvoyé sans persistance.")

    result["cached"] = False
    return result
