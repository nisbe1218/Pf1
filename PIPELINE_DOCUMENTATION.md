# Pipeline de prétraitement médical — AI NéphroCare

## Objectif

Nettoyer, corriger et standardiser les données cliniques importées depuis un fichier Excel avant leur utilisation dans la plateforme, via un LLM médical local.

## Stack technique

| Composant | Technologie |
|---|---|
| Frontend | React 18 |
| Backend API | Django 4 + DRF |
| LLM | Ollama + **Qwen2.5:14B** (local, GPU-accéléré) |
| RAG | ChromaDB + nomic-embed-text |
| File d'attente | Celery + Redis |
| Base de données | PostgreSQL 16 |

---

## Flux du pipeline

```
Utilisateur (frontend)
        │ Upload fichier Excel
        ▼
Django DRF — POST /api/patients/preprocess/
        │ Enregistre la demande (PreprocessValidationRequest)
        ▼
Celery Worker (async)
        │
        ├─ Étape 1  : Lecture et structuration du fichier Excel
        ├─ Étape 2  : Détection des colonnes et typage
        ├─ Étape 3  : Chunking du dataset (lignes par lots)
        ├─ Étape 4  : RAG Retrieval (ChromaDB, nomic-embed-text)
        ├─ Étape 5  : Analyse globale Qwen2.5:14B — pass 1 (détection anomalies)
        ├─ Étape 6  : Analyse par chunk — Qwen2.5:14B (corrections ligne par ligne)
        ├─ Étape 7  : Fusion des résultats par chunk
        ├─ Étape 8  : Validation des corrections proposées
        ├─ Étape 9  : Application des corrections validées
        ├─ Étape 10 : Standardisation (dates, booléens, catégories, encodages)
        ├─ Étape 11 : Génération du rapport JSON (anomalies, corrections, risques)
        └─ Étape 12 : Dataset corrigé prêt pour import en base
        ▼
Frontend — affichage du rapport + dataset corrigé
Chef de service / Admin — validation finale avant insertion PostgreSQL
```

---

## Principes métier

- Analyser l'ensemble du dataset avant toute décision de correction
- Détecter les incohérences structurelles (types, formats) et médicales (valeurs biologiques aberrantes)
- Corriger uniquement les anomalies fiables et traçables — conserver les valeurs ambiguës comme "suspectes"
- Standardiser les colonnes, dates (jj/mm/aaaa), booléens (oui/non → 0/1), catégories, encodages texte
- Produire un JSON strictement valide en sortie (anomalies + corrections + recommandations)

---

## État de la plateforme

- Le pipeline tourne via Docker Compose (`medical_celery_worker`)
- Qwen2.5:14B hébergé localement dans le service `medical_ollama` (port 11434)
- Le frontend affiche l'avancement en temps réel via polling Celery
- La validation chef de service/admin est requise avant insertion définitive en BDD
- Temps estimé pour 478 patients : **1–2 minutes** (GPU-accéléré)

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `backend/preprocessing/tasks.py` | Tâches Celery du pipeline (12 étapes) |
| `backend/preprocessing/views.py` | Endpoints DRF (upload, statut, résultat) |
| `backend/preprocessing/rag_pipeline.py` | Intégration ChromaDB + nomic-embed-text |
| `docker-compose.yml` | Services : ollama, celery, redis |
