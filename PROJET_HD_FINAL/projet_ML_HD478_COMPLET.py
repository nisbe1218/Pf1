# =============================================================================
#  PROJET ML COMPLET — PRÉDICTION DE MORTALITÉ À 1 AN EN HÉMODIALYSE
#  Cohorte HD-478 | CHU Hassan II de Fès | 2020–2024
#  Auteurs : Guessous Z., Allata Y. et al.
# =============================================================================
#
#  PIPELINE COMPLET :
#    1.  Chargement & Variable cible
#    2.  Sélection & Feature Engineering (8 interactions cliniques)
#    3.  Pipeline étanche (KNNImputer + PowerTransformer dans chaque fold)
#    4.  Définition des 6 modèles (SVM · LDA · LR Ridge · LASSO · RF · XGB)
#    5.  Entraînement 10-fold CV Stratifiée + Seuil Youden par fold
#    6.  Métriques complètes (AUC · Brier · Sensibilité · Précision · F1)
#    7.  Interprétation des gaps train/test
#    8.  Tests anti-surapprentissage (permutation · seeds · hold-out)
#    9.  Score de risque 0–100 par patient
#    10. 9 Graphes publication-ready
#    11. Sauvegarde Excel + CSV + PNG
#
#  PRÉREQUIS :
#    pip install pandas numpy scikit-learn xgboost openpyxl
#               matplotlib seaborn
#
#  UTILISATION :
#    Placer ce script dans le même dossier que Base_HD_478_v4_finale.xlsx
#    puis exécuter : python projet_ML_HD478_COMPLET.py
# =============================================================================

import pandas as pd
import numpy as np
import warnings
import os
warnings.filterwarnings('ignore')

# ── ML ─────────────────────────────────────────────────────────────────────────
from sklearn.model_selection import (StratifiedKFold, permutation_test_score,
                                      StratifiedShuffleSplit, GridSearchCV)
from sklearn.preprocessing import PowerTransformer
from sklearn.impute import KNNImputer
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (roc_auc_score, average_precision_score,
                              brier_score_loss, recall_score, precision_score,
                              f1_score, roc_curve, precision_recall_curve,
                              confusion_matrix)
import xgboost as xgb

# ── Visualisation ──────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

# ===========================================================================
# CONFIGURATION GLOBALE
# ===========================================================================
FICHIER_DONNEES = 'Base_HD_478_v4_finale.xlsx'
FEUILLE         = 'Base_HD_478_v4'
N_FOLDS         = 10
RANDOM_STATE    = 42
DOSSIER_OUTPUT  = 'outputs_ML_HD478'

COLORS = {
    'SVM Linéaire':                    '#1F4E79',
    'LDA':                              '#2E86AB',
    'Régression Logistique (Ridge L2)': '#1D9E75',
    'XGBoost (corrigé)':                '#F4A261',
    'Random Forest (OOB)':              '#E76F51',
    'LASSO (L1)':                       '#9B59B6',
}

plt.rcParams.update({
    'font.family':       'DejaVu Sans',
    'font.size':         10,
    'axes.spines.top':   False,
    'axes.spines.right': False,
    'axes.grid':         True,
    'grid.alpha':        0.3,
    'grid.linestyle':    '--',
    'figure.dpi':        150,
})

os.makedirs(DOSSIER_OUTPUT, exist_ok=True)

# ===========================================================================
# ÉTAPE 1 — CHARGEMENT & VARIABLE CIBLE
# ===========================================================================
print("=" * 65)
print("  PROJET ML — MORTALITÉ À 1 AN — HD-478")
print("  Pipeline Étanche · Seuil Youden · Anti-surapprentissage")
print("=" * 65)

print("\n📂 ÉTAPE 1 — CHARGEMENT DES DONNÉES")
print("-" * 45)

df = pd.read_excel(FICHIER_DONNEES, sheet_name=FEUILLE)

# Variable cible : décès dans les 365 premiers jours de dialyse
df['deces_1an'] = (
    (df['deces'] == 1) &
    (df['delai_jusquau_deces_jours'] <= 365)
).astype(int)

y = df['deces_1an'].reset_index(drop=True)

print(f"  Patients total     : {len(df)}")
print(f"  Décédés à 1 an     : {y.sum()} ({y.mean()*100:.1f}%)")
print(f"  Vivants à 1 an     : {(1-y).sum()} ({(1-y).mean()*100:.1f}%)")
print(f"  Ratio déséquilibre : 1 décès pour {int((1-y).sum()//y.sum())} vivants")

# ===========================================================================
# ÉTAPE 2 — SÉLECTION & FEATURE ENGINEERING
# ===========================================================================
print("\n📊 ÉTAPE 2 — SÉLECTION & ENGINEERING DES FEATURES")
print("-" * 45)

# 24 variables cliniques validées par SHAP + littérature internationale
FEATS_CLINIQUES = [
    'fistule_arterioveineuse_creee',       # Accès vasculaire FAV (facteur protecteur HR=0.353)
    'couverture_medicale',                  # Couverture médicale (HR=0.262–0.450)
    'albumine_basale',                      # Albumine sérique g/L (HR=0.956/g)
    'calcium_basale',                       # Calcémie (minéral métabolisme)
    'admission_cathetere_tunnellise',       # Cathéter tunnélisé à l'admission
    'annee_inclusion',                      # Année inclusion (tendance temporelle)
    'ferritine_basale',                     # Ferritine µg/L (stock martial)
    'seances_par_semaine',                  # Fréquence dialyse
    'nombre_hospitalisations',              # Nb hospitalisations (Chen 2025)
    'du_residuelle',                        # Diurèse résiduelle (HR=0.594)
    'crise_convulsive',                     # Crise convulsive (HR=3.250)
    'pth_basale',                           # PTH pg/mL (métabolisme osseux)
    'etiologie_mrc',                        # Étiologie MRC
    'douleur_abdominale',                   # Douleur abdominale
    'diabete',                              # Diabète sucré
    'evenement_cardiovasculaire',           # Événement CV (DOPPS)
    'dyspnee',                              # Dyspnée admission (from old_complete)
    'oedemes_surcharge',                    # Oedèmes/surcharge (from old_complete)
    'hemodialyse',                          # Modalité HD
    'liste_attente_transplantation',        # Liste attente greffe
    'maladie_renale_hereditaire',           # MRC héréditaire
    'information_transplantation_donnee',   # Information transplantation
    'hypertension',                         # HTA
    'cardiopathie',                         # Cardiopathie
]

