"""Smoke tests confirming the modeling library chain works end-to-end.

Each test trains a tiny model on synthetic balanced binary data with a
learnable signal in the first feature. These tests verify that the library
chain (xgboost, scikit-learn, SVM with Platt scaling) is importable and
functional — not statistical performance.
"""
import numpy as np

RANDOM_STATE = 42


def _synthetic_data(n_samples: int = 200, n_features: int = 8, seed: int = 42):
    """Generate a small balanced binary classification dataset.

    The first feature carries the signal (positive class iff x[:, 0] > 0);
    the rest is noise.
    """
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_samples, n_features))
    y = (X[:, 0] > 0).astype(int)
    return X, y


def test_xgboost_train_predict():
    """XGBoost trains and predicts on synthetic data."""
    import xgboost as xgb

    X, y = _synthetic_data()
    model = xgb.XGBClassifier(
        n_estimators=10, random_state=RANDOM_STATE, eval_metric="logloss"
    )
    model.fit(X, y)
    preds = model.predict(X)

    assert preds.shape == y.shape
    assert set(np.unique(preds)).issubset({0, 1})


def test_random_forest_train_predict():
    """Random Forest trains and predicts on synthetic data."""
    from sklearn.ensemble import RandomForestClassifier

    X, y = _synthetic_data()
    model = RandomForestClassifier(
        n_estimators=10, random_state=RANDOM_STATE, n_jobs=1
    )
    model.fit(X, y)
    preds = model.predict(X)

    assert preds.shape == y.shape
    assert set(np.unique(preds)).issubset({0, 1})


def test_svm_train_predict_with_probability():
    """SVC with probability=True and a fixed random_state produces predictions.

    Verifies the Platt-scaling code path that requires a seeded random_state
    for deterministic probability calibration.
    """
    from sklearn.svm import SVC

    X, y = _synthetic_data()
    model = SVC(probability=True, random_state=RANDOM_STATE)
    model.fit(X, y)
    preds = model.predict(X)
    proba = model.predict_proba(X)

    assert preds.shape == y.shape
    assert set(np.unique(preds)).issubset({0, 1})
    assert proba.shape == (len(y), 2)
