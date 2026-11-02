import os
import time
import warnings
import platform
import requests

import yfinance as yf
import pandas as pd

warnings.filterwarnings("ignore")

# =========================================================
# CONFIGURAÇÕES DO TELEGRAM (Opcional)
# =========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TICKER_INDICE = "^BVSP" 

# Parâmetros da Estratégia
WAVE_LENGTH = 34
EMA_FAST_LEN = 13
EMA_SLOW_LEN = 26
EMA_80_LEN = 80
EMA_200_LEN = 200

RSI_LEN = 14
ADX_LEN = 14
ADX_MIN = 15.0
MAX_DIST_EMA80 = 350.0

# Parâmetro de Antecipação de Sinais (Proximidade em pontos para o gráfico de 5m)
DISTANCIA_ANTECIPACAO_PTS = 100.0  # Ajustável para a volatilidade do 5m

INTERVALO_VARREDURA = 60  # Verifica a cada 1 minuto (ideal para gráficos de 5m)

estado_alerta = {}
cache_dados = {}


# =========================================================
# SISTEMA DE ALERTAS (WINDOWS + TELEGRAM)
# =========================================================

try:
    import winsound
    TEM_WINSOUND = platform.system() == "Windows"
except ImportError:
    winsound = None
    TEM_WINSOUND = False

try:
    from winotify import Notification
    TEM_WINOTIFY = True
except ImportError:
    Notification = None
    TEM_WINOTIFY = False


def enviar_telegram(mensagem_texto):
    if not TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": mensagem_texto}, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")


def disparar_alerta_windows(titulo, mensagem, beep_freq=1000):
    if TEM_WINSOUND:
        try:
            winsound.Beep(beep_freq, 800)
            winsound.Beep(beep_freq + 200, 800)
        except Exception:
            pass

    if TEM_WINOTIFY:
        try:
            Notification(
                app_id="Mini Índice Pro V4 (5m)",
                title=titulo,
                msg=mensagem,
                duration="long"
            ).show()
        except Exception as e:
            print(f"Erro na notificação Windows: {e}")

    texto_formatado = f"🚨 *{titulo}* 🚨\n{mensagem}"
    enviar_telegram(texto_formatado)
    print(f"\n[ALERTA 5m] {titulo} -> {mensagem}\n")


# =========================================================
# CÁLCULOS TÉCNICOS (5 MINUTOS)
# =========================================================

def baixar_dados_indice():
    try:
        # Recolhe dados de 5 minutos (o yfinance permite até 60 dias para o intraday de 5m)
        df = yf.download(TICKER_INDICE, period="5d", interval="5m", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return pd.DataFrame()
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
            
        df = df.dropna(subset=["Close", "High", "Low", "Open"])
        return df
    except Exception as e:
        print(f"Erro ao descarregar dados: {e}")
        return pd.DataFrame()


def calcular_indicadores(df):
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    df["emaWaveHigh"] = high.ewm(span=WAVE_LENGTH, adjust=False).mean()
    df["emaWaveClose"] = close.ewm(span=WAVE_LENGTH, adjust=False).mean()
    df["emaWaveLow"] = low.ewm(span=WAVE_LENGTH, adjust=False).mean()

    df["emaFast"] = close.ewm(span=EMA_FAST_LEN, adjust=False).mean()
    df["emaSlow"] = close.ewm(span=EMA_SLOW_LEN, adjust=False).mean()
    df["ema80"] = close.ewm(span=EMA_80_LEN, adjust=False).mean()
    df["ema200"] = close.ewm(span=EMA_200_LEN, adjust=False).mean()

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    df["macdLine"] = exp1 - exp2
    df["signalLine"] = df["macdLine"].ewm(span=9, adjust=False).mean()
    df["histLine"] = df["macdLine"] - df["signalLine"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/ADX_LEN, adjust=False).mean()
    df["atr"] = atr

    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up > down) & (up > 0)] = up
    minus_dm[(down > up) & (down > 0)] = down

    plus_di = 100 * plus_dm.ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adxValue"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()
    df["plusDI"] = plus_di
    df["minusDI"] = minus_di

    return df


