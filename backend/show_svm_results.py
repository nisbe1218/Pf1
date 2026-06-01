#!/usr/bin/env python
import joblib
import json

# Load metadata
m = joblib.load('/app/predictions/models/mortalite_svm_features.joblib')

print("=" * 80)
print("  RÉSULTATS DU RÉENTRAÎNEMENT SVM")
print("=" * 80)

print(f"\n✅ Nombre de features: {len(m['feature_keys'])}")
print(f"\n📊 Features utilisées:")
for i, feat in enumerate(m['feature_keys'], 1):
    print(f"   {i:2}. {feat}")

print(f"\n🎯 Threshold (Youden): {m['threshold']:.4f}")
print(f"\n👥 Class distribution: {m['class_distribution']}")

print(f"\n📈 Metrics:")
for k, v in m['metrics'].items():
    if isinstance(v, float):
        print(f"   {k}: {v:.4f}")
    else:
        print(f"   {k}: {v}")

print("\n" + "=" * 80)
