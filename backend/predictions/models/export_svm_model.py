#!/usr/bin/env python
# =============================================================================
# EXPORT DU MODÈLE SVM LINÉAIRE ENTRAÎNÉ
# Génère svm_linear_hd478.pkl à partir du script ML complet
# =============================================================================

import pandas as pd
import numpy as np
import joblib
from pathlib import Path

# Imports ML (même que le script original)
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import PowerTransformer
from sklearn.impute import KNNImputer
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.metrics import roc_auc_score, roc_curve

# Configuration
FICHIER_DONNEES = 'Base_HD_478_v4_finale.xlsx'
FEUILLE = 'Base_HD_478_v4'
RANDOM_STATE = 42

print("=" * 65)
print("  EXPORT DU MEILLEUR MODÈLE — SVM LINÉAIRE")
print("=" * 65)

# ── Chargement des données ──────────────────────────────────────────────
print("\n📂 Chargement des données...")
df = pd.read_excel(FICHIER_DONNEES, sheet_name=FEUILLE)

# Variable cible
df['deces_1an'] = (
    (df['deces'] == 1) &
    (df['delai_jusquau_deces_jours'] <= 365)
).astype(int)

y = df['deces_1an'].reset_index(drop=True)

# ── Sélection des 32 features ───────────────────────────────────────────
print("📊 Sélection des 32 features...")

FEATS_CLINIQUES = [
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
]

X = df[FEATS_CLINIQUES].apply(pd.to_numeric, errors='coerce')

# Features d'interaction
X['age_x_charlson'] = df['age_annees'] * df['Charlson']
X['dyspnee_x_oedeme'] = df['dyspnee'].fillna(0) * df['oedemes_surcharge'].fillna(0)
X['sodium_lt130'] = (df['sodium_basal'] < 130).astype(float)
X['charlson_x_hosp'] = df['Charlson'] * df['nombre_hospitalisations'].fillna(0)
X['hypert_x_cardio'] = df['hypertension'].fillna(0) * df['cardiopathie'].fillna(0)
X['albumine_x_hosp'] = df['albumine_basale'] * df['nombre_hospitalisations'].fillna(0)
X['albumine_lt35'] = (df['albumine_basale'] < 35).astype(float)
X['age_x_cardio'] = df['age_annees'] * df['cardiopathie'].fillna(0)

X = X.reset_index(drop=True)

print(f"  Total features: {X.shape[1]} (24 cliniques + 8 interactions)")

# ── Pipeline étanche ────────────────────────────────────────────────────
print("\n🔧 Création du pipeline étanche...")

def make_pipe(clf):
    return Pipeline([
        ('imputer', KNNImputer(n_neighbors=3)),
        ('transformer', PowerTransformer(method='yeo-johnson')),
        ('clf', clf)
    ])

# ── Entraînement du SVM sur données complètes ────────────────────────────
print("\n🤖 Entraînement du SVM Linéaire sur données complètes...")

best_pipe = make_pipe(
    SVC(
        C=0.01,
        kernel='linear',
        class_weight='balanced',
        probability=True,
        random_state=RANDOM_STATE
    )
)

best_pipe.fit(X, y)

# Test rapide
proba = best_pipe.predict_proba(X)[:, 1]
auc_full = roc_auc_score(y, proba)
print(f"  AUC sur données complètes: {auc_full:.4f}")

# ── Sauvegarde du modèle ────────────────────────────────────────────────
print("\n💾 Sauvegarde du modèle...")

output_path = Path(__file__).parent / 'svm_linear_hd478.pkl'
joblib.dump(best_pipe, output_path)

print(f"  ✅ Modèle sauvegardé: {output_path}")

# ── Metadata ────────────────────────────────────────────────────────────
metadata = {
    'model_name': 'SVM Linéaire',
    'prediction_type': 'mortalite_1an',
    'n_features': X.shape[1],
    'n_patients_train': len(X),
    'features': list(X.columns),
    'random_state': RANDOM_STATE,
    'auc_full_data': float(auc_full),
    'algorithm': 'SVC(C=0.01, kernel=linear, class_weight=balanced)',
    'pipeline': ['KNNImputer(k=3)', 'PowerTransformer(yeo-johnson)', 'SVC'],
}

print("\n📋 Metadata:")
for key, val in metadata.items():
    if isinstance(val, list) and len(val) > 10:
        print(f"  {key}: {len(val)} features")
    else:
        print(f"  {key}: {val}")

print("\n" + "=" * 65)
print("  ✅ EXPORT TERMINÉ")
print("=" * 65)
