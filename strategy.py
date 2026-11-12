"""래리 윌리엄스 변동성 돌파(Volatility Breakout) 전략 규칙.

Range_{t-1} = High_{t-1} - Low_{t-1}
Target_t    = Open_t + Range_{t-1} * K
진입        : High_t >= Target_t 이면 매수 (체결가는 Target_t, 갭상승 시 시가)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_K = 0.5
K_GRID = (0.3, 0.4, 0.5, 0.6, 0.7)


def add_indicators(data: pd.DataFrame, k: float = DEFAULT_K,
                   ma_filter: int | None = None) -> pd.DataFrame:
    """전일 레인지, 목표가, 진입 신호, (선택) 이동평균 필터를 붙인 데이터프레임."""
    df = data.copy()

    df["Range_prev"] = (df["High"] - df["Low"]).shift(1)
    df["Target"] = df["Open"] + df["Range_prev"] * k
    df["Range_pct_prev"] = df["Range_prev"] / df["Close"].shift(1)

    # 목표가 도달 여부. 시가가 이미 목표가를 넘겼으면(갭상승) 시가 체결로 본다.
    df["Triggered"] = df["High"] >= df["Target"]
    df["Triggered"] = df["Triggered"].fillna(False)
    df["Entry_raw"] = np.where(df["Open"] >= df["Target"], df["Open"], df["Target"])

    # 진입 불가 행: 전일 레인지 없음 / 목표가 0 이하
    invalid = df["Range_prev"].isna() | (df["Range_prev"] <= 0) | (df["Target"] <= 0)
    df.loc[invalid, "Triggered"] = False

    df["Gap_entry"] = df["Triggered"] & (df["Open"] >= df["Target"])

    if ma_filter:
        df[f"MA{ma_filter}"] = df["Close"].rolling(ma_filter).mean().shift(1)
        df["Triggered"] = df["Triggered"] & (df["Open"] >= df[f"MA{ma_filter}"])
        df.loc[invalid, "Triggered"] = False

    return df


def signal_days(data: pd.DataFrame, k: float = DEFAULT_K,
                ma_filter: int | None = None) -> pd.Series:
    """진입 신호가 발생한 날짜의 불리언 시리즈."""
    return add_indicators(data, k, ma_filter)["Triggered"]


def describe() -> str:
    return (
        "변동성 돌파 전략\n"
        "  전일 레인지 = 전일 고가 - 전일 저가\n"
        "  목표가      = 당일 시가 + 전일 레인지 x K\n"
        "  매수        = 당일 고가가 목표가 이상이면 목표가(갭상승 시 시가)에 진입\n"
    )
