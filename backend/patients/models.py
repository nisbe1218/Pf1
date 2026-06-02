import re

from django.db import models
from django.utils import timezone


class Patient(models.Model):
	SEXE_CHOICES = [
		('M', 'Masculin'),
		('F', 'Féminin'),
		('O', 'Autre'),
	]

	nom = models.CharField(max_length=100)
	prenom = models.CharField(max_length=100)
	age = models.PositiveIntegerField(null=True, blank=True)
	sexe = models.CharField(max_length=1, choices=SEXE_CHOICES, blank=True)
	maladie = models.CharField(max_length=200, blank=True)
	telephone = models.CharField(max_length=20, blank=True)
	adresse = models.CharField(max_length=255, blank=True)
	date_naissance = models.DateField(null=True, blank=True)
	date_admission = models.DateField(default=timezone.localdate)
	id_patient = models.CharField(max_length=120, blank=True)
	id_enregistrement_source = models.CharField(max_length=120, blank=True)
	id_site = models.CharField(max_length=120, blank=True)
	statut_inclusion = models.CharField(max_length=80, blank=True)
	statut_consentement = models.CharField(max_length=80, blank=True)
	date_evaluation_initiale = models.DateField(null=True, blank=True)
	utilisateur_saisie = models.CharField(max_length=120, blank=True)
	derniere_mise_a_jour = models.CharField(max_length=120, blank=True)
	demographie_sexe = models.TextField(blank=True)
	demographie_date_naissance = models.TextField(blank=True)
	demographie_age_ans = models.TextField(blank=True)
	demographie_statut_matrimonial = models.TextField(blank=True)
	demographie_mode_vie = models.TextField(blank=True)
	demographie_zone_residence = models.TextField(blank=True)
	demographie_distance_centre_km = models.TextField(blank=True)
	demographie_couverture_sociale = models.TextField(blank=True)
	demographie_statut_professionnel = models.TextField(blank=True)
	demographie_niveau_education = models.TextField(blank=True)
	demographie_tabagisme = models.TextField(blank=True)
	demographie_alcool = models.TextField(blank=True)
	irc_date_premier_contact_nephrologique = models.TextField(blank=True)
	irc_etiologie_principale = models.TextField(blank=True)
	irc_etiologie_secondaire = models.TextField(blank=True)
	irc_maladie_renale_hereditaire = models.TextField(blank=True)
	irc_antecedents_familiaux_renaux = models.TextField(blank=True)
	irc_statut_biopsie_renale = models.TextField(blank=True)
	irc_resultat_biopsie_renale = models.TextField(blank=True)
	irc_connue_avant_dialyse = models.TextField(blank=True)
	irc_source_adressage = models.TextField(blank=True)
	irc_contexte_debut_dialyse = models.TextField(blank=True)
	irc_themes_education_therapeutique = models.TextField(blank=True)
	irc_niveau_comprehension_patient = models.TextField(blank=True)
	irc_preference_therapie_renale = models.TextField(blank=True)
	comorbidite_statut_diabete = models.TextField(blank=True)
	comorbidite_liste = models.TextField(blank=True)
	comorbidite_autre = models.TextField(blank=True)
	icc_charlson = models.CharField(max_length=10, blank=True, null=True)
	presentation_date_episode = models.TextField(blank=True)
	presentation_lieu_debut = models.TextField(blank=True)
	presentation_raisons_debut = models.TextField(blank=True)
	presentation_symptomes = models.TextField(blank=True)
	presentation_tas_mmhg = models.TextField(blank=True)
	presentation_tad_mmhg = models.TextField(blank=True)
	presentation_frequence_cardiaque_bpm = models.TextField(blank=True)
	presentation_temperature_c = models.TextField(blank=True)
	presentation_poids_kg = models.TextField(blank=True)
	presentation_taille_cm = models.TextField(blank=True)
	presentation_statut_diurese = models.TextField(blank=True)
	presentation_volume_urinaire_ml_j = models.TextField(blank=True)
	presentation_autonomie_fonctionnelle = models.TextField(blank=True)
	presentation_notes_examen_clinique = models.TextField(blank=True)
	biologie_date_prelevement = models.TextField(blank=True)
	biologie_creatinine_mg_l = models.TextField(blank=True)
	biologie_uree_g_l = models.TextField(blank=True)
	biologie_hemoglobine_g_dl = models.TextField(blank=True)
	biologie_hba1c_pct = models.TextField(blank=True)
	biologie_leucocytes_g_l = models.TextField(blank=True)
	biologie_plaquettes_g_l = models.TextField(blank=True)
	biologie_albumine_g_l = models.TextField(blank=True)
	biologie_crp_mg_l = models.TextField(blank=True)
	biologie_sodium_mmol_l = models.TextField(blank=True)
	biologie_potassium_mmol_l = models.TextField(blank=True)
	biologie_bicarbonates_mmol_l = models.TextField(blank=True)
	biologie_calcium_corrige_mg_l = models.TextField(blank=True)
	biologie_phosphore_mg_l = models.TextField(blank=True)
	biologie_pth_pg_ml = models.TextField(blank=True)
	biologie_ferritine_ng_ml = models.TextField(blank=True)
	biologie_saturation_transferrine_pct = models.TextField(blank=True)
	biologie_vitamine_d_ng_ml = models.TextField(blank=True)
	biologie_proteinurie_g_24h = models.TextField(blank=True)
	biologie_hbsag = models.TextField(blank=True)
	biologie_vhc = models.TextField(blank=True)
	biologie_vih = models.TextField(blank=True)
	imagerie_date_echographie_renale = models.TextField(blank=True)
	imagerie_taille_reins = models.TextField(blank=True)
	imagerie_echogenicite_renale = models.TextField(blank=True)
	imagerie_hydronephrose = models.TextField(blank=True)
	imagerie_kystes_renaux = models.TextField(blank=True)
	imagerie_lithiase = models.TextField(blank=True)
	imagerie_radiographie_thorax = models.TextField(blank=True)
	imagerie_date_echocardiographie = models.TextField(blank=True)
	imagerie_fevg_pct = models.TextField(blank=True)
	imagerie_hypertrophie_ventriculaire_gauche = models.TextField(blank=True)
	imagerie_valvulopathie = models.TextField(blank=True)
	imagerie_autres_resultats = models.TextField(blank=True)
	dialyse_date_debut = models.TextField(blank=True)
	dialyse_modalite_initiale = models.TextField(blank=True)
	dialyse_modalite_actuelle = models.TextField(blank=True)
	dialyse_type_acces_initial = models.TextField(blank=True)
	dialyse_site_acces_initial = models.TextField(blank=True)
	dialyse_date_creation_acces = models.TextField(blank=True)
	dialyse_date_premiere_utilisation_acces = models.TextField(blank=True)
	dialyse_seances_par_semaine = models.TextField(blank=True)
	dialyse_duree_seance_min = models.TextField(blank=True)
	dialyse_debit_sanguin_ml_min = models.TextField(blank=True)
	dialyse_debit_dialysat_ml_min = models.TextField(blank=True)
	dialyse_potassium_dialysat_mmol_l = models.TextField(blank=True)
	dialyse_calcium_dialysat_mmol_l = models.TextField(blank=True)
	dialyse_type_anticoagulation = models.TextField(blank=True)
	dialyse_statut_fonction_renale_residuelle = models.TextField(blank=True)
	dialyse_type_regime_dp = models.TextField(blank=True)
	dialyse_nombre_echanges_dp_jour = models.TextField(blank=True)
	dialyse_volume_stase_dp_ml = models.TextField(blank=True)
	dialyse_information_transplantation_donnee = models.TextField(blank=True)
	dialyse_statut_liste_attente_transplantation = models.TextField(blank=True)
	qualite_date_evaluation = models.TextField(blank=True)
	qualite_spktv = models.TextField(blank=True)
	qualite_urr_pct = models.TextField(blank=True)
	qualite_prise_poids_interdialytique_kg = models.TextField(blank=True)
	qualite_taux_ultrafiltration_ml_kg_h = models.TextField(blank=True)
	qualite_tas_predialyse_mmhg = models.TextField(blank=True)
	qualite_tas_postdialyse_mmhg = models.TextField(blank=True)
	qualite_poids_sec_kg = models.TextField(blank=True)
	qualite_seances_manquees_30j = models.TextField(blank=True)
	qualite_seances_raccourcies_30j = models.TextField(blank=True)
	qualite_hypotensions_intradialytiques_30j = models.TextField(blank=True)
	qualite_observance_declaree_patient = models.TextField(blank=True)
	traitement_medicaments_renaux_actuels = models.TextField(blank=True)
	traitement_autres_notes = models.TextField(blank=True)
	complication_debut_periode_suivi = models.TextField(blank=True)
	complication_fin_periode_suivi = models.TextField(blank=True)
	complication_liste = models.TextField(blank=True)
	complication_date_premier_evenement = models.TextField(blank=True)
	complication_nombre_hospitalisations = models.TextField(blank=True)
	complication_jours_hospitalisation = models.TextField(blank=True)
	complication_motifs_hospitalisation = models.TextField(blank=True)
	complication_changement_modalite_dialyse = models.TextField(blank=True)
	complication_autres_notes = models.TextField(blank=True)
	devenir_date_dernier_suivi = models.TextField(blank=True)
	devenir_statut = models.TextField(blank=True)
	devenir_date_deces = models.TextField(blank=True)
	devenir_cause_deces = models.TextField(blank=True)
	devenir_date_transplantation = models.TextField(blank=True)
	devenir_qualite_vie = models.TextField(blank=True)
	devenir_categorie_pronostique = models.TextField(blank=True)
	devenir_notes = models.TextField(blank=True)
	demographie_data = models.JSONField(default=dict, blank=True)
	irc_data = models.JSONField(default=dict, blank=True)
	comorbidite_data = models.JSONField(default=dict, blank=True)
	presentation_data = models.JSONField(default=dict, blank=True)
	biologie_data = models.JSONField(default=dict, blank=True)
	imagerie_data = models.JSONField(default=dict, blank=True)
	dialyse_data = models.JSONField(default=dict, blank=True)
	qualite_data = models.JSONField(default=dict, blank=True)
	complication_data = models.JSONField(default=dict, blank=True)
	traitement_data = models.JSONField(default=dict, blank=True)
	devenir_data = models.JSONField(default=dict, blank=True)
	extra_data = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at', '-id']

	def _numeric_suffix(self, value):
		if value is None:
			return None
		match = re.search(r'(\d+)$', str(value).strip())
		if not match:
			return None
		return match.group(1)

	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)

		updates = []
		if not self.id_patient:
			self.id_patient = f"PAT-{self.pk:06d}"
			updates.append('id_patient')
		patient_number = self._numeric_suffix(self.id_patient)
		if patient_number:
			expected_source = f"SRC-{int(patient_number):06d}"
		else:
			expected_source = f"SRC-{self.pk:06d}"
		if self.id_enregistrement_source != expected_source:
			self.id_enregistrement_source = expected_source
			updates.append('id_enregistrement_source')

		section_field_mappings = {
		    'demographie_data': [
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
		    ],
		    'irc_data': [
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
		    ],
		    'comorbidite_data': [
		        'comorbidite_statut_diabete',
		        'comorbidite_liste',
		        'comorbidite_autre',
		    ],
		    'presentation_data': [
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
		    ],
		    'biologie_data': [
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
		    ],
		    'imagerie_data': [
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
		    ],
		    'dialyse_data': [
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
		    ],
		    'qualite_data': [
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
		    ],
		    'complication_data': [
		        'complication_debut_periode_suivi',
		        'complication_fin_periode_suivi',
		        'complication_liste',
		        'complication_date_premier_evenement',
		        'complication_nombre_hospitalisations',
		        'complication_jours_hospitalisation',
		        'complication_motifs_hospitalisation',
		        'complication_changement_modalite_dialyse',
		        'complication_autres_notes',
		    ],
		    'traitement_data': [
		        'traitement_medicaments_renaux_actuels',
		        'traitement_autres_notes',
		    ],
		    'devenir_data': [
		        'devenir_date_dernier_suivi',
		        'devenir_statut',
		        'devenir_date_deces',
		        'devenir_cause_deces',
		        'devenir_date_transplantation',
		        'devenir_qualite_vie',
		        'devenir_categorie_pronostique',
		        'devenir_notes',
		    ],
		}

		for section_field, keys in section_field_mappings.items():
			section_data = getattr(self, section_field) or {}
			for key in keys:
				raw_value = section_data.get(key)
				if raw_value is None:
					normalized_value = ''
				else:
					normalized_value = str(raw_value)
				if getattr(self, key, '') != normalized_value:
					setattr(self, key, normalized_value)
					updates.append(key)

		if updates:
			super().save(update_fields=list(dict.fromkeys(updates)))

	def __str__(self):
		return f"{self.prenom} {self.nom}"


