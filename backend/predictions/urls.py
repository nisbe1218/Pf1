from django.urls import path

from .views import (
    PredictionPredictView,
    PredictionTrainView,
    PredictionHistoryView,
    PredictionMetricsView,
    PredictionPatientView,
)
from .predict_mortalite import PredictMortalitePatientView, LatestMortaliteView, StoredPatientMortaliteView

urlpatterns = [
    # 🔮 Prédiction
    path('predict/', PredictionPredictView.as_view(), name='prediction_predict'),

    # 🔮 Prédiction avec patient ID
    path('predict-patient/', PredictionPatientView.as_view(), name='prediction_predict_patient'),

    # 🏥 Prédiction mortalité à 1 an (SVM)
    path('patient/<int:patient_id>/mortalite/', PredictMortalitePatientView.as_view(), name='predict_mortalite'),

    # 📌 Dernière prédiction mortalité (toutes sessions confondues)
    path('latest-mortalite/', LatestMortaliteView.as_view(), name='latest_mortalite'),

    # 📌 Prédiction stockée pour un patient spécifique (sans relancer le modèle)
    path('stored-mortalite/<int:patient_id>/', StoredPatientMortaliteView.as_view(), name='stored_mortalite'),

    # 🧠 Entraînement modèles
    path('train/', PredictionTrainView.as_view(), name='prediction_train'),

    # 📊 Historique des prédictions
    path('history/', PredictionHistoryView.as_view(), name='prediction_history'),

    # 📈 Métriques modèles ML
    path('metrics/', PredictionMetricsView.as_view(), name='prediction_metrics'),
]