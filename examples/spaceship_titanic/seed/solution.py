"""Baseline solution for the Spaceship Titanic classification task.

Predicts which passengers were transported to an alternate dimension.
Uses a simple Random Forest with basic feature engineering.

Must define run(train_path, test_path) -> pd.DataFrame with columns
[PassengerId, Transported].
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Basic feature engineering."""
    df = df.copy()

    # Parse Cabin into deck, num, side
    cabin_split = df["Cabin"].str.split("/", expand=True)
    if cabin_split.shape[1] == 3:
        df["Deck"] = cabin_split[0]
        df["CabinNum"] = pd.to_numeric(cabin_split[1], errors="coerce")
        df["Side"] = cabin_split[2]
    else:
        df["Deck"] = np.nan
        df["CabinNum"] = np.nan
        df["Side"] = np.nan

    # Parse PassengerId to get group
    df["Group"] = df["PassengerId"].str.split("_").str[0].astype(int)

    # Total spending
    spend_cols = ["RoomService", "FoodCourt", "ShoppingMall", "Spa", "VRDeck"]
    df["TotalSpend"] = df[spend_cols].sum(axis=1)

    # Drop columns we can't use directly
    df = df.drop(columns=["Cabin", "Name", "PassengerId"], errors="ignore")

    # Encode categoricals
    cat_cols = ["HomePlanet", "Destination", "Deck", "Side"]
    for col in cat_cols:
        if col in df.columns:
            df[col] = df[col].astype("category").cat.codes

    # Convert booleans
    for col in ["CryoSleep", "VIP"]:
        if col in df.columns:
            df[col] = df[col].astype(float)

    return df


def run(train_path: str, test_path: str) -> pd.DataFrame:
    """Train model and predict on test set.

    Args:
        train_path: Path to training CSV (with Transported column).
        test_path: Path to test CSV (without Transported column).

    Returns:
        DataFrame with PassengerId and Transported columns.
    """
    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path)

    # Save IDs before feature engineering
    test_ids = test_df["PassengerId"].copy()

    # Separate target
    y_train = train_df["Transported"].astype(int)
    train_df = train_df.drop(columns=["Transported"])

    # Feature engineering
    X_train = engineer_features(train_df)
    X_test = engineer_features(test_df)

    # Align columns
    common_cols = X_train.columns.intersection(X_test.columns)
    X_train = X_train[common_cols]
    X_test = X_test[common_cols]

    # Fill missing values
    X_train = X_train.fillna(-1)
    X_test = X_test.fillna(-1)

    # Train
    model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    # Predict
    preds = model.predict(X_test)

    result = pd.DataFrame({
        "PassengerId": test_ids,
        "Transported": preds.astype(bool),
    })

    return result