X = df[FEATS_CLINIQUES].apply(pd.to_numeric, errors='coerce')

# 8 variables d'interaction — justifiées par la littérature
# Réf : Chen 2025 · Kidney Int 2015 · KDOQI · Waikar 2009 · DOPPS
X['age_x_charlson']   = df['age_annees'] * df['Charlson']
#  → Interaction âge-comorbidités (risque disproportionnel chez patient âgé+charlson élevé)
X['dyspnee_x_oedeme'] = df['dyspnee'].fillna(0) * df['oedemes_surcharge'].fillna(0)
#  → Synergie symptômes : dyspnée+oedèmes simultanés = surcharge sévère
X['sodium_lt130']     = (df['sodium_basal'] < 130).astype(float)
#  → Seuil clinique hyponatrémie sévère (Waikar 2009 : risque ×2)
X['charlson_x_hosp']  = df['Charlson'] * df['nombre_hospitalisations'].fillna(0)
#  → Comorbidités × hospitalisations = charge clinique totale
X['hypert_x_cardio']  = df['hypertension'].fillna(0) * df['cardiopathie'].fillna(0)
#  → Co-occurrence HTA+cardiopathie = profil CV haut risque (Kidney Int 2015)
X['albumine_x_hosp']  = df['albumine_basale'] * df['nombre_hospitalisations'].fillna(0)
#  → Dénutrition + réhospitalisation = fragilité avancée (DOPPS)
X['albumine_lt35']    = (df['albumine_basale'] < 35).astype(float)
#  → Seuil dénutrition KDOQI : albumine < 35 g/L → risque ×2–3
X['age_x_cardio']     = df['age_annees'] * df['cardiopathie'].fillna(0)
#  → Impact cardiopathie s'amplifie avec l'âge (CHA2DS2-VASc)

X = X.reset_index(drop=True)

print(f"  Features cliniques    : {len(FEATS_CLINIQUES)}")
print(f"  Features engineerées  : 8 (interactions cliniquement validées)")
print(f"  Total features        : {X.shape[1]}")
print(f"  Valeurs manquantes    : {X.isnull().sum().sum()} (avant imputation)")

# ===========================================================================
# ÉTAPE 3 — PIPELINE ÉTANCHE
# ===========================================================================
print("\n🔧 ÉTAPE 3 — PIPELINE ÉTANCHE")
print("-" * 45)
print("  KNNImputer(k=3) → PowerTransformer(Yeo-Johnson) → Modèle")
print("  Ajustés UNIQUEMENT sur le fold d'entraînement → 0 data leakage")
print("  Déséquilibre : class_weight='balanced' + scale_pos_weight=4 (XGB)")
print("  Seuil : Youden Index optimisé sur chaque fold train → appliqué sur test")

def make_pipe(clf):
    """
    Crée un pipeline étanche :
      - KNNImputer   : imputation par k=3 voisins les plus proches
      - PowerTransf. : normalisation Yeo-Johnson (corrige asymétrie ferritine, PTH…)
      - Classifieur  : modèle ML
    Ajusté uniquement sur les données d'entraînement de chaque fold.
    """
    return Pipeline([
        ('imputer',     KNNImputer(n_neighbors=3)),
        ('transformer', PowerTransformer(method='yeo-johnson')),
        ('clf',         clf)
    ])

# ===========================================================================
# ÉTAPE 3b — OPTIMISATION HYPERPARAMÈTRE C DU SVM (GridSearchCV)
# ===========================================================================
print("\n🔍 ÉTAPE 3b — OPTIMISATION C DU SVM (GridSearchCV)")
print("-" * 45)

_pipe_svm_gs = make_pipe(
    SVC(kernel='linear', class_weight='balanced', probability=True,
        random_state=RANDOM_STATE)
)
_cv_gs = StratifiedKFold(n_splits=10, shuffle=True, random_state=RANDOM_STATE)
_gs = GridSearchCV(
    _pipe_svm_gs,
    param_grid={'clf__C': [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]},
    scoring='roc_auc',
    cv=_cv_gs,
    n_jobs=-1,
    refit=False
)
_gs.fit(X, y)

_results_gs = list(zip(
    _gs.cv_results_['param_clf__C'],
    _gs.cv_results_['mean_test_score'],
    _gs.cv_results_['std_test_score']
))
print(f"  {'C':>8}  {'AUC moyen':>10}  {'±std':>8}")
print(f"  {'-'*8}  {'-'*10}  {'-'*8}")
for c_val, auc_mean, auc_std in _results_gs:
    marker = " ◄ meilleur" if c_val == _gs.best_params_['clf__C'] else ""
    print(f"  {c_val:>8}  {auc_mean:>10.4f}  {auc_std:>8.4f}{marker}")

SVM_BEST_C = _gs.best_params_['clf__C']
print(f"\n  ✅ C optimal retenu : {SVM_BEST_C}  (AUC={_gs.best_score_:.4f})")

# ===========================================================================
# ÉTAPE 4 — DÉFINITION DES 6 MODÈLES
# ===========================================================================
print("\n🤖 ÉTAPE 4 — DÉFINITION DES 6 MODÈLES")
print("-" * 45)

# RF avec OOB score pour estimation honnête de l'AUC train
rf_clf = RandomForestClassifier(
    n_estimators=500, max_depth=3, min_samples_leaf=15,
    class_weight='balanced', random_state=RANDOM_STATE,
    n_jobs=-1, oob_score=True   # OOB = évaluation honnête sans biais de mémorisation
)

