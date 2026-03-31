"""
=============================================================
 CREDIT CARD FRAUD DETECTION — End-to-End ML Pipeline
 Senior AI/ML Engineer production-ready solution
=============================================================
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Sklearn
from sklearn.model_selection import train_test_split, StratifiedKFold, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (classification_report, confusion_matrix, roc_auc_score,
                             roc_curve, precision_recall_curve, f1_score)
from sklearn.feature_selection import SelectKBest, f_classif

# Imbalanced
from imblearn.over_sampling import SMOTE

# Boosting
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

# Deep Learning
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("[WARN] TensorFlow not available. Using ML models only.")

# Explainability
import shap

import joblib
import json

# ── Output directory ───────────────────────────────────────
OUTDIR = Path("artifacts")
OUTDIR.mkdir(exist_ok=True)

SEED = 42
np.random.seed(SEED)
if TENSORFLOW_AVAILABLE:
    tf.random.set_seed(SEED)


# ══════════════════════════════════════════════════════════════
# 1. DATA LOADING & CLEANING
# ══════════════════════════════════════════════════════════════

def load_and_clean(path: str) -> pd.DataFrame:
    """Load CSV, inspect structure, clean and type-cast."""
    df = pd.read_csv(path)
    print(f"[DATA] Shape: {df.shape}")
    print(f"[DATA] Columns: {df.columns.tolist()}")
    print(f"[DATA] Missing values:\n{df.isnull().sum()}")
    print(f"[DATA] Dtypes:\n{df.dtypes}")

    # Drop ID column — no predictive value
    df = df.drop(columns=["TransactionID"], errors="ignore")

    # Parse datetime and extract temporal features
    df["TransactionDate"] = pd.to_datetime(df["TransactionDate"])
    df["Hour"]       = df["TransactionDate"].dt.hour
    df["DayOfWeek"]  = df["TransactionDate"].dt.dayofweek
    df["Month"]      = df["TransactionDate"].dt.month
    df["IsWeekend"]  = (df["DayOfWeek"] >= 5).astype(int)
    df["IsNightTxn"] = ((df["Hour"] < 6) | (df["Hour"] >= 22)).astype(int)
    df = df.drop(columns=["TransactionDate"])

    # Encode categoricals
    le_type = LabelEncoder()
    df["TransactionType"] = le_type.fit_transform(df["TransactionType"])

    le_loc = LabelEncoder()
    df["Location"] = le_loc.fit_transform(df["Location"])

    # Save encoders for inference
    joblib.dump(le_type, OUTDIR / "le_type.pkl")
    joblib.dump(le_loc,  OUTDIR / "le_loc.pkl")

    print(f"\n[DATA] Fraud rate: {df['IsFraud'].mean()*100:.2f}%")
    return df


# ══════════════════════════════════════════════════════════════
# 2. EDA — saved as PNGs for Streamlit
# ══════════════════════════════════════════════════════════════

def run_eda(df: pd.DataFrame):
    """Generate EDA plots and save to artifacts/."""
    plt.style.use("seaborn-v0_8-whitegrid")

    # 2a — Class distribution
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    counts = df["IsFraud"].value_counts()
    axes[0].bar(["Legit", "Fraud"], counts.values,
                color=["#2196F3", "#f44336"], edgecolor="white", linewidth=1.5)
    axes[0].set_title("Transaction Class Distribution", fontsize=13, fontweight="bold")
    axes[0].set_ylabel("Count")
    for i, v in enumerate(counts.values):
        axes[0].text(i, v + 200, f"{v:,}", ha="center", fontsize=10)

    # Pie
    axes[1].pie(counts.values, labels=["Legit", "Fraud"],
                colors=["#2196F3", "#f44336"], autopct="%1.2f%%",
                startangle=90, wedgeprops={"edgecolor": "white"})
    axes[1].set_title("Fraud vs Legit Ratio", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_class_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2b — Amount distribution by class
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for cls, color, label in [(0, "#2196F3", "Legit"), (1, "#f44336", "Fraud")]:
        axes[0].hist(df[df["IsFraud"] == cls]["Amount"], bins=50,
                     alpha=0.7, color=color, label=label)
    axes[0].set_title("Amount Distribution by Class", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Amount ($)")
    axes[0].legend()

    sns.boxplot(data=df.assign(IsFraud=df["IsFraud"].astype(str)),
                x="IsFraud", y="Amount",
                palette={"0": "#2196F3", "1": "#f44336"}, ax=axes[1])
    axes[1].set_title("Amount Boxplot by Class", fontsize=12, fontweight="bold")
    axes[1].set_xticklabels(["Legit", "Fraud"])
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_amount.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2c — Hourly fraud pattern
    fig, ax = plt.subplots(figsize=(12, 4))
    hourly = df.groupby("Hour")["IsFraud"].mean() * 100
    ax.plot(hourly.index, hourly.values, color="#f44336", linewidth=2, marker="o", markersize=4)
    ax.fill_between(hourly.index, hourly.values, alpha=0.15, color="#f44336")
    ax.set_title("Fraud Rate by Hour of Day", fontsize=13, fontweight="bold")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Fraud Rate (%)")
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_hourly_fraud.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2d — Correlation heatmap
    fig, ax = plt.subplots(figsize=(9, 7))
    corr = df.corr()
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="RdBu_r",
                center=0, linewidths=0.5, ax=ax, annot_kws={"size": 9})
    ax.set_title("Feature Correlation Heatmap", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_correlation.png", dpi=150, bbox_inches="tight")
    plt.close()

    print("[EDA] All plots saved.")


# ══════════════════════════════════════════════════════════════
# 3. PREPROCESSING — Scaling + SMOTE
# ══════════════════════════════════════════════════════════════

def preprocess(df: pd.DataFrame):
    """Scale features, apply SMOTE, split train/test."""
    X = df.drop(columns=["IsFraud"])
    y = df["IsFraud"]

    FEATURE_NAMES = X.columns.tolist()
    joblib.dump(FEATURE_NAMES, OUTDIR / "feature_names.pkl")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y)

    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc  = scaler.transform(X_test)
    joblib.dump(scaler, OUTDIR / "scaler.pkl")

    # SMOTE: oversample minority class to 1:5 ratio
    # WHY: With 1% fraud rate, models learn to always predict Legit.
    # SMOTE synthesises new minority samples → forces model to learn fraud patterns.
    smote = SMOTE(sampling_strategy=0.2, random_state=SEED)
    X_res, y_res = smote.fit_resample(X_train_sc, y_train)
    print(f"[PREPROCESS] After SMOTE — Class 0: {(y_res==0).sum()} | Class 1: {(y_res==1).sum()}")

    return X_res, X_test_sc, y_res, y_test, scaler, FEATURE_NAMES


# ══════════════════════════════════════════════════════════════
# 4. FEATURE SELECTION
# ══════════════════════════════════════════════════════════════

def select_features(X_res, y_res, feature_names, k=9):
    """SelectKBest — F-statistic for ranking features."""
    selector = SelectKBest(f_classif, k=k)
    selector.fit(X_res, y_res)
    mask = selector.get_support()
    selected = [f for f, m in zip(feature_names, mask) if m]
    scores   = dict(zip(feature_names, selector.scores_))
    print(f"[FEATURES] Selected ({k}): {selected}")
    joblib.dump(selector, OUTDIR / "selector.pkl")
    return selector.transform(X_res), selector, selected, scores


# ══════════════════════════════════════════════════════════════
# 5. MACHINE LEARNING MODELS
# ══════════════════════════════════════════════════════════════

def evaluate_model(model, X_test_sel, y_test, name):
    """Compute and print classification metrics."""
    y_pred  = model.predict(X_test_sel)
    y_prob  = model.predict_proba(X_test_sel)[:, 1]
    roc_auc = roc_auc_score(y_test, y_prob)
    report  = classification_report(y_test, y_pred, output_dict=True)
    print(f"\n── {name} ──")
    print(classification_report(y_test, y_pred, target_names=["Legit", "Fraud"]))
    print(f"ROC-AUC: {roc_auc:.4f}")
    return {
        "name":      name,
        "precision": report["1"]["precision"],
        "recall":    report["1"]["recall"],
        "f1":        report["1"]["f1-score"],
        "roc_auc":   roc_auc,
        "y_prob":    y_prob,
        "y_pred":    y_pred,
        "model":     model,
    }


def train_ml_models(X_train_sel, X_test_sel, y_res, y_test):
    """Train LR, RF, XGB, LGBM; return results list."""
    models = {
        "Logistic Regression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=SEED),
        "Random Forest": RandomForestClassifier(
            n_estimators=200, class_weight="balanced", n_jobs=-1, random_state=SEED),
        "XGBoost": XGBClassifier(
            n_estimators=200, scale_pos_weight=5,
            eval_metric="logloss", use_label_encoder=False,
            random_state=SEED, verbosity=0),
        "LightGBM": LGBMClassifier(
            n_estimators=200, class_weight="balanced",
            random_state=SEED, verbose=-1),
    }

    results = []
    for name, model in models.items():
        print(f"\n[TRAIN] {name}...")
        model.fit(X_train_sel, y_res)
        res = evaluate_model(model, X_test_sel, y_test, name)
        results.append(res)

    return results


# ══════════════════════════════════════════════════════════════
# 6. HYPERPARAMETER TUNING — Best ML model
# ══════════════════════════════════════════════════════════════

def tune_best_model(X_train_sel, y_res, best_name):
    """RandomizedSearchCV on XGBoost (typically best performer)."""
    print(f"\n[TUNE] Tuning {best_name} ...")
    param_dist = {
        "n_estimators":    [100, 200, 300],
        "max_depth":       [3, 5, 7],
        "learning_rate":   [0.01, 0.05, 0.1],
        "subsample":       [0.7, 0.8, 1.0],
        "colsample_bytree":[0.7, 0.8, 1.0],
        "scale_pos_weight":[3, 5, 10],
    }
    base = XGBClassifier(eval_metric="logloss", use_label_encoder=False,
                         random_state=SEED, verbosity=0)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    search = RandomizedSearchCV(
        base, param_dist, n_iter=20, cv=cv,
        scoring="roc_auc", n_jobs=-1, random_state=SEED, verbose=1)
    search.fit(X_train_sel, y_res)
    print(f"[TUNE] Best params: {search.best_params_}")
    print(f"[TUNE] Best CV ROC-AUC: {search.best_score_:.4f}")
    return search.best_estimator_, search.best_params_


# ══════════════════════════════════════════════════════════════
# 7. ANN MODEL
# ══════════════════════════════════════════════════════════════

def build_ann(input_dim: int):
    """
    Architecture rationale:
    - Dense(128, relu) → sufficient capacity for tabular fraud patterns
    - BatchNorm + Dropout(0.3) → regularisation, prevents overfitting
    - Dense(64, relu) → mid-level feature abstraction
    - Dense(1, sigmoid) → binary output probability
    - Adam(1e-3) → adaptive lr, fast convergence on imbalanced data
    - focal_loss-like class_weight → handles 1:99 imbalance
    """
    inp = keras.Input(shape=(input_dim,))
    x   = layers.Dense(128, activation="relu")(inp)
    x   = layers.BatchNormalization()(x)
    x   = layers.Dropout(0.3)(x)
    x   = layers.Dense(64, activation="relu")(x)
    x   = layers.BatchNormalization()(x)
    x   = layers.Dropout(0.2)(x)
    x   = layers.Dense(32, activation="relu")(x)
    out = layers.Dense(1, activation="sigmoid")(x)

    model = keras.Model(inputs=inp, outputs=out)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=["AUC", keras.metrics.Recall(name="recall"),
                 keras.metrics.Precision(name="precision")]
    )
    return model


def train_ann(X_train_sel, X_test_sel, y_res, y_test):
    """Train ANN with callbacks and class weights."""
    # Compute class weight to handle residual imbalance post-SMOTE
    from sklearn.utils.class_weight import compute_class_weight
    cw = compute_class_weight("balanced", classes=np.unique(y_res), y=y_res)
    class_weight = {0: cw[0], 1: cw[1]}

    model = build_ann(X_train_sel.shape[1])
    model.summary()

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_AUC", patience=10, restore_best_weights=True, mode="max"),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=5, min_lr=1e-6),
    ]

    history = model.fit(
        X_train_sel, y_res,
        validation_data=(X_test_sel, y_test),
        epochs=60,
        batch_size=256,
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=1,
    )

    model.save(OUTDIR / "ann_model.keras")
    print("[ANN] Model saved.")

    # Plot learning curves
    _plot_ann_history(history)

    # Evaluate
    y_prob_ann = model.predict(X_test_sel).ravel()
    y_pred_ann = (y_prob_ann >= 0.5).astype(int)
    roc_auc    = roc_auc_score(y_test, y_prob_ann)
    report     = classification_report(y_test, y_pred_ann, output_dict=True)
    print("\n── ANN ──")
    print(classification_report(y_test, y_pred_ann, target_names=["Legit", "Fraud"]))
    print(f"ROC-AUC: {roc_auc:.4f}")

    return {
        "name":      "ANN (Keras)",
        "precision": report["1"]["precision"],
        "recall":    report["1"]["recall"],
        "f1":        report["1"]["f1-score"],
        "roc_auc":   roc_auc,
        "y_prob":    y_prob_ann,
        "y_pred":    y_pred_ann,
        "model":     model,
    }, history


def _plot_ann_history(history):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(history.history["loss"],     label="Train Loss", color="#2196F3")
    axes[0].plot(history.history["val_loss"], label="Val Loss",   color="#f44336")
    axes[0].set_title("ANN — Loss Curves", fontweight="bold")
    axes[0].legend()

    axes[1].plot(history.history["AUC"],     label="Train AUC", color="#2196F3")
    axes[1].plot(history.history["val_AUC"], label="Val AUC",   color="#f44336")
    axes[1].set_title("ANN — AUC Curves", fontweight="bold")
    axes[1].legend()
    plt.tight_layout()
    plt.savefig(OUTDIR / "ann_learning_curves.png", dpi=150, bbox_inches="tight")
    plt.close()


# ══════════════════════════════════════════════════════════════
# 8. EVALUATION VISUALS
# ══════════════════════════════════════════════════════════════

def plot_comparison(all_results, y_test):
    """ROC curves, confusion matrices, model comparison table."""

    # ── ROC Curves ──
    fig, ax = plt.subplots(figsize=(9, 6))
    palette = ["#2196F3","#4CAF50","#FF9800","#9C27B0","#f44336","#00BCD4","#FF5722"]
    for i, res in enumerate(all_results):
        fpr, tpr, _ = roc_curve(y_test, res["y_prob"])
        ax.plot(fpr, tpr, lw=2, color=palette[i],
                label=f"{res['name']}  (AUC={res['roc_auc']:.3f})")
    ax.plot([0,1],[0,1],"k--", lw=1)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curves — All Models", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTDIR / "roc_curves.png", dpi=150, bbox_inches="tight")
    plt.close()

    # ── Confusion Matrices ──
    n = len(all_results)
    fig, axes = plt.subplots(1, n, figsize=(4*n, 3.5))
    if n == 1: axes = [axes]
    for ax, res in zip(axes, all_results):
        cm = confusion_matrix(y_test, res["y_pred"])
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=["Legit","Fraud"],
                    yticklabels=["Legit","Fraud"], ax=ax,
                    linewidths=0.5)
        ax.set_title(res["name"], fontsize=9, fontweight="bold")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
    plt.tight_layout()
    plt.savefig(OUTDIR / "confusion_matrices.png", dpi=150, bbox_inches="tight")
    plt.close()

    # ── Model Comparison Table ──
    df_cmp = pd.DataFrame([{
        "Model":     r["name"],
        "Precision": round(r["precision"], 4),
        "Recall":    round(r["recall"], 4),
        "F1-Score":  round(r["f1"], 4),
        "ROC-AUC":   round(r["roc_auc"], 4),
    } for r in all_results]).sort_values("ROC-AUC", ascending=False)
    print("\n═══ MODEL COMPARISON ═══")
    print(df_cmp.to_string(index=False))
    df_cmp.to_csv(OUTDIR / "model_comparison.csv", index=False)

    # Bar chart
    fig, ax = plt.subplots(figsize=(10, 5))
    x   = np.arange(len(df_cmp))
    w   = 0.2
    metrics = ["Precision","Recall","F1-Score","ROC-AUC"]
    colors  = ["#2196F3","#4CAF50","#FF9800","#9C27B0"]
    for i, (m, c) in enumerate(zip(metrics, colors)):
        ax.bar(x + i*w, df_cmp[m], w, label=m, color=c, alpha=0.85)
    ax.set_xticks(x + 1.5*w)
    ax.set_xticklabels(df_cmp["Model"], rotation=15, ha="right")
    ax.set_ylim(0, 1.1)
    ax.set_title("Model Performance Comparison", fontsize=13, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUTDIR / "model_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()

    return df_cmp


# ══════════════════════════════════════════════════════════════
# 9. FEATURE IMPORTANCE + SHAP
# ══════════════════════════════════════════════════════════════

def plot_feature_importance(best_model, selected_features, X_test_sel, y_test):
    """XGBoost native importance + SHAP summary."""

    # Native importance
    try:
        imp = best_model.feature_importances_
        df_imp = pd.DataFrame({"Feature": selected_features, "Importance": imp})
        df_imp = df_imp.sort_values("Importance", ascending=True)
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.barh(df_imp["Feature"], df_imp["Importance"], color="#2196F3", alpha=0.85)
        ax.set_title("Feature Importance (XGBoost)", fontsize=13, fontweight="bold")
        ax.set_xlabel("Importance Score")
        plt.tight_layout()
        plt.savefig(OUTDIR / "feature_importance.png", dpi=150, bbox_inches="tight")
        plt.close()
    except Exception as e:
        print(f"[WARN] Native importance failed: {e}")

    # SHAP
    try:
        sample = X_test_sel[:500]  # fast sample
        explainer = shap.TreeExplainer(best_model)
        shap_vals  = explainer.shap_values(sample)
        fig, ax = plt.subplots(figsize=(9, 5))
        shap.summary_plot(shap_vals, sample, feature_names=selected_features,
                          show=False, plot_size=None)
        plt.title("SHAP Feature Importance", fontsize=13, fontweight="bold")
        plt.tight_layout()
        plt.savefig(OUTDIR / "shap_summary.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("[SHAP] SHAP summary saved.")
    except Exception as e:
        print(f"[WARN] SHAP failed: {e}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    DATA_PATH = "data/credit_card_fraud_dataset.csv"

    # 1. Load & Clean
    df = load_and_clean(DATA_PATH)

    # 2. EDA
    run_eda(df)

    # 3. Preprocess
    X_res, X_test_sc, y_res, y_test, scaler, feature_names = preprocess(df)

    # 4. Feature Selection
    X_train_sel, selector, selected_features, feat_scores = select_features(
        X_res, y_res, feature_names)
    X_test_sel = selector.transform(X_test_sc)

    # Save selected feature names
    joblib.dump(selected_features, OUTDIR / "selected_features.pkl")

    # 5. Train ML models
    ml_results = train_ml_models(X_train_sel, X_test_sel, y_res, y_test)

    # 6. Tune best ML model (XGBoost)
    tuned_xgb, best_params = tune_best_model(X_train_sel, y_res, "XGBoost")
    tuned_res = evaluate_model(tuned_xgb, X_test_sel, y_test, "XGBoost (Tuned)")
    joblib.dump(tuned_xgb, OUTDIR / "best_model.pkl")
    with open(OUTDIR / "best_params.json", "w") as f:
        json.dump(best_params, f, indent=2)

    # 7. ANN (skip if TensorFlow unavailable)
    all_results = ml_results + [tuned_res]
    if TENSORFLOW_AVAILABLE:
        ann_res, history = train_ann(X_train_sel, X_test_sel, y_res, y_test)
        all_results.append(ann_res)
    else:
        print("[INFO] Skipping ANN due to TensorFlow unavailability.")

    # 8. Evaluation comparison
    df_cmp = plot_comparison(all_results, y_test)

    # 9. Feature importance + SHAP
    plot_feature_importance(tuned_xgb, selected_features, X_test_sel, y_test)

    # 10. Save metadata
    meta = {
        "selected_features": selected_features,
        "best_model":        "XGBoost (Tuned)",
        "best_roc_auc":      tuned_res["roc_auc"],
        "best_recall":       tuned_res["recall"],
        "fraud_rate":        float(y_test.mean()),
    }
    with open(OUTDIR / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print("\n✅ Training complete. All artifacts saved to ./artifacts/")
    print(df_cmp.to_string(index=False))


if __name__ == "__main__":
    main()