# Pipeline de Classification du Risque de Mortalité à 1 An

## Objectif

Classifier chaque patient hémodialysé en 3 zones de risque (Faible / Modéré / Élevé) basées sur la probabilité prédite de décès dans les 12 mois suivant le début de la dialyse.

---

## Vue d'ensemble

```
Patient (données cliniques BDD)
        │
        ▼
Extraction des 32 features
(feature_mapping.py)
        │
        ▼
Pipeline SVM Linéaire
KNNImputer(k=3) → PowerTransformer(Yeo-Johnson) → SVM(C=0.05, Platt scaling)
        │
        ▼
p̂ ∈ [0, 1]  — probabilité calibrée de décès à 1 an
        │
        ├── p̂ < T1 (0.10)  →  Zone FAIBLE
        ├── p̂ < T2 (0.29)  →  Zone MODÉRÉE
        └── p̂ ≥ T2 (0.29)  →  Zone ÉLEVÉE
```

---

## Modèle — SVM Linéaire

| Paramètre | Valeur |
|---|---|
| Algorithme | LinearSVC + CalibratedClassifierCV (Platt, 5-fold) |
| C (régularisation) | 0.05 |
| Kernel | Linéaire |
| Préprocessing | KNNImputer(k=3) → PowerTransformer(Yeo-Johnson) |
| Cohorte | HD-478 (478 patients, 94 décès, taux = 19.9%) |
| Validation | Stratified 10-fold CV |
| AUC-ROC | **0.8272** ± 0.0779 |
| Brier Score | 0.1257 |
| F1 | 0.551 |
| Sensibilité | 0.691 |

---

## Seuils de classification (T1 / T2)

| Seuil | Valeur | Méthode |
|---|---|---|
| **T1** (Faible → Modéré) | **0.10** (10%) | Courbe ROC : sensibilité ≥ 90% (91.5% atteinte, 8.5% décès manqués) |
| **T2** (Modéré → Élevé) | **0.29** (29%) | Index de Youden bootstrappé (n=1000, médiane=28.9%, IC95=[10%–33.3%]) |

Stockés dans `backend/predictions/models/seuils_classification.joblib`.

---

## Taux de mortalité observés par zone (cohorte HD-478)

| Zone | Patients | Décès | Mortalité observée | Recommandation |
|---|---|---|---|---|
| **Faible** (p̂ < 10%) | 249 | 14 | **5.6%** | Suivi standard |
| **Modéré** (10% ≤ p̂ < 29%) | 48 | 7 | **14.6%** | Surveillance renforcée |
| **Élevé** (p̂ ≥ 29%) | 181 | 73 | **40.3%** | Prise en charge prioritaire |

---

## Réponse API

`GET /api/predictions/patient/{id}/mortalite/`

```json
{
  "success": true,
  "patient_id": 42,
  "probabilite_deces": 0.152,
  "probabilite_calibree": 0.152,
  "score_risque": 15.2,
  "niveau_risque": "Modéré",
  "risque_relatif": 0.8,
  "seuil_faible_modere": 0.1,
  "seuil_modere_eleve": 0.29,
  "threshold_method": "roc_youden",
  "recommendation": "Zone Modérée — mortalité observée : 14.6 % (cohorte HD-478)...",
  "mort_rates": {"Faible": 5.6, "Modéré": 14.6, "Élevé": 40.3},
  "features_missing": 2,
  "factors": [
    {"label": "albumine_basale", "weight": -0.312},
    {"label": "age_x_charlson", "weight": 0.287}
  ],
  "model_version": "SVM Linéaire v1",
  "auc_cv": 0.8272
}
```

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `backend/predictions/models/mortalite_svm.joblib` | Pipeline SVM complet (imputer + transformer + SVM) |
| `backend/predictions/models/mortalite_svm_features.joblib` | Métadonnées : features, métriques, distribution classes |
| `backend/predictions/models/seuils_classification.joblib` | T1, T2, méthodes de calcul, AUC |
| `backend/predictions/models/feature_mapping.py` | Extraction des 32 features depuis Patient Django ORM |
| `backend/predictions/predict_mortalite.py` | Endpoint de prédiction (GET + POST simulation) |
