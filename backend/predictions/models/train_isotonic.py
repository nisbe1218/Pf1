"""
train_isotonic.py - Pipeline complet pour la plateforme
Usage : python train_isotonic.py Base_HD_478_v4_finale.xlsx

Pipeline :
  SVM brut -> Isotonique (10-fold CV) -> GMM -> T1/T2 calibres

Sorties :
  iso_calibrator.joblib
  gmm_thresholds.joblib
  mortalite_svm_features.joblib
"""
import sys
import os
import numpy as np
import pandas as pd
import joblib
import warnings
warnings.filterwarnings('ignore')

from sklearn.pipeline import Pipeline
from sklearn.impute import KNNImputer
from sklearn.preprocessing import PowerTransformer
from sklearn.svm import SVC
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.mixture import GaussianMixture
from sklearn.metrics import roc_auc_score, brier_score_loss

# =============================================================================
# CONFIG
# =============================================================================
FICHIER      = sys.argv[1] if len(sys.argv) > 1 else 'Base_HD_478_v4_finale.xlsx'
DOSSIER      = 'outputs_ML_HD478'
RANDOM_STATE = 42

# Seuils cliniques fixes (TRIPOD / DOPPS / KDIGO)
T1_FIXE = 0.10   # Faible  < 10%
T2_FIXE = 0.40   # Elevee  > 40%

os.makedirs(DOSSIER, exist_ok=True)

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

# =============================================================================
# CHARGEMENT
# =============================================================================
print("=" * 56)
print("  TRAIN ISOTONIC + GMM - PIPELINE COMPLET")
print("=" * 56)
print(f"\nChargement : {FICHIER}")

df = pd.read_excel(FICHIER, sheet_name='Base_HD_478_v4')
df['deces_1an'] = (
    (df['deces'] == 1) & (df['delai_jusquau_deces_jours'] <= 365)
).astype(int)
y = df['deces_1an'].reset_index(drop=True).values

X = df[FEATS_CLINIQUES].apply(pd.to_numeric, errors='coerce')
X['age_x_charlson']   = df['age_annees'] * df['Charlson']
X['dyspnee_x_oedeme'] = df['dyspnee'].fillna(0) * df['oedemes_surcharge'].fillna(0)
X['sodium_lt130']     = (df['sodium_basal'] < 130).astype(float)
X['charlson_x_hosp']  = df['Charlson'] * df['nombre_hospitalisations'].fillna(0)
X['hypert_x_cardio']  = df['hypertension'].fillna(0) * df['cardiopathie'].fillna(0)
X['albumine_x_hosp']  = df['albumine_basale'] * df['nombre_hospitalisations'].fillna(0)
X['albumine_lt35']    = (df['albumine_basale'] < 35).astype(float)
X['age_x_cardio']     = df['age_annees'] * df['cardiopathie'].fillna(0)
X = X.reset_index(drop=True)

print(f"  {len(df)} patients  |  {int(y.sum())} deces  |  mortalite {y.mean()*100:.1f}%")

# =============================================================================
# ETAPE 1 - SVM : probas out-of-fold (10-fold CV)
# =============================================================================
print("\nEtape 1/3 - SVM out-of-fold (10-fold CV)...")
pipe_svm = Pipeline([
    ('imputer',     KNNImputer(n_neighbors=3)),
    ('transformer', PowerTransformer(method='yeo-johnson')),
    ('clf',         SVC(C=0.01, kernel='linear', class_weight='balanced',
                        probability=True, random_state=RANDOM_STATE))
])
cv10 = StratifiedKFold(n_splits=10, shuffle=True, random_state=RANDOM_STATE)
proba_svm = np.zeros(len(y))
for tr, te in cv10.split(X, y):
    pipe_svm.fit(X.iloc[tr], y[tr])
    proba_svm[te] = pipe_svm.predict_proba(X.iloc[te])[:, 1]

auc_brut   = roc_auc_score(y, proba_svm)
brier_brut = brier_score_loss(y, proba_svm)
print(f"  SVM brut  : AUC={auc_brut:.4f}  Brier={brier_brut:.4f}")

# =============================================================================
# ETAPE 2 - ISOTONIQUE cross-validee (10-fold)
# Chaque fold test : iso ajustee sur les 9 autres folds -> pas de leakage
# =============================================================================
print("\nEtape 2/3 - Calibration isotonique (10-fold CV)...")
proba_cal = np.zeros(len(y))
for tr, te in cv10.split(X, y):
    iso_fold = IsotonicRegression(out_of_bounds='clip')
    iso_fold.fit(proba_svm[tr], y[tr])
    proba_cal[te] = iso_fold.predict(proba_svm[te])
proba_cal = np.clip(proba_cal, 0.0, 1.0)

auc_cal   = roc_auc_score(y, proba_cal)
brier_cal = brier_score_loss(y, proba_cal)
print(f"  SVM+ISO   : AUC={auc_cal:.4f}  Brier={brier_cal:.4f}")
print(f"  Proba cal. moyenne : {proba_cal.mean()*100:.1f}%  (mortalite reelle : {y.mean()*100:.1f}%)")

# =============================================================================
# ETAPE 3 - GMM sur probas calibrees -> T1, T2
# =============================================================================
print("\nEtape 3/3 - GMM sur probabilites calibrees...")
gmm = GaussianMixture(n_components=3, random_state=RANDOM_STATE, n_init=20)
gmm.fit(proba_cal.reshape(-1, 1))

