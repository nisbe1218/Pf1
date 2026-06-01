#!/usr/bin/env python
"""
Inspection du modèle SVM réentraîné avec 32 features
"""
import os
import sys
import joblib
from pathlib import Path

models_dir = Path('/app/predictions/models')  # Docker path
svm_model_path = models_dir / 'mortalite_svm.joblib'
svm_features_path = models_dir / 'mortalite_svm_features.joblib'

print("=" * 80)
print("  INSPECTION DU MODÈLE SVM RÉENTRAÎNÉ")
print("=" * 80)

if not svm_model_path.exists():
    print(f"\n❌ Modèle SVM non trouvé: {svm_model_path}")
    sys.exit(1)

try:
    model = joblib.load(svm_model_path)
    features = joblib.load(svm_features_path) if svm_features_path.exists() else None
    
    print(f"\n✅ Modèle SVM chargé avec succès")
    print(f"\n📊 Informations du modèle:")
    print(f"   Type: {type(model).__name__}")
    
    # Inspectez la structure
    if hasattr(model, 'named_steps'):
        print(f"   Pipeline steps: {list(model.named_steps.keys())}")
        
        # Classifier info
        clf = model.named_steps.get('classifier')
        if clf:
            print(f"\n   Classifier type: {type(clf).__name__}")
            if hasattr(clf, 'base_estimator'):
                print(f"   Base estimator: {type(clf.base_estimator).__name__}")
                if hasattr(clf.base_estimator, 'named_steps'):
                    base_steps = clf.base_estimator.named_steps
                    print(f"   Base pipeline steps: {list(base_steps.keys())}")
                    if 'classifier' in base_steps:
                        svc = base_steps['classifier']
                        print(f"     SVC kernel: {getattr(svc, 'kernel', 'N/A')}")
                        print(f"     SVC C: {getattr(svc, 'C', 'N/A')}")
                        print(f"     SVC class_weight: {getattr(svc, 'class_weight', 'N/A')}")
    
    print(f"\n📁 Features List:")
    if features and isinstance(features, list):
        print(f"   Nombre de features: {len(features)}")
        print(f"   Features:")
        for i, feat in enumerate(features, 1):
            print(f"     {i:2}. {feat}")
    else:
        print(f"   ⚠️  Fichier features non trouvé ou format incorrect")
    
    print("\n" + "=" * 80)
    print("  ✅ MODÈLE PRÊT POUR LES PRÉDICTIONS")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ERREUR: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
