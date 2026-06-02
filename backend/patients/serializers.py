from rest_framework import serializers

from .models import Patient, PatientFormTemplate, PatientFormField


EXCLUDED_SCHEMA_FIELD_KEYS = {
    'irc_duree_suivi_predialytique_mois',
}


class PatientSerializer(serializers.ModelSerializer):
    extra_data = serializers.JSONField(required=False, default=dict)
    nom = serializers.CharField(required=False, allow_blank=True)
    prenom = serializers.CharField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        if 'extra_data' in validated_data:
            existing = instance.extra_data or {}
            existing.update(validated_data['extra_data'])
            validated_data['extra_data'] = existing
        return super().update(instance, validated_data)

    class Meta:
        model = Patient
        fields = [
            'id',
            'nom',
            'prenom',
            'age',
            'sexe',
            'maladie',
            'telephone',
            'adresse',
            'date_naissance',
            'date_admission',
            'id_patient',
            'id_enregistrement_source',
            'id_site',
            'statut_inclusion',
            'statut_consentement',
            'date_evaluation_initiale',
            'utilisateur_saisie',
            'derniere_mise_a_jour',
            'demographie_sexe',
            'demographie_date_naissance',
            'demographie_age_ans',
            'demographie_statut_matrimonial',
            'demographie_mode_vie',
            'demographie_zone_residence',
            'demographie_distance_centre_km',
            'demographie_couverture_sociale',
            'demographie_statut_professionnel',
            'demographie_niveau_education',
            'demographie_tabagisme',
            'demographie_alcool',
            'irc_date_premier_contact_nephrologique',
            'irc_etiologie_principale',
            'irc_etiologie_secondaire',
            'irc_maladie_renale_hereditaire',
            'irc_antecedents_familiaux_renaux',
            'irc_statut_biopsie_renale',
            'irc_resultat_biopsie_renale',
            'irc_connue_avant_dialyse',
            'irc_source_adressage',
            'irc_contexte_debut_dialyse',
            'irc_themes_education_therapeutique',
            'irc_niveau_comprehension_patient',
            'irc_preference_therapie_renale',
            'icc_charlson',
            'comorbidite_statut_diabete',
            'comorbidite_liste',
            'comorbidite_autre',
            'presentation_date_episode',
            'presentation_lieu_debut',
            'presentation_raisons_debut',
            'presentation_symptomes',
            'presentation_tas_mmhg',
            'presentation_tad_mmhg',
            'presentation_frequence_cardiaque_bpm',
            'presentation_temperature_c',
            'presentation_poids_kg',
            'presentation_taille_cm',
            'presentation_statut_diurese',
            'presentation_volume_urinaire_ml_j',
            'presentation_autonomie_fonctionnelle',
            'presentation_notes_examen_clinique',
            'biologie_date_prelevement',
            'biologie_creatinine_mg_l',
            'biologie_uree_g_l',
            'biologie_hemoglobine_g_dl',
            'biologie_hba1c_pct',
            'biologie_leucocytes_g_l',
            'biologie_plaquettes_g_l',
            'biologie_albumine_g_l',
            'biologie_crp_mg_l',
            'biologie_sodium_mmol_l',
            'biologie_potassium_mmol_l',
            'biologie_bicarbonates_mmol_l',
            'biologie_calcium_corrige_mg_l',
            'biologie_phosphore_mg_l',
            'biologie_pth_pg_ml',
            'biologie_ferritine_ng_ml',
            'biologie_saturation_transferrine_pct',
            'biologie_vitamine_d_ng_ml',
            'biologie_proteinurie_g_24h',
            'biologie_hbsag',
            'biologie_vhc',
            'biologie_vih',
            'imagerie_date_echographie_renale',
            'imagerie_taille_reins',
            'imagerie_echogenicite_renale',
            'imagerie_hydronephrose',
            'imagerie_kystes_renaux',
            'imagerie_lithiase',
            'imagerie_radiographie_thorax',
            'imagerie_date_echocardiographie',
            'imagerie_fevg_pct',
            'imagerie_hypertrophie_ventriculaire_gauche',
            'imagerie_valvulopathie',
            'imagerie_autres_resultats',
            'dialyse_date_debut',
            'dialyse_modalite_initiale',
            'dialyse_modalite_actuelle',
            'dialyse_type_acces_initial',
            'dialyse_site_acces_initial',
            'dialyse_date_creation_acces',
            'dialyse_date_premiere_utilisation_acces',
            'dialyse_seances_par_semaine',
            'dialyse_duree_seance_min',
            'dialyse_debit_sanguin_ml_min',
            'dialyse_debit_dialysat_ml_min',
            'dialyse_potassium_dialysat_mmol_l',
            'dialyse_calcium_dialysat_mmol_l',
            'dialyse_type_anticoagulation',
            'dialyse_statut_fonction_renale_residuelle',
            'dialyse_type_regime_dp',
            'dialyse_nombre_echanges_dp_jour',
            'dialyse_volume_stase_dp_ml',
            'dialyse_information_transplantation_donnee',
            'dialyse_statut_liste_attente_transplantation',
            'qualite_date_evaluation',
            'qualite_spktv',
            'qualite_urr_pct',
            'qualite_prise_poids_interdialytique_kg',
            'qualite_taux_ultrafiltration_ml_kg_h',
            'qualite_tas_predialyse_mmhg',
            'qualite_tas_postdialyse_mmhg',
            'qualite_poids_sec_kg',
            'qualite_seances_manquees_30j',
            'qualite_seances_raccourcies_30j',
            'qualite_hypotensions_intradialytiques_30j',
            'qualite_observance_declaree_patient',
            'traitement_medicaments_renaux_actuels',
            'traitement_autres_notes',
            'complication_debut_periode_suivi',
            'complication_fin_periode_suivi',
            'complication_liste',
            'complication_date_premier_evenement',
            'complication_nombre_hospitalisations',
            'complication_jours_hospitalisation',
            'complication_motifs_hospitalisation',
            'complication_changement_modalite_dialyse',
            'complication_autres_notes',
            'devenir_date_dernier_suivi',
            'devenir_statut',
            'devenir_date_deces',
            'devenir_cause_deces',
            'devenir_date_transplantation',
            'devenir_qualite_vie',
            'devenir_categorie_pronostique',
            'devenir_notes',
            'demographie_data',
            'irc_data',
            'comorbidite_data',
            'presentation_data',
            'biologie_data',
            'imagerie_data',
            'dialyse_data',
            'qualite_data',
            'complication_data',
            'traitement_data',
            'devenir_data',
            'extra_data',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class PatientFormFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientFormField
        fields = [
            'id', 'key', 'label', 'field_type', 'order',
            'choices', 'source_hint', 'import_file', 'is_required',
        ]


class PatientFormTemplateSerializer(serializers.ModelSerializer):
    fields = PatientFormFieldSerializer(many=True, read_only=True)

    class Meta:
        model = PatientFormTemplate
        fields = ['id', 'name', 'source_file_name', 'sheet_name', 'imported_at', 'fields']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['fields'] = [
            field for field in data.get('fields', [])
            if field.get('key')
            and field.get('key') not in EXCLUDED_SCHEMA_FIELD_KEYS
            and not field.get('key').startswith('unnamed')
            and field.get('source_hint') != 'auto_detected_from_data_import'
        ]
        return data