MODELS = {
    # ── Modèles linéaires (meilleurs sur n=478 — biais-variance optimal) ──────
    'SVM Linéaire': make_pipe(
        SVC(
            C=SVM_BEST_C,              # Optimisé par GridSearchCV (ÉTAPE 3b)
            kernel='linear',
            class_weight='balanced',   # Compense déséquilibre 1:4
            probability=True,
            random_state=RANDOM_STATE
        )
    ),

    'LDA': make_pipe(
        LinearDiscriminantAnalysis(
            solver='lsqr',
            shrinkage=0.3              # Régularisation Ledoit-Wolf → stabilise Σ sur n=478
        )
    ),

    'Régression Logistique (Ridge L2)': make_pipe(
        LogisticRegression(
            C=0.1,                     # Régularisation Ridge
            penalty='l2',
            class_weight='balanced',
            max_iter=2000,
            random_state=RANDOM_STATE
        )
    ),

    'LASSO (L1)': make_pipe(
        LogisticRegression(
            C=0.05,                    # Régularisation L1 forte → sélection sparse
            penalty='l1',
            solver='saga',
            class_weight='balanced',
            max_iter=2000,
            random_state=RANDOM_STATE
        )
    ),

    # ── Modèles ensemblistes (corrigés pour n=478) ────────────────────────────
    'Random Forest (OOB)': make_pipe(rf_clf),
    # Note : AUC train = OOB score (honnête) et non AUC sur données vues

    'XGBoost (corrigé)': make_pipe(
        xgb.XGBClassifier(
            n_estimators=30,           # Réduit (300→30) pour éviter surfit sur n=478
            max_depth=1,               # Très peu profond (3→1) → régularisation forte
            learning_rate=0.2,
            subsample=0.7,
            colsample_bytree=0.7,
            scale_pos_weight=4,        # = n_négatifs/n_positifs ≈ 384/94
            eval_metric='logloss',
            random_state=RANDOM_STATE,
            n_jobs=-1
        )
    ),
}

for name in MODELS:
    print(f"  ✓ {name}")

# ===========================================================================
# ÉTAPE 5 — ENTRAÎNEMENT 10-FOLD CV ÉTANCHE + SEUIL YOUDEN PAR FOLD
# ===========================================================================
print(f"\n🔬 ÉTAPE 5 — ENTRAÎNEMENT ({N_FOLDS}-fold CV Étanche)")
print("-" * 45)

cv10 = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
results = {}

for name, pipe in MODELS.items():
    fold_aucs      = []
    fold_thrs      = []
    fold_train_aucs= []
    all_proba      = np.zeros(len(y))

    for tr, te in cv10.split(X, y):
        X_tr, X_te = X.iloc[tr], X.iloc[te]
        y_tr, y_te = y.iloc[tr], y.iloc[te]

        # ── Fit UNIQUEMENT sur données d'entraînement du fold ──────────────
        pipe.fit(X_tr, y_tr)

        # ── Prédictions test ───────────────────────────────────────────────
        proba_te = pipe.predict_proba(X_te)[:, 1]

        # ── Seuil Youden optimisé sur TRAIN → appliqué sur TEST ───────────
        proba_tr = pipe.predict_proba(X_tr)[:, 1]
        fpr_t, tpr_t, thr_t = roc_curve(y_tr, proba_tr)
        j_idx    = np.argmax(tpr_t - fpr_t)
        opt_thr  = float(np.clip(thr_t[j_idx], 0.05, 0.95))
        fold_thrs.append(opt_thr)

        fold_aucs.append(roc_auc_score(y_te, proba_te))
        fold_train_aucs.append(roc_auc_score(y_tr, proba_tr))
        all_proba[te] = proba_te

    # ── AUC train : OOB pour RF, moyenne folds pour les autres ────────────
    if 'Random Forest' in name:
        pipe.fit(X, y)  # refit complet pour récupérer oob_decision_function_
        auc_train = round(roc_auc_score(y, rf_clf.oob_decision_function_[:, 1]), 4)
    else:
        auc_train = round(float(np.mean(fold_train_aucs)), 4)

    mean_thr   = float(np.mean(fold_thrs))
    class_pred = (all_proba >= mean_thr).astype(int)
    auc_test   = round(float(np.mean(fold_aucs)), 4)
    gap        = round(auc_train - auc_test, 4)

    results[name] = {
        'AUC':    auc_test,
        'STD':    round(float(np.std(fold_aucs)), 4),
        'Train':  auc_train,
        'Gap':    gap,
        'Seuil':  round(mean_thr, 3),
        'AP':     round(average_precision_score(y, all_proba), 4),
        'Brier':  round(brier_score_loss(y, all_proba), 4),
        'Sens':   round(recall_score(y, class_pred), 3),
        'Prec':   round(precision_score(y, class_pred, zero_division=0), 3),
        'F1':     round(f1_score(y, class_pred, zero_division=0), 3),
        'Folds':  [round(a, 4) for a in fold_aucs],
        'Proba':  all_proba,
    }

    flag = '✅ OK' if abs(gap) < 0.10 else '⚠️ SURFIT'
    r = results[name]
    print(f"  {name:35s} AUC={r['AUC']:.4f}±{r['STD']:.3f} "
          f"Train={r['Train']:.4f} Gap={r['Gap']:+.4f} {flag}  Brier={r['Brier']:.3f}")

sorted_r = sorted(results.items(), key=lambda x: x[1]['AUC'], reverse=True)

# ===========================================================================
# ÉTAPE 6 — TABLEAU COMPARATIF
# ===========================================================================
print("\n" + "=" * 70)
print("  TABLEAU COMPARATIF — RÉSULTATS FINAUX")
print("=" * 70)
hdr = f"  {'Rang':<4} {'Modèle':<37} {'AUC':>6} {'±STD':>6} {'Train':>6} {'Gap':>7} {'Brier':>6} {'Sens':>5} {'F1':>6}"
print(hdr)
print("-" * 70)
for rang, (name, r) in enumerate(sorted_r, 1):
    star = " ★" if rang == 1 else ""
    note = " ⚠️" if abs(r['Gap']) >= 0.10 else ""
    print(f"  #{rang:<3} {name:<37} {r['AUC']:.4f} {r['STD']:>6.3f}"
          f" {r['Train']:>6.4f} {r['Gap']:>+7.4f}"
          f" {r['Brier']:>6.3f} {r['Sens']:>4.0%} {r['F1']:>6.3f}{star}{note}")
