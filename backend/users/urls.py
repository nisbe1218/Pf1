from django.urls import path
from .views import (
    LoginView, UtilisateurListView,
    UtilisateurDetailView, MonProfilView, ConfirmPasswordView,
    MotDePasseUtilisateurView, RoleListView, ChangePasswordView,
    UserAuditHistoryView, PersonalNotesView
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('login/',         LoginView.as_view(),           name='login'),
    path('token/refresh/', TokenRefreshView.as_view(),    name='token_refresh'),
    path('roles/',        RoleListView.as_view(),         name='role_list'),
    path('users/',  UtilisateurListView.as_view(), name='users_list'),
    path('users/<int:pk>/', UtilisateurDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/password/', MotDePasseUtilisateurView.as_view(), name='user_password_hash'),
    path('profil/',        MonProfilView.as_view(),        name='profil'),
    path('notes/',         PersonalNotesView.as_view(),    name='personal_notes'),
    path('audit-history/', UserAuditHistoryView.as_view(), name='user_audit_history'),
    path('confirm-password/', ConfirmPasswordView.as_view(), name='confirm_password'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
]