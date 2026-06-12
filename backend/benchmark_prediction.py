"""
Benchmark réel du pipeline de prédiction de mortalité.
Mesure chaque étape séparément sur 100 itérations.

Usage :
    python benchmark_prediction.py
"""
import sys, time, os
import numpy as np
import pandas as pd
import joblib

# ── Chemins ──────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "predictions", "models", "mortalite_svm.joblib")
META_PATH  = os.path.join(BASE_DIR, "predictions", "models", "mortalite_svm_features.joblib")
EXCEL_PATH = os.path.join(BASE_DIR, "predictions", "models", "Base_HD_478_v4_finale.xlsx")

N = 100   # nombre de requêtes à simuler

# ── Chargement du modèle ──────────────────────────────────────────────────────
print("Chargement du modèle...")
pipeline = joblib.load(MODEL_PATH)
meta     = joblib.load(META_PATH)
feature_keys = meta["feature_keys"] if isinstance(meta, dict) else list(meta)
print(f"  Pipeline: {' -> '.join(s[0] for s in pipeline.steps)}")
print(f"  Features: {len(feature_keys)}")

# ── Données de test réelles (HD-478) ─────────────────────────────────────────
print("\nChargement des données HD-478...")
df_raw = pd.read_excel(EXCEL_PATH, sheet_name="Base_HD_478_v4")

# Interactions (identiques à train_from_excel.py)
df_raw["age_x_charlson"]   = df_raw["age_annees"] * df_raw["Charlson"]
df_raw["dyspnee_x_oedeme"] = df_raw["dyspnee"].fillna(0) * df_raw["oedemes_surcharge"].fillna(0)
df_raw["sodium_lt130"]     = (df_raw["sodium_basal"] < 130).astype(float)
df_raw["charlson_x_hosp"]  = df_raw["Charlson"] * df_raw["nombre_hospitalisations"].fillna(0)
df_raw["hypert_x_cardio"]  = df_raw["hypertension"].fillna(0) * df_raw["cardiopathie"].fillna(0)
df_raw["albumine_x_hosp"]  = df_raw["albumine_basale"] * df_raw["nombre_hospitalisations"].fillna(0)
df_raw["albumine_lt35"]    = (df_raw["albumine_basale"] < 35).astype(float)
df_raw["age_x_cardio"]     = df_raw["age_annees"] * df_raw["cardiopathie"].fillna(0)

# Construire X avec les features du modèle (colonnes disponibles)
available = [k for k in feature_keys if k in df_raw.columns]
X_all = df_raw[available].apply(pd.to_numeric, errors="coerce")
# Ajouter les colonnes manquantes comme NaN
for k in feature_keys:
    if k not in X_all.columns:
        X_all[k] = np.nan
X_all = X_all[feature_keys].reset_index(drop=True)

print(f"  {len(X_all)} patients disponibles, {X_all.isnull().sum().sum()} valeurs manquantes")

# Sélectionner N samples (avec répétitions si besoin)
rng = np.random.RandomState(42)
indices = rng.choice(len(X_all), size=N, replace=(len(X_all) < N))
X_samples = [X_all.iloc[[i]] for i in indices]

# ── Séparer les étapes du pipeline ───────────────────────────────────────────
knn    = pipeline.named_steps["imputer"]     # KNNImputer
pt     = pipeline.named_steps["transformer"] # PowerTransformer
clf    = pipeline.named_steps["clf"]         # SVC (calibré)

# ── Thresholds pour la zone de risque ────────────────────────────────────────
T1, T2 = 0.10, 0.29

def assign_risk_zone(prob):
    return "Faible" if prob < T1 else "Modéré" if prob < T2 else "Élevé"

# ── Simulation "feature extraction" ──────────────────────────────────────────
# Représente : lecture ORM + normalisation + interactions
# On simule avec des opérations de complexité équivalente sur un dict de 32 champs
BINARY_FIELDS = {"fistule_arterioveineuse_creee", "couverture_medicale",
                 "admission_cathetere_tunnellise", "crise_convulsive",
                 "douleur_abdominale", "diabete", "evenement_cardiovasculaire",
                 "dyspnee", "oedemes_surcharge", "hemodialyse",
                 "liste_attente_transplantation", "maladie_renale_hereditaire",
                 "information_transplantation_donnee", "hypertension", "cardiopathie"}

def simulate_feature_extraction(raw_row_dict, feature_keys):
    """Simule extract_features_from_patient : accès dict + normalisation + calcul interactions."""
    row = {}
    for key in feature_keys:
        val = raw_row_dict.get(key, np.nan)
        if key in BINARY_FIELDS:
            row[key] = 1.0 if str(val).strip().lower() in ("1", "oui", "yes", "true") else (
                       0.0 if str(val).strip().lower() in ("0", "non", "no", "false") else np.nan)
        else:
            try:
                row[key] = float(val) if val is not None and str(val).strip() != "" else np.nan
            except (ValueError, TypeError):
                row[key] = np.nan
    # Interactions (équivalent de compute_clinical_risk_indicators)
    age = row.get("age_annees", np.nan)
    charlson = row.get("Charlson", np.nan)
    row["age_x_charlson"]   = age * charlson if not (np.isnan(age) or np.isnan(charlson)) else np.nan
    row["sodium_lt130"]     = 1.0 if (not np.isnan(row.get("sodium_basal", np.nan)) and row.get("sodium_basal", 131) < 130) else 0.0
    row["albumine_lt35"]    = 1.0 if (not np.isnan(row.get("albumine_basale", np.nan)) and row.get("albumine_basale", 36) < 35) else 0.0
    return row

