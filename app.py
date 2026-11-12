"""래리 윌리엄스 변동성 돌파 백테스터 - Streamlit 웹앱.

실행: streamlit run app.py
"""
from __future__ import annotations

import os
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import backtester
import data_fetcher
import metrics


# --------------------------------------------------------------------------
# 기본 설정
# --------------------------------------------------------------------------
def setup_korean_font() -> None:
    """한글 폰트 등록 (Streamlit Cloud: packages.txt 의 fonts-nanum)."""
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            plt.rcParams["font.family"] = fm.FontProperties(fname=path).get_name()
            break
    else:
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [
            "NanumGothic", "Noto Sans CJK KR", "Malgun Gothic", "AppleGothic", "DejaVu Sans",
        ]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.25
    plt.rcParams["axes.edgecolor"] = "#cccccc"


setup_korean_font()

st.set_page_config(
    page_title="변동성 돌파 백테스터 | AI시대의 투자 서바이벌",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRESETS = {
    "069500": ("KODEX 200", "ETF"),
    "122630": ("KODEX 레버리지", "ETF"),
    "005930": ("삼성전자", "개별주식"),
    "000660": ("SK하이닉스", "개별주식"),
}
EXTRA_NAMES = {
    "005380": "현대차", "035420": "NAVER", "035720": "카카오", "051910": "LG화학",
    "006400": "삼성SDI", "005490": "POSCO홀딩스", "068270": "셀트리온",
    "105560": "KB금융", "055550": "신한지주", "012330": "현대모비스",
    "207940": "삼성바이오로직스", "373220": "LG에너지솔루션",
    "229200": "KODEX 코스닥150", "102110": "TIGER 200", "360750": "TIGER 미국S&P500",
    "133690": "TIGER 미국나스닥100", "305720": "KODEX 2차전지산업",
}
ETF_HINTS = {"069500", "122630", "229200", "102110", "360750", "133690", "305720"}


@st.cache_data(ttl=3600, show_spinner=False)
def load_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    return data_fetcher.fetch_ohlcv(ticker, start, end, use_cache=True)


def make_axes(height: float = 4.2):
    fig, ax = plt.subplots(figsize=(12, height))
    fig.tight_layout()
    return fig, ax


# --------------------------------------------------------------------------
# 사이드바: 종목 및 파라미터
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 백테스트 설정")

    st.subheader("1. 종목 선택")
    mode = st.radio("선택 방식", ["대표 프리셋", "직접 입력"], horizontal=True)
    if mode == "대표 프리셋":
        code = st.selectbox(
            "종목",
            list(PRESETS.keys()),
            format_func=lambda c: f"{c} · {PRESETS[c][0]}",
        )
    else:
        code = st.text_input("종목코드 6자리", value="005380",
                             max_chars=6, help="예: 005380 현대차").strip()
        if not (code.isdigit() and len(code) == 6):
            st.error("6자리 숫자 종목코드를 입력해 주세요.")
            st.stop()

    ticker_name = PRESETS.get(code, (EXTRA_NAMES.get(code), None))[0] or f"종목 {code}"

    # 종목별로 자산 구분 기본값을 잡는다 (사용자가 바꾼 값은 그 종목에 한해 유지)
    default_class = "ETF" if code in ETF_HINTS else PRESETS.get(code, ("", "개별주식"))[1]
    asset_class = st.radio(
        "자산 구분", ["ETF", "개별주식"],
        index=0 if default_class == "ETF" else 1,
        horizontal=True, key=f"asset_class_{code}",
        help="개별주식은 매도 시 증권거래세 0.18%를 비용에 반영합니다. ETF는 0%.",
    )
    tax = 0.0 if asset_class == "ETF" else 0.0018

    st.subheader("2. 전략 파라미터")
    k = st.slider("K값 (전일 레인지 × K)", 0.10, 1.00, 0.50, 0.05,
                  help="목표가 = 당일 시가 + 전일 (고가-저가) × K")
    exit_label = st.radio(
        "청산 방식",
        [backtester.EXIT_LABEL["next_open"] + " (기본형)",
         backtester.EXIT_LABEL["same_close"] + " (데이트레이딩)"],
        help="기본형은 진입일 다음 거래일 시가에, 데이트레이딩은 진입일 종가에 청산합니다.",
    )
    exit_mode = "next_open" if exit_label.startswith("익일") else "same_close"

    st.subheader("3. 자본 및 비용")
    capital = st.number_input("초기 자본금 (원)", min_value=1_000_000,
                              max_value=10_000_000_000, value=100_000_000,
                              step=10_000_000, format="%d")
    col1, col2 = st.columns(2)
    with col1:
        slip_pct = st.number_input("슬리피지 (%)", min_value=0.0, max_value=1.0,
                                   value=0.05, step=0.01, format="%.3f")
    with col2:
        fee_pct = st.number_input("수수료 (%)", min_value=0.0, max_value=1.0,
                                  value=0.015, step=0.005, format="%.3f")
    start_date = st.date_input("백테스트 시작일", value=date(2010, 1, 1),
                               min_value=date(2005, 1, 1), max_value=date.today())

    st.divider()
    st.caption(
        "**전략 규칙**\n\n"
        "전일 레인지 = 전일 고가 − 전일 저가\n\n"
        "목표가 = 당일 시가 + 전일 레인지 × K\n\n"
        "당일 고가가 목표가를 터치하면 목표가(갭상승 시 시가)에 매수 → 익일 시가 또는 당일 종가에 청산"
    )


# --------------------------------------------------------------------------
# 헤더
# --------------------------------------------------------------------------
st.title("🚀 래리 윌리엄스 변동성 돌파 백테스터")
st.caption(
    "**AI시대의 투자 서바이벌** · 지수 ETF·개별주식 일봉 백테스트  |  "
    "데이터: 네이버 금융 일봉 (KRX 휴장일·0원 오류 자동 정제)"
)

start_str = start_date.strftime("%Y%m%d")
end_str = data_fetcher.today_kst()

try:
    with st.spinner(f"{ticker_name} ({code}) 일봉 데이터를 불러오는 중..."):
        prices = load_prices(code, start_str, end_str)
except Exception as exc:  # noqa: BLE001
    st.error(f"데이터 조회에 실패했습니다: {exc}")
    st.info("종목코드를 확인하거나 잠시 후 다시 시도해 주세요. "
            "상장 전 기간은 자동으로 상장일부터 계산합니다.")
    st.stop()

if len(prices) < 40:
    st.warning(f"사용 가능한 일봉이 {len(prices)}개뿐입니다. 기간을 늘리거나 다른 종목을 선택해 주세요.")

try:
    result = backtester.run_backtest(
        prices,
        k=float(k),
        exit_mode=exit_mode,
        initial_capital=float(capital),
        slippage=slip_pct / 100.0,
        commission=fee_pct / 100.0,
        tax=tax,
        ticker=code,
    )
    s = metrics.summarize(result)
except Exception as exc:  # noqa: BLE001
    st.error(f"백테스트 계산 중 오류가 발생했습니다: {exc}")
    st.stop()

t = s["trades"]
bm = s["benchmark"]
period = (f"{s['start'].strftime('%Y-%m-%d')} ~ {s['end'].strftime('%Y-%m-%d')}"
          f" ({s['years']:.1f}년)")

st.markdown(
    f"#### {ticker_name} `{code}` · K={k:.2f} · "
    f"{backtester.EXIT_LABEL[exit_mode]} · {asset_class}"
)
st.caption(f"기간 {period} · 초기 자본 {s['initial']:,.0f}원 · "
           f"비용 슬리피지 {slip_pct:.3f}% / 수수료 {fee_pct:.3f}%"
           + (f" / 거래세 {tax*100:.2f}%" if tax else " / 거래세 0% (ETF)"))
if data_fetcher.is_partial_last_bar(prices):
    st.info(f"마지막 봉 {prices.index[-1].date()}은 장중 스냅샷입니다. 종가 확정 후 새로고침하면 정확해집니다.")
for note in s["notes"]:
    st.caption(f"· {note}")

# --------------------------------------------------------------------------
# 핵심 지표
# --------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("최종 자산", f"{s['final']:,.0f}원",
          f"초기 대비 {s['final'] - s['initial']:+,.0f}원")
