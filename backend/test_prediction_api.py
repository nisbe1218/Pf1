#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from patients.models import Patient
from predictions.predict_mortalite import PredictMortalitePatientView
from rest_framework.test import APIRequestFactory
from rest_framework.response import Response

factory = APIRequestFactory()

# Get first patient
try:
    patient = Patient.objects.first()
    if patient:
        print("=" * 80)
        print(f"  TEST PRÉDICTION - Patient ID={patient.id}")
        print("=" * 80)
        
        # Create a test request
        request = factory.get(f'/predictions/patient/{patient.id}/mortalite/')
        view = PredictMortalitePatientView.as_view()
        response = view(request, patient_id=patient.id)
        
        print(f"\nStatus: {response.status_code}")
        print(f"\n✅ Réponse API:")
        import json
        print(json.dumps(response.data, indent=2, ensure_ascii=False))
        
    else:
        print("❌ Aucun patient trouvé dans la base")
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
