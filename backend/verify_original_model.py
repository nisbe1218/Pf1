#!/usr/bin/env python
import joblib
import pprint

m = joblib.load('/app/predictions/models/mortalite_svm_features.joblib')

print("=" * 80)
print("  MODÈLE SVM ORIGINAL (AUC=0.8235)")
print("=" * 80)
print(f"\nType: {type(m)}")
print(f"\nContent:")
pprint.pprint(m, width=120)
