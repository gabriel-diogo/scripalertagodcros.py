import os
import time
import warnings
import platform
import requests
import yfinance as yf
import pandas as pd

warnings.filterwarnings("ignore")

# =========================================================
# CONFIG - TESTE
# =========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TICKER_INDICE = "^BVSP"
WAVE_LENGTH = 34
EMA_FAST_LEN = 13
EMA_SLOW_LEN = 26
EMA_80_LEN = 80
EMA_200_LEN = 200
RSI_LEN = 14
ADX_LEN = 14
ADX_MIN = 15.0
DISTANCIA_ANTECIPACAO_PTS = 250.0  # aumentei de 100 pra 150
INTERVALO_VARREDURA = 600

estado_alerta = {}

# =========================================================
# ALERTAS
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
    if not TOKEN or not CHAT_ID: return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": mensagem_texto}, timeout=10)
    except Exception as e: print(f"Erro Telegram: {e}")

def disparar_alerta_windows(titulo, mensagem, beep_freq=1000):
    if TEM_WINSOUND:
        try:
            winsound.Beep(beep_freq, 800)
            winsound.Beep(beep_freq + 200, 800)
        except: pass
    if TEM_WINOTIFY:
        try: Notification(app_id="Mini Índice Pro V4 (5m)", title=titulo, msg=mensagem, duration="long").show()
        except Exception as e: print(f"Erro notificação: {e}")
    enviar_telegram(f"🚨 *{titulo}* 🚨\n{mensagem}")
    print(f"\n[ALERTA 5m] {titulo} -> {mensagem}\n")

# =========================================================
# DADOS
# =========================================================
def baixar_dados_indice():
    try:
        df = yf.download(TICKER_INDICE, period="5d", interval="5m", progress=False, auto_adjust=False)
        if df is None or df.empty: return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]
        return df.dropna(subset=["Close", "High", "Low", "Open"])
    except Exception as e:
        print(f"Erro dados: {e}")
        return pd.DataFrame()

def calcular_indicadores(df):
    close = df["Close"].astype(float); high = df["High"].astype(float); low = df["Low"].astype(float)
    df["emaWaveHigh"] = high.ewm(span=WAVE_LENGTH, adjust=False).mean()
    df["emaWaveClose"] = close.ewm(span=WAVE_LENGTH, adjust=False).mean()
    df["emaWaveLow"] = low.ewm(span=WAVE_LENGTH, adjust=False).mean()
    df["ema80"] = close.ewm(span=EMA_80_LEN, adjust=False).mean()
    delta = close.diff(); gain = (delta.where(delta > 0, 0)).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss))
    exp1 = close.ewm(span=12, adjust=False).mean(); exp2 = close.ewm(span=26, adjust=False).mean()
    df["macdLine"] = exp1 - exp2; df["signalLine"] = df["macdLine"].ewm(span=9, adjust=False).mean()
    df["histLine"] = df["macdLine"] - df["signalLine"]
    tr1 = high - low; tr2 = (high - close.shift(1)).abs(); tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1); atr = tr.ewm(alpha=1/ADX_LEN, adjust=False).mean()
    up = high.diff(); down = -low.diff()
    plus_dm = pd.Series(0.0, index=df.index); minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up > down) & (up > 0)] = up; minus_dm[(down > up) & (down > 0)] = down
    plus_di = 100 * plus_dm.ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adxValue"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean(); df["plusDI"] = plus_di; df["minusDI"] = minus_di
    return df

