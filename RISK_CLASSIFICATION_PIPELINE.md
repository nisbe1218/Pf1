# Pipeline de Classification du Risque de Mortalité à 1 An

## Objectif

Identifier, parmi les patients hémodialysés, ceux qui présentent un risque élevé de décès dans les 12 mois suivant le début de la dialyse. Le résultat est une classification en 3 zones : **Faible**, **Modéré**, **Élevé**.

---

## Vue d'ensemble du pipeline

```
Patient (données cliniques)
        │
        ▼
┌───────────────────┐
│   Extraction des  │  32 features cliniques extraites
│   32 features     │  depuis la base de données
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│    SVM Linéaire   │  Entraîné sur cohorte HD-478
│  (classificateur) │  → probabilité brute ∈ [0, 1]
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│   Calibration     │  Corrige le biais du SVM
│   Isotonique      │  → probabilité calibrée (optionnelle)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Seuils GMM       │  T1 = 0.1431 / T2 = 0.4211
│  (3 zones)        │  trouvés par Gaussian Mixture Model
└────────┬──────────┘
         │
         ▼
   Faible / Modéré / Élevé
```

---

## Étape 1 — Extraction des 32 features

### Rôle
Transformer les données brutes du dossier patient en un vecteur numérique utilisable par le SVM.

### Source des données
Les données proviennent du modèle `Patient` de la plateforme. Le mapping est défini dans `backend/predictions/models/feature_mapping.py`.

### Les 32 features

#### Features cliniques directes (24)

| Feature | Description | Type |
|---|---|---|
| `fistule_arterioveineuse_creee` | Fistule artérioveineuse créée | Binaire |
| `admission_cathetere_tunnellise` | Admission avec cathéter tunnellisé | Binaire |
| `hemodialyse` | Modalité hémodialyse active | Binaire |
| `seances_par_semaine` | Nombre de séances par semaine | Numérique |
| `nombre_hospitalisations` | Nombre d'hospitalisations | Numérique |
| `du_residuelle` | Diurèse résiduelle | Numérique |
| `albumine_basale` | Albumine basale (g/L) | Numérique |
| `calcium_basale` | Calcium corrigé basale | Numérique |
| `ferritine_basale` | Ferritine basale | Numérique |
| `pth_basale` | PTH basale | Numérique |
| `couverture_medicale` | Couverture médicale (0–3) | Ordinal |
| `etiologie_mrc` | Étiologie de la MRC (11 catégories) | Ordinal |
| `diabete` | Diabète (détecté depuis 3 sources) | Binaire |
| `hypertension` | Hypertension artérielle | Binaire |
| `cardiopathie` | Cardiopathie | Binaire |
| `maladie_renale_hereditaire` | Maladie rénale héréditaire | Binaire |
| `dyspnee` | Dyspnée | Binaire |
| `oedemes_surcharge` | Œdèmes / surcharge | Binaire |
| `crise_convulsive` | Antécédent de crise convulsive | Binaire |
| `douleur_abdominale` | Douleur abdominale | Binaire |
| `evenement_cardiovasculaire` | Événement cardiovasculaire antérieur | Binaire |
| `liste_attente_transplantation` | Sur liste d'attente greffe | Binaire |
| `information_transplantation_donnee` | Information greffe donnée | Binaire |
| `score_charlson` | Score de comorbidité de Charlson | Numérique |

#### Features d'interaction (8)

Ces features capturent les effets combinés entre variables :

| Feature | Formule |
|---|---|
| `age_x_charlson` | âge × score Charlson |
| `dyspnee_x_oedeme` | dyspnée × œdèmes |
| `charlson_x_hosp` | Charlson × hospitalisations |
| `hypert_x_cardio` | hypertension × cardiopathie |
| `albumine_x_hosp` | albumine × hospitalisations |
| `albumine_lt35` | 1 si albumine < 35 g/L, sinon 0 |
| `sodium_lt130` | 1 si natrémie < 130 mmol/L (hyponatrémie) |
| `age_x_cardio` | âge × cardiopathie |