c2.metric("누적 수익률", f"{s['total_return']*100:+.2f}%",
          f"B&H {bm['total_return']*100:+.2f}%")
c3.metric("CAGR (연평균)", f"{s['cagr']*100:+.2f}%",
          f"B&H {bm['cagr']*100:+.2f}%")
c4.metric("MDD (최대 낙폭)", f"{s['mdd']*100:.2f}%",
          f"B&H {bm['mdd']*100:.2f}%")

c5, c6, c7, c8 = st.columns(4)
c5.metric("승률", f"{t['win_rate']*100:.1f}%", f"{t['wins']}승 / {t['losses']}패")
c6.metric("총 거래 횟수", f"{t['trades']}회", f"시장 노출 {s['exposure']*100:.1f}%")
c7.metric("건당 평균수익률 (엣지)", f"{t['avg_return']*100:+.3f}%",
          f"손익비 {t['payoff']:.2f}")
c8.metric("샤프 지수", f"{s['sharpe']:.2f}", f"B&H {bm['sharpe']:.2f}")

# --------------------------------------------------------------------------
# 차트 1: 누적 자산 vs 단순보유 (로그)
# --------------------------------------------------------------------------
st.subheader("📈 전략 누적 자산 vs 단순보유 (B&H)")
fig, ax = make_axes(4.6)
ax.plot(s["equity"].index, s["equity"].values, color="#1f6feb", lw=1.6,
        label=f"변동성 돌파 (K={k:.2f})")
