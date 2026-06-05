from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.hashers import check_password
from django.shortcuts import get_object_or_404
from .models import Utilisateur, Role
from .serializers import (
    UtilisateurSerializer, CreateUtilisateurSerializer, UpdateUtilisateurSerializer,
    CustomTokenSerializer, RolePublicSerializer, PersonalNotesSerializer
)
from .permissions import IsSuperAdmin, IsAdminOrChefService
from audit.models import AuditLog

USER_AUDIT_ACTIONS = [
    'CREATION_UTILISATEUR',
    'MODIFICATION_UTILISATEUR',
    'SUPPRESSION_UTILISATEUR',
    'CONSULTATION_MOT_DE_PASSE_HASH',
    'MODIFICATION_MOT_DE_PASSE',
]


def confirm_admin_password(request):
    password = request.data.get('confirmation_password')
    if not password:
        return False, Response({'error': 'Confirmation administrateur requise'}, status=400)
    if not check_password(password, request.user.password):
        return False, Response({'error': 'Confirmation refusée'}, status=403)
    return True, None


def _role_name(role_obj):
    if not role_obj:
        return None
    if isinstance(role_obj, str):
        return role_obj
    return getattr(role_obj, 'nom', None)


def _actor_label(user_obj):
    if not user_obj:
        return 'system_import'
    first = getattr(user_obj, 'prenom', None) or ''
    last = getattr(user_obj, 'nom', None) or ''
    full_name = f'{first} {last}'.strip()
    if full_name:
        return full_name
    return getattr(user_obj, 'email', None) or str(getattr(user_obj, 'id', 'system_import'))


def _user_snapshot(user_obj):
    if not user_obj:
        return {}
    return {
        'email': getattr(user_obj, 'email', None),
        'nom': getattr(user_obj, 'nom', None),
        'prenom': getattr(user_obj, 'prenom', None),
        'telephone': getattr(user_obj, 'telephone', None),
        'role': _role_name(getattr(user_obj, 'role', None)),
        'is_active': getattr(user_obj, 'is_active', None),
    }


def _format_snapshot(snapshot):
    parts = []
    for key in ['email', 'nom', 'prenom', 'telephone', 'role', 'is_active']:
        value = snapshot.get(key)
        if value in [None, '']:
            continue
        parts.append(f"{key}: {value}")
    return '; '.join(parts) if parts else 'Aucune donnée utile'


def _format_changes(before_snapshot, after_snapshot):
    changed = []
    before_parts = []
    after_parts = []
    keys = ['email', 'nom', 'prenom', 'telephone', 'role', 'is_active']
    for key in keys:
        before_value = before_snapshot.get(key)
        after_value = after_snapshot.get(key)
        before_parts.append(f"{key}: {before_value if before_value not in [None, ''] else '-'}")
        after_parts.append(f"{key}: {after_value if after_value not in [None, ''] else '-'}")
        if str(before_value) == str(after_value):
            continue
        changed.append(f"{key}: {before_value or '-'} -> {after_value or '-'}")
    return {
        'changed': '; '.join(changed) if changed else 'Aucun champ modifié',
        'before': '; '.join(before_parts) if before_parts else 'Aucune donnée utile',
        'after': '; '.join(after_parts) if after_parts else 'Aucune donnée utile',
    }


def _build_creation_details(created_user, actor_user):
    return (
        f"Créé par: {_actor_label(actor_user)}\n"
        f"Valeurs initiales: {_format_snapshot(_user_snapshot(created_user))}"
    )


def _build_update_details(before_snapshot, after_snapshot, actor_user):
    changes = _format_changes(before_snapshot, after_snapshot)
    return (
        f"Modifié par: {_actor_label(actor_user)}\n"
        f"Anciennes valeurs: {changes['before']}\n"
        f"Nouvelles valeurs: {changes['after']}\n"
        f"Modifications: {changes['changed']}"
    )


def _build_deletion_details(deleted_user, actor_user):
    return (
        f"Supprimé par: {_actor_label(actor_user)}\n"
        f"Valeurs avant suppression: {_format_snapshot(_user_snapshot(deleted_user))}"
    )

class LoginView(TokenObtainPairView):
    """Connexion — retourne le token JWT"""
    serializer_class = CustomTokenSerializer


