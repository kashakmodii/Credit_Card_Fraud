"""
src/train.py — Full ML + ANN Pipeline
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, joblib, json
import matplotlib; matplotlib.use("Agg")
from pathlib import Path

from sklearn.model_selection import train_test_split, StratifiedKFold, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.metrics import classification_report, roc_auc_score
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("[WARN] TensorFlow not available - ANN will be skipped")

OUTDIR = Path("artifacts")
OUTDIR.mkdir(exist_ok=True)
SEED = 42


# ── 1. Load & Clean ──────────────────────────────────────────
def load_and_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.drop(columns=["TransactionID"], errors="ignore")

    # Parse datetime → temporal features
    df["TransactionDate"] = pd.to_datetime(df["TransactionDate"])
    df["Hour"]       = df["TransactionDate"].dt.hour
    df["DayOfWeek"]  = df["TransactionDate"].dt.dayofweek
    df["Month"]      = df["TransactionDate"].dt.month
    df["IsWeekend"]  = (df["DayOfWeek"] >= 5).astype(int)
    df["IsNightTxn"] = ((df["Hour"] < 6) | (df["Hour"] >= 22)).astype(int)
    df = df.drop(columns=["TransactionDate"])

    # Encode categoricals
    le_type = LabelEncoder()
    le_loc  = LabelEncoder()
    df["TransactionType"] = le_type.fit_transform(df["TransactionType"])
    df["Location"]        = le_loc.fit_transform(df["Location"])

    joblib.dump(le_type, OUTDIR / "le_type.pkl")
    joblib.dump(le_loc,  OUTDIR / "le_loc.pkl")

    print(f"[DATA] Shape: {df.shape} | Fraud rate: {df['IsFraud'].mean()*100:.2f}%")
    return df


# ── 2. Preprocess ────────────────────────────────────────────
def preprocess(df: pd.DataFrame):
    X, y = df.drop(columns=["IsFraud"]), df["IsFraud"]
    feature_names = X.columns.tolist()
    joblib.dump(feature_names, OUTDIR / "feature_names.pkl")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y)

    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc  = scaler.transform(X_test)
    joblib.dump(scaler, OUTDIR / "scaler.pkl")

    # SMOTE — fix class imbalance before training
    X_res, y_res = SMOTE(sampling_strategy=0.2, random_state=SEED).fit_resample(X_train_sc, y_train)
    print(f"[SMOTE] Class 0: {(y_res==0).sum()} | Class 1: {(y_res==1).sum()}")

    return X_res, X_test_sc, y_res, y_test, feature_names


# ── 3. Feature Selection ─────────────────────────────────────
def select_features(X_res, y_res, feature_names, k=9):
    selector = SelectKBest(f_classif, k=k)
    selector.fit(X_res, y_res)
    selected = [f for f, m in zip(feature_names, selector.get_support()) if m]
    joblib.dump(selector,  OUTDIR / "selector.pkl")
    joblib.dump(selected,  OUTDIR / "selected_features.pkl")
    print(f"[FEATURES] Selected: {selected}")
    return selector.transform(X_res), selector, selected


# ── 4. Train ML Models ───────────────────────────────────────
def train_ml_models(X_train, X_test, y_train, y_test):
    models = {
        "Logistic Regression": LogisticRegression(class_weight="balanced", max_iter=1000, random_state=SEED),
        "Random Forest":       RandomForestClassifier(n_estimators=200, class_weight="balanced", n_jobs=-1, random_state=SEED),
        "XGBoost":             XGBClassifier(n_estimators=200, scale_pos_weight=5, eval_metric="logloss", use_label_encoder=False, random_state=SEED, verbosity=0),
        "LightGBM":            LGBMClassifier(n_estimators=200, class_weight="balanced", random_state=SEED, verbose=-1),
    }
    results = []
    for name, model in models.items():
        model.fit(X_train, y_train)
        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = model.predict(X_test)
        rep = classification_report(y_test, y_pred, output_dict=True)
        auc = roc_auc_score(y_test, y_prob)
        print(f"[{name}] ROC-AUC: {auc:.4f} | Recall(fraud): {rep['1']['recall']:.4f}")
        results.append({"name": name, "precision": rep["1"]["precision"],
                        "recall": rep["1"]["recall"], "f1": rep["1"]["f1-score"],
                        "roc_auc": auc, "y_prob": y_prob, "y_pred": y_pred, "model": model})
    return results


# ── 5. Hyperparameter Tuning ─────────────────────────────────
def tune_best_model(X_train, y_train):
    param_dist = {
        "n_estimators":    [100, 200, 300],
        "max_depth":       [3, 5, 7],
        "learning_rate":   [0.01, 0.05, 0.1],
        "subsample":       [0.7, 0.8, 1.0],
        "colsample_bytree":[0.7, 0.8, 1.0],
        "scale_pos_weight":[3, 5, 10],
    }
    search = RandomizedSearchCV(
        XGBClassifier(eval_metric="logloss", use_label_encoder=False, random_state=SEED, verbosity=0),
        param_dist, n_iter=20,
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED),
        scoring="roc_auc", n_jobs=-1, random_state=SEED, verbose=1
    )
    search.fit(X_train, y_train)
    print(f"[TUNE] Best CV ROC-AUC: {search.best_score_:.4f}")
    print(f"[TUNE] Best params: {search.best_params_}")
    joblib.dump(search.best_estimator_, OUTDIR / "best_model.pkl")
    json.dump(search.best_params_, open(OUTDIR / "best_params.json", "w"), indent=2)
    return search.best_estimator_


# ── 6. ANN Model ─────────────────────────────────────────────
if TENSORFLOW_AVAILABLE:
    def build_ann(input_dim: int):
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
            optimizer=keras.optimizers.Adam(1e-3),
            loss="binary_crossentropy",
            metrics=["AUC", keras.metrics.Recall(name="recall")]
        )
        return model


    def train_ann(X_train, X_test, y_train, y_test):
        from sklearn.utils.class_weight import compute_class_weight
        cw = compute_class_weight("balanced", classes=np.unique(y_train), y=y_train)
        class_weight = {0: cw[0], 1: cw[1]}

        model = build_ann(X_train.shape[1])
        model.fit(
            X_train, y_train,
            validation_data=(X_test, y_test),
            epochs=60, batch_size=256,
            class_weight=class_weight,
            callbacks=[
                keras.callbacks.EarlyStopping(monitor="val_AUC", patience=10,
                                              restore_best_weights=True, mode="max"),
                keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=5),
            ],
            verbose=1,
        )
        model.save(OUTDIR / "ann_model.keras")

        y_prob = model.predict(X_test, verbose=0).ravel()
        y_pred = (y_prob >= 0.5).astype(int)
        rep = classification_report(y_test, y_pred, output_dict=True)
        auc = roc_auc_score(y_test, y_prob)
        print(f"[ANN] ROC-AUC: {auc:.4f} | Recall(fraud): {rep['1']['recall']:.4f}")

        return {"name": "ANN (Keras)", "precision": rep["1"]["precision"],
                "recall": rep["1"]["recall"], "f1": rep["1"]["f1-score"],
                "roc_auc": auc, "y_prob": y_prob, "y_pred": y_pred, "model": model}
else:
    def build_ann(*args, **kwargs):
        raise RuntimeError("TensorFlow not available")
    
    def train_ann(*args, **kwargs):
        raise RuntimeError("TensorFlow not available")