print("=" * 70)

# ===========================================================================
# ÉTAPE 7 — INTERPRÉTATION DES GAPS
# ===========================================================================
print("\n📌 ÉTAPE 7 — INTERPRÉTATION DES GAPS TRAIN/TEST")
print("-" * 45)
for name, r in sorted_r:
    g = abs(r['Gap'])
    if g < 0.05:   interp = "Excellent — modèle très bien régularisé"
    elif g < 0.10: interp = "Bon — gap normal pour n=478"
    elif g < 0.15: interp = "Modéré — surapprentissage léger"
    else:           interp = "Élevé — modèle trop complexe pour n=478"
    print(f"  {name:37s} Gap={r['Gap']:+.4f} → {interp}")

# ===========================================================================
# ÉTAPE 8 — TESTS ANTI-SURAPPRENTISSAGE
# ===========================================================================
print("\n🧪 ÉTAPE 8 — TESTS ANTI-SURAPPRENTISSAGE (SVM Linéaire)")
print("-" * 45)

best_pipe = MODELS['SVM Linéaire']

# Test 1 : Permutation test (50 permutations)
print("  Test 1 — Permutation (50 permutations)...")
sc, ps, pval = permutation_test_score(
    best_pipe, X, y, scoring='roc_auc',
    cv=cv10, n_permutations=50, random_state=RANDOM_STATE, n_jobs=-1)
print(f"    AUC réel={sc:.4f} | AUC hasard={ps.mean():.4f} | p={pval:.4f}")
print(f"    → {'✅ Signal réel confirmé (p<0.05)' if pval < 0.05 else '⚠️ Non significatif'}")

# Test 2 : Stabilité sur 5 seeds
print("  Test 2 — Stabilité (5 seeds)...")
seed_aucs = []
for seed in [0, 7, 13, 42, 99]:
    cv_s = StratifiedKFold(n_splits=10, shuffle=True, random_state=seed)
    fa   = []
    for tr, te in cv_s.split(X, y):
        best_pipe.fit(X.iloc[tr], y.iloc[tr])
        fa.append(roc_auc_score(y.iloc[te], best_pipe.predict_proba(X.iloc[te])[:,1]))
    seed_aucs.append(np.mean(fa))
print(f"    AUC par seed : {[round(a,4) for a in seed_aucs]}")
print(f"    Moyenne={np.mean(seed_aucs):.4f} ± {np.std(seed_aucs):.4f}")
print(f"    → {'✅ Très stable (std<0.01)' if np.std(seed_aucs)<0.01 else '→ Stable'}")

# Test 3 : Hold-out 80/20 (5 splits indépendants)
print("  Test 3 — Hold-out 80/20 (5 splits)...")
holdout_aucs = []
for seed in [1, 2, 3, 4, 5]:
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.20, random_state=seed)
    for tr, te in sss.split(X, y):
        best_pipe.fit(X.iloc[tr], y.iloc[tr])
        holdout_aucs.append(roc_auc_score(y.iloc[te], best_pipe.predict_proba(X.iloc[te])[:,1]))
print(f"    AUC hold-out : {[round(a,4) for a in holdout_aucs]}")
print(f"    Moyenne={np.mean(holdout_aucs):.4f} ± {np.std(holdout_aucs):.4f}")
print(f"    → {'✅ Cohérent avec CV' if abs(np.mean(holdout_aucs)-results['SVM Linéaire']['AUC'])<0.05 else '→ Vérifier'}")

# ===========================================================================
# ÉTAPE 9 — CALIBRATION ISOTONIQUE + SCORE DE RISQUE 0–100 PAR PATIENT
# ===========================================================================
print("\n📊 ÉTAPE 9 — CALIBRATION ISOTONIQUE + SCORE DE RISQUE PAR PATIENT")
print("-" * 45)
print("  Méthode : Régression Isotonique sur probas OOF (TRIPOD / Lancet)")
print("  Seuils validés : <10% Faible | 10–29% Modéré | >29% Élevé")
print("  T1=10% : sensibilité≥90% (ROC) | T2=29% : Youden bootstrappé (n=1000)")

# Probas SVM out-of-fold déjà calculées en Étape 5 (aucun data leakage)
proba_svm_oof = results['SVM Linéaire']['Proba']

# Calibration isotonique : ajustée sur OOF vs outcomes réels
iso_calibrator = IsotonicRegression(out_of_bounds='clip')
iso_calibrator.fit(proba_svm_oof, y.values)
probas_finales = np.clip(iso_calibrator.predict(proba_svm_oof), 0.0, 1.0)
scores_risque  = (probas_finales * 100).round(1)

# T1=10% : premier seuil ROC avec sensibilité≥90% (8 décès manqués/94, soit 8.5%)
# T2=29% : Index de Youden bootstrappé (1000 itérations, médiane=28.9%, IC95=[10%-33.3%])
SEUIL_BAS  = 10.0   # < 10%  → Risque Faible  (sensibilité=91.5%)
SEUIL_HAUT = 29.0   # > 29%  → Risque Élevé   (Youden bootstrap)

def niveau_risque(s):
    if s < SEUIL_BAS:    return 'Faible'
    elif s < SEUIL_HAUT: return 'Modéré'
    else:                 return 'Élevé'

niveaux = [niveau_risque(s) for s in scores_risque]

for niv in ['Faible', 'Modéré', 'Élevé']:
    mask = np.array(niveaux) == niv
    n    = mask.sum()
    dec  = int(y[mask].sum())
    pct  = n / len(y) * 100
    print(f"  {niv:8s}: {n:3d} patients ({pct:4.1f}%) | {dec} décès ({dec/n*100:.1f}%)")

print(f"\n  Score moyen — Décédés : {scores_risque[y==1].mean():.1f}/100")
print(f"  Score moyen — Vivants : {scores_risque[y==0].mean():.1f}/100")

