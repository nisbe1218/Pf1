# AI NéphroCare

Plateforme intelligente d'aide à la décision clinique pour patients hémodialysés (cohorte HD-478, CHU Hassan II, Fès).

## Démarrage rapide

```bash
git clone https://github.com/nisbe1218/Pf1.git
cd Pf1
docker compose up --build -d
```

La plateforme sera accessible sur :
- **Frontend** : http://localhost:3000
- **Backend API** : http://localhost:8000/api/

## Première utilisation

Après le premier démarrage, exécuter les migrations et créer un compte admin :

```bash
docker exec medical_backend python manage.py migrate
docker exec medical_backend python manage.py createsuperuser
```

## Activer le LLM (prétraitement)

Le modèle Qwen2.5:14B doit être téléchargé une seule fois (~8 GB) :

```bash
docker exec medical_ollama ollama pull qwen2.5:14b
docker exec medical_ollama ollama pull nomic-embed-text
```

## Stack technique

| Composant | Technologie |
|---|---|
| Frontend | React 18 |
| Backend | Django 4 + DRF + JWT |
| Base de données | PostgreSQL 16 |
| File d'attente | Celery + Redis |
| LLM | Ollama + Qwen2.5:14B (local) |
| ML | SVM Linéaire (AUC = 0.8272) |
| Déploiement | Docker Compose (7 services) |
