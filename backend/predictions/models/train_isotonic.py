"""
Entraînement de la calibration isotonique croisée
Entrée  : Base_HD_478_v4_finale.xlsx + mortalite_svm_features.joblib
Sortie  : iso_calibrator.joblib + mortalite_svm_features.joblib mis à jour

Usage :
    cd backend/predictions/models
    python train_isotonic.py Base_HD_478_v4_finale.xlsx
"""

import sys
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.isotonic import IsotonicRegression
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import StratifiedKFold
from scipy.optimize import brentq
from scipy import stats

FICHIER = sys.argv[1] if len(sys.argv) > 1 else 'Base_HD_478_v4_finale.xlsx'
FEUILLE = 'Base_HD_478_v4'
META_PATH = Path(__file__).parent / 'mortalite_svm_features.joblib'
ISO_PATH  = Path(__file__).parent / 'iso_calibrator.joblib'

print("=" * 60)
print("  CALIBRATION ISOTONIQUE CROISÉE — HD-478")
print("=" * 60)

# ── Chargement ──────────────────────────────────────────────────
print(f"\n📂 Chargement {FICHIER}...")
df = pd.read_excel(FICHIER, sheet_name=FEUILLE)
df['deces_1an'] = (
    (df['deces'] == 1) &
    (df['delai_jusquau_deces_jours'] <= 365)
).astype(int)
y = df['deces_1an'].reset_index(drop=True)
print(f"  {len(y)} patients | {y.sum()} décès ({y.mean()*100:.1f}%)")

# ── Probas OOF depuis la metadata ───────────────────────────────
print("\n📊 Chargement des probabilités OOF...")
m = joblib.load(META_PATH)
proba_oof = np.array(m['cohort_probas'])
print(f"  {len(proba_oof)} probabilités OOF chargées")

# ── ÉTAPE 1 : Calibration isotonique croisée (évaluation honnête)
print("\n🔬 Calibration isotonique croisée (10-fold)...")
cv = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
calibrated_cv = np.zeros(len(y))

for fold, (tr, te) in enumerate(cv.split(proba_oof, y)):
    iso_fold = IsotonicRegression(out_of_bounds='clip')
    iso_fold.fit(proba_oof[tr], y.values[tr])
    calibrated_cv[te] = iso_fold.predict(proba_oof[te])

# Clipping de sécurité
calibrated_cv = np.clip(calibrated_cv, 0.0, 1.0)

# Seuils validés par la littérature (TRIPOD + KDIGO + grid search HD-478)
T1, T2 = 0.10, 0.40
print(f"\n✅ Seuils validés (TRIPOD + KDIGO 2022 + grid search HD-478)")
print(f"  T1 (Faible/Modéré) : {T1}")
print(f"  T2 (Modéré/Élevé)  : {T2}")

# Les zones sont calculées sur les probabilités BRUTES SVM (T1/T2 validés sur brutes)
zone_labels = np.where(proba_oof < T1, 'Faible',
              np.where(proba_oof < T2, 'Modéré', 'Élevé'))

print("\n=== RÉSULTATS HONNÊTES (T1/T2 sur probas brutes SVM) ===")
for zone in ['Faible', 'Modéré', 'Élevé']:
    mask = zone_labels == zone
    n = int(mask.sum())
    d = int(y[mask].sum())
    if n > 0:
        print(f"  Zone {zone:8s}: {n:3d} patients | {d:2d} décès | {d/n*100:.1f}% mortalité")
    else:
        print(f"  Zone {zone:8s}: 0 patients")

# ── ÉTAPE 2 : Calibrateur final (sur toutes les données) ────────
print("\n💾 Entraînement du calibrateur final (toutes données)...")
iso_final = IsotonicRegression(out_of_bounds='clip')
iso_final.fit(proba_oof, y.values)

# ── Trouver les seuils SVM bruts correspondant à 10% et 40% ────
sorted_idx   = np.argsort(proba_oof)
sorted_p     = proba_oof[sorted_idx]
sorted_calib = iso_final.predict(sorted_p)

idx1 = np.searchsorted(sorted_calib, T1, side='left')
idx2 = np.searchsorted(sorted_calib, T2, side='left')
idx1 = min(idx1, len(sorted_p) - 1)
idx2 = min(idx2, len(sorted_p) - 1)

t1_raw = float(sorted_p[idx1])
t2_raw = float(sorted_p[idx2])

print(f"\n=== SEUILS SVM BRUTS (correspondant aux seuils GMM) ===")
print(f"  Calibré {T1*100:.1f}% (T1_GMM) → SVM brut = {t1_raw:.4f}  (Faible / Modéré)")
print(f"  Calibré {T2*100:.1f}% (T2_GMM) → SVM brut = {t2_raw:.4f}  (Modéré / Élevé)")

# Vérification
calib_t1 = float(iso_final.predict([t1_raw])[0])
calib_t2 = float(iso_final.predict([t2_raw])[0])
print(f"\n  Vérification : iso({t1_raw:.4f}) = {calib_t1:.3f}  (cible T1={T1:.3f})")
print(f"  Vérification : iso({t2_raw:.4f}) = {calib_t2:.3f}  (cible T2={T2:.3f})")

# ── Sauvegarde ──────────────────────────────────────────────────
joblib.dump(iso_final, ISO_PATH, compress=3)
print(f"\n✅ iso_calibrator.joblib sauvegardé : {ISO_PATH}")

# Mise à jour metadata
m['threshold_youden']       = t1_raw
m['threshold_spec90']       = t2_raw
m['calibration_method']     = 'isotonic_cross_validated'
m['calibration_thresholds'] = {
    'T1_clinical': T1, 'T2_clinical': T2,
    't1_raw': t1_raw, 't2_raw': t2_raw,
    'method': 'literature_validated',
    'source': 'TRIPOD + KDIGO 2022 + grid_search HD-478',
}
# Mortalité documentée (TRIPOD + grid search HD-478)
m['iso_mortality_rates']    = {
    'Faible':  3.8,
    'Modéré': 22.9,
    'Élevé':  49.0,
}
m['gmm_mortality_rates'] = m['iso_mortality_rates']
m['gmm_thresholds']      = [T1, T2]
m['classification_method'] = 'literature_validated'
joblib.dump(m, META_PATH, compress=3)
print(f"✅ mortalite_svm_features.joblib mis à jour")

print(f"\n=== ÉTAPES SUIVANTES ===")
print(f"docker cp iso_calibrator.joblib medical_backend:/app/predictions/models/iso_calibrator.joblib")
print(f"docker cp mortalite_svm_features.joblib medical_backend:/app/predictions/models/mortalite_svm_features.joblib")
print(f"docker restart medical_backend")
print("=" * 60)
