#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test async preprocessing pipeline"""
import os
import django
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIRequestFactory, force_authenticate
from django.core.files.uploadedfile import SimpleUploadedFile
from patients.views import PatientPreprocessAnalyzeView, PatientPreprocessStatusView
from users.models import Role, Utilisateur

print("=" * 60)
print("🧪 ASYNC PREPROCESSING PIPELINE TEST")
print("=" * 60)

# Create test user
print("\n1️⃣  Creating test user...")
role, _ = Role.objects.get_or_create(nom='resident')
user, created = Utilisateur.objects.get_or_create(
    email='test_async@example.com',
    defaults={'nom': 'Test', 'prenom': 'Async', 'role': role}
)
user.role = role
user.save()
print(f"   ✅ User: {user.email}")

# Create test CSV
print("\n2️⃣  Creating test CSV data...")
rows = ['patient_id,nom,age,diagnostic,date_visite'] + [
    f'{i},Patient{i},{25+i},Hypertension,2024-01-15' 
    for i in range(1, 11)
]
csv = ('\n'.join(rows) + '\n').encode('utf-8')
upload = SimpleUploadedFile('test.csv', csv, content_type='text/csv')
print(f"   ✅ CSV: {len(rows)} rows, {len(csv)} bytes")

# Test upload (dispatch async job)
print("\n3️⃣  Posting file to /preprocess/analyze/...")
factory = APIRequestFactory()
request = factory.post('/api/patients/preprocess/analyze/', {'file': upload}, format='multipart')
force_authenticate(request, user=user)

view = PatientPreprocessAnalyzeView.as_view()
response = view(request)

preprocess_id = response.data.get('preprocess_id')
status_code = response.status_code
status = response.data.get('status')
message = response.data.get('message')

print(f"   Status Code: {status_code}")
if status_code == 202:
    print(f"   ✅ Accepted! Job dispatched.")
else:
    print(f"   ⚠️  Status {status_code} (expected 202)")

print(f"   Preprocess ID: {preprocess_id}")
print(f"   Status: {status}")
print(f"   Message: {message}")

# Poll for completion
if preprocess_id and status == 'pending':
    max_polls = 45
    print(f"\n4️⃣  Polling for completion (max {max_polls} polls)...")
    for poll_num in range(1, max_polls + 1):
        time.sleep(2)
        
        # Get status
        status_request = factory.get(f'/api/patients/preprocess/{preprocess_id}/status/')
        force_authenticate(status_request, user=user)
        
        status_view = PatientPreprocessStatusView.as_view()
        status_response = status_view(status_request, preprocess_id=preprocess_id)
        
        job_status = status_response.data.get('status')
        progress_msg = status_response.data.get('progress_message', '')
        
        print(f"   Poll {poll_num:2d}: [{job_status:10s}] {progress_msg}")
        
        if job_status == 'completed':
            print(f"\n   ✅ Job completed!")
            report = status_response.data.get('report', {})
            summary = report.get('summary', {})
            
            print(f"\n5️⃣  Analysis Results:")
            print(f"   Quality Score: {summary.get('quality_score', 'N/A')}")
            print(f"   Rows: {summary.get('rows', 'N/A')}")
            print(f"   Columns: {summary.get('columns', 'N/A')}")
            print(f"   Issues: {len(report.get('issues', []))}")
            print(f"   Recommendations: {len(report.get('recommendations', []))}")
            
            print(f"\n✨ Pipeline test PASSED!")
            sys.exit(0)
        elif job_status == 'error':
            print(f"\n   ❌ Job failed: {status_response.data.get('error', 'Unknown')}")
            sys.exit(1)
    
    print(f"\n⏱️  Timeout after {max_polls} polls")
    sys.exit(1)
else:
    print(f"\n❌ Failed to dispatch job (no preprocess_id or not pending)")
    sys.exit(1)