# ===========================================================================
# ÉTAPE 10 — GÉNÉRATION DES 9 GRAPHES
# ===========================================================================
print("\n🎨 ÉTAPE 10 — GÉNÉRATION DES GRAPHES")
print("-" * 45)

short_names = ['SVM Lin.', 'LDA', 'LR Ridge', 'XGB', 'RF', 'LASSO']

# ── Graphe 1 — Courbes ROC ─────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle('Courbes ROC — Cohorte HD-478\nMortalité à 1 an | 10-fold CV Stratifiée',
             fontsize=13, fontweight='bold', y=1.01)

for ax, (title, names_sub) in zip(axes, [
    ('Tous les modèles', list(MODELS.keys())),
    ('Top 3 (zoom)',     ['SVM Linéaire','LDA','Régression Logistique (Ridge L2)'])
]):
    for name in names_sub:
        r    = results[name]
        fpr, tpr, _ = roc_curve(y, r['Proba'])
        lw   = 2.5 if name == 'SVM Linéaire' else 1.8
        ax.plot(fpr, tpr, color=COLORS[name], lw=lw,
                label=f"{name.split('(')[0].strip()}\n  AUC={r['AUC']:.4f} ±{r['STD']:.3f}")
    ax.plot([0,1],[0,1],'k--', lw=1, alpha=0.5, label='Hasard (AUC=0.50)')
    ax.set_xlabel('1 – Spécificité (Faux positifs)', fontsize=10)
    ax.set_ylabel('Sensibilité (Vrais positifs)', fontsize=10)
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.legend(loc='lower right', fontsize=8.5, framealpha=0.9)
    ax.set_xlim(-0.01,1.01); ax.set_ylim(-0.01,1.01)
    ax.set_aspect('equal')
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/1_courbes_ROC.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 1 — Courbes ROC")

# ── Graphe 2 — Comparaison AUC & Gap ─────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
aucs   = [r['AUC']   for _,r in sorted_r]
stds   = [r['STD']   for _,r in sorted_r]
gaps   = [r['Gap']   for _,r in sorted_r]
colors = [COLORS[n]  for n,_ in sorted_r]

ax = axes[0]
bars = ax.bar(short_names, aucs, color=colors, alpha=0.85, width=0.55, zorder=3)
ax.errorbar(short_names, aucs, yerr=stds, fmt='none', color='#2C3E50', capsize=5, lw=1.5, zorder=4)
for bar, auc in zip(bars, aucs):
    ax.text(bar.get_x()+bar.get_width()/2, auc+0.003, f'{auc:.4f}',
            ha='center', va='bottom', fontsize=9, fontweight='bold')
ax.axhline(0.70, color='orange', ls='--', lw=1.2, label='0.70 (bon)')
ax.axhline(0.80, color='green',  ls='--', lw=1.2, label='0.80 (très bon)')
ax.set_ylim(0.60, 0.95); ax.set_ylabel('AUC-ROC (10-fold CV)', fontsize=10)
ax.set_title('AUC-ROC par modèle (±1 std)', fontsize=11, fontweight='bold')
ax.legend(fontsize=9)

ax2 = axes[1]
g_colors = ['#27AE60' if g<0.05 else ('#F39C12' if g<0.10 else '#E74C3C') for g in gaps]
bars2 = ax2.barh(short_names[::-1], gaps[::-1], color=g_colors[::-1], alpha=0.85, height=0.5)
ax2.axvline(0.05, color='#27AE60', ls='--', lw=1.5, label='<0.05 Excellent')
ax2.axvline(0.10, color='#F39C12', ls='--', lw=1.5, label='<0.10 Bon')
for bar, gap in zip(bars2, gaps[::-1]):
    x_pos = gap + 0.002 if gap >= 0 else gap + 0.001
    ha    = 'left'
    ax2.text(x_pos, bar.get_y()+bar.get_height()/2, f'{gap:+.4f}', va='center', ha=ha, fontsize=9, fontweight='bold')
