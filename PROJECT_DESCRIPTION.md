# AI NéphroCare — Plateforme Médicale de Prédiction de Mortalité en Hémodialyse

> **Plateforme clinique intelligente** dédiée à la gestion des données patients hémodialysés et à la prédiction du risque de mortalité à 1 an, développée pour le **CHU Hassan II de Fès (Maroc)**.

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture technique](#2-architecture-technique)
3. [Services Docker](#3-services-docker)
4. [Backend Django — Structure et fonctions](#4-backend-django--structure-et-fonctions)
5. [Frontend React — Interfaces et composants](#5-frontend-react--interfaces-et-composants)
6. [Base de données — Schéma complet](#6-base-de-données--schéma-complet)
7. [API REST — Endpoints complets](#7-api-rest--endpoints-complets)
8. [Modèles ML et IA](#8-modèles-ml-et-ia)
9. [Pipeline de prétraitement LLM + RAG](#9-pipeline-de-prétraitement-llm--rag)
10. [Rôles et permissions](#10-rôles-et-permissions)
11. [Stack technologique complète](#11-stack-technologique-complète)

---

## 1. Vue d'ensemble

**AI NéphroCare** est un système d'aide à la décision clinique (CDSS — *Clinical Decision Support System*) centré sur les patients en hémodialyse chronique. Il combine :

- Une **interface de gestion des dossiers patients** avec plus de 160 champs médicaux structurés en 11 sections cliniques
- Un **pipeline de prétraitement IA** (LLM + RAG via Ollama + ChromaDB) pour nettoyer, corriger et valider les données importées depuis Excel
- Un **modèle SVM de prédiction de mortalité à 1 an** entraîné sur la cohorte HD-478 du CHU Hassan II (2020–2024), calibré par régression isotonique et stratifié en 3 zones de risque (GMM)
- Un **tableau de bord analytique** avec 6 graphiques cliniques interactifs (Chart.js)
- Un **système d'audit complet** traçant automatiquement toutes les modifications avec rétention 15 jours

**Cohorte de référence** :
- 478 patients hémodialysés — 95 décès à 1 an (19,9% de mortalité)
- AUC-ROC (10-fold CV) = **0.8262** | PR-AUC = 0.4887 | F1 = 0.5667

---

## 2. Architecture technique

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Docker Compose Network                       │
│                                                                     │
│  ┌─────────────────┐       ┌──────────────────┐                     │
│  │  Frontend React │       │  Backend Django   │                     │
│  │   (Port 3000)   │◄─────►│   (Port 8000)     │                     │
│  │  SPA / MUI 5    │  REST │  DRF + JWT Auth   │                     │
│  └─────────────────┘  API  └────────┬─────────┘                     │
│                                     │                               │
│              ┌──────────────────────┼───────────────┐               │
│              │                      │               │               │
│   ┌──────────▼──────┐    ┌──────────▼────┐  ┌──────▼──────────┐    │
│   │  PostgreSQL 16   │    │  Redis 7      │  │  Ollama (LLM)   │    │
│   │  (Port 5432)     │    │  (Port 6379)  │  │  (Port 11434)   │    │
│   │  plateforme_     │    │  Broker       │  │  qwen2.5:7b     │    │
│   │  medicale        │    │  Celery       │  │  nomic-embed    │    │
│   └─────────────────┘    └──────────────┘  └─────────────────┘    │
│                                     │                               │
│                          ┌──────────▼────────────────┐              │
│                          │  Celery Workers             │              │
│                          │  ├── celery_worker (async)  │              │
│                          │  └── audit_cleanup (15j)    │              │
│                          └───────────────────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

**Flux de communication** :
- Frontend → Backend : HTTP REST (axios, JWT Bearer token, CORS)
- Backend → PostgreSQL : psycopg2 (ORM Django)
- Backend → Redis : Celery (tâches asynchrones LLM)
- Backend → Ollama : HTTP local (requêtes LLM)
- Backend → ChromaDB : SDK Python (index RAG en mémoire ou persistant)

---

## 3. Services Docker

| Service | Image | Port(s) | Rôle |
|---------|-------|---------|------|
| `medical_frontend` | `node:18-alpine` + `serve` | **3000** | Interface React (SPA) servie statiquement |
| `medical_backend` | `python:3.11 + Django` | **8000** | API REST, logique métier, prédiction ML |
| `medical_db` | `postgres:16` | **5432** | Base de données principale PostgreSQL |
| `medical_redis` | `redis:7-alpine` | **6379** | Broker Celery, cache sessions JWT |
| `medical_ollama` | `ollama/ollama:latest` | **11434** | LLM local (qwen2.5:7b) + embeddings nomic |
| `medical_celery_worker` | Django custom | — | Tâches asynchrones (analyse LLM patients) |
| `medical_audit_cleanup` | Django custom | — | Nettoyage automatique logs d'audit (15 jours) |

**Variables d'environnement principales** :
```env
DB_NAME=plateforme_medicale
DB_USER=medical_user
DB_PASSWORD=***
DB_HOST=db
DB_PORT=5432
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
CELERY_BROKER_URL=redis://redis:6379/0
REACT_APP_API_URL=http://localhost:8000/api/
```

---

## 4. Backend Django — Structure et fonctions

### 4.1 Configuration centrale (`backend/config/`)

| Fichier | Rôle |
|---------|------|
| `settings.py` | Django 6.0 ; base de données PostgreSQL ; JWT (SimpleJWT, token 8h) ; CORS React |
| `urls.py` | Routeur principal : `/api/auth/`, `/api/patients/`, `/api/audit/`, `/api/predictions/` |
| `celery.py` | Configuration Celery avec Redis comme broker ; tâches asynchrones LLM |
| `wsgi.py` / `asgi.py` | Points d'entrée serveur |

---

### 4.2 Module `users/` — Authentification et gestion des utilisateurs

#### Modèles

**`Utilisateur`** (hérite de `AbstractBaseUser`) :
| Champ | Type | Description |
|-------|------|-------------|
| `email` | EmailField (unique) | Identifiant de connexion |
| `nom` | CharField | Nom de famille |
| `prenom` | CharField | Prénom |
| `telephone` | CharField | Numéro de téléphone |
| `role` | ForeignKey → `Role` | Rôle fonctionnel |
| `personal_notes` | TextField | Notes personnelles (privées) |
| `is_active`, `is_staff` | BooleanField | Statut du compte |
| `date_joined` | DateTimeField | Date de création |

**`Role`** :
| Champ | Description |
|-------|-------------|
| `name` | Identifiant : `super_admin`, `chef_service`, `professeur`, `resident` |
| `label` | Libellé affiché |

#### Fonctions clés (views.py)

| Fonction | Méthode | Description |
|----------|---------|-------------|
| `LoginView` | POST | Authentification email/mot de passe → JWT access + refresh token |
| `UserListCreateView` | GET/POST | Liste des utilisateurs (admin) ; création compte |
| `UserDetailView` | GET/PATCH/DELETE | Consultation, modification, suppression d'un utilisateur |
| `ChangePasswordView` | POST | Changement de mot de passe (ancien + nouveau) |
| `ProfileView` | GET | Profil de l'utilisateur connecté |
| `PersonalNotesView` | PATCH | Mise à jour des notes personnelles |
| `RolesListView` | GET | Liste des rôles disponibles |

#### Permissions (`permissions.py`)

| Classe | Accès autorisé |
|--------|---------------|
| `IsSuperAdmin` | super_admin uniquement |
| `IsAdminOrChefService` | super_admin + chef_service |
| `CanViewPatients` | Tous les rôles connectés |
| `CanValidatePreprocess` | super_admin + chef_service |

---

### 4.3 Module `patients/` — Gestion des dossiers patients

#### Modèles

**`Patient`** (160+ champs) — Données stockées dans 11 sections JSON :

| Section JSON | Nombre de champs | Contenu |
|-------------|-----------------|---------|
| `demographie_data` | 14 | Sexe, date naissance, âge, statut matrimonial, résidence, distance hôpital, couverture sociale (RAMED/AMO/auto-paiement), profession, niveau éducation, tabac, alcool |
| `irc_data` | 9 | Diagnostic IRC, étiologie MRC (11 catégories), biopsie rénale, dialyse connue avant, source diagnostic, contexte début dialyse, compréhension patient, préférence traitement |
| `comorbidite_data` | 3 | Diabète, liste comorbidités (HTA, cardiopathie, etc.), autre |
| `presentation_data` | 13 | Date présentation, lieu, raisons consultation, symptômes à l'admission, TA (systolique/diastolique), FC, température, poids, taille, diurèse, volume urinaire, autonomie, notes |
| `biologie_data` | 23 | Créatinine, urée, hémoglobine, HbA1c, leucocytes, plaquettes, albumine, CRP, sodium, potassium, bicarbonates, calcium, phosphore, PTH, ferritine, saturation transferrine, vitamine D, protéinurie, HBsAg, VHC, VIH |
| `imagerie_data` | 10 | Échographie rénale (taille reins), échocardiographie, FEVG, HVG, valvulopathie, autres examens |
| `dialyse_data` | 18 | Modalité dialyse (HD/DP/HDF), accès vasculaire (FAV/cathéter), fréquence séances, débit dialysat, anticoagulation, diurèse résiduelle, info/statut transplantation |
| `qualite_data` | 10 | Kt/V, URR, prise de poids interdialytique, ultrafiltration, TA pré/post séance, poids sec, séances manquées, hypotensions intradialytiques |
| `traitement_data` | 2 | Liste médicaments, notes traitement |
| `complication_data` | 8 | Date début/fin complication, liste complications, date premier événement, nb hospitalisations, nb jours hospitalisés, motifs, changement modalité, notes |
| `devenir_data` | variable | Suivi évolutif, devenir patient |

**Champs supplémentaires** :
| Champ | Type | Description |
|-------|------|-------------|
| `id_patient` | CharField | Auto-généré (format PAT-XXXXXX) |
| `id_enregistrement_source` | CharField | ID dans le fichier source importé |
| `id_site` | CharField | Identifiant du centre de soin |
| `statut_inclusion` | CharField | Inclus / Exclu / En attente |
| `statut_consentement` | CharField | Consentement éclairé obtenu |
| `icc_charlson` | IntegerField | Score de Charlson (0–37) |
| `extra_data` | JSONField | Colonnes dynamiques importées |
| `utilisateur_saisie` | FK → Utilisateur | Créateur du dossier |
| `created_at`, `derniere_mise_a_jour` | DateTimeField | Horodatage |

**`PatientFormTemplate`** et **`PatientFormField`** : définition dynamique des champs du formulaire patient.

**`PreprocessValidationRequest`** : sessions de prétraitement LLM en attente de validation.

**`DynamicColumnRequest`** : demandes d'ajout de colonnes personnalisées.

#### Fonctions clés (views.py patients)

| Fonction | Méthode | Description |
|----------|---------|-------------|
| `PatientListCreateView` | GET/POST | Liste paginée (filtres : sexe, statut, recherche) ; création patient |
| `PatientDetailView` | GET/PATCH/DELETE | Consultation, modification, suppression dossier |
| `PatientImportView` | POST | Import fichier Excel/CSV → mapping colonnes → normalisation → pré-intégration |
| `PatientExportView` | GET | Export complet Excel avec colonnes dynamiques |
| `PatientFlatView` | GET | Vue aplatie (flat) pour les graphiques analytiques |
| `SchemaView` | GET | Documentation JSON du schéma des 135+ colonnes |
| `AnalyzePreprocessView` | POST | Démarrage pipeline LLM (tâche Celery async) |
| `PreprocessStatusView` | GET | Statut de la session de prétraitement |
| `PreprocessRowsView` | GET | Lignes analysées par le LLM avec suggestions |
| `PreprocessRowDetailView` | GET | Détail d'une ligne avec corrections cellule par cellule |
| `CellCorrectionOverrideView` | PATCH | Modification manuelle des corrections LLM |
| `PreprocessIntegrateView` | POST | Finalisation : intégration en base après validation |
| `PreprocessSubmitValidationView` | POST | Soumission à la validation chef_service |
| `PreprocessValidationsListView` | GET | Liste des validations en attente (admin) |
| `DynamicColumnsView` | GET/POST | Gestion colonnes dynamiques personnalisées |

#### Pipeline prétraitement (`preprocess_rag.py`)

Fonctions principales :
- `build_rag_context(column_names)` : Construction du contexte RAG depuis ChromaDB
- `analyze_file_with_llm(file_path, session_id)` : Analyse complète via Ollama
- `correct_cell_value(col, value, context)` : Correction unitaire d'une cellule
- `normalize_bio_units(col, value)` : Normalisation unités biologiques (mg/L ↔ g/L, etc.)
- `detect_anomalies(row_data)` : Détection des valeurs aberrantes cliniques

#### Tâches asynchrones (`tasks.py`)

- `analyze_preprocess_async(session_id, file_path)` : Tâche Celery — analyse LLM d'un fichier importé (exécutée en arrière-plan)

---

### 4.4 Module `predictions/` — Prédiction ML

#### Fonctions clés (views.py / predict_mortalite.py)

| Fonction | Méthode | Description |
|----------|---------|-------------|
| `TrainModelView` | POST | Réentraîne le modèle SVM sur tous les patients en base |
| `PredictPatientView` | POST | Prédit le risque de mortalité pour un patient |
| `ModelMetricsView` | GET | Retourne AUC, PR-AUC, Brier, F1, calibration |
| `PredictionHistoryView` | GET | Historique des prédictions (par patient ou global) |

**`PredictMortaliteView.predict(patient_id)`** :
1. Charge le patient depuis la base de données
2. Appelle `extract_features(patient)` → vecteur 32 features
3. Applique le pipeline SVM (`mortalite_svm.joblib`)
4. Calibre avec `iso_calibrator.joblib`
5. Classe via les seuils GMM (14.3% / 42.1%)
6. Retourne : `risk_zone`, `calibrated_probability`, `top_5_factors`, `recommendation`

#### `models/feature_mapping.py` — Extraction des 32 features

Fonctions :
- `extract_features(patient)` : Extrait et calcule les 32 variables à partir du modèle ORM
- `get_clinical_features(patient)` : 24 features cliniques individuelles
- `compute_interaction_features(features_dict)` : 8 features d'interaction calculées
- `safe_float(value, default)` : Conversion sécurisée avec gestion des valeurs manquantes

#### `models/train_isotonic.py` — Calibration

- `calibrate_model(X, y, base_model)` : Calibration isotonique par validation croisée 10-fold (Out-Of-Fold)
- Produit `iso_calibrator.joblib` avec probabilités calibrées = taux de mortalité réel

#### `train_from_excel.py` — Entraînement

- Lecture `Base_HD_478_v4_finale.xlsx` (478 patients, 95 décès)
- Extraction des 32 features
- Pipeline : `KNNImputer(k=3)` → `PowerTransformer(yeo-johnson)` → `SVC(C=0.01, kernel='linear', class_weight='balanced')`
- Validation croisée 10-fold stratifiée
- Sauvegarde des 4 fichiers `.joblib`

---

### 4.5 Module `audit/` — Traçabilité

#### Modèles

**`AuditLog`** :
| Champ | Type | Description |
|-------|------|-------------|
| `utilisateur` | FK → Utilisateur | Auteur de l'action |
| `action` | CharField | Type : create / update / delete / login / export / import |
| `entite` | CharField | Modèle concerné : Patient, Utilisateur, etc. |
| `entite_id` | IntegerField | ID de l'objet concerné |
| `details` | JSONField | Détails de la modification (avant/après) |
| `adresse_ip` | GenericIPAddressField | IP de la requête |
| `timestamp` | DateTimeField | Horodatage automatique |

**`HiddenAuditLog`** : logs masqués par l'utilisateur (ne sont pas supprimés, juste cachés).

#### Fonctions (`utils.py`)
- `log_action(request, action, entity, entity_id, details)` : Crée une entrée d'audit automatiquement
- `cleanup_old_logs()` : Supprime les logs de plus de 15 jours (exécuté par Celery Beat)

---

## 5. Frontend React — Interfaces et composants

### 5.1 Structure globale (`src/`)

```
src/
├── App.js                     # Routeur principal + ProtectedRoute
├── theme.js                   # Thème MUI (palette teal/rose)
├── context/
│   ├── AuthContext.js         # État JWT, login/logout, user role
│   └── LanguageContext.js     # EN/FR (i18n basique)
├── services/api/
│   └── axios.js               # Instance axios + intercepteur JWT
├── components/common/
│   ├── AppSidebar.js          # Navigation latérale (248px, dégradé teal→rose)
│   ├── ProtectedRoute.js      # Guard de route par rôle
│   └── NotesFab.js            # FAB flottant pour notes personnelles
└── pages/
    ├── auth/                  # Landing + Login
    ├── dashboard/             # Tableau de bord
    ├── patients/              # Gestion patients (CRUD + analytics + prétraitement)
    ├── model-ai/              # Prédiction IA
    ├── monitor/               # Monitoring patient unique
    ├── preprocessing/         # Validation des imports
    ├── profile/               # Profil utilisateur
    └── unauthorized/          # Page 403
```

---

### 5.2 Page : Landing (`/`)

**Fichier** : `src/pages/auth/Landing.js`

Interface publique de présentation du projet :
- Hero section avec titre, description, appel à l'action (bouton "Se connecter")
- Section fonctionnalités (3 cartes : IA, Sécurité, Collaboration)
- Section statistiques (478 patients, AUC 0.82, 4 rôles, 15j audit)
- Footer avec crédits CHU Hassan II

---

### 5.3 Page : Connexion (`/login`)

**Fichier** : `src/pages/auth/Login.js`

- Formulaire email + mot de passe (Material-UI `TextField`)
- Appel `POST /api/auth/login/` → stockage `access` + `refresh` token dans `localStorage`
- Redirection automatique vers `/dashboard` après succès
- Affichage erreur si identifiants incorrects

**Fonctions** :
- `handleLogin()` : Soumission du formulaire, mise à jour `AuthContext`
- `handleKeyPress()` : Soumission via touche Entrée

---

### 5.4 Page : Tableau de bord (`/dashboard`)

**Fichier** : `src/pages/dashboard/Dashboard.js`

Interface principale après connexion :

**Section 1 — KPIs dynamiques** (4 cartes) :
| KPI | Source |
|-----|--------|
| Total patients | `GET /api/patients/?page_size=1` (count) |
| Alertes haut risque | Patients avec zone = "Élevée" dans l'historique prédictions |
| Taux de validation | Ratio `statut_inclusion=inclus / total` |
| Utilisateurs actifs | `GET /api/auth/users/` (admin) |

**Section 2 — Message de bienvenue** : Prénom de l'utilisateur connecté + rôle + date

**Section 3 — Gestion des comptes** (visible admin/chef seulement) :
- Tableau des utilisateurs avec colonnes : Nom, Email, Rôle, Actions
- Bouton "Créer un utilisateur" → Dialog MUI avec formulaire (nom, prénom, email, téléphone, rôle, mot de passe)
- Actions par ligne : Modifier (Dialog), Supprimer (confirmation)

**Fonctions** :
- `fetchDashboardData()` : Chargement KPIs en parallèle
- `handleCreateUser()` : Création d'un compte via `POST /api/auth/users/`
- `handleUpdateUser()` : Modification via `PATCH /api/auth/users/<id>/`
- `handleDeleteUser()` : Suppression avec Dialog de confirmation

---

### 5.5 Page : Gestion des patients (`/patients`)

**Fichier** : `src/pages/patients/PatientsManagement.js`

Interface principale avec **3 onglets** :

#### Onglet 0 — Analyse

6 graphiques cliniques interactifs (Chart.js) :

| N° | Graphique | Type | Données |
|----|-----------|------|---------|
| 1 | Évolution mensuelle des dialyses | Line chart | Nb patients par mois de début dialyse |
| 2 | Répartition et indicateurs clés | Donut + KPIs | Sexe (H/F/inconnu) + âge moyen, complétude, colonnes |
| 3 | Distribution d'âge par sexe | Bar chart groupé | Tranches d'âge (0–30, 31–50, 51–65, 66–80, >80) × sexe |
| 4 | Répartition des complications | Bar chart horizontal | Types de complications + fréquences |
| 5 | Étiologie IRC par statut d'inclusion | Bar chart groupé | 11 étiologies × statuts |
| 6 | Top combinaisons de comorbidités | Bar chart horizontal | Co-occurrences (diabète+HTA, etc.) |

Fonctions :
- `fetchAnalyticsData()` : `GET /api/patients/flat/` → transformation pour Chart.js
- `computeAgeDistribution()`, `computeEtiologyChart()`, `computeComorbidityCombinations()`

#### Onglet 1 — Gestion des données

**Barre d'outils** :
- Champ de recherche (texte libre — nom, ID)
- Filtre sexe (Tous / Homme / Femme)
- Filtre statut inclusion
- Bouton "Importer" → Dialog upload fichier Excel/CSV
- Bouton "Exporter" → `GET /api/patients/export/`
- Bouton "Colonnes dynamiques" → Dialog gestion colonnes personnalisées
- Bouton "Tout supprimer" (admin uniquement) — avec confirmation

**Tableau patients** :
| Colonne | Contenu |
|---------|---------|
| ID Patient | Format PAT-XXXXXX |
| Nom | Nom + prénom |
| Sexe | Homme / Femme |
| Âge | Calculé depuis date de naissance |
| Statut | Badge coloré (Inclus / Exclu / En attente) |
| Charlson | Score numérique |
| Actions | Boutons Voir, Modifier, Supprimer, Prédire |

**Dialog Voir/Modifier patient** :
- Formulaire multi-sections (accordéons) reprenant les 11 sections cliniques
- Tous les champs éditables avec validation

Fonctions :
- `fetchPatients()` : Liste paginée avec filtres
- `handleImport()` : Upload fichier → `POST /api/patients/import/`
- `handleExport()` : Téléchargement Excel
- `handleDeletePatient()` : Suppression avec confirmation
- `handleSearch()`, `handleFilterSex()` : Filtres en temps réel

#### Onglet 2 — Prétraitement IA

**Interface de prétraitement LLM** :

1. **Upload fichier** : Drop zone + bouton "Analyser" → déclenche tâche Celery
2. **Barre de progression** : Polling `GET /api/patients/preprocess/<id>/status/` toutes les 2s
3. **Tableau des lignes analysées** : Chaque ligne avec indicateur (✓ / ⚠ / ✗) + nb corrections suggérées
4. **Vue détaillée** : Cellule par cellule avec :
   - Valeur originale
   - Correction suggérée par le LLM
   - Justification en langage naturel
   - Bouton "Accepter" ou champ de saisie manuelle
5. **Bouton "Valider"** : Soumet à la validation du chef de service
6. **Bouton "Intégrer"** (après validation admin) : `POST /api/patients/preprocess/<id>/integrate/`

Fonctions :
- `startPreprocessing()` : Lance l'analyse asynchrone
- `pollStatus()` : Interrogation périodique du statut
- `handleCellOverride()` : Remplacement manuel d'une suggestion LLM
- `handleSubmitValidation()` : Envoi pour approbation
- `handleIntegrate()` : Intégration finale

---

### 5.6 Page : Modèle IA (`/modele-ai`)

**Fichier** : `src/pages/model-ai/ModelAI.js`

Interface de prédiction de mortalité avec **3 onglets** :

#### Onglet 0 — Dashboard Modèle

KPIs du modèle SVM :

| Indicateur | Valeur |
|-----------|--------|
| AUC-ROC | 0.8262 |
| PR-AUC | 0.4887 |
| F1-Score | 0.5667 |
| Brier Score | 0.1265 |
| Cohorte | 478 patients |
| Décès 1 an | 95 (19.9%) |

Affichage des 3 zones de risque avec couleurs et risques relatifs.

#### Onglet 1 — Patients

- Barre de recherche patients (nom, ID)
- Tableau avec colonne "Score précédent" (si historique)
- Bouton **"Prédire"** par ligne → charge le patient dans l'onglet Score

#### Onglet 2 — Score

Carte patient complète + résultat de prédiction :

**Informations patient** (auto-remplies) :
- Nom, âge, sexe, étiologie MRC, score de Charlson
- Dernière biologie (albumine, PTH, ferritine, sodium, calcium)
- Comorbidités (diabète, HTA, cardiopathie)
- Dialyse (modalité, accès vasculaire, FAV, cathéter)

**Résultat de la prédiction** (après clic "Calculer le risque") :
- **Jauge de risque** : arc coloré (vert → orange → rouge)
- **Zone de risque** : badge Faible / Modérée / Élevée
- **Probabilité calibrée** : ex. "32.4% de risque de décès à 1 an"
- **Risque relatif** : ×1 / ×5.7 / ×10.9 vs zone Faible
- **Top 5 facteurs contributifs** : liste des features SVM les plus déterminantes (avec poids)
- **Recommandation clinique** : texte adaptatif selon la zone

Fonctions :
- `handlePredict()` : `POST /api/predictions/predict-patient/` avec `{patient_id, prediction_type: "mortalite"}`
- `renderRiskGauge()` : Rendu visuel de la jauge (SVG/Canvas)
- `renderTopFactors()` : Affichage top-5 facteurs avec barres de progression

---

### 5.7 Page : Monitoring (`/monitor`)

**Fichier** : `src/pages/monitor/MonitorBoard.js`

Suivi longitudinal d'un patient unique :

- **Sélecteur de patient** : Recherche et sélection
- **Carte biologique** : Évolution des valeurs (albumine, hémoglobine, PTH) dans le temps
- **Suivi des constantes** : TA, FC, poids sec, Kt/V
- **Score IA** : Historique des prédictions avec évolution de la probabilité
- **Journal clinique** : Dernières modifications du dossier (tiré de l'audit)

---

### 5.8 Page : Validation des imports (`/validation-requests`)

**Fichier** : `src/pages/preprocessing/ValidationRequests.js`

Accessible uniquement aux rôles `super_admin` et `chef_service` :

- Liste des sessions de prétraitement en attente
- Pour chaque session : nom du fichier, date, utilisateur, nb lignes, nb corrections
- Actions : **Approuver** → `POST /api/patients/preprocess/<id>/integrate/` | **Rejeter** avec commentaire

---

### 5.9 Page : Profil (`/profil`)

**Fichier** : `src/pages/profile/Profile.js`

- Affichage et modification : prénom, nom, email, téléphone
- Changement de mot de passe (ancien + nouveau + confirmation)
- Zone notes personnelles (textarea, sauvegarde automatique)
- Badge rôle non modifiable

Fonctions :
- `handleUpdateProfile()` : `PATCH /api/auth/users/<id>/`
- `handleChangePassword()` : `POST /api/auth/users/<id>/change-password/`
- `handleSaveNotes()` : `PATCH /api/auth/profile/personal-notes/`

---

### 5.10 Composant : AppSidebar

**Fichier** : `src/components/common/AppSidebar.js`

Navigation latérale fixe (largeur 248px) :
- Logo + titre "AI NéphroCare"
- Dégradé de fond teal (#00897B) → rose (#E91E63)
- Liens avec icônes MUI : Dashboard, Patients, Modèle IA, Monitoring, Validation (admin), Profil
- Indication du rôle de l'utilisateur en bas
- Bouton Déconnexion

Comportement RBAC :
- L'item "Validation" n'apparaît que pour `super_admin` et `chef_service`
- L'item "Gestion comptes" dans Dashboard n'est visible que pour les admins

---

### 5.11 Composant : ProtectedRoute

**Fichier** : `src/components/common/ProtectedRoute.js`

Wrapper de route qui :
1. Vérifie si un token JWT valide est présent dans `localStorage`
2. Vérifie si le rôle de l'utilisateur est dans la liste `allowedRoles` (si spécifiée)
3. Redirige vers `/login` si non authentifié, ou `/unauthorized` si rôle insuffisant

---

## 6. Base de données — Schéma complet

**SGBD** : PostgreSQL 16 | **Base** : `plateforme_medicale`

### Diagramme des tables

```
users_role
├── id (PK)
├── name (unique) : super_admin | chef_service | professeur | resident
└── label

users_utilisateur
├── id (PK)
├── email (unique, identifiant connexion)
├── password (hashé bcrypt via Django)
├── nom, prenom, telephone
├── role_id (FK → users_role)
├── personal_notes
├── is_active, is_staff
└── date_joined

patients_patient (table principale)
├── id (PK, auto-incrément)
├── id_patient (VARCHAR unique : PAT-XXXXXX)
├── id_enregistrement_source
├── id_site
├── statut_inclusion (inclus | exclu | en_attente)
├── statut_consentement
├── icc_charlson (INT)
├── demographie_data (JSONB)
├── irc_data (JSONB)
├── comorbidite_data (JSONB)
├── presentation_data (JSONB)
├── biologie_data (JSONB)
├── imagerie_data (JSONB)
├── dialyse_data (JSONB)
├── qualite_data (JSONB)
├── traitement_data (JSONB)
├── complication_data (JSONB)
├── devenir_data (JSONB)
├── extra_data (JSONB — colonnes dynamiques)
├── utilisateur_saisie_id (FK → users_utilisateur)
├── created_at (TIMESTAMP)
└── derniere_mise_a_jour (TIMESTAMP)

patients_patientformtemplate
├── id (PK)
├── nom, version
└── created_at

patients_patientformfield
├── id (PK)
├── template_id (FK)
├── section, nom_champ, type_champ, label, obligatoire, ordre

patients_preprocessvalidationrequest
├── id (PK)
├── session_id (UUID)
├── fichier_source
├── statut (en_attente | approuve | rejete)
├── soumis_par_id (FK → users_utilisateur)
├── valide_par_id (FK → users_utilisateur, nullable)
├── commentaire_validation
├── created_at, validated_at

patients_dynamiccolumnrequest
├── id (PK)
├── nom_colonne, type_colonne
├── demande_par_id (FK)
└── created_at

audit_auditlog
├── id (PK)
├── utilisateur_id (FK → users_utilisateur)
├── action (create | update | delete | login | export | import)
├── entite (Patient | Utilisateur | ...)
├── entite_id
├── details (JSONB — avant/après modification)
├── adresse_ip
└── timestamp

audit_hiddenauditlog
├── id (PK)
├── utilisateur_id (FK)
├── auditlog_id (FK → audit_auditlog)
└── hidden_at
```

### Indexation

- Index unique sur `users_utilisateur.email`
- Index unique sur `patients_patient.id_patient`
- Index sur `audit_auditlog.timestamp` (pour le nettoyage automatique)
- Index sur `audit_auditlog.utilisateur_id` (pour filtrage)
- Index sur `patients_patient.statut_inclusion`

---

## 7. API REST — Endpoints complets

**Base URL** : `http://localhost:8000/api/`  
**Authentification** : `Authorization: Bearer <access_token>` (JWT, durée 8h)

### 7.1 Authentification (`/api/auth/`)

| Méthode | Endpoint | Rôle requis | Description |
|---------|----------|-------------|-------------|
| POST | `/auth/login/` | Public | Login → `{access, refresh, user}` |
| POST | `/auth/refresh/` | Public | Refresh token → nouveau `access` |
| POST | `/auth/logout/` | Tous | Invalidation token |
| GET | `/auth/users/` | Admin/Chef | Liste des utilisateurs |
| POST | `/auth/users/` | Admin/Chef | Créer un utilisateur |
| GET | `/auth/users/<id>/` | Admin/Chef | Détail utilisateur |
| PATCH | `/auth/users/<id>/` | Admin/Chef | Modifier utilisateur |
| DELETE | `/auth/users/<id>/` | Super Admin | Supprimer utilisateur |
| POST | `/auth/users/<id>/change-password/` | Tous (soi-même) | Changer mot de passe |
| GET | `/auth/profile/` | Tous | Profil connecté |
| PATCH | `/auth/profile/personal-notes/` | Tous | Notes personnelles |
| GET | `/auth/roles/` | Admin | Liste des rôles |

### 7.2 Patients (`/api/patients/`)

| Méthode | Endpoint | Rôle requis | Description |
|---------|----------|-------------|-------------|
| GET | `/patients/` | Tous | Liste paginée (filtres : `?search=`, `?sexe=`, `?statut=`) |
| POST | `/patients/` | Tous | Créer patient |
| GET | `/patients/<id>/` | Tous | Dossier complet |
| PATCH | `/patients/<id>/` | Tous | Modifier dossier |
| DELETE | `/patients/<id>/` | Admin/Chef | Supprimer dossier |
| POST | `/patients/import/` | Tous | Import Excel/CSV (multipart/form-data) |
| GET | `/patients/export/` | Tous | Export Excel (fichier .xlsx) |
| GET | `/patients/flat/` | Tous | Vue plate pour analytics (colonnes aplaties) |
| GET | `/patients/schema/` | Tous | Documentation JSON des 135 colonnes |
| POST | `/patients/preprocess/analyze/` | Tous | Démarrer analyse LLM (Celery async) |
| GET | `/patients/preprocess/<session_id>/status/` | Tous | Statut de la session |
| GET | `/patients/preprocess/<session_id>/rows/` | Tous | Lignes avec suggestions LLM |
| GET | `/patients/preprocess/<session_id>/rows/<row_index>/` | Tous | Détail d'une ligne |
| PATCH | `/patients/preprocess/<session_id>/cell-corrections/` | Tous | Override corrections LLM |
| POST | `/patients/preprocess/<session_id>/submit-validation/` | Tous | Soumettre pour validation |
| POST | `/patients/preprocess/<session_id>/integrate/` | Admin/Chef | Intégrer en base |
| GET | `/patients/preprocess/validations/` | Admin/Chef | Liste validations en attente |
| GET | `/patients/dynamic-columns/` | Tous | Liste colonnes dynamiques |
| POST | `/patients/dynamic-columns/` | Tous | Ajouter colonne dynamique |

### 7.3 Prédictions (`/api/predictions/`)

| Méthode | Endpoint | Rôle requis | Corps | Réponse |
|---------|----------|-------------|-------|---------|
| POST | `/predictions/train/` | Admin | `{}` | `{status, auc, patients_used}` |
| POST | `/predictions/predict-patient/` | Tous | `{patient_id, prediction_type}` | `{risk_zone, calibrated_probability, factors, recommendation}` |
| GET | `/predictions/metrics/` | Tous | — | `{auc, pr_auc, brier, f1, n_patients}` |
| GET | `/predictions/history/` | Tous | `?patient_id=` | Liste historique prédictions |

**Réponse type `predict-patient`** :
```json
{
  "risk_zone": "Élevée",
  "calibrated_probability": 0.471,
  "raw_probability": 0.513,
  "relative_risk": 10.9,
  "top_factors": [
    {"feature": "albumine_basale", "weight": -0.42, "value": 28.5, "direction": "↑ risque"},
    {"feature": "crise_convulsive", "weight": 0.38, "value": 1, "direction": "↑ risque"},
    {"feature": "age_x_charlson", "weight": 0.35, "value": 312, "direction": "↑ risque"}
  ],
  "recommendation": "Suivi rapproché recommandé. Optimiser l'état nutritionnel (albumine < 35 g/L). Évaluation neurologique urgente.",
  "features_used": 32,
  "model_version": "SVM Linear v1.2"
}
```

### 7.4 Audit (`/api/audit/`)

| Méthode | Endpoint | Rôle requis | Description |
|---------|----------|-------------|-------------|
| GET | `/audit/` | Admin/Chef | Liste logs (filtres : `?action=`, `?entite=`, `?date_from=`) |
| GET | `/audit/<id>/` | Admin/Chef | Détail d'un log |
| DELETE | `/audit/<id>/` | Super Admin | Supprimer un log |
| DELETE | `/audit/cleanup-old/` | Super Admin | Nettoyage manuel logs > 15 jours |

---

## 8. Modèles ML et IA

### 8.1 Modèle principal : SVM Linéaire mortalité 1 an

**Cohorte d'entraînement** : `Base_HD_478_v4_finale.xlsx`
- 478 patients hémodialysés, CHU Hassan II Fès, 2020–2024
- 95 décès à 1 an (19,9% de mortalité) — variable cible binaire

#### 32 Features du modèle

**24 features cliniques individuelles** :

| N° | Feature | Type | Description clinique |
|----|---------|------|---------------------|
| 1 | `fistule_arterioveineuse_creee` | Binaire | FAV créée = facteur protecteur majeur |
| 2 | `couverture_medicale` | Catégoriel (0–3) | 0=auto-paiement, 1=RAMED, 2=AMO, 3=autre |
| 3 | `albumine_basale` | Continu (g/L) | Marqueur nutritionnel — seuil critique <35 |
| 4 | `calcium_basale` | Continu (mg/L) | Calcémie à l'entrée en dialyse |
| 5 | `admission_cathetere_tunnellise` | Binaire | Cathéter tunnélisé à l'admission (facteur de risque) |
| 6 | `annee_inclusion` | Continu | Tendance temporelle (améliorations de prise en charge) |
| 7 | `ferritine_basale` | Continu (ng/mL) | Marqueur inflammatoire/statut en fer |
| 8 | `seances_par_semaine` | Catégoriel | 3 séances/semaine = référence ; 2 = risque accru |
| 9 | `nombre_hospitalisations` | Entier | Fragilité cumulée |
| 10 | `du_residuelle` | Continu (mL/24h) | Diurèse résiduelle — fonction rénale résiduelle |
| 11 | `crise_convulsive` | Binaire | HR=3.25 dans la cohorte |
| 12 | `pth_basale` | Continu (pg/mL) | PTH — hyperparathyroïdie secondaire |
| 13 | `etiologie_mrc` | Catégoriel (11) | Cause IRC (diabétique, vasculaire, GN, etc.) |
| 14 | `douleur_abdominale` | Binaire | Symptôme à l'admission |
| 15 | `diabete` | Binaire | Détecté depuis 3 sources (comorbidités, HbA1c, étiologie) |
| 16 | `evenement_cardiovasculaire` | Binaire | ATCD cardiovasculaire |
| 17 | `dyspnee` | Binaire | Dyspnée à l'admission |
| 18 | `oedemes_surcharge` | Binaire | Œdèmes de surcharge cardiaque |
| 19 | `hemodialyse` | Binaire | Modalité HD vs DP/autre |
| 20 | `liste_attente_transplantation` | Binaire | Inscription liste greffe = meilleur pronostic |
| 21 | `maladie_renale_hereditaire` | Binaire | ADPKD, Alport, etc. |
| 22 | `information_transplantation_donnee` | Binaire | Patient informé sur la greffe |
| 23 | `hypertension` | Binaire | HTA — comorbidité fréquente HD |
| 24 | `cardiopathie` | Binaire | Cardiopathie documentée |

**8 features d'interaction (calculées automatiquement)** :

| Feature | Formule | Justification clinique |
|---------|---------|----------------------|
| `age_x_charlson` | age × score_charlson | Risque disproportionnel avec cumulatif âge+comorbidités |
| `dyspnee_x_oedeme` | dyspnee × oedemes | Signature surcharge sévère — insuffisance cardiaque décompensée |
| `sodium_lt130` | 1 si sodium <130 mmol/L | Hyponatrémie sévère = marqueur pronostique indépendant |
| `charlson_x_hosp` | charlson × nb_hosp | Charge clinique totale (comorbidités × recours aux soins) |
| `hypert_x_cardio` | hypertension × cardiopathie | Profil CV haut risque combiné |
| `albumine_x_hosp` | albumine × nb_hosp | Fragilité avancée : dénutrition + morbidité élevée |
| `albumine_lt35` | 1 si albumine <35 g/L | Seuil dénutrition KDOQI — indicateur mortalité significatif |
| `age_x_cardio` | age × cardiopathie | L'impact de la cardiopathie augmente avec l'âge |

#### Pipeline technique SVM

```
Données patient (32 features extraites)
       ↓
KNNImputer(n_neighbors=3)
   Imputation valeurs manquantes par k plus proches voisins
       ↓
PowerTransformer(method='yeo-johnson')
   Transformation non-linéaire pour normaliser distributions asymétriques
       ↓
StandardScaler()
   Centrage-réduction (μ=0, σ=1)
       ↓
SVC(C=0.01, kernel='linear', class_weight='balanced', probability=True)
   SVM linéaire avec ajustement des poids de classe (déséquilibre 80/20)
       ↓
Probabilité brute P ∈ [0, 1]
       ↓
IsotonicRegression (calibration 10-fold Out-Of-Fold)
   Probabilité calibrée = taux de mortalité empirique réel
       ↓
Classification en zones de risque (seuils DCA) :
   ├── P < 14.3% → Zone FAIBLE  (5.1% mortalité, RR×1, N=257, 53.8%)
   ├── 14.3% ≤ P < 42.1% → Zone MODÉRÉE (29.1% mortalité, RR×5.7, N=158, 33.1%)
   └── P ≥ 42.1% → Zone ÉLEVÉE (55.6% mortalité, RR×10.9, N=63, 13.2%)
       ↓
Top-5 facteurs contributifs (poids SVM) + Recommandation clinique
```

#### Performances (validation croisée 10-fold stratifiée)

| Métrique | Valeur |
|---------|--------|
| **AUC-ROC** | **0.8262** |
| AUC nested honest (cross-val interne) | 0.8241 |
| **PR-AUC** | **0.4887** |
| Brier Score | 0.1265 (calibration correcte) |
| **F1-Score** | **0.5667** |
| Gap train-test AUC | +0.047 ✅ (pas de sur-apprentissage) |
| Permutation test p-value | 0.020 ✅ (modèle significatif) |
| Zone d'utilité clinique DCA | 2.8% → 50.5% seuil de traitement |
| Risque relatif Élevée/Faible | **22.6×** |

### 8.2 Fichiers sérialisés (joblib)

| Fichier | Contenu | Taille approx. |
|---------|---------|---------------|
| `mortalite_svm.joblib` | Pipeline complet : KNNImputer + PowerTransformer + SVC calibré | ~500 KB |
| `mortalite_svm_features.joblib` | Metadata : liste des 32 features, seuils, cohort_probas, métriques AUC | ~50 KB |
| `iso_calibrator.joblib` | IsotonicRegression entraîné sur probabilités OOF | ~10 KB |
| `gmm_classifier.joblib` | GaussianMixture(n_components=3) pour classification initiale | ~5 KB |

### 8.3 LLM de prétraitement (Ollama)

- **Modèle** : `qwen2.5:7b-instruct` (7 milliards de paramètres, exécution locale)
- **Embeddings** : `nomic-embed-text` (1536 dimensions, ChromaDB)
- **Usage** : Analyse de la structure des fichiers Excel importés, correction des valeurs aberrantes, normalisation des données biologiques, détection des incohérences

---

## 9. Pipeline de prétraitement LLM + RAG

```
1. Upload fichier Excel/CSV
        ↓
2. Parsing (pandas + openpyxl)
   → Détection types de colonnes, taux de valeurs manquantes
        ↓
3. Chunking sémantique
   → Découpage par section médicale (biologie, démographie, dialyse...)
        ↓
4. RAG — ChromaDB
   → Indexation des colonnes (embeddings nomic-embed-text)
   → Recherche du contexte médical pour chaque chunk
        ↓
5. Analyse LLM — Ollama (qwen2.5:7b)
   → Prompt : "[contexte médical RAG] + [données brutes]"
   → Réponse : corrections suggérées cellule par cellule avec justification
        ↓
6. Interface utilisateur
   → Affichage suggestions, acceptation/rejet manuel
        ↓
7. Validation chef_service (obligatoire)
   → Approbation ou rejet avec commentaire
        ↓
8. Intégration base de données
   → Normalisation finale → création objets Patient Django
```

**Corrections types effectuées par le LLM** :
- Virgule décimale → point (3,5 → 3.5)
- Unités biologiques (créatinine : mg/dL ↔ μmol/L)
- Sexe (M/F → Homme/Femme, normalisation casse)
- Dates (formats variés → ISO 8601)
- Codes étiologie (texte libre → catégorie standardisée)
- Valeurs aberrantes cliniques (albumine = 350 g/L → signalé comme erreur probable)

---

## 10. Rôles et permissions

| Fonctionnalité | Super Admin | Chef Service | Professeur | Résident |
|---------------|:-----------:|:------------:|:----------:|:--------:|
| Gestion utilisateurs (CRUD) | ✅ | ✅ | — | — |
| Création de comptes | ✅ | ✅ | — | — |
| Import données Excel | ✅ | ✅ | ✅ | ✅ |
| **Validation import** (étape obligatoire) | ✅ | ✅ | — | — |
| CRUD patients | ✅ | ✅ | ✅ | ✅ |
| Suppression massive données | ✅ | ✅ | — | — |
| Prédiction IA (SVM) | ✅ | ✅ | ✅ | ✅ |
| Réentraînement modèle | ✅ | — | — | — |
| Prétraitement LLM | ✅ | ✅ | ✅ | ✅ |
| **Validation prétraitement** | ✅ | ✅ | — | — |
| Monitoring patient | ✅ | ✅ | ✅ | ✅ |
| Consultation audit | ✅ | ✅ | — | — |
| Suppression logs audit | ✅ | — | — | — |
| Notes personnelles | ✅ | ✅ | ✅ | ✅ |
| Export Excel | ✅ | ✅ | ✅ | ✅ |

---

## 11. Stack technologique complète

### Backend

| Outil | Version | Rôle précis |
|-------|---------|------------|
| **Python** | 3.11 | Langage principal backend |
| **Django** | 6.0 | Framework web MVC ; ORM ; admin ; migrations |
| **Django REST Framework** | 3.15 | Sérialisation, vues API, pagination, filtres |
| **SimpleJWT** | 5.3 | Authentification JWT (access 8h, refresh 7j) |
| **scikit-learn** | 1.4 | SVM (SVC), KNNImputer, PowerTransformer, IsotonicRegression, GaussianMixture, GridSearchCV |
| **pandas** | 2.2 | Manipulation DataFrames, parsing Excel/CSV, agrégations analytiques |
| **numpy** | 1.26 | Calculs vectoriels, gestion arrays features ML |
| **joblib** | 1.4 | Sérialisation/désérialisation modèles ML (.joblib) |
| **Celery** | 5.3 | File de tâches asynchrones (analyse LLM en background) |
| **ChromaDB** | latest | Base vectorielle pour RAG (index embeddings colonnes médicales) |
| **openpyxl** | latest | Import/export fichiers Excel (.xlsx) |
| **psycopg2** | 2.9 | Driver PostgreSQL pour Django ORM |
| **XGBoost / LightGBM** | latest | Modèles ensemblistes (entraînement comparatif) |
| **djangorestframework-simplejwt** | 5.3 | Middleware JWT pour DRF |
| **django-cors-headers** | latest | Gestion CORS (Cross-Origin Resource Sharing) |

### Frontend

| Outil | Version | Rôle précis |
|-------|---------|------------|
| **React** | 18 | Framework UI déclaratif, state management (Hooks + Context API) |
| **React Router** | 6 | Routing SPA (client-side navigation, lazy loading) |
| **Material-UI (MUI)** | 5.15 | Composants UI : Button, TextField, Dialog, DataGrid, Tabs, Accordion, Badge, Chip |
| **@mui/icons-material** | 5.15 | Icônes SVG (Dashboard, People, Analytics, etc.) |
| **Chart.js** | 4 | Rendu graphiques : Line, Bar, Doughnut, groupés, horizontaux |
| **react-chartjs-2** | latest | Wrapper React pour Chart.js (composants déclaratifs) |
| **axios** | latest | Client HTTP : requêtes REST API, intercepteurs JWT, gestion erreurs |
| **jwt-decode** | latest | Décodage payload JWT (extraction rôle, expiration) |
| **xlsx (SheetJS)** | latest | Export Excel côté client (génération .xlsx depuis tableaux) |
| **Node.js** | 18 | Runtime de build React |
| **serve** | latest | Serveur de fichiers statiques pour le build React en production |

### Infrastructure et DevOps

| Outil | Version | Rôle précis |
|-------|---------|------------|
| **Docker** | 24+ | Conteneurisation de tous les services |
| **Docker Compose** | 2+ | Orchestration multi-services avec réseau interne |
| **PostgreSQL** | 16 | SGBD relationnel ; JSONB pour données flexibles ; indexation |
| **Redis** | 7 Alpine | Broker de messages Celery ; cache sessions |
| **Ollama** | latest | Serveur LLM local (API REST `/api/generate`, `/api/embed`) |
| **ChromaDB** | latest | Base vectorielle locale persistante pour RAG |
| **Git** | — | Contrôle de version ; branche `fix/repair-contract-gate` |
| **GitHub** | — | Repository distant : https://github.com/nisbe1218/Pf1 |

---

## Auteurs & Contexte

- **Établissement** : CHU Hassan II de Fès, Service de Néphrologie et d'Hémodialyse, Maroc
- **Cohorte de référence** : 478 patients hémodialysés, 2020–2024
- **Référence clinique** : Guessous Z., Allata Y. et al.
- **Contact développeur** : nisrineben1812@gmail.com
- **Repository** : https://github.com/nisbe1218/Pf1
- **Branche active** : `fix/repair-contract-gate`

---

*Document mis à jour le 2026-06-03 — AI NéphroCare v1.0*
