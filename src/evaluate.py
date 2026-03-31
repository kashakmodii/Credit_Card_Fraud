"""
src/evaluate.py — EDA, Evaluation Plots & Metrics
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from sklearn.metrics import roc_curve, confusion_matrix, roc_auc_score
import shap, joblib

OUTDIR = Path("artifacts")
OUTDIR.mkdir(exist_ok=True)


# ── EDA Plots ────────────────────────────────────────────────
def run_eda(df: pd.DataFrame):
    plt.style.use("seaborn-v0_8-whitegrid")

    # 1. Class distribution
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    counts = df["IsFraud"].value_counts()
    axes[0].bar(["Legit", "Fraud"], counts.values, color=["#2196F3", "#f44336"], edgecolor="white")
    axes[0].set_title("Class Distribution", fontweight="bold")
    for i, v in enumerate(counts.values):
        axes[0].text(i, v + 200, f"{v:,}", ha="center")
    axes[1].pie(counts.values, labels=["Legit", "Fraud"],
                colors=["#2196F3", "#f44336"], autopct="%1.2f%%",
                startangle=90, wedgeprops={"edgecolor": "white"})
    axes[1].set_title("Fraud vs Legit Ratio", fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_class_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2. Amount distribution
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for cls, color, label in [(0, "#2196F3", "Legit"), (1, "#f44336", "Fraud")]:
        axes[0].hist(df[df["IsFraud"] == cls]["Amount"], bins=50, alpha=0.7, color=color, label=label)
    axes[0].set_title("Amount Distribution", fontweight="bold")
    axes[0].legend()
    sns.boxplot(data=df.assign(IsFraud=df["IsFraud"].astype(str)),
                x="IsFraud", y="Amount",
                palette={"0": "#2196F3", "1": "#f44336"}, ax=axes[1])
    axes[1].set_title("Amount by Class", fontweight="bold")
    axes[1].set_xticklabels(["Legit", "Fraud"])
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_amount.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 3. Hourly fraud rate
    fig, ax = plt.subplots(figsize=(12, 4))
    hourly = df.groupby("Hour")["IsFraud"].mean() * 100
    ax.plot(hourly.index, hourly.values, color="#f44336", linewidth=2, marker="o", markersize=4)
    ax.fill_between(hourly.index, hourly.values, alpha=0.15, color="#f44336")
    ax.set_title("Fraud Rate by Hour of Day", fontweight="bold")
    ax.set_xlabel("Hour"); ax.set_ylabel("Fraud Rate (%)")
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_hourly_fraud.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 4. Correlation heatmap
    fig, ax = plt.subplots(figsize=(9, 7))
    corr = df.corr()
    sns.heatmap(corr, mask=np.triu(np.ones_like(corr, dtype=bool)),
                annot=True, fmt=".2f", cmap="RdBu_r", center=0,
                linewidths=0.5, ax=ax, annot_kws={"size": 9})
    ax.set_title("Feature Correlation Heatmap", fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUTDIR / "eda_correlation.png", dpi=150, bbox_inches="tight")
    plt.close()

    print("[EDA] All plots saved.")


# ── Model Evaluation ─────────────────────────────────────────
def plot_comparison(all_results, y_test):
    palette = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#f44336", "#00BCD4", "#FF5722"]

    # ROC Curves
    fig, ax = plt.subplots(figsize=(9, 6))
    for i, res in enumerate(all_results):
        fpr, tpr, _ = roc_curve(y_test, res["y_prob"])
        ax.plot(fpr, tpr, lw=2, color=palette[i],
                label=f"{res['name']}  (AUC={res['roc_auc']:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curves — All Models", fontweight="bold")
    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTDIR / "roc_curves.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Confusion Matrices
    n = len(all_results)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 3.5))
    if n == 1: axes = [axes]
    for ax, res in zip(axes, all_results):
        cm = confusion_matrix(y_test, res["y_pred"])
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=["Legit", "Fraud"],
                    yticklabels=["Legit", "Fraud"], ax=ax, linewidths=0.5)
        ax.set_title(res["name"], fontsize=9, fontweight="bold")
        ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    plt.tight_layout()
    plt.savefig(OUTDIR / "confusion_matrices.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Bar comparison
    df_cmp = pd.DataFrame([{
        "Model":     r["name"],
        "Precision": round(r["precision"], 4),
        "Recall":    round(r["recall"], 4),
        "F1-Score":  round(r["f1"], 4),
        "ROC-AUC":   round(r["roc_auc"], 4),
    } for r in all_results]).sort_values("ROC-AUC", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(df_cmp)); w = 0.2
    for i, (m, c) in enumerate(zip(["Precision","Recall","F1-Score","ROC-AUC"], palette)):
        ax.bar(x + i * w, df_cmp[m], w, label=m, color=c, alpha=0.85)
    ax.set_xticks(x + 1.5 * w)
    ax.set_xticklabels(df_cmp["Model"], rotation=15, ha="right")
    ax.set_ylim(0, 1.1)
    ax.set_title("Model Performance Comparison", fontweight="bold")
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUTDIR / "model_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()

    df_cmp.to_csv(OUTDIR / "model_comparison.csv", index=False)
    print("\n═══ MODEL COMPARISON ═══")
    print(df_cmp.to_string(index=False))
    return df_cmp


# ── Feature Importance + SHAP ────────────────────────────────
def plot_feature_importance(best_model, selected_features, X_test_sel):
    # Native importance
    try:
        imp = best_model.feature_importances_
        df_imp = pd.DataFrame({"Feature": selected_features, "Importance": imp}).sort_values("Importance")
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.barh(df_imp["Feature"], df_imp["Importance"], color="#2196F3", alpha=0.85)
        ax.set_title("Feature Importance (XGBoost)", fontweight="bold")
        plt.tight_layout()
        plt.savefig(OUTDIR / "feature_importance.png", dpi=150, bbox_inches="tight")
        plt.close()
    except Exception as e:
        print(f"[WARN] Importance: {e}")

    # SHAP
    try:
        explainer = shap.TreeExplainer(best_model)
        shap_vals = explainer.shap_values(X_test_sel[:500])
        shap.summary_plot(shap_vals, X_test_sel[:500],
                          feature_names=selected_features, show=False)
        plt.title("SHAP Feature Importance", fontweight="bold")
        plt.tight_layout()
        plt.savefig(OUTDIR / "shap_summary.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("[SHAP] Saved.")
    except Exception as e:
        print(f"[WARN] SHAP: {e}")