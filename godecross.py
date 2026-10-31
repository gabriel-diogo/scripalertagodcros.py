import time, requests, yfinance as yf, pandas as pd, warnings
warnings.filterwarnings("ignore")
from datetime import datetime

TOKEN = "9070151788:AAFhgfJpi_I3-wiochhLFgoVT2k7JXQNxlY"
CHAT_ID = "9106333952"

CATEGORIAS = {
    "💱 FOREX": ["EURUSD=X", "GBPUSD=X", "AUDUSD=X", "USDJPY=X", "USDCAD=X", "NZDUSD=X", "EURGBP=X"],
    "📈 ÍNDICES": ["^GSPC", "^DJI", "^IXIC", "^BVSP"]
}

def enviar_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id":CHAT_ID,"text":msg,"parse_mode":"Markdown"}, timeout=10)
    except: pass

def download_seguro(ticker, period, interval):
    for per, inter in [(period, interval), ("30d","1h"), ("90d","1d")]:
        try:
            df = yf.download(ticker, period=per, interval=inter, progress=False, auto_adjust=True, threads=False)
            if not df.empty and len(df)>20: return df
        except: pass
        time.sleep(0.5)
    return pd.DataFrame()

def pegar_close(d):
    if d.empty: return None
    try:
        if isinstance(d.columns, pd.MultiIndex): return d.xs('Close', axis=1, level=0).iloc[:,0]
        c=d['Close']
        if hasattr(c,'columns'): c=c.iloc[:,0]
        return c
    except: return None

def calcular_adx(df, window=14):
    try:
        df=df.copy()
        high=df['High']; low=df['Low']; close=df['Close']
        tr1=(high-low).abs()
        tr2=(high-close.shift(1)).abs()
        tr3=(low-close.shift(1)).abs()
        tr=pd.concat([tr1,tr2,tr3], axis=1).max(axis=1)
        up=high-high.shift(1)
        down=low.shift(1)-low
        plus_dm=pd.Series(0.0, index=df.index)
        minus_dm=pd.Series(0.0, index=df.index)
        plus_dm[(up>down)&(up>0)]=up
        minus_dm[(down>up)&(down>0)]=down
        tr_smooth=tr.ewm(span=window, adjust=False).mean()
        plus_di=100*(plus_dm.ewm(span=window, adjust=False).mean()/tr_smooth)
        minus_di=100*(minus_dm.ewm(span=window, adjust=False).mean()/tr_smooth)
        dx=100*((plus_di-minus_di).abs()/(plus_di+minus_di))
        adx=dx.ewm(span=window, adjust=False).mean()
        return float(adx.iloc[-1])
    except Exception as e:
        return 0.0

def print_tabela(titulo, lista):
    # lista = [(ticker, dist, adx, cruzou), ...]
    lista = sorted(lista, key=lambda x: x[1]) # ordena por distancia
    print(f"\n{titulo}")
    print(f"{'ATIVO':<12} | {'DIST':<7} | {'ADX':<6} | STATUS")
    print("-"*45)
    for t, dist, adx, cruzou in lista:
        status = "🔥 CRUZOU" if cruzou else ("🟢 PERTO" if dist<=0.10 else "🟡 OK" if dist<=0.25 else "")
        print(f"{t:<12} | {dist:5.3f}% | {adx:5.1f} | {status}")

def verificar_tudo():
    lista_15m=[]; lista_4h=[]; lista_cruz=[]
    for cat, tickers in CATEGORIAS.items():
        for t in tickers:
            d=download_seguro(t,"7d","15m")
            if d.empty: d=download_seguro(t,"90d","1d")
            close=pegar_close(d)
            if close is None or len(close)<20: continue
            if isinstance(d.columns, pd.MultiIndex):
                try: d_full=d.xs(t, axis=1, level=1)
                except: d_full=d
            else: d_full=d

            ema80=close.ewm(span=80, adjust=False).mean()
            ema200=close.ewm(span=200, adjust=False).mean()
            dist=abs((ema80.iloc[-1]-ema200.iloc[-1])/ema200.iloc[-1])*100
            adx=calcular_adx(d_full) if 'High' in d_full else 0
            cruzou=(ema80.iloc[-2]<=ema200.iloc[-2]) and (ema80.iloc[-1]>ema200.iloc[-1])

            lista_15m.append((t, dist, adx, cruzou))
            lista_4h.append((t, dist, adx, cruzou))
            lista_cruz.append((t, dist, adx, cruzou))

            # envia só os bons pro Telegram pra não spammar
            if dist<=0.10 or cruzou:
                enviar_telegram(f"🟢 *15m {cat} - {t}* Dist `{dist:.3f}%` ADX `{adx:.1f}` {'CRUZOU!' if cruzou else ''}")
            time.sleep(0.3)

    print_tabela("--- [15m] DISTANCIA EMA 80x200 (ordenado) ---", lista_15m)
    print_tabela("--- [4h] TENDENCIA + ADX (ordenado) ---", lista_4h)
    
    print("\n--- [NOVO] CRUZAMENTO RECENTE + ADX VERDE ---")
    print(f"{'ATIVO':<12} | {'DIST':<7} | {'ADX':<6} | CRUZOU?")
    print("-"*45)
    for t, dist, adx, cruzou in sorted(lista_cruz, key=lambda x: x[1]):
        if cruzou and adx>=25:
            print(f"{t:<12} | {dist:5.3f}% | {adx:5.1f} | SIM 🔥")
            enviar_telegram(f"🚀 *CRUZAMENTO + ADX VERDE - {t}* Dist `{dist:.3f}%` ADX `{adx:.1f}`")
        else:
            print(f"{t:<12} | {dist:5.3f}% | {adx:5.1f} | {cruzou}")

if __name__=="__main__":
    print("Bot ORGANIZADO Iniciado!")
    while True:
        verificar_tudo()
        print("\n--- Aguardando 15 min ---")
        time.sleep(900)
