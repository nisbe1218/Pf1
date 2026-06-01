import hashlib
import json
import os
from math import sqrt
from urllib import error as urllib_error
from urllib import request as urllib_request

import pandas as pd

try:
    import chromadb
except Exception:  # pragma: no cover - optional dependency
    chromadb = None

_MEDICAL_KB_PATH = os.path.join(os.path.dirname(__file__), 'medical_kb.json')
_medical_kb_cache = None


def _load_medical_kb():
    global _medical_kb_cache
    if _medical_kb_cache is not None:
        return _medical_kb_cache
    try:
        with open(_MEDICAL_KB_PATH, encoding='utf-8') as fh:
            _medical_kb_cache = json.load(fh).get('documents', [])
    except Exception:
        _medical_kb_cache = []
    return _medical_kb_cache


def build_medical_rag_context(column_names, max_entries=8):
    """Return a compact medical reference block for column_names, or '' if nothing matched."""
    documents = _load_medical_kb()
    if not documents or not column_names:
        return ''

    normalized_columns = [str(c).lower() for c in column_names]
    matched = []
    for doc in documents:
        patterns = [str(p).lower() for p in doc.get('patterns', [])]
        if any(
            pat in col or col in pat
            for pat in patterns
            for col in normalized_columns
        ):
            matched.append(doc)
        if len(matched) >= max_entries:
            break

    if not matched:
        return ''

    lines = ['Normes medicales de reference (nephrologie/dialyse):']
    for doc in matched:
        normal = doc.get('normal', [None, None])
        unit = doc.get('unit', '')
        label = doc.get('label', doc.get('id', ''))
        crit_low = doc.get('critical_low')
        crit_high = doc.get('critical_high')
        notes = doc.get('notes', '')
        errors = doc.get('common_errors', [])

        parts = [f'- {label}: Normal {normal[0]}-{normal[1]} {unit}.']
        if crit_low is not None and crit_high is not None:
            parts.append(f'Critique < {crit_low} ou > {crit_high}.')
        if notes:
            parts.append(notes)
        if errors:
            parts.append('Erreurs courantes: ' + '; '.join(errors[:2]) + '.')
        lines.append(' '.join(parts))

    return '\n'.join(lines)


def _normalize_text(value):
    text = str(value or '').strip().lower()
    return ''.join(character if character.isalnum() else '_' for character in text).strip('_')


