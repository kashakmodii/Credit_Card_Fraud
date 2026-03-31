"""
======================================================
 CREDIT CARD FRAUD DETECTION — Streamlit Web App
======================================================
Run: streamlit run app.py
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import joblib, json

# ── Page config ──────────────────────────────────────
st.set_page_config(
    page_title="💳 Fraud Detection System",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────
st.markdown("""
<style>
    .main {background-color: #0e1117;}
    .stMetric {background: #1e2130; border-radius: 10px; padding: 10px;}
    .fraud-box {
        background: linear-gradient(135deg, #ff4b4b22, #ff4b4b44);
        border: 2px solid #ff4b4b;
        border-radius: 12px; padding: 20px; text-align: center;
    }
    .legit-box {
        background: linear-gradient(135deg, #00d4aa22, #00d4aa44);
        border: 2px solid #00d4aa;
        border-radius: 12px; padding: 20px; text-align: center;
    }
    .metric-title {font-size: 0.85rem; color: #8b8d9e; font-weight: 600;}
    .metric-value {font-size: 2rem; font-weight: 800; color: white;}
</style>
""", unsafe_allow_html=True)

ARTIFACT_DIR = Path("artifacts")

# ── Load artifacts ────────────────────────────────────
@st.cache_resource
def load_models():
    """Load ML model, scaler, selector — cached for performance."""
    try:
        scaler    = joblib.load(ARTIFACT_DIR / "scaler.pkl")
        selector  = joblib.load(ARTIFACT_DIR / "selector.pkl")
        model     = joblib.load(ARTIFACT_DIR / "best_model.pkl")
        features  = joblib.load(ARTIFACT_DIR / "feature_names.pkl")
        sel_feat  = joblib.load(ARTIFACT_DIR / "selected_features.pkl")
        le_type   = joblib.load(ARTIFACT_DIR / "le_type.pkl")
        le_loc    = joblib.load(ARTIFACT_DIR / "le_loc.pkl")
        meta      = json.load(open(ARTIFACT_DIR / "meta.json"))
        return scaler, selector, model, features, sel_feat, le_type, le_loc, meta
    except Exception as e:
        st.error(f"Model files not found. Run train_models.py first. Error: {e}")
        st.stop()


def predict_transaction(inputs: dict, scaler, selector, model, feature_names, le_type, le_loc):
    """Full inference pipeline."""
    # Encode categoricals
    try:
        inputs["TransactionType"] = le_type.transform([inputs["TransactionType"]])[0]
    except Exception:
        inputs["TransactionType"] = 0
    try:
        inputs["Location"] = le_loc.transform([inputs["Location"]])[0]
    except Exception:
        inputs["Location"] = 0

    # Build feature vector in the correct order
    row = [inputs.get(f, 0) for f in feature_names]
    X = np.array(row).reshape(1, -1)
    X_sc  = scaler.transform(X)
    X_sel = selector.transform(X_sc)

    prob = model.predict_proba(X_sel)[0, 1]
    pred = int(prob >= 0.5)
    return pred, float(prob)


# ══════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/credit-card-front.png", width=80)
    st.title("Fraud Detection")
    st.caption("AI-powered transaction analysis")
    st.divider()

    page = st.radio(
        "Navigate",
        ["🔍 Predict Transaction",
         "📊 EDA & Insights",
         "📈 Model Performance",
         "ℹ️ About"],
        label_visibility="collapsed"
    )
    st.divider()
    st.caption("Powered by XGBoost + Keras ANN")

# Load resources
scaler, selector, model, feature_names, sel_feat, le_type, le_loc, meta = load_models()


# ══════════════════════════════════════════════════════
# PAGE 1 — PREDICTION
# ══════════════════════════════════════════════════════
if "Predict" in page:
    st.title("💳 Transaction Fraud Detector")
    st.markdown("Enter transaction details below to classify as **Fraud** or **Legitimate**.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Transaction Details")
        amount = st.number_input("Transaction Amount ($)", min_value=1.0, max_value=10000.0, value=250.0, step=10.0)
        merchant_id = st.number_input("Merchant ID", min_value=1, max_value=10000, value=500)
        txn_type = st.selectbox("Transaction Type", ["purchase", "refund"])

    with col2:
        st.subheader("Location & Time")
        location = st.selectbox("Location", [
            "Chicago", "San Diego", "Dallas", "San Antonio", "New York",
            "Houston", "Phoenix", "Los Angeles", "Philadelphia", "San Jose"
        ])
        hour = st.slider("Hour of Day", 0, 23, 14)
        day_of_week = st.slider("Day of Week (0=Mon)", 0, 6, 2)

    with col3:
        st.subheader("Additional Context")
        month = st.slider("Month", 1, 12, 6)
        is_weekend = 1 if day_of_week >= 5 else 0
        is_night = 1 if (hour < 6 or hour >= 22) else 0

        st.metric("Is Weekend?", "Yes 🌙" if is_weekend else "No 📅")
        st.metric("Is Night Transaction?", "Yes 🌙" if is_night else "No ☀️")

    st.divider()
    col_btn, col_result = st.columns([1, 3])

    with col_btn:
        predict_btn = st.button("🔍 Analyze Transaction", type="primary", use_container_width=True)

    if predict_btn:
        inputs = {
            "Amount": amount,
            "MerchantID": merchant_id,
            "TransactionType": txn_type,
            "Location": location,
            "Hour": hour,
            "DayOfWeek": day_of_week,
            "Month": month,
            "IsWeekend": is_weekend,
            "IsNightTxn": is_night,
        }

        with st.spinner("Analyzing transaction..."):
            pred, prob = predict_transaction(inputs, scaler, selector, model, feature_names, le_type, le_loc)

        with col_result:
            if pred == 1:
                st.markdown(f"""
                <div class="fraud-box">
                    <h1 style="color:#ff4b4b; margin:0">🚨 FRAUD DETECTED</h1>
                    <p style="color:#ff4b4b; font-size:1.2rem">Fraud Probability: <b>{prob*100:.1f}%</b></p>
                    <p style="color:#888; margin:0">This transaction has been flagged for review.</p>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="legit-box">
                    <h1 style="color:#00d4aa; margin:0">✅ LEGITIMATE</h1>
                    <p style="color:#00d4aa; font-size:1.2rem">Fraud Probability: <b>{prob*100:.1f}%</b></p>
                    <p style="color:#888; margin:0">Transaction appears safe to process.</p>
                </div>""", unsafe_allow_html=True)

        # Probability gauge
        st.markdown("#### Risk Gauge")
        fig, ax = plt.subplots(figsize=(10, 1.2))
        ax.barh(0, prob, color="#ff4b4b" if prob > 0.5 else "#00d4aa", height=0.5)
        ax.barh(0, 1 - prob, left=prob, color="#1e2130", height=0.5)
        ax.axvline(0.5, color="white", linewidth=2, linestyle="--")
        ax.set_xlim(0, 1)
        ax.axis("off")
        fig.patch.set_facecolor("#0e1117")
        st.pyplot(fig)
        plt.close()

        # Breakdown
        st.markdown("#### Input Summary")
        input_df = pd.DataFrame([inputs])
        st.dataframe(input_df, use_container_width=True)

# ══════════════════════════════════════════════════════
# PAGE 2 — EDA
# ══════════════════════════════════════════════════════
elif "EDA" in page:
    st.title("📊 Exploratory Data Analysis")

    plots = {
        "Class Distribution":   "eda_class_distribution.png",
        "Amount by Class":       "eda_amount.png",
        "Hourly Fraud Pattern":  "eda_hourly_fraud.png",
        "Correlation Heatmap":   "eda_correlation.png",
    }

    for title, fname in plots.items():
        path = ARTIFACT_DIR / fname
        if path.exists():
            st.subheader(title)
            st.image(str(path), use_container_width=True)
            st.divider()
        else:
            st.warning(f"Plot not found: {fname}. Run train_models.py first.")

    st.subheader("🔑 Key Insights")
    insights = [
        "**Class Imbalance**: Only 1% of transactions are fraudulent — standard accuracy is misleading.",
        "**Amount Distribution**: Fraudulent transactions span the full amount range — no simple threshold works.",
        "**Night Hours (22:00–06:00)**: Higher fraud rates during low-monitoring windows.",
        "**SMOTE Applied**: Synthetic minority oversampling rebalanced the training set from 1:99 to 1:5.",
        "**Recall Priority**: In fraud detection, a missed fraud (false negative) costs far more than a false alarm.",
    ]
    for i in insights:
        st.markdown(f"- {i}")

# ══════════════════════════════════════════════════════
# PAGE 3 — MODEL PERFORMANCE
# ══════════════════════════════════════════════════════
elif "Model" in page:
    st.title("📈 Model Performance Dashboard")

    # Comparison table
    cmp_path = ARTIFACT_DIR / "model_comparison.csv"
    if cmp_path.exists():
        df_cmp = pd.read_csv(cmp_path)
        st.subheader("Model Comparison")
        st.dataframe(df_cmp.style.highlight_max(axis=0, subset=["ROC-AUC","Recall","F1-Score"],
                                                 color="#00d4aa33"), use_container_width=True)

    for title, fname in [
        ("ROC Curves",            "roc_curves.png"),
        ("Confusion Matrices",    "confusion_matrices.png"),
        ("Model Comparison",      "model_comparison.png"),
        ("Feature Importance",    "feature_importance.png"),
        ("SHAP Explainability",   "shap_summary.png"),
        ("ANN Learning Curves",   "ann_learning_curves.png"),
    ]:
        p = ARTIFACT_DIR / fname
        if p.exists():
            st.subheader(title)
            st.image(str(p), use_container_width=True)

    st.subheader("🏆 Final Model Justification")
    st.markdown(f"""
    **Chosen Model: {meta.get('best_model', 'XGBoost (Tuned)')}**

    | Criterion | Justification |
    |-----------|---------------|
    | Performance | Best CV ROC-AUC across all models |
    | Generalisation | Hyperparameter-tuned via 5-fold StratifiedKFold |
    | Speed | Sub-millisecond inference at production scale |
    | Interpretability | SHAP values provide transparent fraud explanations |
    | Imbalance Handling | `scale_pos_weight` natively handles class imbalance |

    **Fraud Detection Tradeoff:**
    > *Recall > Precision*. Missing a real fraud transaction is far more costly (financial loss, customer harm)
    than flagging a legitimate transaction for review. We optimise for recall while keeping false positives acceptable.
    """)

# ══════════════════════════════════════════════════════
# PAGE 4 — ABOUT
# ══════════════════════════════════════════════════════
elif "About" in page:
    st.title("ℹ️ About This System")
    st.markdown("""
    ## Credit Card Fraud Detection System

    **Stack:**
    - **Data**: 100,000 transactions, 1% fraud rate
    - **ML Models**: Logistic Regression, Random Forest, XGBoost, LightGBM
    - **Deep Learning**: Keras ANN (128→64→32→1) with BatchNorm + Dropout
    - **Imbalance**: SMOTE (sampling_strategy=0.2)
    - **Tuning**: RandomizedSearchCV with 5-fold StratifiedKFold
    - **Explainability**: SHAP TreeExplainer
    - **Deployment**: Streamlit

    **Feature Engineering:**
    - Hour, DayOfWeek, Month extracted from timestamp
    - IsWeekend, IsNightTxn binary flags
    - All 9 features selected via SelectKBest (F-statistic)

    **Architecture:**
    ```
    Input(9) → Dense(128,relu) → BN → Dropout(0.3)
             → Dense(64,relu)  → BN → Dropout(0.2)
             → Dense(32,relu)
             → Dense(1,sigmoid)
    ```
    Optimiser: Adam(lr=1e-3) | Loss: Binary CrossEntropy | EarlyStopping(patience=10)
    """)