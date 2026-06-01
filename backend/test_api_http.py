#!/usr/bin/env python
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

# Get or create test user
user, created = User.objects.get_or_create(email='testuser@test.com')
if created:
    user.set_password('testpass123')
    user.nom = 'Test'
    user.prenom = 'User'
    user.save()
    print("Created test user: testuser@test.com")
else:
    print("Using existing test user: testuser@test.com")

# Get JWT token
refresh = RefreshToken.for_user(user)
access_token = str(refresh.access_token)

# Get patient
patient = Patient.objects.first()
if not patient:
    print("❌ Aucun patient")
    exit(1)

# Create test client with token
client = Client()

# Try prediction endpoint
url = f'/api/predictions/patient/{patient.id}/mortalite/'
print(f"\nTesting: GET {url}")
print("=" * 80)

try:
    response = client.get(
        url,
        HTTP_AUTHORIZATION=f'Bearer {access_token}'
    )
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = json.loads(response.content)
        print(f"\n✅ PRÉDICTION RÉUSSIE!")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"\n❌ Erreur: {response.status_code}")
        print(response.content.decode())
        
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
