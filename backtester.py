"""변동성 돌파 백테스트 엔진.

청산 모드
  - next_open : 진입일 다음 거래일 시가 청산 (오버나잇 포지션, 기본)
  - same_close: 진입일 당일 종가 청산 (데이트레이딩)

비용
  - 슬리피지 편도 0.05%  (매수 체결가 x1.0005, 매도 체결가 x0.9995)
  - 수수료   편도 0.015% (매수 x1.00015, 매도 x0.99985)
  - 거래세   : 국내 주식형 ETF 비과세 (0%)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

import strategy as strategy_mod

INITIAL_CAPITAL = 100_000_000
SLIPPAGE = 0.0005
COMMISSION = 0.00015

EXIT_MODES = ("next_open", "same_close")
EXIT_LABEL = {
    "next_open": "익일 시가 청산",
    "same_close": "당일 종가 청산",
}


@dataclass
class BacktestResult:
    ticker: str
    k: float
    exit_mode: str
    initial_capital: float
    equity: pd.Series
    benchmark: pd.Series
    trades: pd.DataFrame
    exposure: float
    params: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def run_backtest(data: pd.DataFrame, k: float = strategy_mod.DEFAULT_K,
                 exit_mode: str = "next_open",
                 initial_capital: float = INITIAL_CAPITAL,
                 slippage: float = SLIPPAGE,
                 commission: float = COMMISSION,
                 tax: float = 0.0,
                 exclude_last_day_entry: bool = True,
                 ticker: str = "069500") -> BacktestResult:
    if exit_mode not in EXIT_MODES:
        raise ValueError(f"exit_mode 는 {EXIT_MODES} 중 하나여야 합니다: {exit_mode}")

    df = strategy_mod.add_indicators(data, k)
    dates = df.index
    n = len(df)
    last_i = n - 1

    buy_factor = (1 + slippage) * (1 + commission)
    sell_factor = (1 - slippage) * (1 - commission) * (1 - tax)

    cash = float(initial_capital)
    shares = 0
    position: dict | None = None
    trades: list[dict] = []
    equity_vals: list[float] = []
    held_days = 0

    for i in range(n):
        d = dates[i]
        row = df.iloc[i]

        # --- 1) 전일 진입분 청산 (익일 시가)
        if position is not None and exit_mode == "next_open":
            exit_raw = float(row["Open"])
            proceeds = shares * exit_raw * sell_factor
            pnl = proceeds - position["비용"]
            trades.append(_trade_row(position, d, exit_raw, proceeds, pnl,
                                     "익일 시가", cash + proceeds, sell_factor))
            cash += proceeds
            shares = 0
            position = None

        # --- 2) 신규 진입
        can_enter = position is None and bool(row["Triggered"])
        if exclude_last_day_entry and i == last_i:
            can_enter = False  # 마지막 봉은 청산가(다음 시가) 또는 당일 종가가 확정되지 않음
        if can_enter:
            entry_raw = float(row["Entry_raw"])
            unit_cost = entry_raw * buy_factor
            qty = int(math.floor(cash / unit_cost))
            if qty > 0:
                cost = qty * unit_cost
                cash -= cost
                shares = qty
                position = {
                    "진입일": d,
                    "전일레인지": float(row["Range_prev"]),
                    "목표가": float(row["Target"]),
                    "진입가(호가)": entry_raw,
                    "진입가(체결)": unit_cost,
                    "수량": qty,
                    "비용": cost,
                    "갭상승체결": bool(row["Gap_entry"]),
                    "당일고가": float(row["High"]),
                }

        # --- 3) 당일 종가 청산 (데이트레이딩 모드)
        if position is not None and exit_mode == "same_close":
            exit_raw = float(row["Close"])
            proceeds = shares * exit_raw * sell_factor
            pnl = proceeds - position["비용"]
            trades.append(_trade_row(position, d, exit_raw, proceeds, pnl,
                                     "당일 종가", cash + proceeds, sell_factor))
            cash += proceeds
            shares = 0
            position = None

        # --- 4) 일별 평가
        equity_vals.append(cash + shares * float(row["Close"]))
        if shares > 0:
            held_days += 1

    equity = pd.Series(equity_vals, index=dates, name="equity")

    # 벤치마크: 첫날 종가 매수 후 보유
    bench_shares = initial_capital / float(df["Close"].iloc[0])
    benchmark = (df["Close"] * bench_shares).rename("benchmark")

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["수익률(%)"] = trades_df["수익률(%)"].round(4)
        trades_df["실현손익(원)"] = trades_df["실현손익(원)"].round(0)
        trades_df["보유일수"] = 1

    notes = []
    if exclude_last_day_entry:
        notes.append(f"마지막 봉({dates[-1].date()})은 신규 진입 제외")

    return BacktestResult(
        ticker=ticker,
        k=k,
        exit_mode=exit_mode,
        initial_capital=initial_capital,
        equity=equity,
        benchmark=benchmark,
        trades=trades_df,
        exposure=held_days / n if n else 0.0,
        params={
            "k": k,
            "exit_mode": exit_mode,
            "slippage": slippage,
            "commission": commission,
            "initial_capital": initial_capital,
        },
        notes=notes,
    )


def _trade_row(pos: dict, exit_date, exit_raw: float, proceeds: float,
               pnl: float, reason: str, equity_after: float,
               sell_factor: float) -> dict:
    ret = (exit_raw * sell_factor) / pos["진입가(체결)"] - 1
    return {
        "진입일": pos["진입일"].strftime("%Y-%m-%d"),
        "청산일": exit_date.strftime("%Y-%m-%d"),
        "전일레인지": round(pos["전일레인지"], 2),
        "목표가": round(pos["목표가"], 2),
        "진입가": round(pos["진입가(체결)"], 2),
        "청산가": round(exit_raw, 2),
        "수량": pos["수량"],
        "수익률(%)": ret * 100,
        "실현손익(원)": pnl,
        "청산사유": reason,
        "갭상승체결": "Y" if pos["갭상승체결"] else "",
        "누적자산": round(equity_after, 0),
    }
