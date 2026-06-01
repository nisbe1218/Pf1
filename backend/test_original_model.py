#!/usr/bin/env python
import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.svm import SVC

# Load main model
model = joblib.load('/app/predictions/models/mortalite_svm.joblib')

print("=" * 80)
print("  MODÈLE SVM ORIGINAL - INSPECTION COMPLÈTE")
print("=" * 80)

print(f"\nType du modèle: {type(model)}")
print(f"Est CalibratedClassifierCV: {isinstance(model, CalibratedClassifierCV)}")

if hasattr(model, 'base_estimator'):
    print(f"Base estimator: {type(model.base_estimator)}")
    
if hasattr(model, 'cv'):
    print(f"CV method: {model.cv}")
    
# Check calibrator
if hasattr(model, 'calibrators_'):
    print(f"Calibrators fitted: {len(model.calibrators_)} (one per fold)")
    
# Try to get the classes
if hasattr(model, 'classes_'):
    print(f"Classes: {model.classes_}")

# Try prediction on dummy data
try:
    import numpy as np
    X_dummy = np.random.randn(1, 32)
    proba = model.predict_proba(X_dummy)
    print(f"\n✅ Modèle peut prédire sur 32 features")
    print(f"   Probabilité test: {proba[0]}")
except Exception as e:
    print(f"\n❌ Erreur: {e}")

print("\n✅ Modèle original copié avec succès!")
