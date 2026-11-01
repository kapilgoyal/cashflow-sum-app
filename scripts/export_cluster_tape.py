"""
Export compact loan tape JSON with 4-feature K-Prototypes (k=3) labels.
Matches internal/plot_kproto_4feat_scatter_labeled.py / kproto_4feat_vs_cohort.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from kmodes.kprototypes import KPrototypes
from scipy.spatial import ConvexHull
from sklearn.preprocessing import StandardScaler

REPO = Path(__file__).resolve().parents[1]
STORE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files"
)
TAPE = STORE / "docs" / "data" / "Minimum_Case.xlsx"
OUT_JSON = REPO / "public" / "cluster-tape.json"

NUM = ["ORIGINAL_CLTV", "REMAINING_TERM", "refinance incentive"]
CAT = ["DOCUMENTATION_TYPE"]
K = 3
N_INIT = 3
MAX_ITER = 50
RANDOM_STATE = 42

CLUSTER_META = {
    0: {"code": "LLTV-LRI", "color": "#1f77b4", "label": "LLTV-LRI"},
    1: {"code": "HLTV-HRI", "color": "#ff7f0e", "label": "HLTV-HRI"},
    2: {"code": "HLTV-LRI", "color": "#2ca02c", "label": "HLTV-LRI"},
}


def load_work() -> pd.DataFrame:
    df = pd.read_excel(TAPE, sheet_name="Loan Tape")
    if "LOAN_ID" in df.columns:
        df = df.drop_duplicates(subset=["LOAN_ID"], keep="first")
    if "refinance incentive" not in df.columns:
        df["refinance incentive"] = (
            df["CURRENT_INTEREST_RATE"].astype(float) * 100 - 6.86
        )
    return df


def fit_labels(df: pd.DataFrame) -> np.ndarray:
    work = df[NUM + CAT].copy()
    for c in NUM:
        work[c] = pd.to_numeric(work[c], errors="coerce")
        work[c] = work[c].fillna(work[c].median())
    for c in CAT:
        work[c] = (
            work[c]
            .astype(str)
            .str.strip()
            .replace({"nan": "MISSING", "None": "MISSING", "": "MISSING"})
        )

    X_num = StandardScaler().fit_transform(work[NUM].to_numpy(dtype=float))
    X = np.empty((len(work), len(NUM) + len(CAT)), dtype=object)
    for j in range(len(NUM)):
        X[:, j] = X_num[:, j]
    X[:, len(NUM)] = work[CAT[0]].to_numpy()

    kp = KPrototypes(
        n_clusters=K,
        init="Huang",
        n_init=N_INIT,
        max_iter=MAX_ITER,
        random_state=RANDOM_STATE,
        verbose=0,
    )
    return kp.fit_predict(X, categorical=[len(NUM)]).astype(int)


def hull_points(pts: np.ndarray) -> list[dict[str, float]]:
    if len(pts) < 3:
        return []
    rounded = np.round(pts, decimals=8)
    _, uniq_idx = np.unique(rounded, axis=0, return_index=True)
    uniq = pts[np.sort(uniq_idx)]
    if len(uniq) < 3:
        return []
    try:
        hull = ConvexHull(uniq)
    except Exception:
        return []
    hull_pts = uniq[hull.vertices]
    closed = np.vstack([hull_pts, hull_pts[0]])
    return [
        {"cltv": round(float(x), 6), "incentive": round(float(y), 6)}
        for x, y in closed
    ]


def round_or_none(v, nd=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def main() -> None:
    df = load_work()
    labels = fit_labels(df)

    fico = pd.to_numeric(df.get("ORIGINAL_FICO"), errors="coerce")
    cltv = pd.to_numeric(df["ORIGINAL_CLTV"], errors="coerce")
    term = pd.to_numeric(df["REMAINING_TERM"], errors="coerce")
    incentive = pd.to_numeric(df["refinance incentive"], errors="coerce")
    docs = (
        df["DOCUMENTATION_TYPE"]
        .astype(str)
        .str.strip()
        .replace({"nan": "MISSING", "None": "MISSING", "": "MISSING"})
    )
    loan_ids = (
        df["LOAN_ID"].astype(str)
        if "LOAN_ID" in df.columns
        else pd.Series([f"LN-{i}" for i in range(len(df))])
    )

    loans = []
    for i in range(len(df)):
        cl = int(labels[i])
        meta = CLUSTER_META[cl]
        loans.append(
            {
                "loanId": loan_ids.iloc[i],
                "fico": round_or_none(fico.iloc[i], 0),
                "cltv": round_or_none(cltv.iloc[i], 6),
                "documentation": docs.iloc[i],
                "remainingTerm": round_or_none(term.iloc[i], 0),
                "refinanceIncentive": round_or_none(incentive.iloc[i], 6),
                "clusterId": cl,
                "cluster": meta["code"],
            }
        )

    counts = {CLUSTER_META[i]["code"]: int((labels == i).sum()) for i in range(K)}
    hulls = {}
    for cl in range(K):
        mask = labels == cl
        pts = np.column_stack(
            [
                cltv.to_numpy(dtype=float)[mask],
                incentive.to_numpy(dtype=float)[mask],
            ]
        )
        pts = pts[~np.isnan(pts).any(axis=1)]
        hulls[CLUSTER_META[cl]["code"]] = hull_points(pts)

    payload = {
        "meta": {
            "nLoans": len(loans),
            "features": NUM + CAT,
            "k": K,
            "randomState": RANDOM_STATE,
            "counts": counts,
            "colors": {m["code"]: m["color"] for m in CLUSTER_META.values()},
            "labels": {
                "HLTV-HRI": "Orange — high CLTV / high refinance incentive",
                "HLTV-LRI": "Green — high CLTV / low refinance incentive",
                "LLTV-LRI": "Blue — low CLTV / low refinance incentive",
            },
        },
        "hulls": hulls,
        "loans": loans,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    size_kb = OUT_JSON.stat().st_size / 1024
    print(f"Wrote {OUT_JSON} ({size_kb:.1f} KB)")
    print("counts:", counts)


if __name__ == "__main__":
    main()