ax.plot(bm["underwater"].index, result.benchmark.values, color="#9aa0a6", lw=1.1,
        label=f"{ticker_name} 단순보유")
ax.set_yscale("log")
ax.set_ylabel("평가 자산 (원, 로그 스케일)")
ax.xaxis.set_major_locator(mdates.YearLocator(2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.legend(loc="upper left")
ax.set_title(f"{ticker_name} 누적 자산 비교 ({period})", fontsize=12)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

# --------------------------------------------------------------------------
# 차트 2: 언더워터 (MDD)
# --------------------------------------------------------------------------
st.subheader("📉 낙폭(Underwater) 비교")
fig, ax = make_axes(3.2)
ax.fill_between(s["underwater"].index, s["underwater"].values * 100, 0,
                color="#1f6feb", alpha=0.35, label="변동성 돌파")
ax.plot(s["underwater"].index, s["underwater"].values * 100, color="#1f6feb", lw=1.0)
ax.plot(bm["underwater"].index, bm["underwater"].values * 100, color="#e8710a",
        lw=1.0, label="단순보유")
ax.set_ylabel("고점 대비 낙폭 (%)")
ax.xaxis.set_major_locator(mdates.YearLocator(2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.legend(loc="lower left")
ax.set_title(f"최대 낙폭: 전략 {s['mdd']*100:.2f}% vs 단순보유 {bm['mdd']*100:.2f}%", fontsize=12)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

# --------------------------------------------------------------------------
# 차트 3: 연도별 수익률
# --------------------------------------------------------------------------
st.subheader("📅 연도별 수익률 비교")
yearly = s["yearly"]
bm_yearly = bm["yearly"]
years = sorted(set(yearly.index) | set(bm_yearly.index))
if years:
    import numpy as np

    ys = [float(yearly.get(y, np.nan)) * 100 for y in years]
    bs = [float(bm_yearly.get(y, np.nan)) * 100 for y in years]
    fig, ax = make_axes(3.6)
    x = np.arange(len(years))
    width = 0.4
    ax.bar(x - width / 2, ys, width, color="#1f6feb", label="변동성 돌파")
    ax.bar(x + width / 2, bs, width, color="#c4c7c5", label="단순보유")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], rotation=45, ha="right")
    ax.set_ylabel("연간 수익률 (%)")
    ax.axhline(0, color="#888888", lw=0.8)
    ax.legend(loc="upper left")
    ax.set_title("연도별 수익률 (전략 vs 단순보유)", fontsize=12)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    yearly_table = pd.DataFrame({
        "연도": years,
        "전략 (%)": [round(v, 2) if v == v else None for v in ys],
        "단순보유 (%)": [round(v, 2) if v == v else None for v in bs],
        "차이 (%p)": [round(a - b, 2) if (a == a and b == b) else None for a, b in zip(ys, bs)],
    })
    st.dataframe(
        yearly_table.style.format({"전략 (%)": "{:+.2f}", "단순보유 (%)": "{:+.2f}",
                                   "차이 (%p)": "{:+.2f}"}, na_rep="-"),
        use_container_width=True, hide_index=True,
    )

# --------------------------------------------------------------------------
# 매매일지
# --------------------------------------------------------------------------
st.subheader("📋 전체 매매일지")
trades = s["trades_df"]
if trades is None or trades.empty:
    st.warning("이 조건에서는 체결된 거래가 없습니다. K값을 낮추거나 기간을 늘려 보세요.")
else:
    st.caption(f"총 {len(trades)}건 · 수익 거래 {t['wins']}건 / 손실 거래 {t['losses']}건 · "
               f"최대 연속 손실 {t['max_consec_losses']}회 · 갭상승 시가 체결 {t['gap_entries']}건")
    show = trades.style.format({
        "전일레인지": "{:,.2f}", "목표가": "{:,.2f}", "진입가": "{:,.2f}",
        "청산가": "{:,.2f}", "수익률(%)": "{:+.2f}", "실현손익(원)": "{:+,.0f}",
        "누적자산": "{:,.0f}",
    })
    st.dataframe(show, use_container_width=True, height=420, hide_index=True)

    csv_bytes = trades.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ 매매일지 CSV 다운로드",
        data=csv_bytes,
        file_name=f"volatility_breakout_{code}_K{k:.2f}_{exit_mode}_trades.csv",
        mime="text/csv",
    )

with st.expander("🔍 상세 성과 지표 및 전략 설명"):
    detail = pd.DataFrame([
        ("소르티노 지수", f"{s['sortino']:.2f}", f"{bm['sortino']:.2f}"),
        ("연변동성", f"{s['vol']*100:.2f}%", f"{bm['vol']*100:.2f}%"),
        ("칼마 지수", f"{s['calmar']:.2f}", "-"),
        ("손익비 (Profit Factor)", "inf" if t["profit_factor"] == float("inf") else f"{t['profit_factor']:.2f}", "-"),
        ("평균 수익 / 평균 손실", f"{t['avg_win']*100:+.2f}% / {t['avg_loss']*100:+.2f}%", "-"),
        ("평균 손익금액", f"{t['avg_win_amt']:+,.0f}원 / {t['avg_loss_amt']:+,.0f}원", "-"),
        ("최고 / 최저 거래", f"{t['best_trade']*100:+.2f}% / {t['worst_trade']*100:+.2f}%", "-"),
        ("MDD 저점 / 회복", s["mdd_trough"].strftime("%Y-%m-%d") + " / "
         + (s["mdd_recovery"].strftime("%Y-%m-%d") if s["mdd_recovery"] is not None else "미회복"), "-"),
    ], columns=["지표", "전략", "단순보유"])
    st.dataframe(detail, use_container_width=True, hide_index=True)

    st.markdown(
        """
**전략 계산 방식**
- 목표가 = 당일 시가 + (전일 고가 − 전일 저가) × K
- 당일 고가가 목표가 이상이면 목표가에 매수 (시가가 이미 목표가를 넘긴 갭상승은 시가 체결)
- 청산: 다음 거래일 시가(기본형) 또는 당일 종가(데이트레이딩)
- 매수 시점 가용 현금 100% 투입, 정수 주 단위
- 비용: 매수·매도 각각 슬리피지 + 수수료, 개별주식은 매도 시 증권거래세 0.18%

**데이터**: 네이버 금융 일봉. 거래정지·휴장일의 0원 행, 고가<저가 등 비정상 봉은 자동 제외합니다.

**주의**: 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다. 투자 판단의 책임은 투자자 본인에게 있습니다.
        """
    )

st.caption("AI시대의 투자 서바이벌 · finsnap.tistory.com")
