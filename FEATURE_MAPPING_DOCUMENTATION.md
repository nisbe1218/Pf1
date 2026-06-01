# 📊 Feature Mapping - Modèle ML Mortalité 1 an

## Vue d'ensemble

Le modèle SVM entraîné utilise **32 features** pour prédire la mortalité à 1 an :
- **24 features individuelles** (cliniques)
- **8 features d'interaction** (calculées à partir des individuelles)

---

## 24 Features Individuelles (à importer)

Ces features doivent être présentes dans le fichier d'import :

### Démographie & Comorbidités (6)
1. `age_annees` - Âge en années (nécessaire pour interactions)
2. `Charlson` - Index de Charlson (nécessaire pour interactions)
3. `hypertension` - Hypertension (0/1)
4. `cardiopathie` - Cardiopathie (0/1, nécessaire pour interactions)
5. `diabete` - Diabète (0/1)
6. `maladie_renale_hereditaire` - Maladie rénale héréditaire (0/1)

### Symptomatologie (5)
7. `douleur_abdominale` - Douleur abdominale (0/1)
8. `dyspnee` - Dyspnée (0/1, nécessaire pour interactions)
9. `oedemes_surcharge` - Œdèmes de surcharge (0/1, nécessaire pour interactions)
10. `crise_convulsive` - Crise convulsive (0/1)
11. `evenement_cardiovasculaire` - Événement cardiovasculaire (0/1)

### Biologie de base (5)
12. `albumine_basale` - Albumine basale en g/L (nécessaire pour interactions)
13. `calcium_basale` - Calcium basale en mg/L
14. `ferritine_basale` - Ferritine basale en ng/mL
15. `pth_basale` - PTH basale en pg/mL
16. `sodium_basal` - Sodium basal en mmol/L (nécessaire pour interactions)

### Traitement de base (3)
17. `hemodialyse` - Hémodialyse (0/1)
18. `seances_par_semaine` - Séances par semaine (nécessaire pour interactions)
19. `nombre_hospitalisations` - Nombre hospitalisations (nécessaire pour interactions)

### Accès vasculaire (2)
20. `fistule_arterioveineuse_creee` - Fistule artério-veineuse créée (0/1)
21. `admission_cathetere_tunnellise` - Admission par cathéter tunnellisé (0/1)

### Transplantation & Information (3)
22. `information_transplantation_donnee` - Information transplantation donnée (0/1)
23. `liste_attente_transplantation` - Liste attente transplantation (0/1)
24. `couverture_medicale` - Couverture médicale (0/1)

### Autres (0)
25. `du_residuelle` - Diurèse résiduelle (0/1)
26. `etiologie_mrc` - Étiologie MRC (catégorique)
27. `annee_inclusion` - Année inclusion

---

## 8 Features d'Interaction (calculées automatiquement)

Ces features sont **CALCULÉES automatiquement** à partir des individuelles :

### Interactions Age-Comorbidités
1. **`age_x_charlson`** = `age_annees` × `Charlson`
   - Capture l'effet combiné de l'âge et de la charge de comorbidités

2. **`age_x_cardio`** = `age_annees` × `cardiopathie`
   - Capture l'effet combiné de l'âge et de la cardiopathie

### Interactions Symptomatologie
3. **`dyspnee_x_oedeme`** = `dyspnee` × `oedemes_surcharge`
   - Capture la co-occurrence de dyspnée et œdèmes (signes d'insuffisance cardiaque)

### Interactions Comorbidités
4. **`hypert_x_cardio`** = `hypertension` × `cardiopathie`
   - Capture la co-occurrence d'hypertension et cardiopathie

### Seuils cliniques
5. **`sodium_lt130`** = 1 si `sodium_basal` < 130 mmol/L, sinon 0
   - Hyponatrémie sévère (marqueur de gravité)

6. **`albumine_lt35`** = 1 si `albumine_basale` < 35 g/L, sinon 0
   - Malnutrition sévère

### Interactions Nutritionnelles
7. **`albumine_x_hosp`** = `albumine_basale` × `nombre_hospitalisations`
   - Capture l'effet de la malnutrition combinée aux hospitalisations

### Interactions Comorbidités-Traitement
8. **`charlson_x_hosp`** = `Charlson` × `nombre_hospitalisations`
   - Capture l'effet de la charge de comorbidités combinée aux hospitalisations

---

## Workflow d'Intégration

### 1️⃣ Import du fichier
L'utilisateur importe un fichier Excel/CSV avec **au moins** les 24 features individuelles

### 2️⃣ Validation
Chef de service/Super admin valide les données

### 3️⃣ Insertion en BD
Les données sont insérées dans le modèle `Patient` Django

### 4️⃣ Prédiction
Quand on demande une prédiction :
- **Extraction** : Les 24 features + 9 variables supplémentaires (age, Charlson, sodium...) sont extraites de Patient ORM
- **Calcul** : Les 8 interactions sont CALCULÉES
- **Normalisation** : Pipeline KNNImputer + PowerTransformer appliqué
- **Prédiction** : Le modèle SVM prédit la probabilité de décès

### 5️⃣ Résultat
- **Score risque** : Probabilité × 100 (0-100)
- **Niveau risque** : Faible (0-33) / Modéré (33-66) / Élevé (66-100)
- **Recommandation** : Suivi standard / renforcé / intensif

---

## Gestion des valeurs manquantes

- **Tolérance** : Jusqu'à 5 features manquantes autorisées (sur 32)
- **Imputation** : Les valeurs manquantes sont remplacées par 0 lors de la prédiction
- **Pipeline** : Le KNNImputer(k=3) gère aussi les valeurs manquantes

---

## Ordre des 32 Features (Pour le modèle ML)

```python
[
    # 24 cliniques
    'fistule_arterioveineuse_creee',
    'couverture_medicale',
    'albumine_basale',
    'calcium_basale',
    'admission_cathetere_tunnellise',
    'annee_inclusion',
    'ferritine_basale',
    'seances_par_semaine',
    'nombre_hospitalisations',
    'du_residuelle',
    'crise_convulsive',
    'pth_basale',
    'etiologie_mrc',
    'douleur_abdominale',
    'diabete',
    'evenement_cardiovasculaire',
    'dyspnee',
    'oedemes_surcharge',
    'hemodialyse',
    'liste_attente_transplantation',
    'maladie_renale_hereditaire',
    'information_transplantation_donnee',
    'hypertension',
    'cardiopathie',
    
    # 8 interactions
    'age_x_charlson',
    'dyspnee_x_oedeme',
    'sodium_lt130',
    'charlson_x_hosp',
    'hypert_x_cardio',
    'albumine_x_hosp',
    'albumine_lt35',
    'age_x_cardio',
]
```

**⚠️ ATTENTION** : Cet ordre DOIT être respecté exactement pour que le modèle fonctionne !

---

## Fichiers concernés

- `backend/predictions/models/feature_mapping.py` - Mapping centralisé
- `backend/predictions/predict_mortalite.py` - Endpoint prédiction
- `backend/predictions/models/export_svm_model.py` - Export du modèle

---

## Test

```bash
# Faire une prédiction
GET /predictions/patient/1/mortalite/

# Response
{
    "success": true,
    "patient_id": 1,
    "score_risque": 45.2,
    "niveau_risque": "Modéré",
    "probabilite_deces": 0.452,
    "recommendation": "Suivi renforcé...",
    "features_missing": [],
    "auc_cv": 0.8235
}
```
