from django.urls import path
from . import views

urlpatterns = [
    path('analyze/', views.analyze_file, name='analyze'),
    path('health/', views.health_check, name='health'),
    path('<str:preprocess_id>/status/', views.get_status, name='status'),
    path('<str:preprocess_id>/report/', views.get_report, name='report'),
    path('<str:preprocess_id>/export/', views.export_corrected, name='export'),
    path('<str:preprocess_id>/integrate/', views.integrate_data, name='integrate'),
]