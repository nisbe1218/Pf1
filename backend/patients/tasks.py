import json
import os
import uuid
from celery import shared_task
from django.utils import timezone
from .views import (
    _append_preprocess_event,
    _load_preprocess_session,
    _read_uploaded_dataframe,
    _build_technical_profile,
    _determine_preprocess_route,
    _call_ollama_qwen_analysis,
    _build_preprocess_chunks,
    _build_retrieval_context,
    _apply_llm_correction_plan,
    _run_bio_value_correction_pass,
    _run_llm_flagged_corrections,
    _run_model_imputation,
    _build_preprocess_report,
    _dataframe_to_rows,
    _save_preprocess_session,
    resolve_entry_user_label,
)


@shared_task(bind=True, name='patients.analyze_preprocess')
def analyze_preprocess_async(self, session_id, file_path, user_id, use_llm=True):
    """
    Async task to perform LLM analysis on uploaded file.
    Updates session with results or error status.
    """
    def update_session_progress(msg):
        """Update session with progress message"""
        try:
            session = _load_preprocess_session(session_id)
            if not session:
                return
            session['progress_message'] = msg
            _append_preprocess_event(
                session,
                event_type='progress_update',
                event_data={
                    'status': session.get('status', 'pending'),
                    'message': msg,
                },
            )
            _save_preprocess_session(session)
        except Exception as e:
            print(f"Could not update progress: {e}")

    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)
    except Exception as e:
        print(f"Could not load user {user_id}: {e}")
        user = None

    try:
        update_session_progress("Lecture du fichier...")
        # Read file from temporary path
        with open(file_path, 'rb') as f:
            from django.core.files.uploadedfile import SimpleUploadedFile
            file_name = os.path.basename(file_path)
            uploaded_file = SimpleUploadedFile(file_name, f.read())

        update_session_progress("Profilage technique...")
        dataframe, source_file_name = _read_uploaded_dataframe(uploaded_file)
        technical_profile = _build_technical_profile(dataframe)

        update_session_progress("Découpage intelligent en chunks...")
        chunks = _build_preprocess_chunks(dataframe, technical_profile)
        update_session_progress(f"Chunks détectés: {len(chunks)}")
        retrieval_context = _build_retrieval_context(
            dataframe, chunks, technical_profile,
            stage_name='diagnostic',
            max_chunks=3,
            progress_callback=update_session_progress,
        )
        update_session_progress(f"Retrieval: {retrieval_context.get('retrieval_policy')}")

        # Call LLM only (this might take time, hence async)
        if not use_llm:
            update_session_progress("Mode LLM forcé: le paramètre use_llm est ignoré.")

        route = _determine_preprocess_route(technical_profile)
        update_session_progress(
            f"Route LLM {route.get('label')} avec {route.get('primary_model')}..."
        )
        update_session_progress("Construction du contexte de retrieval...")
        llm_analysis = _call_ollama_qwen_analysis(
            dataframe,
            technical_profile,
            progress_callback=update_session_progress,
            precomputed_chunks=chunks,
            precomputed_retrieval_context=retrieval_context,
        )

        update_session_progress("Application du plan de correction LLM...")
        corrected_df, applied_actions = _apply_llm_correction_plan(dataframe, llm_analysis)
        n_corrections = sum(a.get('cells_changed', 0) for a in applied_actions)
        update_session_progress(f"Plan LLM appliqué: {len(applied_actions)} action(s), {n_corrections} cellule(s) modifiée(s).")

        update_session_progress("Correction des valeurs biologiques aberrantes (KB médicale)...")
        bio_mappings, bio_actions = _run_bio_value_correction_pass(
            corrected_df,
            progress_callback=update_session_progress,
        )
        if bio_mappings:
            corrected_df = corrected_df.replace(bio_mappings)
            applied_actions.extend(bio_actions)

        # Extract columns already handled by bio pass
        bio_corrected_cols = set()
        for bio_action in bio_actions:
            for col_detail in (bio_action.get('details', {}).get('columns') or []):
                if isinstance(col_detail, dict) and col_detail.get('column'):
                    bio_corrected_cols.add(col_detail['column'])

        update_session_progress("Correction LLM des valeurs aberrantes détectées...")
        llm_issues = llm_analysis.get('issues') if isinstance(llm_analysis, dict) else []
        flagged_mappings, flagged_actions, knn_columns = _run_llm_flagged_corrections(
            corrected_df,
            llm_issues=llm_issues or [],
            already_corrected_columns=bio_corrected_cols,
            progress_callback=update_session_progress,
        )
        if flagged_mappings:
            corrected_df = corrected_df.replace(flagged_mappings)
            applied_actions.extend(flagged_actions)

        update_session_progress("Imputation KNN des valeurs nullifiées (estimation contextuelle)...")
        corrected_df, knn_report = _run_model_imputation(
            corrected_df,
            columns_to_impute=knn_columns,
            n_neighbors=5,
            progress_callback=update_session_progress,
        )
        if knn_report:
            applied_actions.append({
                'action': 'knn_imputation',
                'count': sum(r['imputed_count'] for r in knn_report),
                'cells_changed': sum(r['imputed_count'] for r in knn_report),
                'details': {'columns': knn_report, 'needs_review': True},
            })

        update_session_progress("Génération du rapport final...")
        report = _build_preprocess_report(
            dataframe,
            technical_profile,
            llm_analysis=llm_analysis,
            corrected_df=corrected_df,
            applied_actions=applied_actions,
        )

        report['pipeline'] = llm_analysis.get('pipeline') if isinstance(llm_analysis, dict) else {}
        report['route'] = llm_analysis.get('route') if isinstance(llm_analysis, dict) else {}
        llm_internal_status = report.get('llm_internal_status') if isinstance(report, dict) else {}
        confidence_contract = llm_internal_status.get('confidence_contract') if isinstance(llm_internal_status, dict) else {}

        # Build and save session
        update_session_progress("Finalisation...")
        session = {
            'id': session_id,
            'created_at': timezone.now().isoformat(),
            'created_by': resolve_entry_user_label(user) if user else 'system',
            'source_file_name': source_file_name,
            'columns': [str(col) for col in corrected_df.columns.tolist()],
            'original_rows': _dataframe_to_rows(dataframe),
            'corrected_rows': _dataframe_to_rows(corrected_df),
            'report': report,
            'change_log': [],
            'status': 'completed',
            'error': None,
            'progress_message': 'Analyse terminée avec succès!',
        }
        session['monitoring_snapshot'] = {
            'confidence_score': confidence_contract.get('confidence_score'),
            'risk_level': confidence_contract.get('risk_level'),
            'requires_review': confidence_contract.get('requires_review'),
            'second_pass_status': ((llm_internal_status.get('second_pass') or {}).get('status') if isinstance(llm_internal_status, dict) else None),
            'visible_issues_count': (report.get('summary') or {}).get('total_issues'),
            'internal_issues_count': (report.get('summary') or {}).get('internal_issues_count'),
        }
        _append_preprocess_event(
            session,
            event_type='analysis_completed',
            event_data={
                'status': 'completed',
                'confidence_score': confidence_contract.get('confidence_score'),
                'risk_level': confidence_contract.get('risk_level'),
                'requires_review': confidence_contract.get('requires_review'),
                'total_issues': (report.get('summary') or {}).get('total_issues'),
                'internal_issues_count': (report.get('summary') or {}).get('internal_issues_count'),
                'second_pass_status': ((llm_internal_status.get('second_pass') or {}).get('status') if isinstance(llm_internal_status, dict) else None),
            },
        )
        _save_preprocess_session(session)

        # Clean up temp file
        try:
            os.remove(file_path)
        except Exception:
            pass

    except Exception as e:
        print(f"Error in analyze_preprocess_async for session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Save error session
        try:
            session = _load_preprocess_session(session_id) or {}
        except Exception:
            session = {}
        
        session.update({
            'id': session_id,
            'created_at': timezone.now().isoformat(),
            'created_by': resolve_entry_user_label(user) if user else 'system',
            'source_file_name': '',
            'columns': [],
            'original_rows': [],
            'corrected_rows': [],
            'report': {},
            'change_log': [],
            'status': 'error',
            'error': str(e),
            'progress_message': f'Erreur: {str(e)}',
        })
        _append_preprocess_event(
            session,
            event_type='analysis_failed',
            event_data={'status': 'error', 'error': str(e)},
        )
        _save_preprocess_session(session)

        # Clean up temp file
        try:
            os.remove(file_path)
        except Exception:
            pass

        raise