def verificar_sinais():
    df = baixar_dados_indice()
    if df.empty or len(df) < 200:
        print("Dados insuficientes para análise no gráfico de 5m.")
        return

    df = calcular_indicadores(df)
    
    atual = df.iloc[-2]
    anterior = df.iloc[-3]

    close = atual["Close"]
    ema80 = atual["ema80"]
    ema_wave_close = atual["emaWaveClose"]
    ant_ema_wave_close = anterior["emaWaveClose"]

    # Diferença absoluta em pontos entre a Wave e a EMA 80 no gráfico de 5m
    diff_pontos = abs(ema_wave_close - ema80)

    # Condição de Proximidade (Antecipação no 5m)
    proximo_alta = (ema_wave_close < ema80) and (diff_pontos <= DISTANCIA_ANTECIPACAO_PTS)
    proximo_baixa = (ema_wave_close > ema80) and (diff_pontos <= DISTANCIA_ANTECIPACAO_PTS)

    timestamp_vela = str(df.index[-2])

    # 1. ALERTA ANTECIPADO (QUASE A CRUZAR NO 5M)
    if proximo_alta:
        chave_perto = f"PERTO_BUY_5M_{timestamp_vela}"
        if not estado_alerta.get(chave_perto, False):
            estado_alerta[chave_perto] = True
            msg = f"Ativo: {TICKER_INDICE} (5m)\nPreço: {close:.2f}\nDistância para EMA 80: {diff_pontos:.1f} pts\nA Wave está prestes a cruzar PARA CIMA da EMA 80 no gráfico de 5 minutos!"
            disparar_alerta_windows("⚠️ ATENÇÃO [5m]: WAVE PRÓXIMA DA EMA 80 (COMPRA)", msg, 700)

    elif proximo_baixa:
        chave_perto = f"PERTO_SELL_5M_{timestamp_vela}"
        if not estado_alerta.get(chave_perto, False):
            estado_alerta[chave_perto] = True
            msg = f"Ativo: {TICKER_INDICE} (5m)\nPreço: {close:.2f}\nDistância para EMA 80: {diff_pontos:.1f} pts\nA Wave está prestes a cruzar PARA BAIXO da EMA 80 no gráfico de 5 minutos!"
            disparar_alerta_windows("⚠️ ATENÇÃO [5m]: WAVE PRÓXIMA DA EMA 80 (VENDA)", msg, 700)

    # 2. GATILHOS DE CRUZAMENTO CONFIRMADO NO 5M
    cross_wave_up = (ant_ema_wave_close <= anterior["ema80"]) and (ema_wave_close > ema80)
    cross_wave_down = (ant_ema_wave_close >= anterior["ema80"]) and (ema_wave_close < ema80)

    price_above_wave = close > atual["emaWaveHigh"]
    price_below_wave = close < ema_wave_close
    inside_wave = (close >= atual["emaWaveLow"]) and (close <= atual["emaWaveHigh"])

    rsi_buy_ok = atual["rsi"] <= 65
    rsi_sell_ok = atual["rsi"] >= 35

    distance_ema80 = abs(close - ema80)
    distance_ok = distance_ema80 <= MAX_DIST_EMA80

    macd_buy_ok = atual["macdLine"] > 0
    macd_sell_ok = atual["macdLine"] < 0

    adx_buy_ok = (atual["adxValue"] >= ADX_MIN) and (atual["plusDI"] > atual["minusDI"])
    adx_sell_ok = (atual["adxValue"] >= ADX_MIN) and (atual["minusDI"] > atual["plusDI"])

    buy_trigger = (
        cross_wave_up and price_above_wave and not inside_wave and
        rsi_buy_ok and distance_ok and macd_buy_ok and adx_buy_ok
    )

    sell_trigger = (
        cross_wave_down and price_below_wave and not inside_wave and
        rsi_sell_ok and distance_ok and macd_sell_ok and adx_sell_ok
    )

    if buy_trigger:
        chave_alerta = f"BUY_5M_{timestamp_vela}"
        if not estado_alerta.get(chave_alerta, False):
            estado_alerta[chave_alerta] = True
            msg = f"Ativo: {TICKER_INDICE} (5m)\nPreço: {close:.2f}\nADX: {atual['adxValue']:.1f}\nRSI: {atual['rsi']:.1f}\nCruzamento de alta confirmado no gráfico de 5m!"
            disparar_alerta_windows("🚀 SINAL DE COMPRA [5m] CONFIRMADO", msg, 1200)

    elif sell_trigger:
        chave_alerta = f"SELL_5M_{timestamp_vela}"
        if not estado_alerta.get(chave_alerta, False):
            estado_alerta[chave_alerta] = True
            msg = f"Ativo: {TICKER_INDICE} (5m)\nPreço: {close:.2f}\nADX: {atual['adxValue']:.1f}\nRSI: {atual['rsi']:.1f}\nCruzamento de baixa confirmado no gráfico de 5m!"
            disparar_alerta_windows("🚀 SINAL DE VENDA [5m] CONFIRMADO", msg, 600)
    else:
        print(f"[{time.strftime('%H:%M:%S')}] [5m] Varredura OK. Distância Wave/EMA80: {diff_pontos:.1f} pts. Preço: {close:.2f}")


# =========================================================
# LOOP PRINCIPAL
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 BOT PYTHON - MINI ÍNDICE (GRÁFICO DE 5 MINUTOS)")
    print("=" * 60)
    print(f"Timeframe: 5m | Antecipação configurada para <= {DISTANCIA_ANTECIPACAO_PTS} pontos.")
    
    disparar_alerta_windows("Bot 5m Ativo", "O scanner de 5 minutos com antecipação foi iniciado.", 900)

    while True:
        try:
            verificar_sinais()
        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as erro:
            print(f"\n[ERRO] {erro}\n")

        time.sleep(INTERVALO_VARREDURA)