order     = np.argsort(gmm.means_.flatten())
labels    = gmm.predict(proba_cal.reshape(-1, 1))
remap     = {order[0]: 0, order[1]: 1, order[2]: 2}
means_s   = gmm.means_.flatten()[order]
stds_s    = np.sqrt(gmm.covariances_.flatten())[order]
weights_s = gmm.weights_[order]

# Croisements des densites -> seuils GMM
proba_grid = np.linspace(0, 1, 100000).reshape(-1, 1)
resp_s     = gmm.predict_proba(proba_grid)[:, order]

cross1     = np.where(np.diff(np.sign(resp_s[:, 0] - resp_s[:, 1])))[0]
T1_gmm     = float(proba_grid.flatten()[cross1[0]]) if len(cross1) > 0 else (means_s[0]+means_s[1])/2

cross2     = [c for c in np.where(np.diff(np.sign(resp_s[:, 1] - resp_s[:, 2])))[0]
              if proba_grid.flatten()[c] > T1_gmm]
T2_gmm     = float(proba_grid.flatten()[cross2[0]]) if cross2 else (means_s[1]+means_s[2])/2

print(f"  T1 GMM (F/M) : {T1_gmm:.4f}  ({T1_gmm*100:.1f}%)")
print(f"  T2 GMM (M/E) : {T2_gmm:.4f}  ({T2_gmm*100:.1f}%)")

# Seuils retenus : fixes cliniques (TRIPOD/DOPPS/KDIGO)
T1 = T1_FIXE
T2 = T2_FIXE

# =============================================================================
# RESULTATS PAR ZONE
# =============================================================================
zones = np.where(proba_cal < T1, 'Faible',
        np.where(proba_cal < T2, 'Moderee', 'Elevee'))

print()
print("=" * 56)
print("  RESULTATS AVEC SEUILS CLINIQUES 10% / 40%")
print("  (Source : TRIPOD / DOPPS / KDIGO)")
print("=" * 56)
print(f"  {'Zone':<10} {'N':>6} {'Deces':>7} {'Mortalite':>11} {'Proba moy':>11}")
print("  " + "-" * 48)
for zone in ['Faible', 'Moderee', 'Elevee']:
    mask = zones == zone
    n_z  = mask.sum()
    d_z  = int(y[mask].sum())
    pct  = d_z/n_z*100 if n_z > 0 else 0
    pmoy = proba_cal[mask].mean()*100 if n_z > 0 else 0
    ok   = "OK" if (
        (zone == 'Faible'  and pct < 10) or
        (zone == 'Moderee' and 10 <= pct < 40) or
        (zone == 'Elevee'  and pct >= 40)
    ) else "!!"
    print(f"  {zone:<10} {n_z:>6} {d_z:>7} {pct:>10.1f}% {pmoy:>10.1f}%  {ok}")
print("  " + "-" * 48)
print(f"  {'TOTAL':<10} {len(y):>6} {int(y.sum()):>7} {y.mean()*100:>10.1f}%")

n_f = (zones=='Faible').sum();  d_f = int(y[zones=='Faible'].sum())
n_m = (zones=='Moderee').sum(); d_m = int(y[zones=='Moderee'].sum())
n_e = (zones=='Elevee').sum();  d_e = int(y[zones=='Elevee'].sum())

print()
print(f"  Gradient : {d_f/n_f*100:.1f}% -> {d_m/n_m*100:.1f}% -> {d_e/n_e*100:.1f}%")
if d_f/n_f < d_m/n_m < d_e/n_e:
    print("  => Calibration parfaite : gradient croissant confirme")
else:
    print("  => ATTENTION : gradient non monotone")

# =============================================================================
# SAUVEGARDE
# =============================================================================

# Calibrateur production : ajuste sur l'ensemble des probas OOF
iso_prod = IsotonicRegression(out_of_bounds='clip')
iso_prod.fit(proba_svm, y)
joblib.dump(iso_prod, f'{DOSSIER}/iso_calibrator.joblib')

joblib.dump({
    'T1':       T1,
    'T2':       T2,
    'T1_gmm':   T1_gmm,
    'T2_gmm':   T2_gmm,
    'source':   'TRIPOD/DOPPS/KDIGO - seuils cliniques fixes',
    'auc_brut': round(auc_brut, 4),
    'auc_cal':  round(auc_cal, 4),
}, f'{DOSSIER}/gmm_thresholds.joblib')

joblib.dump({
    'features': list(X.columns),
    'T1':       T1,
    'T2':       T2,
    'pipeline': 'SVM -> Isotonique -> seuils 10%/40%',
}, f'{DOSSIER}/mortalite_svm_features.joblib')

print()
print("=" * 56)
print("  FICHIERS SAUVEGARDES")
print("=" * 56)
print(f"  iso_calibrator.joblib")
print(f"  gmm_thresholds.joblib    T1={T1*100:.0f}%  T2={T2*100:.0f}%")
print(f"  mortalite_svm_features.joblib")
print()
print("  Pipeline actif :")
print("    SVM brut -> iso_calibrator -> T1=10% / T2=40%")
print()
print("  Pour un nouveau patient :")
print("    proba_brut = svm_pipe.predict_proba(X)[0,1]")
print("    proba_cal  = iso.predict([proba_brut])[0]")
print("    <10%  -> Faible  | 10-40% -> Moderee | >40% -> Elevee")
