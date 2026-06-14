# PROJET : Subtext AI
**Objectif :** Application d'analyse psychologique et narrative à partir de fichiers de sous-titres (.srt).
**Stack Technique :**
- Backend : Python (FastAPI, Asynchrone)
- Frontend : HTML/CSS/JS (Design : Glassmorphism, UI type Apple natif)
- IA Core : LLM local via Ollama (Llama3/Mistral) tournant sur Mac M2 Pro.
- Data : PostgreSQL (prévu)

**Règles pour les Agents IA :**
1. Ne pas utiliser d'API payantes externes (OpenAI, Anthropic) pour l'analyse NLP. Tout doit passer par `localhost:11434` (Ollama).
2. Prioriser la performance asynchrone (async/await) dans FastAPI.
3. Le code doit être modulaire et propre, prêt pour un niveau Master Universitaire.

**État Actuel :**
- V1 en cours : Script de parsing (.srt) validé. API FastAPI en construction.