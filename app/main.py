from fastapi import FastAPI, File, UploadFile, HTTPException
import httpx
from app.parser import parse_srt_to_chunks

app = FastAPI(
    title="Subtext AI",
    description="Analyse psychologique de dialogues issus de fichiers SRT",
    version="1.0.0"
)

OLLAMA_API_URL = "http://localhost:11434/api/generate"

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """
    Endpoint POST asynchrone qui accepte un fichier .srt, en extrait les dialogues
    et envoie le premier bloc (chunk) à un modèle Ollama local pour une analyse psychologique.
    """
    # 1. Validation de l'extension du fichier
    if not file.filename.endswith(".srt"):
        raise HTTPException(
            status_code=400,
            detail="Le fichier fourni doit avoir l'extension .srt."
        )

    # 2. Lecture asynchrone du fichier et décodage en UTF-8
    try:
        file_bytes = await file.read()
        file_content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Le fichier fourni doit être encodé en UTF-8 valide."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la lecture du fichier : {str(e)}"
        )

    # 3. Extraction et division des dialogues du fichier SRT en chunks
    chunks = await parse_srt_to_chunks(file_content)
    
    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="Aucun dialogue valide n'a pu être extrait du fichier SRT."
        )

    # 4. Pour cette V1 de test : on extrait uniquement le premier élément de la liste
    first_chunk = chunks[0]

    # 5. Préparation du prompt et du payload JSON pour Ollama
    prompt = (
        "Tu es un profileur psychologique. Analyse le dialogue suivant et renvoie "
        "STRICTEMENT un objet JSON valide avec les clés 'tension_score' (int de 1 à 10), "
        "'dominant_emotion' (string) et 'manipulation_detected' (bool). Dialogue : "
        + first_chunk
    )
    
    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    # 6. Envoi de la requête asynchrone à l'API locale d'Ollama
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(OLLAMA_API_URL, json=payload)
            response.raise_for_status()
            ollama_response = response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Ollama a retourné une erreur : {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Impossible de se connecter à Ollama à l'adresse {OLLAMA_API_URL} : {str(e)}"
            )

    # 7. Retourner la réponse JSON d'Ollama directement au client
    return ollama_response
