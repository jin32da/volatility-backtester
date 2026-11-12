"""성과 지표 계산 모듈 (누적 수익률, CAGR, MDD, 샤프, 승률, PF, 페이오프, 연도별)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252
RISK_FREE = 0.0  # 지표 비교를 단순화하기 위해 무위험수익률 0% 기준


def _period_years(index: pd.DatetimeIndex) -> float:
    days = (index[-1] - index[0]).days
    return max(days / 365.25, 1e-9)


def total_return(equity: pd.Series) -> float:
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def cagr(equity: pd.Series) -> float:
    years = _period_years(equity.index)
    growth = float(equity.iloc[-1] / equity.iloc[0])
    if growth <= 0:
        return -1.0
    return growth ** (1 / years) - 1


def drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def mdd(equity: pd.Series) -> float:
    return float(drawdown_series(equity).min())


def mdd_detail(equity: pd.Series) -> dict:
    dd = drawdown_series(equity)
    trough = dd.idxmin()
    peak = equity.loc[:trough].idxmax()
    after = equity.loc[trough:]
    rec = after[after >= equity.loc[peak]]
    return {
        "mdd": float(dd.min()),
        "peak_date": peak,
        "trough_date": trough,
        "recovery_date": rec.index[0] if len(rec) else None,
        "underwater": dd,
    }


def sharpe(equity: pd.Series, rf: float = RISK_FREE) -> float:
    rets = equity.pct_change().dropna()
    if len(rets) < 2 or rets.std() == 0:
        return 0.0
    excess = rets - rf / TRADING_DAYS
    return float(excess.mean() / rets.std() * math.sqrt(TRADING_DAYS))


def sortino(equity: pd.Series, rf: float = RISK_FREE) -> float:
    rets = equity.pct_change().dropna()
    if len(rets) < 2:
        return 0.0
    excess = rets - rf / TRADING_DAYS
    downside = rets[rets < 0]
    if len(downside) < 2:
        return 0.0
    dd_std = math.sqrt(float((downside ** 2).mean()))
    if dd_std == 0:
        return 0.0
    return float(excess.mean() / dd_std * math.sqrt(TRADING_DAYS))


def annual_volatility(equity: pd.Series) -> float:
    rets = equity.pct_change().dropna()
    return float(rets.std() * math.sqrt(TRADING_DAYS))


def calmar(equity: pd.Series) -> float:
    m = mdd(equity)
    return float(cagr(equity) / abs(m)) if m < 0 else 0.0


def yearly_returns(equity: pd.Series) -> pd.Series:
    """연도별 수익률 (해당 연도 마지막 평가액 / 전년도 마지막 평가액 - 1)."""
    if equity.empty:
        return pd.Series(dtype=float)
    year_end = equity.groupby(equity.index.year).last()
    prev = year_end.shift(1)
    prev.iloc[0] = float(equity.iloc[0])
    return (year_end / prev - 1).rename("수익률")


def _max_consecutive_losses(returns: pd.Series) -> int:
    best = cur = 0
    for r in returns:
        if r < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def trade_stats(trades: pd.DataFrame) -> dict:
    empty = {
        "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
        "profit_factor": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "payoff": 0.0,
        "avg_return": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
        "max_consec_losses": 0, "avg_win_amt": 0.0, "avg_loss_amt": 0.0,
        "gross_profit": 0.0, "gross_loss": 0.0, "gap_entries": 0,
    }
    if trades is None or trades.empty:
        return empty

    ret = trades["수익률(%)"] / 100.0
    pnl = trades["실현손익(원)"]
    wins = ret > 0
    losses = ret <= 0
    gp = float(pnl[wins].sum())
    gl = float(-pnl[losses].sum())
    avg_win = float(ret[wins].mean()) if wins.any() else 0.0
    avg_loss = float(ret[losses].mean()) if losses.any() else 0.0
    return {
        "trades": int(len(trades)),
        "wins": int(wins.sum()),
        "losses": int(losses.sum()),
        "win_rate": float(wins.mean()),
        "profit_factor": (gp / gl) if gl > 0 else float("inf"),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": (avg_win / abs(avg_loss)) if avg_loss < 0 else 0.0,
        "avg_return": float(ret.mean()),
        "best_trade": float(ret.max()),
        "worst_trade": float(ret.min()),
        "max_consec_losses": _max_consecutive_losses(ret),
        "avg_win_amt": float(pnl[wins].mean()) if wins.any() else 0.0,
        "avg_loss_amt": float(pnl[losses].mean()) if losses.any() else 0.0,
        "gross_profit": gp,
        "gross_loss": gl,
        "gap_entries": int((trades["갭상승체결"] == "Y").sum()),
    }


def summarize(result) -> dict:
    eq, bm = result.equity, result.benchmark
    dd = mdd_detail(eq)
    stats = trade_stats(result.trades)
    return {
        "ticker": result.ticker,
        "k": result.k,
        "exit_mode": result.exit_mode,
        "start": eq.index[0],
        "end": eq.index[-1],
        "years": _period_years(eq.index),
        "initial": result.initial_capital,
        "final": float(eq.iloc[-1]),
        "total_return": total_return(eq),
        "cagr": cagr(eq),
        "mdd": dd["mdd"],
        "mdd_peak": dd["peak_date"],
        "mdd_trough": dd["trough_date"],
        "mdd_recovery": dd["recovery_date"],
        "underwater": dd["underwater"],
        "sharpe": sharpe(eq),
        "sortino": sortino(eq),
        "vol": annual_volatility(eq),
        "calmar": calmar(eq),
        "exposure": result.exposure,
        "yearly": yearly_returns(eq),
        "benchmark": {
            "final": float(bm.iloc[-1]),
            "total_return": total_return(bm),
            "cagr": cagr(bm),
            "mdd": mdd(bm),
            "sharpe": sharpe(bm),
            "sortino": sortino(bm),
            "vol": annual_volatility(bm),
            "underwater": drawdown_series(bm),
            "yearly": yearly_returns(bm),
        },
        "trades": stats,
        "params": result.params,
        "notes": result.notes,
        "equity": eq,
        "trades_df": result.trades,
    }


def format_summary(s: dict, benchmark_name: str = "KODEX 200") -> str:
    t = s["trades"]
    b = s["benchmark"]
    pf = "inf" if math.isinf(t["profit_factor"]) else f"{t['profit_factor']:.2f}"
    dd_txt = s["mdd_trough"].strftime("%Y-%m-%d")
    rec = s["mdd_recovery"]
    rec_txt = rec.strftime("%Y-%m-%d") if rec is not None else "미회복"
    rows = [
        ("백테스트 기간", f"{s['start'].strftime('%Y-%m-%d')} ~ {s['end'].strftime('%Y-%m-%d')} ({s['years']:.1f}년)"),
        ("대상 / K / 청산", f"{s['ticker']} / K={s['k']:.1f} / {s['exit_mode']}"),
        ("초기 자본", f"{s['initial']:,.0f}원"),
        ("최종 자산", f"{s['final']:,.0f}원"),
        ("총 수익률", f"{s['total_return']*100:+.2f}%"),
        ("CAGR (연평균)", f"{s['cagr']*100:+.2f}%"),
        ("최대 낙폭 (MDD)", f"{s['mdd']*100:.2f}% (저점 {dd_txt}, 회복 {rec_txt})"),
        ("샤프 지수 (rf 0%)", f"{s['sharpe']:.2f}"),
        ("소르티노 지수", f"{s['sortino']:.2f}"),
        ("연변동성", f"{s['vol']*100:.2f}%"),
        ("칼마 지수", f"{s['calmar']:.2f}"),
        ("시장 노출도 (보유일 비중)", f"{s['exposure']*100:.1f}%"),
        ("총 거래 횟수", f"{t['trades']}회"),
        ("승 / 패", f"{t['wins']}승 / {t['losses']}패"),
        ("승률", f"{t['win_rate']*100:.1f}%"),
        ("손익비 (Profit Factor)", pf),
        ("평균 수익 / 평균 손실", f"{t['avg_win']*100:+.2f}% / {t['avg_loss']*100:+.2f}%"),
        ("페이오프 (평균수익÷|평균손실|)", f"{t['payoff']:.2f}"),
        ("평균 손익금액", f"{t['avg_win_amt']:+,.0f}원 / {t['avg_loss_amt']:+,.0f}원"),
        ("최대 연속 손실", f"{t['max_consec_losses']}회"),
        ("최고 / 최저 거래", f"{t['best_trade']*100:+.2f}% / {t['worst_trade']*100:+.2f}%"),
        ("갭상승 시가 체결", f"{t['gap_entries']}건"),
    ]
    bm_rows = [
        ("Buy & Hold 최종 자산", f"{b['final']:,.0f}원"),
        ("Buy & Hold 총 수익률", f"{b['total_return']*100:+.2f}%"),
        ("Buy & Hold CAGR", f"{b['cagr']*100:+.2f}%"),
        ("Buy & Hold MDD", f"{b['mdd']*100:.2f}%"),
        ("Buy & Hold 샤프", f"{b['sharpe']:.2f}"),
        ("Buy & Hold 연변동성", f"{b['vol']*100:.2f}%"),
    ]
    width = 34
    line = "=" * 70
    out = [line, " 변동성 돌파 백테스트 결과 요약", line]
    out += [f" {k:<{width}} {v}" for k, v in rows]
    out += [line, f" 벤치마크 ({benchmark_name} 단순보유)", line]
    out += [f" {k:<{width}} {v}" for k, v in bm_rows]
    out.append(line)
    return "\n".join(out)


def format_yearly_table(s: dict) -> str:
    ys = s["yearly"]
    by = s["benchmark"]["yearly"]
    lines = ["연도    전략        Buy&Hold    차이"]
    for year in ys.index:
        a = ys.get(year, float("nan"))
        b = by.get(year, float("nan"))
        lines.append(f"{year}  {a*100:+8.2f}%  {b*100:+8.2f}%  {(a-b)*100:+8.2f}%p")
    return "\n".join(lines)
