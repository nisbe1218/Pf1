# État actuel du module ML — AI NéphroCare

## Modèle actif

**SVM Linéaire** (unique modèle de prédiction de mortalité à 1 an)

| Paramètre | Valeur |
|---|---|
| Algorithme | LinearSVC + CalibratedClassifierCV (Platt scaling, 5-fold) |
| Régularisation | C = 0.05 |
| Préprocessing | KNNImputer(k=3) → PowerTransformer(Yeo-Johnson) |
| Features | 32 (24 cliniques + 8 interactions) |
| AUC-ROC | 0.8272 ± 0.0779 |
| Cohorte | HD-478 (478 patients, 94 décès à 1 an) |

---

## Architecture Backend

### Endpoint principal
`GET /api/predictions/patient/{id}/mortalite/`

Flux :
1. Charger le patient depuis PostgreSQL
2. Extraire les 32 features via `feature_mapping.py`
3. Imputer les valeurs manquantes (KNN k=3)
4. Appliquer PowerTransformer (Yeo-Johnson)
5. Prédire avec SVM Linéaire (Platt scaling)
6. Classifier selon T1=10% / T2=29%
7. Retourner : probabilité, zone, facteurs explicatifs, recommandation

### Fichiers backend
| Fichier | Rôle |
|---|---|
| `backend/predictions/predict_mortalite.py` | Endpoint GET + POST simulation |
| `backend/predictions/models/feature_mapping.py` | Mapping 32 features ↔ champs Patient ORM |
| `backend/predictions/models/mortalite_svm.joblib` | Modèle entraîné |
| `backend/predictions/models/seuils_classification.joblib` | Seuils T1/T2 |

---

## Architecture Frontend (ModelAI.js)

### Onglets
1. **Vue d'ensemble du modèle** — Métriques AUC, Brier, F1, graphiques de performance, zones de risque
2. **Patients** — Recherche + liste des patients avec bouton prédiction
3. **Prédiction individuelle** — Résultat complet pour un patient sélectionné

### Flux de prédiction (frontend)
```
Liste patients → Sélectionner un patient → Cliquer "Prédire"
→ GET /api/predictions/patient/{id}/mortalite/
→ Affichage : score (%), zone, facteurs top-5, recommandation, graphique
```

### Auto-extraction des features
Les features sont extraites automatiquement depuis la base de données — aucune saisie manuelle de variables par l'utilisateur.

---

## Zones de risque et mortalité observée

| Zone | Seuil | Mortalité HD-478 |
|---|---|---|
| Faible | p̂ < 10% | 5.6% |
| Modéré | 10% ≤ p̂ < 29% | 14.6% |
| Élevé | p̂ ≥ 29% | 40.3% |

---

## Déploiement

Le modèle tourne dans le conteneur `medical_backend` (Docker Compose).  
Les fichiers `.joblib` sont montés dans `/app/predictions/models/`.  
Aucun réentraînement en ligne — le modèle est fixe et versionné.
