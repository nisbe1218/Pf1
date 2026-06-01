# ML Platform Refactoring Summary

## Overview
The ML prediction module has been successfully refactored to focus on the best-performing model (SVM Linéaire) while simplifying the user interface and backend architecture.

---

## Backend Changes (Python/Django)

### 1. **Updated Imports** (`backend/predictions/views.py`)
- ✅ Uncommented `joblib` import (line 8)
- ✅ Added `SVC` from `sklearn.svm` (line 43)

### 2. **Updated SVM Model Configuration** (`get_model_map`)
- ✅ Replaced `CalibratedClassifierCV(LinearSVC(...))` with native `SVC`
- ✅ Configuration: `C=0.01, kernel='linear', class_weight='balanced', probability=True`
- ✅ This matches the best-model parameters from the ML project

### 3. **Added SVM-Specific Preprocessing**
- ✅ New function: `get_svm_preprocessor()` (line ~870)
- ✅ Uses **KNN Imputation** (3 neighbors) instead of SimpleImputer
- ✅ Applies PowerTransformer (Yeo-Johnson) for better feature scaling
- ✅ Pipeline chain: KNNImputer → PowerTransformer → StandardScaler

### 4. **New SVM Pipeline Function**
- ✅ `get_svm_pipeline()` function (line ~903)
- ✅ Uses `get_svm_preprocessor()` for consistent feature processing
- ✅ Dedicated to SVM model training and prediction

### 5. **Updated Training Logic**
- ✅ Modified `train_models()` function (line ~1151)
- ✅ SVM now trains with fixed hyperparameters (no hyperparameter tuning)
- ✅ Skips RandomizedSearchCV for SVM; direct training with `pipeline.fit()`
- ✅ Uses `get_svm_pipeline()` for consistent preprocessing

### 6. **New Patient Prediction Endpoint**
- ✅ `PredictionPatientView` class (line ~1863)
- ✅ Endpoint: `POST /predictions/predict-patient/`
- ✅ Takes: `patient_id` and `prediction_type`
- ✅ Automatically extracts all features from patient database
- ✅ Uses SVM Linear as the fixed model
- ✅ Returns: score, risk_level, recommendation, factors, DOI score
- ✅ Automatically logs predictions to history

### 7. **Updated URLs** (`backend/predictions/urls.py`)
- ✅ Added new route: `path('predict-patient/', PredictionPatientView.as_view(), ...)`
- ✅ Registered `PredictionPatientView` import

---

## Frontend Changes (React)

### 1. **Simplified Tab Structure**
- ✅ Reduced from 4 tabs → **3 tabs**:
  - `['Tableau de bord', 'Patients', 'Score']` (FR)
  - `['Dashboard', 'Patients', 'Score']` (EN)

### 2. **Removed UI Complexity**
- ✅ Removed variable selection UI
- ✅ Removed model selection UI
- ✅ Removed model training UI
- ✅ Removed step-by-step workflow
- ✅ Removed `MODEL_OPTIONS`, `MODEL_RECOMMENDATIONS` constants
- ✅ Removed all related state (selectedVariableKeys, selectedModel, trainingLoading, etc.)

### 3. **Tab 0: Dashboard**
- ✅ Shows KPI cards:
  - Total validated patients
  - High-risk patient alerts
  - Recent patients (30 days)
  - Validation rate percentage
- ✅ Informational card about SVM Linear model
- ✅ No changes to dashboard logic

### 4. **Tab 1: Patients**
- ✅ Patient search by name/ID
- ✅ Filter by sex
- ✅ Displays patient table with:
  - Name, Age, Sex, Status, Risk flag
  - "Predict" button for each patient
- ✅ Click prediction button → auto-navigate to Score tab

### 5. **Tab 2: Score (NEW INTEGRATED DESIGN)**
- ✅ Two-column layout:
  - **Left column**:
    - Patient information card (name, age, sex, status)
    - Prediction type selector (Mortalité / Coagulation)
    - Launch Prediction button
  - **Right column**:
    - Circular score gauge (0-100)
    - Risk level display (color-coded)
    - DOI risk score (if available)
    - Clinical recommendation alert
    - Contributing factors (accordion)