# Préparer les dicts bruts pour feature extraction
raw_dicts = [X_all.iloc[i].to_dict() for i in indices]

# ── BENCHMARK ────────────────────────────────────────────────────────────────
print(f"\nBenchmark sur {N} requêtes...\n")

t_feat   = []   # feature extraction
t_knn    = []   # KNN imputation
t_pt     = []   # Yeo-Johnson
t_svc    = []   # SVC predict_proba
t_risk   = []   # risk zone assignment
t_total  = []   # end-to-end pipeline complet

for i in range(N):
    raw = raw_dicts[i]
    sample_df = X_samples[i]

    # ── 1. Feature extraction ─────────────────────────────────────────────
    t0 = time.perf_counter()
    row = simulate_feature_extraction(raw, feature_keys)
    input_df = pd.DataFrame([row], columns=feature_keys)
    t_feat.append((time.perf_counter() - t0) * 1000)

    # ── 2. KNN imputation ─────────────────────────────────────────────────
    t0 = time.perf_counter()
    X_imp = knn.transform(input_df)
    t_knn.append((time.perf_counter() - t0) * 1000)

    # ── 3. Yeo-Johnson (PowerTransformer) ─────────────────────────────────
    t0 = time.perf_counter()
    X_tr = pt.transform(X_imp)
    t_pt.append((time.perf_counter() - t0) * 1000)

    # ── 4. SVC predict_proba ──────────────────────────────────────────────
    t0 = time.perf_counter()
    prob = float(clf.predict_proba(X_tr)[:, 1][0])
    t_svc.append((time.perf_counter() - t0) * 1000)

    # ── 5. Risk zone assignment ───────────────────────────────────────────
    t0 = time.perf_counter()
    zone = assign_risk_zone(prob)
    t_risk.append((time.perf_counter() - t0) * 1000)

    # ── Total pipeline complet (steps 2+3+4+5) ────────────────────────────
    t_total.append(t_feat[-1] + t_knn[-1] + t_pt[-1] + t_svc[-1] + t_risk[-1])

# ── Résultats ─────────────────────────────────────────────────────────────────
def stats(arr):
    a = np.array(arr)
    return np.mean(a), np.percentile(a, 95), np.min(a), np.max(a)

print("=" * 60)
print(f"{'Operation':<30} {'Mean (ms)':>10} {'P95 (ms)':>10} {'Min':>8} {'Max':>8}")
print("-" * 60)
rows = [
    ("Feature extraction",    t_feat),
    ("KNN imputation",        t_knn),
    ("Yeo-Johnson + SVC",     t_pt),        # PowerTransformer only
    ("SVC predict_proba",     t_svc),        # SVC only (séparé)
    ("Risk zone assignment",  t_risk),
    ("Total prediction",      t_total),
]
for label, arr in rows:
    m, p95, mn, mx = stats(arr)
    print(f"  {label:<28} {m:>10.2f} {p95:>10.2f} {mn:>8.2f} {mx:>8.2f}")
print("=" * 60)

print("\nNote : 'Yeo-Johnson + SVC' inclus dans le tableau du rapport")
yj_svc = [t_pt[i] + t_svc[i] for i in range(N)]
m, p95, _, _ = stats(yj_svc)
print(f"  Yeo-Johnson + SVC combinés : mean={m:.2f} ms, P95={p95:.2f} ms")

print(f"\nConclusion :")
m_tot, p95_tot, _, _ = stats(t_total)
print(f"  Latence médiane totale : {np.median(t_total):.1f} ms")
print(f"  Latence moyenne totale : {m_tot:.1f} ms")
print(f"  P95 totale             : {p95_tot:.1f} ms")
print(f"  Objectif < 200 ms      : {'✅ ATTEINT' if p95_tot < 200 else '❌ DÉPASSÉ'}")

print("\n  Comparaison avec les valeurs dans le rapport (Tableau 7.1) :")
report_vals = {
    "Feature extraction":   (12, 18),
    "KNN imputation":       (8,  14),
    "Yeo-Johnson + SVC":    (23, 35),
    "Risk zone assignment": (2,   4),
    "Total prediction":     (48, 76),
}
measured = {
    "Feature extraction":   stats(t_feat)[:2],
    "KNN imputation":       stats(t_knn)[:2],
    "Yeo-Johnson + SVC":    stats(yj_svc)[:2],
    "Risk zone assignment": stats(t_risk)[:2],
    "Total prediction":     stats(t_total)[:2],
}
print(f"  {'Opération':<28} {'Rapport':>12} {'Mesuré':>12} {'Écart'}")
print("  " + "-" * 65)
for op in report_vals:
    rm, rp = report_vals[op]
    mm, mp = measured[op]
    delta = mm - rm
    flag = "⚠️" if abs(delta) > rm * 0.5 else "✅"
    print(f"  {op:<28} {rm:>5}/{rp:<5}    {mm:>5.1f}/{mp:<5.1f}  {delta:>+.1f} ms  {flag}")
