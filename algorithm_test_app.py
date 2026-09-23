"""Remote-safe Streamlit showcase for the Experimental v4 chart engine.

This page intentionally uses deterministic synthetic OHLCV data only.  It does
not import the KIS client, read .env/secrets, or display portfolio information.
"""

import numpy as np
import pandas as pd
import streamlit as st

from src.indicators.technicals import calc_indicators
from src.ui.charts import CHART_CONFIG, create_detail_chart
from src.ui.pattern_view import render_pattern_analysis_dashboard


st.set_page_config(page_title="Smart Chart v4 Test", page_icon="🧪", layout="wide")


def make_synthetic_ohlcv(scenario: str) -> pd.DataFrame:
    rng = np.random.default_rng(20260923)
    dates = pd.date_range("2025-10-01", periods=230, freq="B")

    if scenario == "VCP 수축 후 돌파":
        base = np.linspace(82, 126, 135) + np.sin(np.arange(135) / 6) * 2.0
        contractions = np.concatenate(
            [
                np.linspace(126, 107, 14),
                np.linspace(107, 124, 14),
                np.linspace(124, 114, 12),
                np.linspace(114, 123, 12),
                np.linspace(123, 118.5, 10),
                np.linspace(118.5, 123.5, 10),
                np.linspace(123.5, 121.5, 8),
                np.linspace(121.5, 130, 15),
            ]
        )
        close = np.concatenate([base, contractions])[:230]
        volume = np.linspace(3_000_000, 900_000, len(close))
        volume[-1] = 2_400_000
    elif scenario == "시장 국면 전환":
        flat = 100 + np.sin(np.arange(110) / 5) * 1.2
        decline = np.linspace(100, 82, 45) + np.sin(np.arange(45) / 3) * 0.7
        recovery = np.linspace(82, 128, 75) + np.sin(np.arange(75) / 4) * 1.0
        close = np.concatenate([flat, decline, recovery])
        volume = 1_100_000 + rng.normal(0, 110_000, len(close))
        volume[150:165] *= 1.5
    else:
        close_parts = [100 + np.sin(np.arange(55) / 6) * 0.35]
        volume_parts = [np.full(55, 900_000.0)]
        level = float(close_parts[0][-1])
        for _ in range(7):
            quiet = level + np.sin(np.arange(20) / 4) * 0.35
            breakout = np.linspace(float(quiet[-1]) + 4.0, float(quiet[-1]) + 8.0, 5)
            close_parts.extend([quiet, breakout])
            volume_parts.extend([np.full(20, 820_000.0), np.linspace(4_000_000, 1_200_000, 5)])
            level = float(breakout[-1])
        close = np.concatenate(close_parts)[:230]
        volume = np.concatenate(volume_parts)[:230]

    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    if len(close) < 230:
        pad = 230 - len(close)
        close = np.concatenate([close, np.linspace(close[-1], close[-1] * 1.03, pad)])
        volume = np.concatenate([volume, np.full(pad, volume[-1])])
    open_price = np.r_[close[0] * 0.998, close[:-1] * (1 + rng.normal(0, 0.002, len(close) - 1))]
    spread = np.maximum(close * 0.009, 0.55)
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": open_price,
            "high": np.maximum(open_price, close) + spread,
            "low": np.minimum(open_price, close) - spread,
            "close": close,
            "volume": np.maximum(volume, 1),
        }
    )
    return calc_indicators(frame)


st.title("🧪 Smart Chart Experimental v4")
st.warning("테스트 전용: 합성 시세만 사용하며 실계좌·API 키·포트폴리오 데이터는 이 페이지에서 읽지 않습니다.")
scenario = st.selectbox(
    "테스트 시나리오",
    ["반복 돌파 워크포워드", "VCP 수축 후 돌파", "시장 국면 전환"],
)
df = make_synthetic_ohlcv(scenario)

selected_engine = st.session_state.get("smart_analysis_engine_SYNTH", "v4")
settings = {
    "smart_analysis_engine": selected_engine,
    "smart_analysis_v2": selected_engine != "v1",
    "show_support_resistance": True,
    "show_trendlines": True,
    "show_pattern_lines": True,
    "show_ema5": True,
    "show_ma10": False,
    "show_ma20": True,
    "show_ma30": False,
    "show_ma50": True,
    "show_ma150": False,
    "show_ma200": True,
    "selected_indicators": ["RSI"],
    "timeframe": "일봉",
}

st.plotly_chart(
    create_detail_chart(df, f"SYNTH-{scenario}", settings=settings),
    use_container_width=True,
    config=CHART_CONFIG,
)
render_pattern_analysis_dashboard(df, "SYNTH")