### 6. **Auto-Feature Extraction**
- ✅ Backend extracts all features automatically
- ✅ No frontend feature selection needed
- ✅ Calls new `predict-patient/` endpoint
- ✅ Passes only: `patient_id` and `prediction_type`

### 7. **Updated Prediction Flow**
```
Patient List (Tab 1) 
  ↓ [Select Patient]
Score Tab (Tab 2) 
  ↓ [Choose Prediction Type]
  ↓ [Launch Prediction]
Auto-Extract Features (Backend)
  ↓ [Run SVM Linear]
Display Results with Risk Score
```

---

## Data Flow

### Before (Old)
```
Frontend:
  1. Patient selection
  2. Manual variable selection
  3. Model selection
  4. Execute
Backend:
  1. Build feature set from selected variables
  2. Load/train selected model
  3. Predict
```

### After (New)
```
Frontend:
  1. Patient selection → Auto-navigate to Score tab
  2. Choose prediction type
  3. Click "Launch Prediction"
Backend:
  1. Load patient from database
  2. Auto-extract all available features
  3. Use SVM Linear (fixed model)
  4. Predict with KNN preprocessing
  5. Return risk score + recommendations
```

---

## Configuration

### SVM Model Parameters
```python
SVC(
    C=0.01,                      # Regularization (lower = more regularization)
    kernel='linear',              # Linear kernel for interpretability
    class_weight='balanced',      # Handle class imbalance
    probability=True,             # Enable probability estimates
    random_state=42,              # Reproducibility
    max_iter=5000                 # Iteration limit
)
```

### Feature Preprocessing (SVM Pipeline)
```
1. KNNImputer(n_neighbors=3)    # Handle missing values with k-nearest neighbors
2. PowerTransformer(method='yeo-johnson')  # Non-linear feature scaling
3. StandardScaler()             # Normalize to mean=0, std=1
```

---

## Benefits

### ✅ Simplified UX
- Reduced complexity: 4 tabs → 3 tabs
- Streamlined workflow: 4 steps → 2 steps
- Auto-population of features eliminates user error

### ✅ Better ML Performance
- KNN imputation preserves data patterns better than simple median
- Power transformation handles skewed distributions
- SVM Linear with C=0.01 provides good generalization

### ✅ Maintainability
- Fixed model = fewer configuration choices
- Automatic feature extraction = less parameter passing
- Dedicated SVM pipeline = easier to optimize

### ✅ Clinical Workflow
- One-click predictions after patient selection
- Automatic risk stratification
- DOI risk score integration
- Tailored clinical recommendations

---

## Testing Checklist

### Backend
- [ ] Train SVM model with new preprocessing
- [ ] Test PredictionPatientView endpoint
- [ ] Verify auto-feature extraction
- [ ] Check KNN imputation on missing values
- [ ] Validate risk score calculation
- [ ] Test DOI score logic
- [ ] Verify prediction logging

### Frontend
- [ ] Tab navigation (0→1→2)
- [ ] Patient search/filter
- [ ] Prediction type selector
- [ ] Circular gauge rendering
- [ ] Risk level coloring
- [ ] Contributing factors display
- [ ] Error handling
- [ ] Loading states

### Integration
- [ ] End-to-end prediction flow
- [ ] Patient data retrieval
- [ ] Feature mapping
- [ ] Result display
- [ ] Multilingual support (EN/FR)

---

## Files Modified

### Backend
- `backend/predictions/views.py` - SVM config, new endpoint, preprocessing
- `backend/predictions/urls.py` - New route registration

### Frontend
- `frontend/src/pages/model-ai/ModelAI.js` - Complete rewrite (simplified)

---

## Next Steps

1. **Train the SVM model**:
   ```bash
   POST /predictions/train/
   {
     "prediction_type": "mortalite",
     "feature_keys": [...]  // optional
   }
   ```

2. **Test patient prediction**:
   ```bash
   POST /predictions/predict-patient/
   {
     "prediction_type": "mortalite",
     "patient_id": 1
   }
   ```

3. **Monitor performance** via:
   - `/predictions/metrics/` - Model performance metrics
   - `/predictions/history/` - Prediction history

---

## Notes

- The refactoring preserves all existing data and models
- Random Forest and other models remain available via the `/predictions/predict/` endpoint
- Dashboard KPIs continue to work as before
- All risk score calculations remain unchanged
- Multilingual support (EN/FR) is maintained