---

## Étape 2 — SVM Linéaire

### Rôle
Répondre à la question : **"Ce patient ressemble-t-il davantage à un patient décédé dans l'année ou à un patient vivant ?"**

### Entraînement
- **Cohorte** : HD-478 (478 patients hémodialysés)
- **Label** : `deces_1an = 1` si décès survenu dans les 365 jours après début dialyse, sinon `0`
- **Taux de mortalité dans la cohorte** : 19.9% (base rate)
- **Validation** : cross-validation stratifiée, sélection par PR-AUC

### Ce que le SVM produit

```
input_df (1 ligne × 32 colonnes)
    → pipeline.predict_proba(input_df)[:, 1]
    → proba_brute ∈ [0, 1]
```

`proba_brute` est un score de vraisemblance de décès. Ce n'est pas encore une probabilité cliniquement interprétable — le SVM est optimisé pour séparer les classes, pas pour estimer des probabilités absolues.

### Limites du SVM seul
- Produit **une seule frontière** entre vivants et décédés
- Ne peut pas directement produire **deux frontières** pour 3 zones
- Ses scores sont souvent compressés vers 0.5 (biais sigmoid)

---

## Étape 3 — Calibration Isotonique (optionnelle)

### Rôle
Corriger le biais du SVM pour que la probabilité corresponde au taux de mortalité réellement observé.

### Pourquoi c'est nécessaire
Le SVM peut dire `proba = 0.72` alors que dans la réalité, parmi tous les patients avec ce score, seulement 45% sont décédés. La calibration corrige cet écart.

```
SVM brut   →  Mortalité réelle observée
  0.10     →       3%
  0.30     →      18%
  0.50     →      31%
  0.72     →      45%   ← correction du biais
  0.90     →      68%
```

### Méthode : Régression isotonique croisée (10-fold)
- Apprise sur les probabilités OOF (Out-Of-Fold) de la cohorte HD-478
- Transformation monotone : si SVM dit A > B, l'isotonique préserve A > B
- Sauvegardée dans `iso_calibrator.joblib`

### État dans la plateforme
L'isotonique n'est **pas active actuellement** (`iso_calibrator.joblib` absent). La probabilité calibrée est donc égale à la probabilité brute SVM. Quand elle sera disponible, le pipeline la prioritise automatiquement.

---

## Étape 4 — Classification par GMM (Gaussian Mixture Model)

### Rôle
Trouver les **deux frontières naturelles** (T1 et T2) qui séparent les 3 populations de patients.

### Pourquoi le GMM plutôt que des seuils arbitraires
Les seuils T1/T2 ne doivent pas être choisis à la main — ils doivent refléter la vraie structure des données. Le GMM modélise la distribution des probabilités comme la superposition de 3 sous-populations :

```
         Faible          Modéré           Élevé
    ____           _____           ______
   /    \         /     \         /      \
  /      \       /       \       /        \
─────────────────────────────────────────────
 0       T1                T2              1
          ↑                ↑
    intersection      intersection
    Gauss 0/1         Gauss 1/2
```

### Comment le GMM trouve T1 et T2

1. Fitter `GaussianMixture(n_components=3)` sur toutes les probabilités de la cohorte
2. Trier les 3 composantes par leur moyenne (basse → haute)
3. Trouver le point d'intersection entre la Gaussienne 0 et la Gaussienne 1 → **T1**
4. Trouver le point d'intersection entre la Gaussienne 1 et la Gaussienne 2 → **T2**

L'intersection est le point où il est mathématiquement optimal de changer de zone — probabilité d'appartenir à la classe inférieure = probabilité d'appartenir à la classe supérieure.

### Seuils actuels dans la plateforme

| Seuil | Valeur | Signification |
|---|---|---|
| T1 (Faible / Modéré) | **0.1431** | En-dessous : zone Faible |
| T2 (Modéré / Élevé) | **0.4211** | Au-dessus : zone Élevée |

