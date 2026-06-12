"""
Entraîne le modèle SVM mortalité depuis le fichier Excel de recherche
et sauvegarde les fichiers .joblib au format attendu par la plateforme.

Usage :
    python train_from_excel.py Base_HD_478_v4_finale.xlsx

Puis copier les fichiers générés dans Docker :
    docker cp mortalite_svm.joblib medical_backend:/app/predictions/models/mortalite_svm.joblib
    docker cp mortalite_svm_features.joblib medical_backend:/app/predictions/models/mortalite_svm_features.joblib
    docker restart medical_backend
"""

import sys
import numpy as np
import pandas as pd
import joblib
import warnings
warnings.filterwarnings('ignore')

from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_curve
from sklearn.preprocessing import PowerTransformer
from sklearn.impute import KNNImputer
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, f1_score

FICHIER = sys.argv[1] if len(sys.argv) > 1 else 'Base_HD_478_v4_finale.xlsx'
FEUILLE = 'Base_HD_478_v4'
N_FOLDS = 10
RANDOM_STATE = 42

print(f"Chargement de {FICHIER}...")
df = pd.read_excel(FICHIER, sheet_name=FEUILLE)

# Variable cible
df['deces_1an'] = (
    (df['deces'] == 1) &
    (df['delai_jusquau_deces_jours'] <= 365)
).astype(int)
y = df['deces_1an'].reset_index(drop=True)
print(f"  {len(df)} patients | {y.sum()} décès ({y.mean()*100:.1f}%)")

# 24 features cliniques (ordre identique à feature_mapping.py)
FEATS_CLINIQUES = [
    'fistule_arterioveineuse_creee', 'couverture_medicale', 'albumine_basale',
    'calcium_basale', 'admission_cathetere_tunnellise', 'annee_inclusion',
    'ferritine_basale', 'seances_par_semaine', 'nombre_hospitalisations',
    'du_residuelle', 'crise_convulsive', 'pth_basale', 'etiologie_mrc',
    'douleur_abdominale', 'diabete', 'evenement_cardiovasculaire', 'dyspnee',
    'oedemes_surcharge', 'hemodialyse', 'liste_attente_transplantation',
    'maladie_renale_hereditaire', 'information_transplantation_donnee',
    'hypertension', 'cardiopathie',
]

X = df[FEATS_CLINIQUES].apply(pd.to_numeric, errors='coerce')

# 8 interactions (ordre identique à feature_mapping.py)
X['age_x_charlson']   = df['age_annees'] * df['Charlson']
X['dyspnee_x_oedeme'] = df['dyspnee'].fillna(0) * df['oedemes_surcharge'].fillna(0)
X['sodium_lt130']     = (df['sodium_basal'] < 130).astype(float)
X['charlson_x_hosp']  = df['Charlson'] * df['nombre_hospitalisations'].fillna(0)
X['hypert_x_cardio']  = df['hypertension'].fillna(0) * df['cardiopathie'].fillna(0)
X['albumine_x_hosp']  = df['albumine_basale'] * df['nombre_hospitalisations'].fillna(0)
X['albumine_lt35']    = (df['albumine_basale'] < 35).astype(float)
X['age_x_cardio']     = df['age_annees'] * df['cardiopathie'].fillna(0)

X = X.reset_index(drop=True)
feature_keys = list(X.columns)
print(f"  {X.shape[1]} features | {X.isnull().sum().sum()} valeurs manquantes")

# Pipeline SVM (identique au script de recherche)
base_pipe = Pipeline([
    ('imputer',     KNNImputer(n_neighbors=3)),
    ('transformer', PowerTransformer(method='yeo-johnson')),
    ('clf',         SVC(C=0.05, kernel='linear', class_weight='balanced',
                        probability=True, random_state=RANDOM_STATE)),
])

# Évaluation 10-fold CV pour obtenir l'AUC réelle et le seuil Youden
print(f"\nÉvaluation {N_FOLDS}-fold CV...")
cv = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
fold_aucs = []
fold_thrs = []
all_proba = np.zeros(len(y))

for tr, te in cv.split(X, y):
    X_tr, X_te = X.iloc[tr], X.iloc[te]
    y_tr, y_te = y.iloc[tr], y.iloc[te]

    base_pipe.fit(X_tr, y_tr)
    proba_te = base_pipe.predict_proba(X_te)[:, 1]

    proba_tr = base_pipe.predict_proba(X_tr)[:, 1]
    fpr_t, tpr_t, thr_t = roc_curve(y_tr, proba_tr)
    j_idx = np.argmax(tpr_t - fpr_t)
    fold_thrs.append(float(np.clip(thr_t[j_idx], 0.05, 0.95)))

    fold_aucs.append(roc_auc_score(y_te, proba_te))
    all_proba[te] = proba_te

auc_cv = float(np.mean(fold_aucs))
threshold = float(np.mean(fold_thrs))
ap = average_precision_score(y, all_proba)
brier = brier_score_loss(y, all_proba)
pred_bin = (all_proba >= threshold).astype(int)
f1 = f1_score(y, pred_bin)

print(f"  AUC-ROC (10-fold CV) : {auc_cv:.4f} ± {np.std(fold_aucs):.4f}")
print(f"  Seuil Youden moyen   : {threshold:.3f}")
print(f"  AP                   : {ap:.4f}")
print(f"  Brier Score          : {brier:.4f}")
print(f"  F1                   : {f1:.4f}")

# Entraînement final sur toutes les données
print("\nEntraînement final (toutes données)...")
final_pipeline = base_pipe
final_pipeline.fit(X, y)

# Métadonnées au format attendu par la plateforme
metadata = {
    'feature_keys': feature_keys,
    'threshold': threshold,
    'class_distribution': {0: int((y == 0).sum()), 1: int((y == 1).sum())},
    'metrics': {
        'auc': round(auc_cv, 4),
        'pr_auc': round(ap, 4),
        'brier': round(brier, 4),
        'f1': round(f1, 4),
        'n_train': int(len(y) * (1 - 1/N_FOLDS)),
        'n_test': int(len(y) / N_FOLDS),
    },
}

# Sauvegarde
joblib.dump(final_pipeline, 'mortalite_svm.joblib', compress=3)
joblib.dump(metadata, 'mortalite_svm_features.joblib', compress=3)
print(f"\n  mortalite_svm.joblib sauvegardé")
print(f"  mortalite_svm_features.joblib sauvegardé")

print(f"""
=== Étapes suivantes ===
1. Copier les fichiers dans Docker :
   docker cp mortalite_svm.joblib medical_backend:/app/predictions/models/mortalite_svm.joblib
   docker cp mortalite_svm_features.joblib medical_backend:/app/predictions/models/mortalite_svm_features.joblib

2. Redémarrer le backend :
   docker restart medical_backend

AUC obtenu : {auc_cv:.4f}
""")
