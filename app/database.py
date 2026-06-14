"""
Couche de persistance SQLite pour Subtext AI.

Le module utilise la bibliothèque standard ``sqlite3`` (synchrone) mais expose
une API entièrement asynchrone : chaque accès disque est délégué à un thread via
``asyncio.to_thread`` afin de ne jamais bloquer la boucle d'événements de
FastAPI. Aucune dépendance externe n'est requise.
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("subtext.database")

# Base de données stockée à la racine du projet.
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "subtext.db"


def _connect() -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec accès aux colonnes par nom."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_sync() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                filename         TEXT    NOT NULL,
                timestamp        TEXT    NOT NULL,
                full_json_result TEXT    NOT NULL
            )
            """
        )
        # Index sur filename : la recherche de cache se fait par nom de fichier.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analyses_filename ON analyses (filename)"
        )
        conn.commit()


async def init_db() -> None:
    """Crée la table `analyses` si elle n'existe pas (appelée au démarrage)."""
    await asyncio.to_thread(_init_db_sync)
    logger.info("Base de données initialisée : %s", DB_PATH)


def _get_by_filename_sync(filename: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, filename, timestamp, full_json_result
            FROM analyses
            WHERE filename = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (filename,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "filename": row["filename"],
        "timestamp": row["timestamp"],
        "result": json.loads(row["full_json_result"]),
    }


async def get_analysis_by_filename(filename: str) -> Optional[Dict[str, Any]]:
    """
    Retourne la dernière analyse enregistrée pour ce nom de fichier, ou ``None``.

    Le champ ``result`` contient le payload JSON désérialisé tel qu'il a été
    renvoyé au client lors de l'analyse initiale.
    """
    return await asyncio.to_thread(_get_by_filename_sync, filename)


def _save_analysis_sync(filename: str, result: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(result, ensure_ascii=False)
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analyses (filename, timestamp, full_json_result)
            VALUES (?, ?, ?)
            """,
            (filename, timestamp, payload),
        )
        conn.commit()
        new_id = cursor.lastrowid
    return {"id": new_id, "filename": filename, "timestamp": timestamp}


async def save_analysis(filename: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Sauvegarde une analyse et retourne ses métadonnées (id, filename, timestamp)."""
    meta = await asyncio.to_thread(_save_analysis_sync, filename, result)
    logger.info("Analyse sauvegardée (id=%s, filename=%s).", meta["id"], filename)
    return meta


def _get_history_sync() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, timestamp, full_json_result
            FROM analyses
            ORDER BY id DESC
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "filename": row["filename"],
            "timestamp": row["timestamp"],
            "result": json.loads(row["full_json_result"]),
        }
        for row in rows
    ]


async def get_history() -> List[Dict[str, Any]]:
    """Retourne la liste de toutes les analyses, de la plus récente à la plus ancienne."""
    return await asyncio.to_thread(_get_history_sync)