Ces valeurs sont stockées dans `mortalite_svm_features.joblib` sous la clé `gmm_thresholds`.

### Garde-fous cliniques
Pour éviter des seuils aberrants si le GMM diverge :
- T1 est contraint dans `[0.05, 0.30]`
- T2 est contraint dans `[T1 + 0.05, 0.65]`

---

## Étape 5 — Classification finale

```python
if proba_calibrated < T1:      # < 0.1431
    niveau = "Faible"
elif proba_calibrated < T2:    # 0.1431 – 0.4211
    niveau = "Modéré"
else:                          # > 0.4211
    niveau = "Élevé"
```

### Taux de mortalité observés par zone (cohorte HD-478)

| Zone | Patients | Mortalité observée | Interprétation |
|---|---|---|---|
| Faible | 257 | ~5.1% | Suivi standard |
| Modéré | 158 | ~29.1% | Surveillance renforcée |
| Élevé | 63 | ~55.6% | Prise en charge prioritaire |

---

## Priorité des seuils (logique de résolution)

Le système choisit les seuils dans cet ordre :

```
1. calibration_thresholds.T1_clinical / T2_clinical
   (si train_isotonic.py a été relancé avec GMM)
        ↓ sinon
2. gmm_thresholds[0] / gmm_thresholds[1]
   ✅ ACTIF ACTUELLEMENT  →  T1=0.1431, T2=0.4211
        ↓ sinon
3. Défaut fixe : T1=0.10, T2=0.40
```

---

## Réponse API complète

`GET /predictions/patient/<id>/mortalite/`

```json
{
  "success": true,
  "patient_id": 42,
  "probabilite_deces": 0.3821,
  "probabilite_calibree": 0.3821,
  "score_risque": 38.2,
  "niveau_risque": "Modéré",
  "risque_relatif": 1.9,
  "seuil_faible_modere": 0.143,
  "seuil_modere_eleve": 0.421,
  "threshold_method": "gmm",
  "recommendation": "Zone Modérée — mortalité observée : 29.1% (cohorte HD-478)...",
  "features_missing": 2,
  "factors": [
    { "label": "albumine_basale", "weight": -0.312 },
    { "label": "nombre_hospitalisations", "weight": 0.287 }
  ],
  "model_version": "SVM Linéaire v1",
  "auc_cv": 0.821
}
```

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `backend/predictions/models/mortalite_svm.joblib` | Modèle SVM entraîné |
| `backend/predictions/models/mortalite_svm_features.joblib` | Métadonnées : features, seuils GMM, taux mortalité |
| `backend/predictions/models/iso_calibrator.joblib` | Calibrateur isotonique (absent = non actif) |
| `backend/predictions/models/gmm_classifier.joblib` | GMM entraîné (utilisé pour les seuils) |
| `backend/predictions/models/feature_mapping.py` | Extraction des 32 features depuis Patient ORM |
| `backend/predictions/models/train_isotonic.py` | Script de re-calibration + recalcul GMM |
| `backend/predictions/predict_mortalite.py` | Endpoint de prédiction (GET + POST simulation) |

---

## Pour recalculer les seuils GMM

Si de nouvelles données sont disponibles ou si le SVM est ré-entraîné :

```bash
cd backend/predictions/models
python train_isotonic.py Base_HD_478_v4_finale.xlsx
```

Le script :
1. Recharge les probabilités OOF depuis les métadonnées SVM
2. Refait la calibration isotonique (10-fold)
3. Refait le GMM sur les probabilités calibrées
4. Calcule les nouveaux T1/T2 par intersection des Gaussiennes
5. Met à jour `mortalite_svm_features.joblib` et `iso_calibrator.joblib`

Puis copier dans Docker :

```bash
docker cp iso_calibrator.joblib medical_backend:/app/predictions/models/
docker cp mortalite_svm_features.joblib medical_backend:/app/predictions/models/
docker restart medical_backend
```
