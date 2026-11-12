"""일봉(OHLCV) 데이터 수집 및 캐싱 모듈 (웹앱용).

1차 소스: 네이버 금융 일봉 API (별도 인증 없이 동작, Streamlit Cloud 에서도 안정적)
2차 소스: pykrx (설치되어 있고 KRX 접속이 가능한 환경에서만 사용)

전처리: 중복/결측 제거, 0원(거래정지·휴장 오류) 행 제거, 가격 논리 검사.
"""
from __future__ import annotations

import os
import re
import time
import urllib.request
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
KST = ZoneInfo("Asia/Seoul")


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


# --------------------------------------------------------------------------
# 소스별 수집기
# --------------------------------------------------------------------------
def _fetch_naver(ticker: str, start: str, end: str, retries: int = 3) -> pd.DataFrame:
    """네이버 금융 siseJson API 로 일봉 수집."""
    url = (
        "https://api.finance.naver.com/siseJson.naver"
        f"?symbol={ticker}&requestType=1&startTime={start}&endTime={end}&timeframe=day"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    body = None
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("euc-kr", errors="replace")
            if body and re.search(r'\["\d{8}"', body):
                break
            body = None
            last_err = ValueError("네이버 응답에 데이터 행이 없습니다")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            body = None
        time.sleep(1.0 * (attempt + 1))
    if not body:
        raise RuntimeError(f"네이버 수집 실패: {last_err}")

    # 응답 예: [["20100104", 16864, 16992, 16864, 16966, 1047416, 0.0], ...]
    rows = re.findall(
        r'\["(\d{8})"\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*'
        r'([-\d.]+)\s*,\s*([-\d.]+)', body)
    if not rows:
        raise ValueError("네이버 응답에 데이터 행이 없습니다")

    df = pd.DataFrame(
        [
            {
                "Date": pd.to_datetime(r[0], format="%Y%m%d"),
                "Open": float(r[1]),
                "High": float(r[2]),
                "Low": float(r[3]),
                "Close": float(r[4]),
                "Volume": float(r[5]),
            }
            for r in rows
        ]
    )
    df = df.set_index("Date").sort_index()
    df.index.name = "Date"
    return df


def _fetch_pykrx(ticker: str, start: str, end: str) -> pd.DataFrame:
    """pykrx 로 일봉 수집 (선택적 2차 경로)."""
    from pykrx import stock  # 지연 임포트

    raw = stock.get_market_ohlcv_by_date(start, end, ticker)
    if raw is None or raw.empty:
        raise ValueError("pykrx 응답이 비어 있습니다")
    rename = {"시가": "Open", "고가": "High", "저가": "Low",
              "종가": "Close", "거래량": "Volume"}
    df = raw.rename(columns=rename)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"pykrx 컬럼 누락: {missing}")
    df = df[COLUMNS].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "Date"
    return df


# --------------------------------------------------------------------------
# 검증 / 캐시
# --------------------------------------------------------------------------
def validate(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """필수 컬럼, 중복/결측, 가격 논리, 0원 결측치 제거."""
    if df is None or df.empty:
        raise ValueError(f"[{ticker}] 수집된 데이터가 없습니다.")
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"[{ticker}] 누락 컬럼: {missing}")

    out = df[COLUMNS].copy()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out.dropna(subset=["Open", "High", "Low", "Close"])

    # 거래정지 / 액면분할 오류 / 휴장일 잔여 행: 0원, 고가<저가, 종가·시가가 고저 범위 밖
    bad = (
        (out[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
        | (out["High"] < out["Low"])
        | (out["Close"] > out["High"] * 1.001)
        | (out["Close"] < out["Low"] * 0.999)
        | (out["Open"] > out["High"] * 1.001)
        | (out["Open"] < out["Low"] * 0.999)
    )
    out = out[~bad]

    out["Volume"] = out["Volume"].fillna(0.0)
    out = out.astype(float)
    if out.empty:
        raise ValueError(f"[{ticker}] 검증 후 남은 데이터가 없습니다.")
    return out


def cache_path(ticker: str, start: str, end: str) -> str:
    return os.path.join(DATA_DIR, f"{ticker}_{start}_{end}.csv")


def _cached_is_fresh(path: str, end: str) -> bool:
    try:
        head = pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception:  # noqa: BLE001
        return False
    if head.empty:
        return False
    last = pd.Timestamp(head.index[-1]).date()
    want = pd.to_datetime(end).date()
    today = datetime.now(KST).date()
    target = min(want, today)
    while target.weekday() >= 5:  # 주말이면 금요일까지면 충분
        target = (pd.Timestamp(target) - pd.Timedelta(days=1)).date()
    return last >= target


def fetch_ohlcv(ticker: str = "069500", start: str = "20100101",
                end: str | None = None, use_cache: bool = True,
                force_refresh: bool = False) -> pd.DataFrame:
    """일봉 OHLCV 반환 (Date 인덱스, Open/High/Low/Close/Volume)."""
    end = end or today_kst()
    os.makedirs(DATA_DIR, exist_ok=True)
    path = cache_path(ticker, start, end)

    if use_cache and not force_refresh and os.path.exists(path) and _cached_is_fresh(path, end):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index.name = "Date"
        df.index = df.index.tz_localize(None)
        df.attrs["source"] = "캐시"
        return validate(df, ticker)

    errors = []
    for name, fn in (("네이버 금융", _fetch_naver), ("pykrx", _fetch_pykrx)):
        try:
            df = validate(fn(ticker, start, end), ticker)
            try:
                df.to_csv(path, encoding="utf-8-sig", float_format="%.4f")
            except Exception:  # noqa: BLE001
                pass  # 읽기 전용 환경이면 캐시 생략
            df.attrs["source"] = name
            return df
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    raise RuntimeError("일봉 데이터를 가져오지 못했습니다 -> " + " | ".join(errors))


def is_partial_last_bar(df: pd.DataFrame) -> bool:
    """마지막 봉이 오늘자 장중 봉(종가 미확정)인지."""
    if df.empty:
        return False
    now = datetime.now(KST)
    last = df.index[-1].date()
    return last == now.date() and now.time() < dtime(15, 30)