class PatientFormTemplate(models.Model):
	name = models.CharField(max_length=150)
	source_file_name = models.CharField(max_length=255, blank=True)
	sheet_name = models.CharField(max_length=150, blank=True)
	imported_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.name


class PatientFormField(models.Model):
	FIELD_TYPES = [
		('text_short', 'Texte libre court'),
		('text_long', 'Texte libre long'),
		('single_choice', 'Choix unique'),
		('multiple_choice', 'Choix multiple'),
		('date', 'Sélecteur de date'),
		('integer', 'Nombre entier'),
		('decimal', 'Nombre décimal'),
		('boolean', 'Oui / Non'),
		('auto', 'Automatique'),
	]

	template = models.ForeignKey(PatientFormTemplate, related_name='fields', on_delete=models.CASCADE)
	key = models.CharField(max_length=150)
	label = models.CharField(max_length=255)
	field_type = models.CharField(max_length=30, choices=FIELD_TYPES)
	order = models.PositiveIntegerField()
	choices = models.JSONField(default=list, blank=True)
	source_hint = models.CharField(max_length=255, blank=True)
	import_file = models.CharField(max_length=255, blank=True, default='')
	is_required = models.BooleanField(default=False)

	class Meta:
		unique_together = ('template', 'key')
		ordering = ['order', 'id']

	def __str__(self):
		return f"{self.template.name} - {self.label}"


