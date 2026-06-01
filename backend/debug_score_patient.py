#!/usr/bin/env python
"""Debug script: Analyze why patient 47364 has score 0.0/100"""

import os
import sys
import django
import joblib
import numpy as np
import pandas as pd
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from patients.models import Patient
from predictions.models.feature_mapping import (
    extract_features_for_patient, 
    features_dict_to_array,
    ALL_FEATURES
)

print("="*80)
print("DEBUG: ANALYSE DU SCORE 0.0/100 - Patient 47364")
print("="*80)

# Load patient
try:
    patient = Patient.objects.get(id=47364)
    print(f"\n✅ Patient trouvé: ID={patient.id}, Name={patient.prenom} {patient.nom}")
except Patient.DoesNotExist:
    print(f"❌ Patient 47364 not found!")
    sys.exit(1)

# Extract features
print("\n" + "="*80)
print("ÉTAPE 1: EXTRACTION DES FEATURES")
print("="*80)

features_dict = extract_features_for_patient(patient)

print(f"\n📊 Nombre de features: {len(features_dict)}")
print(f"   Features attendues: {len(ALL_FEATURES)}")

# Show non-null features
non_null_features = {k: v for k, v in features_dict.items() if v is not None}
null_features = {k: v for k, v in features_dict.items() if v is None}

print(f"\n✅ Features NON-NULL: {len(non_null_features)}/{len(ALL_FEATURES)}")
print(f"❌ Features NULL (manquantes): {len(null_features)}/{len(ALL_FEATURES)}")

print(f"\n--- Features NON-NULL ({len(non_null_features)}) ---")
for name, value in sorted(non_null_features.items()):
    print(f"  {name:40s} = {value:10.4f}" if isinstance(value, (int, float)) else f"  {name:40s} = {value}")

print(f"\n--- Features NULL ({len(null_features)}) ---")
for name in sorted(null_features.keys()):
    print(f"  {name:40s} = None")

# Convert to array
print("\n" + "="*80)
print("ÉTAPE 2: CONVERSION EN ARRAY ET IMPUTATION")
print("="*80)

X_array = features_dict_to_array(features_dict)
print(f"\n✅ Array shape: {X_array.shape}")
print(f"   NaN count: {np.isnan(X_array).sum()}")
print(f"   Min value: {np.nanmin(X_array):.4f}")
print(f"   Max value: {np.nanmax(X_array):.4f}")
print(f"   Mean value: {np.nanmean(X_array):.4f}")

print(f"\n--- Array values (first 10 features) ---")
for i in range(min(10, X_array.shape[1])):
    val = X_array[0, i]
    status = "✅" if not np.isnan(val) else "⚠️ NaN"
    print(f"  [{i:2d}] {ALL_FEATURES[i]:40s} = {val:10.4f} {status}" if not np.isnan(val) else f"  [{i:2d}] {ALL_FEATURES[i]:40s} = NaN {status}")

# Load model and predict
print("\n" + "="*80)
print("ÉTAPE 3: PRÉDICTION DU MODÈLE")
print("="*80)

try:
    model = joblib.load('/app/predictions/models/mortalite_svm.joblib')
    print(f"\n✅ Modèle chargé: {type(model)}")
    print(f"   Type: CalibratedClassifierCV with SVM")
    
    # Predict with full pipeline
    proba = model.predict_proba(X_array)[0, 1]
    prediction = model.predict(X_array)[0]
    
    print(f"\n📈 Probabilité de décès (1 an): {proba:.6f}")
    print(f"   Score 0-100: {proba*100:.2f}")
    print(f"   Prediction binaire: {prediction} ({'Décès' if prediction == 1 else 'Survie'})")
    
    # Decision function (SVM score)
    try:
        decision = model.estimator_.decision_function(model.estimator_[:-1].transform(X_array))[0]
        print(f"   Decision function (SVM score): {decision:.6f}")
    except:
        print(f"   Decision function: Not available")
    
except Exception as e:
    print(f"\n❌ Erreur lors du chargement du modèle: {e}")
    import traceback
    traceback.print_exc()

# Risk stratification
print("\n" + "="*80)
print("ÉTAPE 4: STRATIFICATION DU RISQUE")
print("="*80)

score_risque = proba * 100

if score_risque < 33:
    niveau = "Faible (VERT)"
    color = "🟢"
elif score_risque < 66:
    niveau = "Modéré (ORANGE)"
    color = "🟠"
else:
    niveau = "Élevé (ROUGE)"
    color = "🔴"

print(f"\n{color} Score: {score_risque:.2f}/100")
print(f"{color} Niveau: {niveau}")

# Interpretation
print("\n" + "="*80)
print("INTERPRÉTATION")
print("="*80)

if score_risque < 5:
    print(f"\n💚 Score TRÈS BAS ({score_risque:.2f})")
    print(f"   Possible raison 1: Peu/pas de facteurs de risque cliniques")
    print(f"                    → Presque toutes les features NULL")
    print(f"   Possible raison 2: Valeurs des features très favorables")
    print(f"                    → Pas d'albumine basse, pas de comorbidités, etc.")
    print(f"   Possible raison 3: Patient très stable et peu malade")
    print(f"\n   ✅ C'est NORMAL si le patient n'a pas de facteurs de risque documentés")
else:
    print(f"\n📊 Score NORMAL: {score_risque:.2f}/100")

print("\n" + "="*80)
