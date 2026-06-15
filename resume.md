# Vue d'ensemble — Plateforme AI NéphroCare

## Architecture générale

```
┌─ Frontend React 18 (http://localhost:3000)
│  └─ Pages : Dashboard, Gestion Patients, Modèle IA, Patient Monitor, Profil
│
├─ Backend Django 4 + DRF (http://localhost:8000/api/)
│  ├─ auth/       → Authentification JWT, gestion utilisateurs & rôles
│  ├─ patients/   → CRUD patients, import Excel, prétraitement LLM
│  ├─ predictions/→ Prédiction mortalité SVM Linéaire
│  └─ audit/      → Journalisation des actions (AuditLog)
│
├─ PostgreSQL 16  → Données patients, utilisateurs, logs d'audit
├─ Redis          → Broker Celery
├─ Celery Worker  → Pipeline prétraitement LLM asynchrone
└─ Ollama         → Qwen2.5:14B en local (port 11434)
```

Déploiement : **Docker Compose** (7 services, commande unique `docker compose up --build -d`)

---

## Les 4 rôles & permissions

| Rôle | Permissions principales |
|---|---|
| **super_admin** | Gestion complète utilisateurs, import/validation patients, toutes statistiques |
| **chef_service** | Création professeurs/résidents, validation imports patients, stats équipe |
| **professeur** | Lecture patients, lancement prédictions IA, suivi résidents |
| **resident** | Lecture patients supervisés, consultation prédictions IA |

Contrôle d'accès :
- Lecture patients : **tous les rôles authentifiés**
- Écriture/suppression patients : **super_admin + chef_service uniquement**
- Gestion utilisateurs : **super_admin + chef_service uniquement**

---

## Workflows principaux

### 1. Authentification
```
Login (email + mot de passe) → JWT (access=8h, refresh=1 jour)
→ Stocké localStorage → Authorization: Bearer {token} sur chaque requête API
```

### 2. Import et prétraitement patients
```
Upload Excel (478 colonnes dynamiques)
→ Celery : pipeline LLM Qwen2.5:14B (12 étapes, ~1–2 min pour 478 patients)
→ Rapport JSON : anomalies + corrections proposées
→ Validation chef de service / admin
→ Insertion PostgreSQL (modèle Patient : 162 champs + JSONField extra_data)
```

### 3. Prédiction IA (mortalité à 1 an)
```
Sélectionner un patient → GET /api/predictions/patient/{id}/mortalite/
→ Auto-extraction 32 features depuis BDD (feature_mapping.py)
→ KNNImputer(k=3) + PowerTransformer + SVM Linéaire (Platt scaling)
→ Probabilité p̂ → Zone Faible (<10%) / Modéré (10–29%) / Élevé (≥29%)
→ Affichage : score, zone, top-5 facteurs, recommandation clinique
```

### 4. Dashboard
```
super_admin  → Stats globales : comptes, patients, imports, activités
chef_service → Stats équipe : professeurs/résidents, leurs patients
professeur / resident → Vue personnelle, accès lecture patients
```

---

## Pages principales

| Page | Fichier | Description |
|---|---|---|
| Dashboard | `Dashboard.js` | KPIs selon le rôle, gestion utilisateurs (admin) |
| Gestion Patients | `PatientsManagement.js` | Liste CRUD, import Excel, visualisations |
| Modèle IA | `ModelAI.js` | Métriques du modèle SVM, prédiction par patient |
| Patient Monitor | `MonitorBoard.js` | Vue centrée patient : clinique + IA + historique |
| Profil | `Profile.js` | Informations compte, changement mot de passe |
| Prétraitement | `Preprocessing.js` | Upload fichier, suivi pipeline LLM, rapport |

---

## Modèle ML — SVM Linéaire

| Paramètre | Valeur |
|---|---|
| Algorithme | LinearSVC + CalibratedClassifierCV (Platt, 5-fold) |
| Features | 32 (24 cliniques + 8 interactions) |
| Cohorte entraînement | HD-478 (478 patients, 94 décès à 1 an) |
| AUC-ROC | **0.8272** ± 0.0779 |
| Brier Score | 0.1257 |
| Zones de risque | T1=10% (ROC, Sens≥90%) / T2=29% (Youden bootstrappé) |
| Mortalité observée | Faible : 5.6% · Modéré : 14.6% · Élevé : 40.3% |

---

## Sécurité

- JWT stateless (SimpleJWT), tokens expirés rejetés
- RBAC par décorateur `@permission_classes` sur chaque endpoint
- Audit complet : chaque action inscrite dans `AuditLog` (user, IP, timestamp, action)
- Logs purgés automatiquement après 15 jours (`medical_audit_cleanup`)
- Variables sensibles en `.env` (SECRET_KEY, DB_PASSWORD, etc.)
