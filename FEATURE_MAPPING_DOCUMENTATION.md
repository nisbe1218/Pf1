# Feature Mapping — Modèle ML Mortalité 1 an (SVM Linéaire)

## Vue d'ensemble

Le modèle SVM Linéaire (C=0.05, Platt scaling) utilise **32 features** pour prédire la mortalité à 1 an :
- **24 features cliniques** individuelles
- **8 features d'interaction** calculées automatiquement

**Cohorte d'entraînement** : HD-478 (478 patients, 94 décès à 1 an, taux = 19.9%)  
**AUC-ROC** : 0.8272 | **Brier Score** : 0.1257 | **F1** : 0.551

---

## 24 Features Cliniques

### Démographie & Comorbidités (6)
| Feature | Description | Type |
|---|---|---|
| `age_annees` | Âge en années | Numérique |
| `Charlson` | Index de Charlson | Numérique |
| `hypertension` | Hypertension artérielle | Binaire (0/1) |
| `cardiopathie` | Cardiopathie | Binaire (0/1) |
| `diabete` | Diabète (détecté depuis 3 sources) | Binaire (0/1) |
| `maladie_renale_hereditaire` | Maladie rénale héréditaire | Binaire (0/1) |

### Symptomatologie (5)
| Feature | Description | Type |
|---|---|---|
| `douleur_abdominale` | Douleur abdominale | Binaire (0/1) |
| `dyspnee` | Dyspnée | Binaire (0/1) |
| `oedemes_surcharge` | Œdèmes de surcharge | Binaire (0/1) |
| `crise_convulsive` | Crise convulsive | Binaire (0/1) |
| `evenement_cardiovasculaire` | Événement cardiovasculaire antérieur | Binaire (0/1) |

### Biologie (5)
| Feature | Description | Type |
|---|---|---|
| `albumine_basale` | Albumine basale (g/L) | Numérique |
| `calcium_basale` | Calcium corrigé basale (mg/L) | Numérique |
| `ferritine_basale` | Ferritine basale (ng/mL) | Numérique |
| `pth_basale` | PTH basale (pg/mL) | Numérique |
| `sodium_basal` | Sodium basal (mmol/L) | Numérique |

### Dialyse (3)
| Feature | Description | Type |
|---|---|---|
| `hemodialyse` | Modalité hémodialyse active | Binaire (0/1) |
| `seances_par_semaine` | Nombre de séances par semaine | Numérique |
| `nombre_hospitalisations` | Nombre d'hospitalisations | Numérique |

### Accès vasculaire (2)
| Feature | Description | Type |
|---|---|---|
| `fistule_arterioveineuse_creee` | Fistule artério-veineuse créée | Binaire (0/1) |
| `admission_cathetere_tunnellise` | Admission par cathéter tunnellisé | Binaire (0/1) |

### Données administratives & sociales (3)
| Feature | Description | Type |
|---|---|---|
| `couverture_medicale` | Couverture médicale (0=auto-paiement, 1=RAMED, 2=AMO, 3=autre) | Ordinal (0–3) |
| `annee_inclusion` | Année d'inclusion — encodage ordinal (0=2020, 1=2021, …, 4=2024) | Ordinal (0–4) |
| `du_residuelle` | Diurèse résiduelle | Binaire (0/1) |

### Étiologie & Transplantation (3)
| Feature | Description | Type |
|---|---|---|
| `etiologie_mrc` | Étiologie de la MRC (11 catégories ordinales) | Ordinal (1–11) |
| `information_transplantation_donnee` | Information transplantation donnée | Binaire (0/1) |
| `liste_attente_transplantation` | Inscrit sur liste d'attente greffe | Binaire (0/1) |

---

## 8 Features d'Interaction (calculées automatiquement)

| Feature | Formule | Signification clinique |
|---|---|---|
| `age_x_charlson` | âge × Charlson | Effet combiné âge + charge de comorbidités |
| `age_x_cardio` | âge × cardiopathie | Effet combiné âge + cardiopathie |
| `dyspnee_x_oedeme` | dyspnée × œdèmes | Co-occurrence signes d'insuffisance cardiaque |
| `hypert_x_cardio` | hypertension × cardiopathie | Co-occurrence HTA + cardiopathie |
| `albumine_x_hosp` | albumine × hospitalisations | Malnutrition + hospitalisations répétées |
| `charlson_x_hosp` | Charlson × hospitalisations | Charge comorbidités + hospitalisations |
| `sodium_lt130` | 1 si sodium < 130 mmol/L | Hyponatrémie sévère |
| `albumine_lt35` | 1 si albumine < 35 g/L | Malnutrition sévère |

---

## Seuils de classification (zones de risque)

| Zone | Seuil | Mortalité observée (HD-478) | Méthode |
|---|---|---|---|
| **Faible** | p̂ < 10% | **5.6%** (249 patients) | T1 = ROC, Sensibilité ≥ 90% |
| **Modéré** | 10% ≤ p̂ < 29% | **14.6%** (48 patients) | — |
| **Élevé** | p̂ ≥ 29% | **40.3%** (181 patients) | T2 = Youden bootstrappé (n=1000) |

---

## Pipeline de prédiction

```
Patient (BDD) → extract_features_for_patient()
             → KNNImputer(k=3) + PowerTransformer(Yeo-Johnson)
             → SVM Linéaire (C=0.05, Platt scaling)
             → p̂ ∈ [0, 1]
             → Zone Faible / Modéré / Élevé
```

**Tolérance aux valeurs manquantes** : jusqu'à 5 features manquantes sur 32 (KNN imputation).

---

## Ordre exact des 32 features (modèle ML)

```python
# 24 cliniques
['fistule_arterioveineuse_creee', 'couverture_medicale', 'albumine_basale',
 'calcium_basale', 'admission_cathetere_tunnellise', 'annee_inclusion',
 'ferritine_basale', 'seances_par_semaine', 'nombre_hospitalisations',
 'du_residuelle', 'crise_convulsive', 'pth_basale', 'etiologie_mrc',
 'douleur_abdominale', 'diabete', 'evenement_cardiovasculaire', 'dyspnee',
 'oedemes_surcharge', 'hemodialyse', 'liste_attente_transplantation',
 'maladie_renale_hereditaire', 'information_transplantation_donnee',
 'hypertension', 'cardiopathie',
 # 8 interactions
 'age_x_charlson', 'dyspnee_x_oedeme', 'sodium_lt130', 'charlson_x_hosp',
 'hypert_x_cardio', 'albumine_x_hosp', 'albumine_lt35', 'age_x_cardio']
```

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `backend/predictions/models/feature_mapping.py` | Extraction des 32 features depuis Patient ORM |
| `backend/predictions/models/mortalite_svm.joblib` | Modèle SVM entraîné (pipeline complet) |
| `backend/predictions/models/mortalite_svm_features.joblib` | Métadonnées : features, métriques |
| `backend/predictions/models/seuils_classification.joblib` | Seuils T1/T2 et méthodes de calcul |
| `backend/predictions/predict_mortalite.py` | Endpoint GET /predictions/patient/{id}/mortalite/ |
