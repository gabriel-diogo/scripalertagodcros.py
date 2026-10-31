import time
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime

# Configurações do Telegram
TOKEN = "9070151788:AAFhgfJpi_I3-wiochhLFgoVT2k7JXQNxlY"
CHAT_ID = "9106333952"

# Ativos separados por categoria
CATEGORIAS = {
    "💱 FOREX": [
        "EURUSD=X", "GBPUSD=X", "AUDUSD=X", "USDJPY=X", 
        "USDCAD=X", "NZDUSD=X", "EURGBP=X"
    ],
    "📈 ÍNDICES": [
        "^GSPC", "^DJI", "^IXIC", "^BVSP"
    ]
}

# Limites de distância percentual
LIMITE_VERDE = 0.10  # Muito próximo ou cruzado
LIMITE_AMARELO = 0.25 # A aproximar-se

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def calcular_adx(df, window=14):
    """Calcula o indicador ADX (Average Directional Index) para medir força de tendência."""
    df = df.copy()
    df['tr0'] = abs(df['High'] - df['Low'])
    df['tr1'] = abs(df['High'] - df['Close'].shift(1))
    df['tr2'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)

    df['up_move'] = df['High'] - df['High'].shift(1)
    df['down_move'] = df['Low'].shift(1) - df['Low']

    df['plus_dm'] = 0.0
    df['minus_dm'] = 0.0

    df.loc[(df['up_move'] > df['down_move']) & (df['up_move'] > 0), 'plus_dm'] = df['up_move']
    df.loc[(df['down_move'] > df['up_move']) & (df['down_move'] > 0), 'minus_dm'] = df['down_move']

    tr_smooth = df['TR'].ewm(span=window, adjust=False).mean()
    plus_di = 100 * (df['plus_dm'].ewm(span=window, adjust=False).mean() / tr_smooth)
    minus_di = 100 * (df['minus_dm'].ewm(span=window, adjust=False).mean() / tr_smooth)

    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    adx = dx.ewm(span=window, adjust=False).mean()
    return adx.iloc[-1]

def verificar_mercado_15m():
    print(f"\n--- [15m] A verificar mercado em {datetime.now().strftime('%H:%M:%S')} ---")
    
    for categoria, tickers in CATEGORIAS.items():
        for ticker in tickers:
            try:
                dados = yf.download(ticker, period="60d", interval="15m", progress=False)
                if dados.empty or len(dados) < 200:
                    continue
                
                close_series = dados['Close']
                if hasattr(close_series, 'iloc') and len(close_series.shape) > 1:
                    close_series = close_series.iloc[:, 0]

                ema80_series = close_series.ewm(span=80, adjust=False).mean()
                ema200_series = close_series.ewm(span=200, adjust=False).mean()
                
                ema80_atual, ema200_atual = ema80_series.iloc[-1], ema200_series.iloc[-1]
                ema80_anterior, ema200_anterior = ema80_series.iloc[-2], ema200_series.iloc[-2]
                
                distancia_pct = abs((ema80_atual - ema200_atual) / ema200_atual) * 100
                cruzou_acima = (ema80_anterior <= ema200_anterior) and (ema80_atual > ema200_atual)
                
                print(f"  [15m] {ticker} | Distância: {distancia_pct:.3f}%")
                
                if cruzou_acima:
                    msg = f"🟢 *SINAL VERDE (CRUZAMENTO 15m)*\nCategoria: *{categoria}*\nAtivo: *{ticker}*\nA EMA 80 acabou de cruzar ACIMA da EMA 200!"
                    enviar_telegram(msg)
                elif distancia_pct <= LIMITE_VERDE:
                    msg = f"🟢 *SINAL VERDE (MUITO PRÓXIMO 15m)*\nCategoria: *{categoria}*\nAtivo: *{ticker}*\nDistância atual: `{distancia_pct:.3f}%` (Colado nas EMAs)"
                    enviar_telegram(msg)
                elif distancia_pct <= LIMITE_AMARELO:
                    msg = f"🟡 *SINAL AMARELO (APROXIMANDO 15m)*\nCategoria: *{categoria}*\nAtivo: *{ticker}*\nDistância atual: `{distancia_pct:.3f}%`"
                    enviar_telegram(msg)
                    
            except Exception as e:
                print(f"  Erro no ativo {ticker} (15m): {e}")

def verificar_mercado_4h():
    print(f"\n--- [4h] A verificar tendência macro e ADX ---")
    
    for categoria, tickers in CATEGORIAS.items():
        for ticker in tickers:
            try:
                dados = yf.download(ticker, period="60d", interval="1h", progress=False)
                if dados.empty or len(dados) < 200:
                    dados = yf.download(ticker, period="60d", interval="1d", progress=False)
                    if dados.empty: continue
                
                if isinstance(dados.columns, pd.MultiIndex):
                    dados = dados.xs(ticker, axis=1, level=1) if ticker in dados.columns.levels[1] else dados

                # Reamostra para 4 horas
                df_4h = dados.resample('4h').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last'
                }).dropna()

                if len(df_4h) < 200:
                    continue

                close_series = df_4h['Close']
                ema80_series = close_series.ewm(span=80, adjust=False).mean()
                ema200_series = close_series.ewm(span=200, adjust=False).mean()
                
                ema80_atual, ema200_atual = ema80_series.iloc[-1], ema200_series.iloc[-1]
                ema80_anterior, ema200_anterior = ema80_series.iloc[-2], ema200_series.iloc[-2]
                
                distancia_pct = abs((ema80_atual - ema200_atual) / ema200_atual) * 100
                cruzou_acima = (ema80_anterior <= ema200_anterior) and (ema80_atual > ema200_atual)
                
                # ADX para medir a força da tendência
                adx_atual = calcular_adx(df_4h)
                tendencia_forte = adx_atual >= 25.0
                status_tendencia = "🔥 Tendência Forte (ADX > 25)" if tendencia_forte else "💤 Mercado Lateral / Sem Tendência Forte"
                
                print(f"  [4h] {ticker} | Distância: {distancia_pct:.3f}% | ADX: {adx_atual:.2f}")
                
                # Alerta estruturado combinando proximidade/cruzamento com o contexto de tendência
                if distancia_pct <= LIMITE_AMARELO or cruzou_acima:
                    status_msg = "🚀 Cruzamento Confirmado" if cruzou_acima else "⚡ Próximo de Cruzar"
                    msg = (
                        f"📊 *ANÁLISE DE TENDÊNCIA (4H) - {categoria}*\n"
                        f"Ativo: *{ticker}*\n"
                        f"Estado: {status_msg}\n"
                        f"Distância EMA 80/200: `{distancia_pct:.3f}%`\n"
                        f"Força do Movimento: `{status_tendencia}` (ADX: {adx_atual:.2f})"
                    )
                    enviar_telegram(msg)
                    
            except Exception as e:
                print(f"  Erro no ativo {ticker} (4h): {e}")

if __name__ == "__main__":
    print("Bot Avançado Multi-Timeframe com Filtro de Tendência Iniciado!")
    enviar_telegram("🤖 Bot Inteligente Ligado: A monitorizar M15 (Distância/Cruzamento) e H4 (Tendência ADX)!")
    
    while True:
        verificar_mercado_15m()
        verificar_mercado_4h()
        time.sleep(900) # Pausa de 15 minutos