class UtilisateurListView(APIView):
    """Lister et créer des utilisateurs"""
    permission_classes = [IsAdminOrChefService]

    def _manageable_queryset(self, request):
        if request.user.role and request.user.role.nom == 'super_admin':
            return Utilisateur.objects.all()
        return Utilisateur.objects.exclude(role__nom='super_admin').exclude(role__nom='chef_service')

    def _can_manage_role(self, request, role):
        if request.user.role and request.user.role.nom == 'super_admin':
            return True
        return role and role.nom in ['professeur', 'resident']

    def get(self, request):
        users = self._manageable_queryset(request)
        serializer = UtilisateurSerializer(users, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        payload.pop('confirmation_password', None)
        serializer = CreateUtilisateurSerializer(data=payload)
        if serializer.is_valid():
            role = serializer.validated_data.get('role')
            if not self._can_manage_role(request, role):
                return Response({'error': 'Rôle non autorisé'}, status=403)
            user = serializer.save()
            details = _build_creation_details(user, request.user)
            AuditLog.objects.create(
                utilisateur=request.user,
                action='CREATION_UTILISATEUR',
                entite='Utilisateur',
                entite_id=user.id,
                details=details,
                adresse_ip=request.META.get('REMOTE_ADDR')
            )
            return Response(UtilisateurSerializer(user, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UtilisateurDetailView(APIView):
    """Modifier et supprimer un utilisateur"""
    permission_classes = [IsAdminOrChefService]

    def get_object(self, pk):
        try:
            return Utilisateur.objects.get(pk=pk)
        except Utilisateur.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'Utilisateur introuvable'}, status=404)
        serializer = UtilisateurSerializer(user, context={'request': request})
        return Response(serializer.data)

    def put(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'Utilisateur introuvable'}, status=404)
        if request.user.role and request.user.role.nom == 'chef_service' and user.role and user.role.nom in ['super_admin', 'chef_service']:
            return Response({'error': 'Action non autorisée'}, status=403)
        confirmed, error_response = confirm_admin_password(request)
        if not confirmed:
            return error_response

        payload = request.data.copy()
        payload.pop('confirmation_password', None)
        serializer = UpdateUtilisateurSerializer(user, data=payload, partial=True)
        if serializer.is_valid():
            new_role = serializer.validated_data.get('role', user.role)
            if request.user.role and request.user.role.nom == 'chef_service' and new_role and new_role.nom not in ['professeur', 'resident']:
                return Response({'error': 'Rôle non autorisé'}, status=403)
            before_snapshot = _user_snapshot(user)
            serializer.save()
            after_snapshot = _user_snapshot(user)
            AuditLog.objects.create(
                utilisateur=request.user,
                action='MODIFICATION_UTILISATEUR',
                entite='Utilisateur',
                entite_id=user.id,
                details=_build_update_details(before_snapshot, after_snapshot, request.user),
                adresse_ip=request.META.get('REMOTE_ADDR')
            )
            return Response(UtilisateurSerializer(user, context={'request': request}).data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'Utilisateur introuvable'}, status=404)
        confirmed, error_response = confirm_admin_password(request)
        if not confirmed:
            return error_response

        requester_role = getattr(getattr(request, 'user', None), 'role', None)
        requester_role_name = getattr(requester_role, 'nom', None)
        target_role_name = getattr(getattr(user, 'role', None), 'nom', None)

        if requester_role_name == 'chef_service' and target_role_name in ['super_admin', 'chef_service']:
            return Response({'error': 'Action non autorisée'}, status=403)
        if target_role_name == 'super_admin' and requester_role_name != 'super_admin':
            return Response({'error': 'Action non autorisée'}, status=403)
        details = _build_deletion_details(user, request.user)
        AuditLog.objects.create(
            utilisateur=request.user,
            action='SUPPRESSION_UTILISATEUR',
            entite='Utilisateur',
            entite_id=user.id,
            details=details,
            adresse_ip=request.META.get('REMOTE_ADDR')
        )
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleListView(APIView):
    permission_classes = [IsAdminOrChefService]

    def get(self, request):
        if request.user.role and request.user.role.nom == 'super_admin':
            roles = Role.objects.all()
        else:
            roles = Role.objects.filter(nom__in=['professeur', 'resident'])
        return Response(RolePublicSerializer(roles, many=True).data)


