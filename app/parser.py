import logging
import re
from typing import List

logger = logging.getLogger("subtext.parser")


class SRTParseError(ValueError):
    """Erreur levée lorsqu'un fichier SRT ne peut pas être analysé correctement."""


# Expressions régulières pour le nettoyage (compilées une seule fois au chargement du module)
# 1. Numéros de séquence : une ligne contenant uniquement des chiffres
_SEQUENCE_PATTERN = re.compile(r"^\d+$")

# 2. Timestamps SRT classiques (ex: 00:01:23,456 --> 00:01:25,789)
# Gère également les variations de séparateurs décimaux (virgule ou point) et d'éventuels espaces
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{1,2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[.,]\d{3}.*$"
)

# 3. Balises HTML (ex: <i>, <b>, <font ...>) : tout ce qui est entre < et >
_HTML_PATTERN = re.compile(r"<[^>]+>")


async def parse_srt_to_chunks(
    file_content: str, chunk_size: int = 50, overlap: int = 5
) -> List[str]:
    """
    Analyse le contenu textuel d'un fichier .srt, le nettoie et le regroupe en blocs (chunks)
    glissants avec recouvrement (overlap).

    Étapes :
    1. Découpe le contenu par ligne.
    2. Supprime les numéros de séquence, les timestamps et les balises HTML.
    3. Ignore les lignes vides ou devenues vides après nettoyage.
    4. Regroupe les répliques nettoyées en blocs de taille maximale `chunk_size`,
       chaque nouveau bloc reprenant les `overlap` dernières répliques du bloc
       précédent afin de préserver la continuité narrative pour l'IA.

    Args:
        file_content: Le contenu brut du fichier .srt sous forme de chaîne de caractères.
        chunk_size: Le nombre maximal de répliques par bloc (chunk) (par défaut 50).
        overlap: Le nombre de répliques de fin du bloc précédent réinjectées au
            début du bloc suivant (par défaut 5). Doit être strictement inférieur
            à `chunk_size`. Mettre à 0 pour désactiver le recouvrement.

    Returns:
        Une liste de chaînes de caractères, où chaque chaîne représente un bloc (chunk)
        de dialogues nettoyés. Peut être vide si aucun dialogue exploitable n'est trouvé.

    Raises:
        SRTParseError: Si l'entrée n'est pas une chaîne de caractères, si
            `chunk_size` n'est pas un entier strictement positif, ou si `overlap`
            n'est pas un entier compris dans [0, chunk_size[.
    """
    # Validation défensive des arguments : un SRT mal formé ne doit pas faire planter le serveur.
    if not isinstance(file_content, str):
        raise SRTParseError(
            "Le contenu du fichier doit être une chaîne de caractères "
            f"(type reçu : {type(file_content).__name__})."
        )

    if not isinstance(chunk_size, int) or chunk_size <= 0:
        raise SRTParseError(
            f"chunk_size doit être un entier strictement positif (reçu : {chunk_size!r})."
        )

    if not isinstance(overlap, int) or overlap < 0 or overlap >= chunk_size:
        raise SRTParseError(
            "overlap doit être un entier compris dans [0, chunk_size[ "
            f"(reçu : overlap={overlap!r}, chunk_size={chunk_size!r})."
        )

    try:
        cleaned_dialogues: List[str] = []

        # Découpage du fichier ligne par ligne
        for line in file_content.splitlines():
            stripped_line = line.strip()

            # Ignorer les lignes vides
            if not stripped_line:
                continue

            # Supprimer les numéros de séquence
            if _SEQUENCE_PATTERN.match(stripped_line):
                continue

            # Supprimer les timestamps
            if _TIMESTAMP_PATTERN.match(stripped_line):
                continue

            # Nettoyer les balises HTML
            cleaned_line = _HTML_PATTERN.sub("", stripped_line).strip()

            # Ignorer la ligne si elle est vide après nettoyage des balises
            if not cleaned_line:
                continue

            cleaned_dialogues.append(cleaned_line)

        # Regroupement des répliques en blocs (chunks) avec fenêtre glissante.
        # On avance d'un pas de (chunk_size - overlap) : chaque bloc reprend ainsi
        # automatiquement les `overlap` dernières répliques du bloc précédent.
        chunks: List[str] = []
        step = chunk_size - overlap
        start = 0
        total = len(cleaned_dialogues)
        while start < total:
            chunks.append("\n".join(cleaned_dialogues[start : start + chunk_size]))
            # Le bloc courant atteint la fin : inutile de produire un bloc
            # purement constitué de recouvrement.
            if start + chunk_size >= total:
                break
            start += step
    except SRTParseError:
        raise
    except Exception as exc:  # garde-fou : on convertit toute erreur inattendue
        logger.exception("Erreur inattendue lors de l'analyse du fichier SRT.")
        raise SRTParseError(
            f"Le fichier SRT n'a pas pu être analysé : {exc}"
        ) from exc

    logger.info(
        "SRT analysé : %d répliques nettoyées regroupées en %d chunk(s).",
        sum(len(c.splitlines()) for c in chunks),
        len(chunks),
    )
    return chunks
