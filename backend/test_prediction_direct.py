#!/usr/bin/env python
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from patients.models import Patient
from predictions.models.feature_mapping import extract_features_for_patient
import joblib
import numpy as np

# Get first patient
try:
    patient = Patient.objects.first()
    if not patient:
        print("❌ Aucun patient trouvé")
        exit(1)
    
    print("=" * 80)
    print(f"  TEST PRÉDICTION DE BOUT EN BOUT")
    print(f"  Patient ID={patient.id}")
    print("=" * 80)
    
    # Step 1: Extract features
    print(f"\n1️⃣  Extraction des 32 features...")
    features_dict = extract_features_for_patient(patient)
    n_missing = sum(1 for v in features_dict.values() if v is None)
    print(f"   ✅ {len(features_dict)} features extraites ({n_missing} manquantes)")
    
    # Step 2: Convert to array
    print(f"\n2️⃣  Conversion en array (1, 32)...")
    from predictions.models.feature_mapping import features_dict_to_array
    X_array = features_dict_to_array(features_dict)
    print(f"   ✅ Shape: {X_array.shape}")
    
    # Step 3: Load model
    print(f"\n3️⃣  Chargement du modèle SVM original...")
    model = joblib.load('/app/predictions/models/mortalite_svm.joblib')
    print(f"   ✅ Modèle chargé: {type(model).__name__}")
    
    # Step 4: Predict
    print(f"\n4️⃣  Prédiction...")
    proba = model.predict_proba(X_array)[0, 1]
    score_risque = round(proba * 100, 1)
    
    if score_risque < 33:
        niveau = "Faible"
    elif score_risque < 66:
        niveau = "Modéré"
    else:
        niveau = "Élevé"
    
    print(f"   ✅ Probabilité décès: {proba:.4f}")
    print(f"   ✅ Score risque (0-100): {score_risque}")
    print(f"   ✅ Niveau risque: {niveau}")
    
    print("\n" + "=" * 80)
    print("  ✅ PRÉDICTION RÉUSSIE!")
    print("=" * 80)
    print(f"\n  Patient ID: {patient.id}")
    print(f"  Score de risque: {score_risque}/100")
    print(f"  Niveau: {niveau}")
    print(f"  Probabilité décès (1 an): {proba*100:.2f}%")
    
    if niveau == "Faible":
        print(f"  Recommandation: 🟢 Suivi standard")
    elif niveau == "Modéré":
        print(f"  Recommandation: 🟡 Suivi renforcé")
    else:
        print(f"  Recommandation: 🔴 Suivi intensif")
        
except Exception as e:
    print(f"\n❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