class MonProfilView(APIView):
    """Voir son propre profil"""
    def get(self, request):
        serializer = UtilisateurSerializer(request.user, context={'request': request})
        return Response(serializer.data)


class PersonalNotesView(APIView):
    """Consulter et mettre a jour les notes personnelles de l'utilisateur connecte."""

    def get(self, request):
        serializer = PersonalNotesSerializer({'notes': request.user.personal_notes or ''})
        return Response(serializer.data)

    def put(self, request):
        serializer = PersonalNotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.personal_notes = serializer.validated_data.get('notes', '')
        request.user.save(update_fields=['personal_notes'])
        return Response({'notes': request.user.personal_notes})


class UserAuditHistoryView(APIView):
    """Historique des actions utilisateur visibles par les administrateurs."""
    permission_classes = [IsAdminOrChefService]

    def get(self, request):
        entries = (
            AuditLog.objects
            .filter(entite='Utilisateur', action__in=USER_AUDIT_ACTIONS)
            .select_related('utilisateur')
            .order_by('-date')[:50]
        )

        def _actor_name(user_obj):
            if not user_obj:
                return None
            first = getattr(user_obj, 'prenom', None) or ''
            last = getattr(user_obj, 'nom', None) or ''
            full_name = f"{first} {last}".strip()
            return full_name or getattr(user_obj, 'email', None)

        payload = [
            {
                'id': entry.id,
                'action': entry.action,
                'date': entry.date,
                'user': _actor_name(entry.utilisateur),
                'ip': entry.adresse_ip,
                'entite_id': entry.entite_id,
                'details': entry.details or '',
            }
            for entry in entries
        ]
        return Response(payload)


class ConfirmPasswordView(APIView):
    """Confirmer le mot de passe pour accéder aux données sensibles"""
    permission_classes = [IsAdminOrChefService]

    def post(self, request):
        password = request.data.get('password')
        if not password:
            return Response({'error': 'Mot de passe requis'}, status=400)
        if check_password(password, request.user.password):
            return Response({'confirmed': True})
        return Response({'confirmed': False}, status=403)


class MotDePasseUtilisateurView(APIView):
    """Retourne le hash du mot de passe après confirmation du mot de passe de l'utilisateur connecté."""
    permission_classes = [IsAdminOrChefService]

    def post(self, request, pk):
        password = request.data.get('password')
        if not password:
            return Response({'error': 'Mot de passe requis'}, status=400)

        if not check_password(password, request.user.password):
            return Response({'error': 'Confirmation refusée'}, status=403)

        utilisateur = get_object_or_404(Utilisateur, pk=pk)
        AuditLog.objects.create(
            utilisateur=request.user,
            action='CONSULTATION_MOT_DE_PASSE_HASH',
            entite='Utilisateur',
            entite_id=utilisateur.id,
            details=f"Consultation du hash pour: {_format_snapshot(_user_snapshot(utilisateur))}",
            adresse_ip=request.META.get('REMOTE_ADDR')
        )
        return Response({
            'id': utilisateur.id,
            'email': utilisateur.email,
            'password_hash': utilisateur.password,
        })


class ChangePasswordView(APIView):
    """Changer le mot de passe de l'utilisateur connecté"""
    permission_classes = [IsAdminOrChefService]

    def post(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password:
            return Response({'error': 'Le mot de passe actuel est requis'}, status=400)

        if not new_password:
            return Response({'error': 'Le nouveau mot de passe est requis'}, status=400)

        if len(new_password) < 8:
            return Response({'error': 'Le mot de passe doit contenir au moins 8 caractères'}, status=400)

        # Vérifier que le mot de passe actuel est correct
        if not check_password(current_password, request.user.password):
            return Response({'error': 'Le mot de passe actuel est incorrect'}, status=403)

        # Changer le mot de passe
        request.user.set_password(new_password)
        request.user.save()

        # Enregistrer dans l'audit
        AuditLog.objects.create(
            utilisateur=request.user,
            action='MODIFICATION_MOT_DE_PASSE',
            entite='Utilisateur',
            entite_id=request.user.id,
            details=f"Mot de passe modifié pour: {_format_snapshot(_user_snapshot(request.user))}",
            adresse_ip=request.META.get('REMOTE_ADDR')
        )

        return Response({'success': 'Mot de passe modifié avec succès'}, status=200)