def _env_bool(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() not in {'0', 'false', 'no', 'non', ''}


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return int(default)


def _get_ollama_candidate_bases():
    # Prefer explicit base set by docker/env: OLLAMA_BASE_URL
    configured_base = str(os.environ.get('OLLAMA_BASE_URL', '') or os.environ.get('OLLAMA_URL', '')).rstrip('/')
    fallback_base = str(os.environ.get('OLLAMA_FALLBACK_URL', '')).rstrip('/')
    running_in_docker = os.path.exists('/.dockerenv')
    # Use host.docker.internal inside containers by default when provided by env.
    # Fallback to 'http://ollama:11434' for legacy compose setups when running in docker,
    # otherwise use localhost for local development.
    default_base = 'http://ollama:11434' if running_in_docker else 'http://127.0.0.1:11434'

    candidate_bases = []
    for base in [configured_base, fallback_base, default_base]:
        normalized_base = str(base).rstrip('/')
        if normalized_base and normalized_base not in candidate_bases:
            candidate_bases.append(normalized_base)
    return candidate_bases


def _get_embedding_model_name():
    return os.environ.get('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')


def _get_chroma_persist_dir():
    persist_dir = os.environ.get('CHROMA_PERSIST_DIR', '/tmp/preprocess/chroma')
    os.makedirs(persist_dir, exist_ok=True)
    return persist_dir


def _build_collection_name(technical_profile):
    payload = {
        'rows': int(technical_profile.get('rows') or 0),
        'columns': int(technical_profile.get('columns') or 0),
        'missing_pct': float(technical_profile.get('missing_pct') or 0.0),
        'duplicate_rows': int(technical_profile.get('duplicate_rows') or 0),
        'column_names': [str(name) for name in (technical_profile.get('column_names') or [])[:60]],
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:24]
    return f'preprocess_{digest}'


def _chunk_frame(dataframe, chunk):
    columns = [str(column) for column in chunk.get('columns', [])]
    if not columns:
        return dataframe.iloc[0:0]

    rows_range = chunk.get('rows_range') or [0, -1]
    start_index = int(rows_range[0] or 0)
    end_index = int(rows_range[1] or -1)
    if end_index < start_index:
        return dataframe.iloc[0:0][columns]

    return dataframe.iloc[start_index:end_index + 1][columns]


def _critical_signals_for_columns(columns):
    critical_tokens = [
        'deces', 'dialyse', 'biologie', 'albumine', 'hemoglobine', 'creatinine',
        'phosphore', 'calcium', 'infection', 'hospitalisation', 'transplant',
        'complication', 'urgence', 'cardio', 'cardiaque', 'renal', 'rein',
    ]
    signals = []
    for column_name in columns:
        normalized = _normalize_text(column_name)
        if any(token in normalized for token in critical_tokens):
            signals.append(str(column_name))
    return list(dict.fromkeys(signals))


# String tokens that indicate a value is a disguised missing rather than real data
_DISGUISED_MISSING_TOKENS = {
    'n/a', 'na', 'nan', 'null', 'none', 'nil', '?', '-', '--', '---',
    'inconnu', 'inconnue', 'unknown', 'nd', 'nr', 'ns', 'nc',
    'non renseigne', 'non renseignee', 'non disponible', 'not available',
    'not applicable', 'missing', 'vide', 'absent', 'absente',
    '#n/a', '#value!', '#ref!', 'inf', '-inf', 'inf.', 'indisponible',
}


def _analyse_column_semantics(series, col_name):
    """Return a rich semantic profile for a single column to help the LLM detect issues."""
    entry = {}
    dtype_str = str(series.dtype).lower()
    is_numeric = 'int' in dtype_str or 'float' in dtype_str
    is_object = 'object' in dtype_str or 'str' in dtype_str or 'category' in dtype_str

    non_null = series.dropna()
    total = len(series)
    non_null_count = len(non_null)

    # Representative samples — up to 8 distinct non-null values
    samples = list(dict.fromkeys(non_null.astype(str).tolist()))[:8]
    if samples:
        entry['samples'] = samples

    # Disguised missing detection (object / mixed columns)
    if is_object or not is_numeric:
        values_lower = non_null.astype(str).str.strip().str.lower()
        disguised_mask = values_lower.isin(_DISGUISED_MISSING_TOKENS)
        disguised_series = values_lower[disguised_mask]
        if len(disguised_series) > 0:
            counts = disguised_series.value_counts().head(5).to_dict()
            entry['disguised_missing'] = {str(k): int(v) for k, v in counts.items()}

    # Value distribution for low-cardinality categorical columns
    if is_object:
        unique_count = int(non_null.nunique())
        entry['unique_count'] = unique_count
        if 0 < unique_count <= 30:
            vc = non_null.astype(str).value_counts().head(10)
            entry['value_distribution'] = {str(k): int(v) for k, v in vc.items()}

    # Numeric stats + actual outlier values
    if is_numeric:
        numeric = pd.to_numeric(series, errors='coerce').dropna()
        if len(numeric) > 0:
            _unique_num = set(numeric.unique())
            _is_binary = _unique_num.issubset({0, 1, 0.0, 1.0})
            if _is_binary:
                entry['is_binary'] = True
                entry['numeric_stats'] = {
                    'min': float(numeric.min()),
                    'max': float(numeric.max()),
                    'median': float(numeric.median()),
                    'q1': 0.0,
                    'q3': 1.0,
                }
            else:
                q1 = float(numeric.quantile(0.25))
                q3 = float(numeric.quantile(0.75))
                iqr = q3 - q1
                lower_fence = q1 - 3 * iqr
                upper_fence = q3 + 3 * iqr
                outlier_vals = numeric[(numeric < lower_fence) | (numeric > upper_fence)]
                entry['numeric_stats'] = {
                    'min': float(numeric.min()),
                    'max': float(numeric.max()),
                    'median': float(numeric.median()),
                    'q1': round(q1, 3),
                    'q3': round(q3, 3),
                }
                if len(outlier_vals) > 0:
                    entry['outlier_values'] = [round(float(v), 4) for v in outlier_vals.head(5).tolist()]
                    entry['outlier_count'] = int(len(outlier_vals))

    return entry if entry else None


def _summarize_chunk(dataframe, chunk, technical_profile):
    chunk_frame = _chunk_frame(dataframe, chunk)
    columns = [str(column) for column in chunk.get('columns', [])]
    row_count = int(chunk.get('row_count') or len(chunk_frame.index))

    if row_count <= 0 or chunk_frame.empty:
        preview_rows = []
        missing_pct = 0.0
        duplicate_rows = 0
        top_missing_columns = []
        column_semantics = {}
    else:
        preview_rows = chunk_frame.head(3).to_dict(orient='records')
        total_cells = int(len(chunk_frame.index) * len(chunk_frame.columns))
        missing_cells = int(chunk_frame.isna().sum().sum()) if total_cells else 0
        missing_pct = round((missing_cells / total_cells) * 100, 2) if total_cells else 0.0
        duplicate_rows = int(chunk_frame.duplicated().sum())

        top_missing_columns = []
        for column_name in chunk_frame.columns:
            col_series = chunk_frame[column_name]
            if len(col_series.index) == 0:
                continue
            col_missing_pct = round((int(col_series.isna().sum()) / len(col_series.index)) * 100, 2)
            if col_missing_pct > 0:
                top_missing_columns.append({'column': str(column_name), 'missing_pct': col_missing_pct})
        top_missing_columns = sorted(top_missing_columns, key=lambda item: item['missing_pct'], reverse=True)[:6]

        # Rich per-column semantic profile — ALL columns in the chunk
        column_semantics = {}
        for column_name in chunk_frame.columns:
            profile = _analyse_column_semantics(chunk_frame[column_name], str(column_name))
            if profile:
                column_semantics[str(column_name)] = profile

    critical_signals = _critical_signals_for_columns(columns)
    section_name = str(chunk.get('section') or 'generic_data')
    kind = str(chunk.get('kind') or 'generic')
    rows_range = chunk.get('rows_range') or [0, 0]
    row_span_text = f'{int(rows_range[0] or 0)}-{int(rows_range[1] or 0)}'

    # Enrich deterministic summary with semantic signals
    summary_fragments = [
        f'Section {section_name}',
        f'chunk {chunk.get("chunk_id")}',
        f'{row_count} ligne(s)',
        f'{len(columns)} colonne(s)',
        f'missing {missing_pct}%',
        f'duplicate_rows {duplicate_rows}',
    ]
    if critical_signals:
        summary_fragments.append(f'critical_columns {", ".join(critical_signals[:6])}')
    if top_missing_columns:
        summary_fragments.append(
            'top_missing ' + ', '.join(
                f'{item["column"]}:{item["missing_pct"]}%' for item in top_missing_columns[:4]
            )
        )

    # Flag columns with disguised missing or encoding inconsistencies in summary
    disguised_cols = [
        col for col, info in column_semantics.items()
        if info.get('disguised_missing')
    ]
    encoding_cols = [
        col for col, info in column_semantics.items()
        if info.get('value_distribution') and info.get('unique_count', 0) > 1
    ]
    if disguised_cols:
        summary_fragments.append(f'disguised_missing_cols {", ".join(disguised_cols[:4])}')
    if encoding_cols:
        summary_fragments.append(f'categorical_cols {", ".join(encoding_cols[:4])}')

    deterministic_summary = '. '.join(summary_fragments) + '.'
    if critical_signals and technical_profile.get('missing_pct'):
        deterministic_summary += f' Signaux critiques: {", ".join(critical_signals[:4])}.'

    # Build embedding text: summary + column semantics (for ChromaDB vector search)
    semantics_blob = json.dumps(column_semantics, ensure_ascii=False, default=str)
    embedding_text = '\n'.join([
        deterministic_summary,
        f'rows_range={row_span_text}',
        f'kind={kind}',
        f'columns={", ".join(columns[:20])}',
        f'column_semantics={semantics_blob}',
    ])

    try:
        max_embed_chars = int(os.environ.get('EMBEDDING_MAX_CHARS', '3000'))
    except Exception:
        max_embed_chars = 3000

    embedding_truncated = False
    if max_embed_chars and isinstance(embedding_text, str) and len(embedding_text) > max_embed_chars:
        embedding_text = embedding_text[:max_embed_chars]
        embedding_truncated = True

    return {
        'chunk_id': str(chunk.get('chunk_id')),
        'kind': kind,
        'section': section_name,
        'row_count': row_count,
        'column_count': len(columns),
        'rows_range': [int(rows_range[0] or 0), int(rows_range[1] or 0)],
        'columns': columns,
        'preview_rows': preview_rows,
        'missing_pct': missing_pct,
        'duplicate_rows': duplicate_rows,
        'top_missing_columns': top_missing_columns,
        'column_semantics': column_semantics,
        'critical_signals': critical_signals,
        'deterministic_summary': deterministic_summary,
        'embedding_text': embedding_text,
        'embedding_truncated': embedding_truncated,
        'estimated_chars': int(chunk.get('estimated_chars') or 0),
        'patient_id_column': chunk.get('patient_id_column'),
        'units': chunk.get('units') or {},
    }



def _embed_texts_with_ollama(texts):
    model_name = _get_embedding_model_name()
    timeout_seconds = _env_int('OLLAMA_EMBEDDING_TIMEOUT_SECONDS', 60)
    embeddings = []

    for text in texts:
        text = str(text or '').strip()
        if not text:
            embeddings.append([])
            continue

        embedded = None
        for ollama_base in _get_ollama_candidate_bases():
            ollama_endpoint = f'{ollama_base}/api/embeddings'
            request_payload = {
                'model': model_name,
                'prompt': text,
            }
            request_data = json.dumps(request_payload).encode('utf-8')
            req = urllib_request.Request(
                ollama_endpoint,
                data=request_data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            try:
                with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
                    body = response.read().decode('utf-8')
                payload = json.loads(body)
                vector = payload.get('embedding') or payload.get('embeddings')
                if isinstance(vector, list) and vector and isinstance(vector[0], (int, float)):
                    embedded = [float(value) for value in vector]
                    break
            except Exception:
                continue

        embeddings.append(embedded or [])

    return embeddings


def _build_retrieval_query(technical_profile, chunk_summaries, stage_name='diagnostic'):
    rows = int(technical_profile.get('rows') or 0)
    columns = int(technical_profile.get('columns') or 0)
    missing_pct = float(technical_profile.get('missing_pct') or 0.0)
    duplicate_rows = int(technical_profile.get('duplicate_rows') or 0)
    outlier_total = sum(int(item.get('outlier_count') or 0) for item in (technical_profile.get('numeric_columns_profile') or []))
    highlighted_sections = []
    highlighted_signals = []
    for chunk in chunk_summaries[:6]:
        highlighted_sections.append(str(chunk.get('section') or 'generic_data'))
        highlighted_signals.extend(chunk.get('critical_signals') or [])

    query_fragments = [
        f'preprocess stage={stage_name}',
        f'rows={rows}',
        f'columns={columns}',
        f'missing_pct={missing_pct}',
        f'duplicate_rows={duplicate_rows}',
        f'outliers={outlier_total}',
    ]
    if highlighted_sections:
        query_fragments.append('sections=' + ','.join(list(dict.fromkeys(highlighted_sections))[:8]))
    if highlighted_signals:
        query_fragments.append('critical=' + ','.join(list(dict.fromkeys(highlighted_signals))[:8]))
    if stage_name == 'correction':
        query_fragments.append('focus=correction_plan_and_safe_normalization')
    else:
        query_fragments.append('focus=clinical_risk_missing_values_duplicates_outliers')
    return ' | '.join(query_fragments)


def _heuristic_rank_chunks(chunk_summaries, max_chunks=4):
    ranked_chunks = []
    for chunk in chunk_summaries:
        score = 0.0
        section_name = str(chunk.get('section') or '')
        if section_name.startswith('biologie') or section_name.startswith('devenir'):
            score += 4
        if section_name.startswith('irc') or section_name.startswith('dialyse'):
            score += 3
        if chunk.get('critical_signals'):
            score += min(5, len(chunk.get('critical_signals') or []))
        score += min(3, float(chunk.get('missing_pct') or 0.0) / 20.0)
        score += min(2, float(chunk.get('duplicate_rows') or 0))
        if chunk.get('row_count', 0) > 0:
            score += 1
        ranked_chunks.append((score, chunk))

    ranked_chunks.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked_chunks[:max_chunks]]


def _cosine_similarity(vector_a, vector_b):
    if not vector_a or not vector_b:
        return 0.0
    if len(vector_a) != len(vector_b):
        return 0.0

    dot_product = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for index in range(len(vector_a)):
        value_a = float(vector_a[index])
        value_b = float(vector_b[index])
        dot_product += value_a * value_b
        norm_a += value_a * value_a
        norm_b += value_b * value_b

    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot_product / (sqrt(norm_a) * sqrt(norm_b))


def _embedding_rank_chunks(chunk_summaries, technical_profile, stage_name='diagnostic', max_chunks=4):
    documents = [chunk['embedding_text'] for chunk in chunk_summaries]
    doc_embeddings = _embed_texts_with_ollama(documents)
    if not doc_embeddings or len(doc_embeddings) != len(documents) or any(not vector for vector in doc_embeddings):
        return None, None

    query_text = _build_retrieval_query(technical_profile, chunk_summaries, stage_name=stage_name)
    query_embedding = _embed_texts_with_ollama([query_text])
    if not query_embedding or not query_embedding[0]:
        return None, None

    scored_chunks = []
    for chunk, doc_vector in zip(chunk_summaries, doc_embeddings):
        similarity = _cosine_similarity(query_embedding[0], doc_vector)
        scored_chunks.append((similarity, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    ranked_chunks = [chunk for _, chunk in scored_chunks[:max_chunks]]
    return ranked_chunks, query_text


def build_rag_context(dataframe, chunks, technical_profile, stage_name='diagnostic', max_chunks=4, progress_callback=None):
    if not chunks:
        return {
            'retrieval_policy': 'no_chunks',
            'retrieved_chunks': [],
            'retrieved_chunks_count': 0,
            'chunk_summaries': [],
            'vector_store': {'enabled': False, 'reason': 'no_chunks'},
        }

    chunk_summaries = [_summarize_chunk(dataframe, chunk, technical_profile) for chunk in chunks]
    chunk_lookup = {chunk['chunk_id']: chunk for chunk in chunk_summaries}
    section_fusion = build_section_fusion(chunk_summaries)

    if not _env_bool('CHROMA_ENABLED', True) or chromadb is None:
        embedded_chunks, query_text = _embedding_rank_chunks(
            chunk_summaries,
            technical_profile,
            stage_name=stage_name,
            max_chunks=max_chunks,
        )
        if embedded_chunks:
            return {
                'retrieval_policy': 'embedding_local_no_chroma',
                'retrieved_chunks': embedded_chunks,
                'retrieved_chunks_count': len(embedded_chunks),
                'chunk_summaries': chunk_summaries,
                'section_fusion': section_fusion,
                'rag_query': query_text,
                'vector_store': {
                    'enabled': False,
                    'reason': 'chromadb_missing_or_disabled',
                    'provider': 'local_embeddings',
                },
            }

        retrieved_chunks = _heuristic_rank_chunks(chunk_summaries, max_chunks=max_chunks)
        return {
            'retrieval_policy': 'heuristic_local',
            'retrieved_chunks': retrieved_chunks,
            'retrieved_chunks_count': len(retrieved_chunks),
            'chunk_summaries': chunk_summaries,
            'section_fusion': section_fusion,
            'vector_store': {
                'enabled': False,
                'reason': 'chromadb_missing_or_disabled',
                'provider': 'heuristic',
            },
        }

    try:
        chroma_client = chromadb.PersistentClient(path=_get_chroma_persist_dir())
        collection_name = _build_collection_name(technical_profile)
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={'hnsw:space': 'cosine'},
        )

        documents = [chunk['embedding_text'] for chunk in chunk_summaries]
        embeddings = _embed_texts_with_ollama(documents)
        if not embeddings or len(embeddings) != len(documents) or any(not vector for vector in embeddings):
            retrieved_chunks = _heuristic_rank_chunks(chunk_summaries, max_chunks=max_chunks)
            return {
                'retrieval_policy': 'heuristic_local',
                'retrieved_chunks': retrieved_chunks,
                'retrieved_chunks_count': len(retrieved_chunks),
                'chunk_summaries': chunk_summaries,
                'section_fusion': section_fusion,
                'vector_store': {
                    'enabled': False,
                    'reason': 'embedding_unavailable',
                    'provider': 'chroma',
                    'collection_name': collection_name,
                    'persist_dir': _get_chroma_persist_dir(),
                },
            }

        ids = [chunk['chunk_id'] for chunk in chunk_summaries]
        metadatas = [
            {
                'section': chunk['section'],
                'kind': chunk['kind'],
                'row_count': int(chunk['row_count']),
                'column_count': int(chunk['column_count']),
                'missing_pct': float(chunk['missing_pct']),
                'duplicate_rows': int(chunk['duplicate_rows']),
                'summary': chunk['deterministic_summary'][:1000],
            }
            for chunk in chunk_summaries
        ]
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        query_text = _build_retrieval_query(technical_profile, chunk_summaries, stage_name=stage_name)
        query_embedding = _embed_texts_with_ollama([query_text])
        if not query_embedding or not query_embedding[0]:
            retrieved_chunks = _heuristic_rank_chunks(chunk_summaries, max_chunks=max_chunks)
            return {
                'retrieval_policy': 'heuristic_local',
                'retrieved_chunks': retrieved_chunks,
                'retrieved_chunks_count': len(retrieved_chunks),
                'chunk_summaries': chunk_summaries,
                'section_fusion': section_fusion,
                'vector_store': {
                    'enabled': False,
                    'reason': 'query_embedding_unavailable',
                    'provider': 'chroma',
                    'collection_name': collection_name,
                    'persist_dir': _get_chroma_persist_dir(),
                },
            }

        results = collection.query(
            query_embeddings=[query_embedding[0]],
            n_results=min(max_chunks, len(chunk_summaries)),
            include=['documents', 'metadatas', 'distances'],
        )
        retrieved_ids = (results.get('ids') or [[]])[0]
        retrieved_chunks = [chunk_lookup.get(chunk_id) for chunk_id in retrieved_ids if chunk_lookup.get(chunk_id)]

        if not retrieved_chunks:
            retrieved_chunks = _heuristic_rank_chunks(chunk_summaries, max_chunks=max_chunks)

        if callable(progress_callback):
            try:
                progress_callback(f'RAG Chroma indexé: {collection_name} ({len(chunk_summaries)} chunks)')
            except Exception:
                pass

        return {
            'retrieval_policy': 'chroma_rag',
            'retrieved_chunks': retrieved_chunks,
            'retrieved_chunks_count': len(retrieved_chunks),
            'chunk_summaries': chunk_summaries,
            'section_fusion': section_fusion,
            'rag_query': query_text,
            'vector_store': {
                'enabled': True,
                'provider': 'chroma',
                'collection_name': collection_name,
                'persist_dir': _get_chroma_persist_dir(),
                'indexed_chunks': len(chunk_summaries),
            },
        }
    except Exception as error:
        retrieved_chunks = _heuristic_rank_chunks(chunk_summaries, max_chunks=max_chunks)
        return {
            'retrieval_policy': 'heuristic_local',
            'retrieved_chunks': retrieved_chunks,
            'retrieved_chunks_count': len(retrieved_chunks),
            'chunk_summaries': chunk_summaries,
            'section_fusion': section_fusion,
            'vector_store': {
                'enabled': False,
                'provider': 'chroma',
                'reason': str(error),
            },
        }


def build_section_fusion(chunk_summaries, llm_analysis=None):
    section_map = {}
    for chunk in chunk_summaries:
        section_name = str(chunk.get('section') or 'generic_data')
        entry = section_map.setdefault(
            section_name,
            {
                'section': section_name,
                'chunks_count': 0,
                'row_count': 0,
                'critical_signals': [],
                'deterministic_summaries': [],
                'llm_notes': [],
                'issue_count': 0,
                'recommendation_count': 0,
            },
        )
        entry['chunks_count'] += 1
        entry['row_count'] += int(chunk.get('row_count') or 0)
        entry['critical_signals'].extend(chunk.get('critical_signals') or [])
        entry['deterministic_summaries'].append(chunk.get('deterministic_summary') or '')

    for entry in section_map.values():
        entry['critical_signals'] = list(dict.fromkeys([signal for signal in entry['critical_signals'] if signal]))[:8]
        entry['deterministic_summary'] = ' '.join(
            summary for summary in entry['deterministic_summaries'][:4] if summary
        )
        if entry['critical_signals']:
            entry['deterministic_summary'] = (
                entry['deterministic_summary'] +
                f" Signaux critiques: {', '.join(entry['critical_signals'][:5])}."
            ).strip()

    if isinstance(llm_analysis, dict):
        issues = llm_analysis.get('issues') if isinstance(llm_analysis.get('issues'), list) else []
        recommendations = llm_analysis.get('recommendations') if isinstance(llm_analysis.get('recommendations'), list) else []
        for issue in issues:
            issue_text = str(issue.get('explanation') or issue.get('message') or '').strip()
            column_name = str(issue.get('column') or '').strip()
            target_sections = list(section_map.keys()) if column_name in {'', '*'} else []
            if column_name not in {'', '*'}:
                normalized = _normalize_text(column_name)
                for section_name in section_map.keys():
                    section_key = _normalize_text(section_name)
                    if section_key and section_key in normalized:
                        target_sections.append(section_name)
                if not target_sections:
                    target_sections = list(section_map.keys())[:1]
            for section_name in target_sections:
                entry = section_map.setdefault(section_name, {
                    'section': section_name,
                    'chunks_count': 0,
                    'row_count': 0,
                    'critical_signals': [],
                    'deterministic_summaries': [],
                    'llm_notes': [],
                    'issue_count': 0,
                    'recommendation_count': 0,
                })
                if issue_text:
                    entry['llm_notes'].append(f'Issue {issue.get("severity", "info")} • {issue_text}')
                entry['issue_count'] += 1
        if recommendations:
            for section_name in section_map.keys():
                section_entry = section_map[section_name]
                section_entry['recommendation_count'] = len(recommendations)
                section_entry['llm_notes'].extend([str(item) for item in recommendations[:3]])

    return list(section_map.values())


def estimate_route(technical_profile):
    rows = int(technical_profile.get('rows') or 0)
    columns = int(technical_profile.get('columns') or 0)
    missing_pct = float(technical_profile.get('missing_pct') or 0.0)
    duplicate_rows = int(technical_profile.get('duplicate_rows') or 0)
    outlier_total = sum(int(item.get('outlier_count') or 0) for item in (technical_profile.get('numeric_columns_profile') or []))
    critical_columns = 0
    ambiguous_columns = 0
    critical_tokens = [
        'deces', 'dialyse', 'biologie', 'albumine', 'hemoglobine', 'creatinine',
        'infection', 'transplant', 'complication', 'urgence', 'cardio', 'renal',
    ]

    for column_meta in technical_profile.get('columns_profile', []):
        column_name = _normalize_text(column_meta.get('column'))
        column_missing_pct = float(column_meta.get('missing_pct') or 0.0)
        if any(token in column_name for token in critical_tokens):
            if column_missing_pct >= 15 or not column_meta.get('sample_values'):
                critical_columns += 1
        if column_missing_pct >= 25:
            ambiguous_columns += 1

    clinical_complexity_score = (critical_columns * 3) + (ambiguous_columns * 2) + outlier_total + (2 if duplicate_rows else 0)

    if rows <= 50 and columns <= 15 and missing_pct == 0 and duplicate_rows == 0 and outlier_total == 0 and clinical_complexity_score == 0:
        return {
            'mode': 'deterministic',
            'label': 'deterministic_only',
            'reason': 'Dataset simple: pas de LLM necessaire.',
            'primary_model': None,
            'fallback_model': None,
            'primary_timeout_seconds': 0,
            'fallback_timeout_seconds': 0,
            'primary_num_predict': 0,
            'fallback_num_predict': 0,
            'clinical_complexity_score': clinical_complexity_score,
        }

    if clinical_complexity_score >= 6 or rows > 300 or columns > 40 or missing_pct >= 10 or duplicate_rows > 0 or outlier_total > 5:
        return {
            'mode': 'advanced',
            'label': 'advanced_medical',
            'reason': 'Dataset medical complexe ou ambigu: modele equilibre priorise.',
            'primary_model': os.environ.get('OLLAMA_PREPROCESS_MODEL', os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b-instruct')),
            'fallback_model': os.environ.get('OLLAMA_FALLBACK_MODEL', os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b-instruct')),
            'primary_timeout_seconds': _env_int('OLLAMA_ADVANCED_TIMEOUT_SECONDS', _env_int('OLLAMA_PRIMARY_TIMEOUT_SECONDS', min(_env_int('OLLAMA_TIMEOUT_SECONDS', 420), 180))),
            'fallback_timeout_seconds': _env_int('OLLAMA_FALLBACK_TIMEOUT_SECONDS', _env_int('OLLAMA_TIMEOUT_SECONDS', 420)),
            'primary_num_predict': _env_int('OLLAMA_NUM_PREDICT', 32),
            'fallback_num_predict': _env_int('OLLAMA_NUM_PREDICT', 32),
            'clinical_complexity_score': clinical_complexity_score,
        }

    return {
        'mode': 'balanced',
        'label': 'balanced_default',
        'reason': 'Dataset standard: modele equilibre priorise.',
        'primary_model': os.environ.get('OLLAMA_BALANCED_MODEL', os.environ.get('OLLAMA_PREPROCESS_MODEL', os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b-instruct'))),
        'fallback_model': os.environ.get('OLLAMA_FALLBACK_MODEL', os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b-instruct')),
        'primary_timeout_seconds': _env_int('OLLAMA_PRIMARY_TIMEOUT_SECONDS', min(_env_int('OLLAMA_TIMEOUT_SECONDS', 420), 180)),
        'fallback_timeout_seconds': _env_int('OLLAMA_FALLBACK_TIMEOUT_SECONDS', _env_int('OLLAMA_TIMEOUT_SECONDS', 420)),
        'primary_num_predict': _env_int('OLLAMA_NUM_PREDICT', 32),
        'fallback_num_predict': _env_int('OLLAMA_RETRY_NUM_PREDICT', _env_int('OLLAMA_NUM_PREDICT', 32)),
        'clinical_complexity_score': clinical_complexity_score,
    }
