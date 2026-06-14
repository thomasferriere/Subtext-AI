import re
from typing import List

async def parse_srt_to_chunks(file_content: str, chunk_size: int = 50) -> List[str]:
    """
    Analyse le contenu textuel d'un fichier .srt, le nettoie et le regroupe en blocs (chunks).

    Cette fonction effectue les étapes suivantes de manière asynchrone :
    1. Découpe le contenu par ligne.
    2. Utilise des expressions régulières pour :
       - Supprimer les numéros de séquence (ex: 1, 2, 103).
       - Supprimer les lignes de timestamps (ex: 00:01:23,456 --> 00:01:25,789).
       - Nettoyer les balises HTML éventuelles (ex: <i>, <b>, <font color="...">).
    3. Ignore les lignes vides ou devenues vides après nettoyage.
    4. Regroupe les répliques nettoyées en blocs de taille maximale `chunk_size` et les joint par un retour à la ligne.

    Args:
        file_content: Le contenu brut du fichier .srt sous forme de chaîne de caractères.
        chunk_size: Le nombre approximatif de répliques par bloc (chunk) (par défaut 50).

    Returns:
        Une liste de chaînes de caractères, où chaque chaîne représente un bloc (chunk)
        de dialogues nettoyés.
    """
    # Expressions régulières pour le nettoyage
    # 1. Numéros de séquence : une ligne contenant uniquement des chiffres
    sequence_pattern = re.compile(r"^\d+$")
    
    # 2. Timestamps SRT classiques (ex: 00:01:23,456 --> 00:01:25,789)
    # Gère également les variations de séparateurs décimaux (virgule ou point) et d'éventuels espaces
    timestamp_pattern = re.compile(
        r"^\d{1,2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[.,]\d{3}.*$"
    )
    
    # 3. Balises HTML (ex: <i>, <b>, <font ...>) : tout ce qui est entre < et >
    html_pattern = re.compile(r"<[^>]+>")

    cleaned_dialogues: List[str] = []

    # Découpage du fichier ligne par ligne
    for line in file_content.splitlines():
        stripped_line = line.strip()

        # Ignorer les lignes vides initiales
        if not stripped_line:
            continue

        # Supprimer les numéros de séquence
        if sequence_pattern.match(stripped_line):
            continue

        # Supprimer les timestamps
        if timestamp_pattern.match(stripped_line):
            continue

        # Nettoyer les balises HTML
        cleaned_line = html_pattern.sub("", stripped_line).strip()

        # Ignorer la ligne si elle est vide après nettoyage des balises
        if not cleaned_line:
            continue

        # Ajouter la réplique nettoyée
        cleaned_dialogues.append(cleaned_line)

    # Regroupement des répliques en blocs (chunks)
    chunks: List[str] = []
    for i in range(0, len(cleaned_dialogues), chunk_size):
        chunk = cleaned_dialogues[i : i + chunk_size]
        # On joint les répliques du bloc avec un saut de ligne
        chunks.append("\n".join(chunk))

    return chunks
