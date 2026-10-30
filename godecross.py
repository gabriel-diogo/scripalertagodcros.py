import time
import requests
import yfinance as yf

# Configurações do Telegram
TOKEN = ""
CHAT_ID = ""

# Lista expandida de ativos (Forex e Índices no Yahoo Finance)
ATIVOS = [
    "EURUSD=X", "GBPUSD=X", "AUDUSD=X", "USDJPY=X", 
    "USDCAD=X", "NZDUSD=X", "EURGBP=X",
    "^GSPC", "^DJI", "^IXIC", "^BVSP" # S&P 500, Dow Jones, Nasdaq, Ibovespa
]

# Limite de proximidade percentual para o alerta (ex: 0.15%)
LIMITE_PERC = 0.15

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def verificar_mercado():
    print("A verificar a distância das EMAs no gráfico de 15 minutos...")
    for ticker in ATIVOS:
        try:
            # Descarrega os dados históricos no timeframe de 15 minutos (15m)
            dados = yf.download(ticker, period="60d", interval="15m", progress=False)
            
            if len(dados) < 200:
                continue
                
            # Garante a extração correta da série de preços de fecho
            close_series = dados['Close']
            if hasattr(close_series, 'iloc') and len(close_series.shape) > 1:
                close_series = close_series.iloc[:, 0]

            # Calcula as EMAs
            ema80 = close_series.ewm(span=80, adjust=False).mean().iloc[-1]
            ema200 = close_series.ewm(span=200, adjust=False).mean().iloc[-1]
            
            # Calcula a distância percentual absoluta
            distancia_pct = abs((ema80 - ema200) / ema200) * 100
            
            print(f"Ativo: {ticker} | Distância EMA 80/200: {distancia_pct:.3f}%")
            
            if distancia_pct <= LIMITE_PERC:
                msg = f"🟢 *ATENÇÃO - EMA COLADA (15m)*!\nA EMA 80 está próxima da EMA 200 no ativo *{ticker}*!\nDistância atual: {distancia_pct:.3f}%"
                enviar_telegram(msg)
                
        except Exception as e:
            print(f"Erro ao processar {ticker}: {e}")

if __name__ == "__main__":
    print("Bot de monitorização por distância iniciado com sucesso!")
    enviar_telegram("🟢 Bot de Alertas EMA 80/200 (Distância/15m) ligado e a monitorizar o mercado!")
    
    while True:
        verificar_mercado()
        # Aguarda 15 minutos antes de fazer uma nova verificação
        time.sleep(900)
