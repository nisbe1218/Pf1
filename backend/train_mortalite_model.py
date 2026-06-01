#!/usr/bin/env python
"""
Script de réentraînement du modèle SVM avec 32 features
Utilise feature_mapping.py pour les 32 features (24 + 8 interactions)
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, str(Path(__file__).parent))
django.setup()

from predictions.views import train_models
import json

print("=" * 80)
print("  RÉENTRAÎNEMENT DU MODÈLE MORTALITE AVEC 32 FEATURES")
print("=" * 80)

try:
    print("\n🚀 Lancement de l'entraînement...")
    print("   Type: mortalite")
    print("   Features: 32 (24 cliniques + 8 interactions)")
    print("   Algorithm: SVM avec calibration Platt (sigmoid)")
    print()
    
    report, best_model_name = train_models('mortalite', feature_keys=None)
    
    print("\n✅ ENTRAÎNEMENT TERMINÉ")
    print("=" * 80)
    
    if report:
        # Afficher les résultats pour SVM
        svm_result = next((r for r in report if r.get('model') == 'svm'), None)
        if svm_result:
            print("\n📊 RÉSULTATS SVM (32 features):")
            print(f"  AUC CV (mean): {svm_result.get('cv_auc_mean', 'N/A'):.4f}")
            print(f"  AUC CV (std):  {svm_result.get('cv_auc_std', 'N/A'):.4f}")
            print(f"  AUC Test:      {svm_result.get('auc', 'N/A'):.4f}")
            print(f"  Accuracy:      {svm_result.get('accuracy', 'N/A'):.4f}")
            print(f"  Precision:     {svm_result.get('precision', 'N/A'):.4f}")
            print(f"  Recall:        {svm_result.get('recall', 'N/A'):.4f}")
            print(f"  F1:            {svm_result.get('f1', 'N/A'):.4f}")
            print(f"  Features:      {len(svm_result.get('feature_keys', []))}")
            print(f"  N Train:       {svm_result.get('n_train', 'N/A')}")
            print(f"  N Test:        {svm_result.get('n_test', 'N/A')}")
        else:
            print("⚠️  Pas de résultats SVM")
        
        print("\n✨ Meilleur modèle:", best_model_name)
    
    print("\n" + "=" * 80)
    print("  ✅ Le modèle a été sauvegardé dans predictions/models/")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ERREUR: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
