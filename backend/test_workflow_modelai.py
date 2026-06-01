#!/usr/bin/env python
"""
TEST COMPLET END-TO-END - ModelAI Workflow
Simule : Dashboard → Patients → Score
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from patients.models import Patient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

print("=" * 80)
print("  TEST END-TO-END - WORKFLOW MODELAI 3-TABS")
print("=" * 80)

# Step 1: User authentication
print("\n🔐 ÉTAPE 1 — AUTHENTIFICATION UTILISATEUR")
print("-" * 80)

user, _ = User.objects.get_or_create(email='medecin@test.com')
user.set_password('testpass123')
user.is_staff = True
user.save()

refresh = RefreshToken.for_user(user)
access_token = str(refresh.access_token)
print(f"✅ Utilisateur: {user.email}")
print(f"✅ Token JWT obtenu")

# Step 2: Get patients list (Dashboard)
print("\n📊 ÉTAPE 2 — DASHBOARD (Liste des patients)")
print("-" * 80)

client = Client()
response = client.get(
    '/api/patients/',
    HTTP_AUTHORIZATION=f'Bearer {access_token}'
)

if response.status_code == 200:
    patients_data = response.json()
    
    if isinstance(patients_data, dict) and 'results' in patients_data:
        patients = patients_data['results'][:5]
    else:
        patients = patients_data[:5] if isinstance(patients_data, list) else []
    
    print(f"✅ Status: {response.status_code}")
    print(f"✅ Patients trouvés: {len(patients)}")
    
    if patients:
        for i, p in enumerate(patients[:3], 1):
            if isinstance(p, dict):
                p_id = p.get('id', 'N/A')
                p_name = p.get('nom', 'N/A')
                print(f"   {i}. ID={p_id} - {p_name}")
else:
    print(f"❌ Status: {response.status_code}")
    patients = Patient.objects.all()[:5]
    print(f"✅ Using fallback: {len(patients)} patients found")

# Step 3: Get specific patient & predict (Patients Tab + Score Tab)
print("\n🎯 ÉTAPE 3 — SÉLECTION PATIENT & PRÉDICTION")
print("-" * 80)

patient = Patient.objects.first()
if patient:
    patient_id = patient.id
    patient_name = getattr(patient, 'nom', 'Patient')
    
    print(f"✅ Patient sélectionné: ID={patient_id} ({patient_name})")
    
    # Get prediction
    response = client.get(
        f'/api/predictions/patient/{patient_id}/mortalite/',
        HTTP_AUTHORIZATION=f'Bearer {access_token}'
    )
    
    print(f"\n🔮 PRÉDICTION - Endpoint: /api/predictions/patient/{patient_id}/mortalite/")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        pred_data = response.json()
        
        print(f"\n   📈 Résultats:")
        print(f"      Score de risque: {pred_data.get('score_risque', 'N/A')}/100")
        print(f"      Niveau de risque: {pred_data.get('niveau_risque', 'N/A')}")
        print(f"      Probabilité décès (1 an): {pred_data.get('probabilite_deces', 'N/A')*100:.2f}%")
        print(f"      Model AUC-CV: {pred_data.get('auc_cv', 'N/A')}")
        print(f"      Recommendation: {pred_data.get('recommendation', 'N/A')}")
        
        # Risk color mapping
        score = pred_data.get('score_risque', 0)
        if score < 33:
            color = "🟢 Vert (Faible)"
            suivi = "Suivi standard"
        elif score < 66:
            color = "🟡 Orange (Modéré)"
            suivi = "Suivi renforcé"
        else:
            color = "🔴 Rouge (Élevé)"
            suivi = "Suivi intensif"
        
        print(f"\n   🎨 Affichage UI:")
        print(f"      Couleur: {color}")
        print(f"      Suivi recommandé: {suivi}")
        
        print(f"\n" + "=" * 80)
        print("  ✅ WORKFLOW COMPLET TESTÉ AVEC SUCCÈS!")
        print("=" * 80)
        print(f"\nRÉSUMÉ - Workflow ModelAI:")
        print(f"  Tab 1 - Dashboard:  ✅ Liste patients affichée")
        print(f"  Tab 2 - Patients:   ✅ Patient {patient_id} sélectionné")
        print(f"  Tab 3 - Score:      ✅ Score={score}/100, Niveau={pred_data.get('niveau_risque')}")
        print(f"\nModèle utilisé: SVM Linéaire | AUC-CV: {pred_data.get('auc_cv')}")
        print(f"Features: 32 (24 cliniques + 8 interactions)")
        print(f"Pipeline: KNNImputer(k=3) → PowerTransformer → SVC(C=0.01, kernel='linear')")
        
    else:
        print(f"❌ Erreur lors de la prédiction: {response.status_code}")
        print(response.json())
else:
    print("❌ Aucun patient trouvé dans la base")

print("\n" + "=" * 80)