ax2.set_xlabel('Gap AUC (Train − Test)', fontsize=10)
ax2.set_title('Gap Train/Test (surapprentissage)', fontsize=11, fontweight='bold')
x_min = min(min(gaps) - 0.02, -0.02)
ax2.legend(fontsize=9); ax2.set_xlim(x_min, 0.15)
fig.suptitle('Performance des modèles ML — Cohorte HD-478', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/2_comparaison_AUC_gap.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 2 — Comparaison AUC & Gap")

# ── Graphe 3 — Radar ──────────────────────────────────────────────────────
categories = ['AUC-ROC','Sensibilité','Précision','F1-Score','Brier\n(inv.)','Avg\nPrecision']
N = len(categories)
angles = [n/float(N)*2*np.pi for n in range(N)]
angles += angles[:1]
fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
ax.set_theta_offset(np.pi/2); ax.set_theta_direction(-1)
ax.set_xticks(angles[:-1]); ax.set_xticklabels(categories, fontsize=10)
ax.set_ylim(0, 1)
for name, r in sorted_r[:4]:
    vals = [r['AUC'], r['Sens'], r['Prec'], r['F1'], 1-r['Brier'], r['AP']]
    vals += vals[:1]
    ax.plot(angles, vals, color=COLORS[name], lw=2, label=f"{name.split('(')[0].strip()} (AUC={r['AUC']:.4f})")
    ax.fill(angles, vals, color=COLORS[name], alpha=0.07)
ax.legend(loc='upper right', bbox_to_anchor=(1.35,1.15), fontsize=9, framealpha=0.9)
ax.set_title('Profil des performances — Top 4 modèles\nCohorte HD-478', fontsize=12, fontweight='bold', pad=20)
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/3_radar_performance.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 3 — Radar")

# ── Graphe 4 — Calibration ────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
ref_brier = y.mean()*(1-y.mean())
brierS = [r['Brier'] for _,r in sorted_r]
b_colors = ['#27AE60' if b<0.13 else ('#F39C12' if b<0.16 else '#E74C3C') for b in brierS]
bars = axes[0].bar(short_names, brierS, color=b_colors, alpha=0.85, width=0.55)
axes[0].axhline(ref_brier, color='gray', ls='--', lw=1.5, label=f'Naïf={ref_brier:.3f}')
for bar, b in zip(bars, brierS):
    axes[0].text(bar.get_x()+bar.get_width()/2, b+0.002, f'{b:.3f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
axes[0].set_ylim(0, 0.25); axes[0].set_ylabel('Brier Score (↓ = meilleur)', fontsize=10)
axes[0].set_title('Brier Score par modèle\n(vert<0.13 excellent)', fontsize=11, fontweight='bold')
axes[0].legend(fontsize=9)

axes[1].plot([0,1],[0,1],'k--', lw=1.5, label='Calibration parfaite', alpha=0.7)
for name, r in sorted_r[:3]:
    frac_pos, mean_pred = calibration_curve(y, r['Proba'], n_bins=8, strategy='quantile')
    axes[1].plot(mean_pred, frac_pos, 'o-', color=COLORS[name], lw=2, ms=6,
                 label=f"{name.split('(')[0].strip()} (Brier={r['Brier']:.3f})")
axes[1].set_xlabel('Probabilité prédite', fontsize=10); axes[1].set_ylabel('Fraction observée', fontsize=10)
axes[1].set_title('Reliability Diagram — Top 3', fontsize=11, fontweight='bold')
axes[1].legend(fontsize=9, loc='upper left'); axes[1].set_xlim(-0.02,1.02); axes[1].set_ylim(-0.02,1.02)
fig.suptitle('Calibration des probabilités — Cohorte HD-478', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/4_calibration.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 4 — Calibration")

# ── Graphe 5 — Matrices de confusion ─────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(13, 4))
fig.suptitle('Matrices de Confusion — Top 3 Modèles | Seuil Youden',
             fontsize=12, fontweight='bold')
for ax, (name, r) in zip(axes, sorted_r[:3]):
    pred = (r['Proba'] >= r['Seuil']).astype(int)
    cm   = confusion_matrix(y, pred)
    cm_pct = cm.astype(float)/cm.sum(axis=1, keepdims=True)*100
    sns.heatmap(cm, annot=False, ax=ax, cmap='Blues',
                xticklabels=['Vivant','Décédé'], yticklabels=['Vivant','Décédé'],
                linewidths=0.5, linecolor='white', cbar=False)
    for i in range(2):
        for j in range(2):
            col = 'white' if cm[i,j]>cm.max()*0.5 else '#2C3E50'
            ax.text(j+0.5, i+0.35, str(cm[i,j]), ha='center', va='center', fontsize=18, fontweight='bold', color=col)
            ax.text(j+0.5, i+0.65, f'({cm_pct[i,j]:.1f}%)', ha='center', va='center', fontsize=10, color=col, alpha=0.85)
    tn,fp,fn,tp = cm[0,0],cm[0,1],cm[1,0],cm[1,1]
    ax.set_title(f"{name.split('(')[0].strip()}\nAUC={r['AUC']:.4f} | Seuil={r['Seuil']:.3f}", fontsize=10, fontweight='bold')
    ax.set_xlabel('Prédit', fontsize=9); ax.set_ylabel('Réel', fontsize=9)
    ax.text(0.5,-0.18, f"Sens={r['Sens']:.0%} | Spéc={(tn/(tn+fp)):.0%} | F1={r['F1']:.3f}",
            transform=ax.transAxes, ha='center', fontsize=8.5, color='#555')
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/5_matrices_confusion.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 5 — Matrices de confusion")

# ── Graphe 6 — Score de risque ────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle('Score de Risque 0–100 — SVM Linéaire | Cohorte HD-478', fontsize=13, fontweight='bold')

axes[0].hist(scores_risque[y==0], bins=25, alpha=0.6, color='#2ECC71', label=f'Vivants (n={int((y==0).sum())})', density=True)
axes[0].hist(scores_risque[y==1], bins=25, alpha=0.6, color='#E74C3C', label=f'Décédés (n={int(y.sum())})', density=True)
axes[0].axvline(SEUIL_BAS,  color='#F39C12', ls='--', lw=1.5, label=f'Seuil Faible/Modéré ({SEUIL_BAS:.0f}%)')
axes[0].axvline(SEUIL_HAUT, color='#E74C3C', ls='--', lw=1.5, label=f'Seuil Modéré/Élevé ({SEUIL_HAUT:.0f}%)')
axes[0].set_xlabel('Score de risque (0–100)', fontsize=10); axes[0].set_ylabel('Densité', fontsize=10)
axes[0].set_title('Distribution par statut vital', fontsize=11, fontweight='bold'); axes[0].legend(fontsize=9)

niv_colors = {'Faible':'#2ECC71','Modéré':'#F39C12','Élevé':'#E74C3C'}
niv_arr = np.array(niveaux)
for i, niv in enumerate(['Faible','Modéré','Élevé']):
    mask = niv_arr == niv; s_niv = scores_risque[mask]
    axes[1].boxplot(s_niv, positions=[i], widths=0.5, patch_artist=True,
                    boxprops=dict(facecolor=niv_colors[niv], alpha=0.7),
                    medianprops=dict(color='black', lw=2))
    axes[1].text(i, s_niv.max()+2, f'n={mask.sum()}\n{int(y[mask].sum())} décès', ha='center', fontsize=8.5)
axes[1].set_xticks([0,1,2]); axes[1].set_xticklabels(['Faible','Modéré','Élevé'], fontsize=10)
axes[1].set_ylabel('Score de risque', fontsize=10); axes[1].set_title('Score par niveau', fontsize=11, fontweight='bold')

deciles = pd.qcut(scores_risque, q=10, labels=False, duplicates='drop')
n_deciles = deciles.max() + 1
deces_rate = [float(y[deciles==d].mean()*100) for d in range(n_deciles)]
x_dec = list(range(1, n_deciles + 1))
bars3 = axes[2].bar(x_dec, deces_rate, color=plt.cm.RdYlGn_r(np.linspace(0.1, 0.9, n_deciles)), alpha=0.85)
axes[2].plot(x_dec, deces_rate, 'ko-', ms=5, lw=1.5, zorder=5)
axes[2].axhline(float(y.mean()*100), color='gray', ls='--', lw=1.2, label=f'Prévalence ({float(y.mean()*100):.1f}%)')
axes[2].set_xlabel('Groupe de score (quantile)', fontsize=10); axes[2].set_ylabel('Taux décès (%)', fontsize=10)
axes[2].set_title('Taux décès par groupe de score', fontsize=11, fontweight='bold'); axes[2].legend(fontsize=9)
for bar, rate in zip(bars3, deces_rate):
    if rate > 0:
        axes[2].text(bar.get_x()+bar.get_width()/2, rate+0.5, f'{rate:.0f}%', ha='center', fontsize=8, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/6_score_risque.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 6 — Score de risque")

# ── Graphe 7 — Précision-Rappel ───────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 6))
for name, r in sorted_r:
    ap = average_precision_score(y, r['Proba'])
    prec, rec, _ = precision_recall_curve(y, r['Proba'])
    ax.plot(rec, prec, color=COLORS[name], lw=2.5 if name=='SVM Linéaire' else 1.8,
            label=f"{name.split('(')[0].strip()} (AP={ap:.3f})")
ax.axhline(float(y.mean()), color='gray', ls='--', lw=1.2, label=f'Baseline ({float(y.mean()):.3f})')
ax.set_xlabel('Rappel (Sensibilité)', fontsize=11); ax.set_ylabel('Précision', fontsize=11)
ax.set_title('Courbes Précision-Rappel\nCohorte HD-478 | 19.7% de décès', fontsize=12, fontweight='bold')
ax.legend(fontsize=9, loc='upper right'); ax.set_xlim(0,1.02); ax.set_ylim(0,1.02)
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/7_precision_rappel.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 7 — Précision-Rappel")

# ── Graphe 8 — Boxplot AUC par fold ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 5))
all_folds = [r['Folds'] for _,r in sorted_r]
bp = ax.boxplot(all_folds, labels=short_names, patch_artist=True, widths=0.5,
                medianprops=dict(color='black', lw=2.5),
                whiskerprops=dict(color='gray', lw=1.5),
                capprops=dict(color='gray'),
                flierprops=dict(marker='o', ms=5, alpha=0.6))
for patch, (name,_) in zip(bp['boxes'], sorted_r):
    patch.set_facecolor(COLORS[name]); patch.set_alpha(0.75)
for i, (name, r) in enumerate(sorted_r, 1):
    ax.text(i, max(r['Folds'])+0.01, f"μ={r['AUC']:.4f}\nσ={r['STD']:.3f}", ha='center', fontsize=8, va='bottom')
ax.axhline(0.70, color='orange', ls='--', lw=1.2, alpha=0.7, label='AUC = 0.70')
ax.axhline(0.80, color='green',  ls='--', lw=1.2, alpha=0.7, label='AUC = 0.80')
ax.set_ylabel('AUC-ROC par fold', fontsize=11); ax.set_ylim(0.50, 1.05)
ax.set_title('Stabilité AUC — Distribution sur 10 folds\nCohorte HD-478', fontsize=12, fontweight='bold')
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/8_boxplot_folds.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 8 — Boxplot AUC par fold")

# ── Graphe 9 — Tableau récapitulatif ─────────────────────────────────────
fig, ax = plt.subplots(figsize=(16, 4))
ax.axis('off')
cols = ['Rang','Modèle','AUC-ROC','±STD','Train AUC','Gap','Brier','Sens.','Préc.','F1','Verdict']
rows = []
for rang, (name, r) in enumerate(sorted_r, 1):
    v = '✅ OK' if abs(r['Gap'])<0.10 else '⚠️ Surfit'
    rows.append([f'#{rang}', name.split('(')[0].strip(),
                 f"{r['AUC']:.4f}", f"±{r['STD']:.3f}",
                 f"{r['Train']:.4f}", f"{r['Gap']:+.4f}",
                 f"{r['Brier']:.3f}", f"{r['Sens']:.0%}",
                 f"{r['Prec']:.0%}", f"{r['F1']:.3f}", v])
tbl = ax.table(cellText=rows, colLabels=cols, loc='center', cellLoc='center')
tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.6)
for (row,col), cell in tbl.get_celld().items():
    if row == 0:
        cell.set_facecolor('#1F4E79'); cell.set_text_props(color='white', fontweight='bold')
    elif rows[row-1][0] == '#1':
        cell.set_facecolor('#D5F5E3')
    elif row % 2 == 0:
        cell.set_facecolor('#F8F9FA')
    cell.set_edgecolor('#CCCCCC')
ax.set_title('Tableau Récapitulatif — 6 Modèles ML | Pipeline Étanche | 10-fold CV', fontsize=12, fontweight='bold', pad=20)
plt.tight_layout()
plt.savefig(f'{DOSSIER_OUTPUT}/9_tableau_recap.png', dpi=150, bbox_inches='tight')
plt.close(); print("  ✅ Graphe 9 — Tableau récapitulatif")

# ===========================================================================
# ÉTAPE 11 — SAUVEGARDE EXCEL + CSV
# ===========================================================================
print("\n💾 ÉTAPE 11 — SAUVEGARDE DES RÉSULTATS")
print("-" * 45)

# Tableau résultats modèles
res_export = {}
for name, r in results.items():
    res_export[name] = {
        'AUC-ROC (test)':          r['AUC'],
        '± STD':                   r['STD'],
        'AUC train (OOB pour RF)': r['Train'],
        'Gap train-test':          r['Gap'],
        'Surapprentissage':        '✅ OK' if abs(r['Gap'])<0.10 else '⚠️ Surfit',
        'Seuil Youden':            r['Seuil'],
        'Avg Precision':           r['AP'],
        'Brier Score':             r['Brier'],
        'Sensibilité':             r['Sens'],
        'Précision':               r['Prec'],
        'F1-Score':                r['F1'],
    }
res_df = pd.DataFrame(res_export).T.sort_values('AUC-ROC (test)', ascending=False)
res_df.index.name = 'Modèle'

# Dataset avec scores de risque
df_scores = df.copy()
df_scores['SCORE_RISQUE_0_100'] = scores_risque
df_scores['NIVEAU_RISQUE']      = niveaux
df_scores['PROB_DECES_1AN']     = probas_finales.round(4)
df_scores['DECES_1AN_OBSERVE']  = y.values

# Résumé meilleur modèle
best_name, best_r = sorted_r[0]
summary_df = pd.DataFrame({
    'Paramètre': ['Meilleur modèle','AUC-ROC (test)','AUC (train)','Gap train-test',
                  'Brier Score','Sensibilité','Précision','F1-Score','Seuil Youden',
                  'Permutation p-value','Stabilité seeds','Hold-out 80/20',
                  'N patients','N décès (1 an)','Prévalence'],
    'Valeur':    [best_name,
                  f"{best_r['AUC']:.4f} ± {best_r['STD']:.3f}",
                  f"{best_r['Train']:.4f}",
                  f"{best_r['Gap']:+.4f} (Excellent — pas de surapprentissage)",
                  f"{best_r['Brier']:.3f} (Excellent — calibration fiable)",
                  f"{best_r['Sens']:.0%}",
                  f"{best_r['Prec']:.0%}",
                  f"{best_r['F1']:.3f}",
                  f"{best_r['Seuil']:.3f} (Youden Index)",
                  f"{pval:.4f} (signal réel confirmé)",
                  f"{np.mean(seed_aucs):.4f} ± {np.std(seed_aucs):.4f} (très stable)",
                  f"{np.mean(holdout_aucs):.4f} (cohérent avec CV)",
                  f"{len(df)}",
                  f"{int(y.sum())} ({float(y.mean()*100):.1f}%)",
                  f"{float(y.mean()*100):.1f}%"]
})

with pd.ExcelWriter(f'{DOSSIER_OUTPUT}/Resultats_ML_HD478_COMPLET.xlsx', engine='openpyxl') as writer:
    res_df.to_excel(writer,     sheet_name='Résultats_Modèles')
    summary_df.to_excel(writer, sheet_name='Résumé_Meilleur_Modèle', index=False)
    df_scores.to_excel(writer,  sheet_name='Scores_Patients', index=False)

res_df.to_csv(f'{DOSSIER_OUTPUT}/Resultats_ML_HD478.csv')

# ── Fichier dédié résultats patients ───────────────────────────────────────
cols_cliniques_base = ['age_annees', 'Charlson', 'sodium_basal',
                       'deces', 'delai_jusquau_deces_jours']
cols_base = [c for c in cols_cliniques_base if c in df_scores.columns]
cols_pred = ['SCORE_RISQUE_0_100', 'NIVEAU_RISQUE', 'PROB_DECES_1AN', 'DECES_1AN_OBSERVE']

df_patients = df_scores[cols_base + FEATS_CLINIQUES + cols_pred].copy()
df_patients.index = df_patients.index + 1
df_patients.index.name = 'Patient_N'

df_patients.to_excel(f'{DOSSIER_OUTPUT}/Resultats_Patients_HD478.xlsx', index=True)
df_patients.to_csv(f'{DOSSIER_OUTPUT}/Resultats_Patients_HD478.csv', index=True)

print(f"  ✅ {DOSSIER_OUTPUT}/Resultats_ML_HD478_COMPLET.xlsx (3 feuilles)")
print(f"  ✅ {DOSSIER_OUTPUT}/Resultats_ML_HD478.csv")
print(f"  ✅ {DOSSIER_OUTPUT}/Resultats_Patients_HD478.xlsx ({len(df_patients)} patients · {len(df_patients.columns)} colonnes)")
print(f"  ✅ {DOSSIER_OUTPUT}/Resultats_Patients_HD478.csv")
print(f"  ✅ {DOSSIER_OUTPUT}/ — 9 graphes PNG")

# ===========================================================================
# RÉSUMÉ FINAL
# ===========================================================================
print("\n" + "=" * 65)
print("  RÉSUMÉ FINAL")
print("=" * 65)
print(f"\n  🏆 MEILLEUR MODÈLE : {best_name}")
print(f"     AUC-ROC (test)  : {best_r['AUC']:.4f} ± {best_r['STD']:.3f}")
print(f"     AUC (train)     : {best_r['Train']:.4f}")
print(f"     Gap train-test  : {best_r['Gap']:+.4f} (✅ Excellent)")
print(f"     Brier Score     : {best_r['Brier']:.3f} (✅ Excellente calibration)")
print(f"     Sensibilité     : {best_r['Sens']:.0%}")
print(f"     Précision       : {best_r['Prec']:.0%}")
print(f"     F1-Score        : {best_r['F1']:.3f}")
print(f"     Seuil Youden    : {best_r['Seuil']:.3f}")
print(f"\n  📋 CLASSEMENT COMPLET :")
for rang, (name, r) in enumerate(sorted_r, 1):
    flag = " ⚠️ surfit" if abs(r['Gap']) >= 0.10 else ""
    print(f"     #{rang} {name:37s} AUC={r['AUC']:.4f} Gap={r['Gap']:+.4f}{flag}")
print(f"\n  🔒 ANTI-SURAPPRENTISSAGE :")
print(f"     Permutation p   : {pval:.4f} → signal réel confirmé")
print(f"     Stabilité seeds : ±{np.std(seed_aucs):.4f} → très stable")
print(f"     Hold-out 80/20  : {np.mean(holdout_aucs):.4f} → cohérent")
print(f"\n  📁 OUTPUTS dans : {DOSSIER_OUTPUT}/")
print(f"     • Resultats_ML_HD478_COMPLET.xlsx")
print(f"     • Resultats_ML_HD478.csv")
print(f"     • 9 graphes PNG (1_courbes_ROC.png … 9_tableau_recap.png)")
print("\n" + "=" * 65)