# =========================================================
# SINAIS - SEM LIMITE DE MÉDIA + ANTECIPAÇÃO
# =========================================================
def verificar_sinais():
    df = baixar_dados_indice()
    if df.empty or len(df) < 200: return
    df = calcular_indicadores(df)
    atual = df.iloc[-2]; anterior = df.iloc[-3]
    close = atual["Close"]; ema80 = atual["ema80"]; ema_wave_close = atual["emaWaveClose"]
    diff_pontos = abs(ema_wave_close - ema80); dist_anterior = abs(anterior["emaWaveClose"] - anterior["ema80"])
    timestamp_vela = str(df.index[-2])
    rsi = atual["rsi"]; macd = atual["macdLine"]; signal = atual["signalLine"]; hist = atual["histLine"]
    adx = atual["adxValue"]; plus = atual["plusDI"]; minus = atual["minusDI"]
    inclinacao_wave = ema_wave_close - anterior["emaWaveClose"]
    se_aproximando = diff_pontos < dist_anterior

    print(f"[{time.strftime('%H:%M:%S')}] [5m] Preço: {close:.2f} | Dist: {diff_pontos:.1f} pts (ant {dist_anterior:.1f}) | "
          f"RSI: {rsi:.1f} | MACD: {macd:.2f} (Sig {signal:.2f} Hist {hist:.2f}) | ADX: {adx:.1f} (+DI {plus:.1f} / -DI {minus:.1f}) | Wave: {inclinacao_wave:+.1f}")

    # 1. ANTECIPAÇÃO INTELIGENTE - AVISA ANTES
    if ema_wave_close < ema80 and se_aproximando and inclinacao_wave > 0 and diff_pontos <= DISTANCIA_ANTECIPACAO_PTS:
        chave = f"ANTECIPA_BUY_5M_{timestamp_vela}"
        if not estado_alerta.get(chave):
            estado_alerta[chave] = True
            disparar_alerta_windows("👀 ANTECIPAÇÃO COMPRA [5m]", 
                f"{TICKER_INDICE} 5m\nPreço: {close:.2f}\nDist: {diff_pontos:.1f} pts (era {dist_anterior:.1f})\nWave subindo {inclinacao_wave:.1f} pts\nRSI: {rsi:.1f} | ADX: {adx:.1f}\nCruzamento chegando!", 800)
    elif ema_wave_close > ema80 and se_aproximando and inclinacao_wave < 0 and diff_pontos <= DISTANCIA_ANTECIPACAO_PTS:
        chave = f"ANTECIPA_SELL_5M_{timestamp_vela}"
        if not estado_alerta.get(chave):
            estado_alerta[chave] = True
            disparar_alerta_windows("👀 ANTECIPAÇÃO VENDA [5m]", 
                f"{TICKER_INDICE} 5m\nPreço: {close:.2f}\nDist: {diff_pontos:.1f} pts (era {dist_anterior:.1f})\nWave descendo {inclinacao_wave:.1f} pts\nRSI: {rsi:.1f} | ADX: {adx:.1f}\nCruzamento chegando!", 800)

    # 2. CRUZAMENTO CONFIRMADO - SEM LIMITE DE DISTÂNCIA
    cross_up = (anterior["emaWaveClose"] <= anterior["ema80"]) and (ema_wave_close > ema80)
    cross_down = (anterior["emaWaveClose"] >= anterior["ema80"]) and (ema_wave_close < ema80)
    price_above_wave = close > atual["emaWaveHigh"]; price_below_wave = close < ema_wave_close
    inside_wave = (close >= atual["emaWaveLow"]) and (close <= atual["emaWaveHigh"])

    buy_trigger = cross_up and price_above_wave and not inside_wave and rsi <= 65 and macd > 0 and adx >= ADX_MIN and plus > minus
    sell_trigger = cross_down and price_below_wave and not inside_wave and rsi >= 35 and macd < 0 and adx >= ADX_MIN and minus > plus

    if buy_trigger:
        chave = f"BUY_5M_{timestamp_vela}"
        if not estado_alerta.get(chave):
            estado_alerta[chave] = True
            disparar_alerta_windows("🚀 COMPRA [5m] CONFIRMADO", f"{TICKER_INDICE} - Preço: {close:.2f}\nRSI: {rsi:.1f} | MACD: {macd:.2f} | ADX: {adx:.1f}", 1200)
    elif sell_trigger:
        chave = f"SELL_5M_{timestamp_vela}"
        if not estado_alerta.get(chave):
            estado_alerta[chave] = True
            disparar_alerta_windows("🔻 VENDA [5m] CONFIRMADO", f"{TICKER_INDICE} - Preço: {close:.2f}\nRSI: {rsi:.1f} | MACD: {macd:.2f} | ADX: {adx:.1f}", 600)

if __name__ == "__main__":
    print("="*70 + "\n🤖 BOT 5M - SEM LIMITE + ANTECIPAÇÃO + LOG COMPLETO\n" + "="*70)
    disparar_alerta_windows("Bot 5m Ativo", "Scanner com antecipação iniciado.", 900)
    while True:
        try: verificar_sinais()
        except KeyboardInterrupt: break
        except Exception as e: print(f"[ERRO] {e}")
        time.sleep(INTERVALO_VARREDURA)