class PreprocessValidationRequest(models.Model):
	STATUS_CHOICES = [
		('pending', 'En attente de validation'),
		('approved', 'Validé et intégré'),
		('rejected', 'Rejeté'),
	]

	session_id = models.CharField(max_length=64)
	source = models.CharField(max_length=20, default='corrected')  # 'corrected' or 'original'
	source_file_name = models.CharField(max_length=255, blank=True)
	submitted_by = models.ForeignKey(
		'users.Utilisateur', on_delete=models.SET_NULL, null=True, related_name='submitted_validations'
	)
	submitted_at = models.DateTimeField(auto_now_add=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
	reviewed_by = models.ForeignKey(
		'users.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_validations'
	)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	comment = models.TextField(blank=True)
	rows_count = models.PositiveIntegerField(default=0)
	columns_count = models.PositiveIntegerField(default=0)
	quality_score = models.FloatField(null=True, blank=True)

	class Meta:
		ordering = ['-submitted_at']

	def __str__(self):
		return f"Validation {self.session_id[:8]} — {self.status}"


class DynamicColumnRequest(models.Model):
	ACTION_CHOICES = [
		('add',    'Ajout de colonne'),
		('delete', 'Suppression de colonne'),
	]
	STATUS_CHOICES = [
		('pending',  'En attente'),
		('approved', 'Approuvé'),
		('rejected', 'Rejeté'),
	]

	action       = models.CharField(max_length=10, choices=ACTION_CHOICES)
	column_key   = models.CharField(max_length=150)
	column_label = models.CharField(max_length=255, blank=True)
	field_type   = models.CharField(max_length=30, default='text_short')
	submitted_by = models.ForeignKey(
		'users.Utilisateur', on_delete=models.SET_NULL, null=True,
		related_name='dynamic_column_requests'
	)
	submitted_at = models.DateTimeField(auto_now_add=True)
	status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
	reviewed_by  = models.ForeignKey(
		'users.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True,
		related_name='reviewed_column_requests'
	)
	reviewed_at  = models.DateTimeField(null=True, blank=True)
	comment      = models.TextField(blank=True)

	class Meta:
		ordering = ['-submitted_at']

	def __str__(self):
		return f"{self.get_action_display()} — {self.column_key} ({self.status})"