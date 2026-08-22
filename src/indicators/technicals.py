import pandas as pd
import numpy as np


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Relative Strength Index, Wilder's Smoothing) 계산"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3, sd_period: int = 3):
    """Slow Stochastic (%K, %D) 계산"""
    low_min = df["low"].rolling(window=k_period).min()
    high_max = df["high"].rolling(window=k_period).max()

    fast_k = 100 * ((df["close"] - low_min) / ((high_max - low_min) + 1e-9))
    slow_k = fast_k.rolling(window=d_period).mean()
    slow_d = slow_k.rolling(window=sd_period).mean()

    return slow_k, slow_d


def calc_williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R (-100 ~ 0) 계산"""
    high_max = df["high"].rolling(window=period).max()
    low_min = df["low"].rolling(window=period).min()

    w_r = -100 * ((high_max - df["close"]) / ((high_max - low_min) + 1e-9))
    return w_r


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD, Signal, Histogram 계산"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """모든 주요 기술 지표 및 이동평균(5, 10, 20, 30, 50, 150, 200)을 일괄 산출"""
    if df.empty or len(df) < 5:
        return df

    res = df.copy()
    res = res.sort_values("date").reset_index(drop=True)

    # 1. 이동평균선
    res["ema_5"] = res["close"].ewm(span=5, adjust=False).mean()
    res["sma_10"] = res["close"].rolling(window=10).mean()
    res["sma_20"] = res["close"].rolling(window=20).mean()
    res["sma_30"] = res["close"].rolling(window=30).mean()
    res["sma_50"] = res["close"].rolling(window=50).mean()
    res["sma_150"] = res["close"].rolling(window=150, min_periods=10).mean()
    res["sma_200"] = res["close"].rolling(window=200, min_periods=20).mean()

    # 2. 거래량 & RVOL (20기간 평균 거래량 대비 비율)
    res["vol_ma20"] = res["volume"].rolling(window=20, min_periods=5).mean()
    res["rvol"] = res["volume"] / (res["vol_ma20"] + 1e-9)

    # 3. 오실레이터 (RSI, Stochastic, Williams %R, MACD)
    res["rsi_14"] = calc_rsi(res["close"], 14)
    stoch_k, stoch_d = calc_stochastic(res, 14, 3, 3)
    res["stoch_k"] = stoch_k
    res["stoch_d"] = stoch_d
    res["williams_r"] = calc_williams_r(res, 14)

    macd_line, sig_line, hist = calc_macd(res["close"])
    res["macd_line"] = macd_line
    res["macd_signal"] = sig_line
    res["macd_hist"] = hist

    # 4. 52주(최고가) 및 이격도
    res["high_52w"] = res["high"].rolling(window=min(250, len(res)), min_periods=10).max()
    res["dist_52w_high"] = ((res["close"] - res["high_52w"]) / res["high_52w"]) * 100

    # 5. 기간별 수익률 (%)
    res["pct_change_1d"] = res["close"].pct_change(1) * 100
    res["pct_change_1w"] = res["close"].pct_change(5) * 100 if len(res) >= 5 else 0
    res["pct_change_1m"] = res["close"].pct_change(20) * 100 if len(res) >= 20 else 0

    return res


def resample_ohlcv(df: pd.DataFrame, timeframe: str = "일봉") -> pd.DataFrame:
    """
    일봉 OHLCV 데이터를 주봉(Weekly) 또는 월봉(Monthly)으로 완벽 리샘플링
    - timeframe: '일봉' | '주봉' | '월봉'
    """
    if df.empty or timeframe == "일봉":
        return calc_indicators(df)

    df_work = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_work["date"]):
        df_work["date"] = pd.to_datetime(df_work["date"])

    df_work = df_work.set_index("date").sort_index()

    # 리샘플 규칙: 주봉(W-FRI), 월봉(ME)
    rule = "W-FRI" if timeframe == "주봉" else "ME"

    resampled = df_work.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()

    # 리샘플링된 캔들에 대해 기술 지표 다시 계산
    return calc_indicators(resampled)
