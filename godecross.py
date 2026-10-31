import time, requests, yfinance as yf, pandas as pd, warnings
warnings.filterwarnings("ignore")
from datetime import datetime

TOKEN = ""
CHAT_ID = ""

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
    lista = sorted(lista, key=lambda x: x[1])
    print(f"\n{titulo}")
    print(f"{'ATIVO':<12} | {'DIST':<7} | {'ADX':<6} | STATUS")
    print("-"*45)
    for t, dist, adx, cruzou in lista:
        status = "🔥 CRUZOU" if cruzou else ("🟢 PERTO" if dist<=0.10 else "🟡 OK" if dist<=0.25 else "")
        print(f"{t:<12} | {dist:5.3f}% | {adx:5.1f} | {status}")

# ==========================================
# 1. ANÁLISE MACRO (4H) - O GRANDE MANDA NO MENOR
# ==========================================
def analisar_mercado_4h():
    macro_aprovados = {} # Guarda a força da tendência macro por ativo
    print("\n--- [4h] Analisando Gráfico Macro (O gráfico maior manda) ---")
    
    for cat, tickers in CATEGORIAS.items():
        for t in tickers:
            d = download_seguro(t, "60d", "1h")
            if d.empty: d = download_seguro(t, "60d", "1d")
            if d.empty: continue
            
            if isinstance(d.columns, pd.MultiIndex):
                try: d_full = d.xs(t, axis=1, level=1)
                except: d_full = d
            else: d_full = d

            try:
                df_4h = d_full.resample('4h').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
                }).dropna()
            except:
                continue

            close = pegar_close(df_4h)
            if close is None or len(close) < 200: continue

            ema80 = close.ewm(span=80, adjust=False).mean()
            ema200 = close.ewm(span=200, adjust=False).mean()
            dist = abs((ema80.iloc[-1] - ema200.iloc[-1]) / ema200.iloc[-1]) * 100
            adx = calcular_adx(df_4h)
            
            # Condição macro de alta: EMA 80 acima da 200 (ou muito perto) e ADX indicando tendência
            tendencia_alta_macro = (ema80.iloc[-1] > ema200.iloc[-1]) or (dist <= 0.25)
            adx_forte = adx >= 20.0
            
            score_macro = adx if (tendencia_alta_macro and adx_forte) else 0
            macro_aprovados[t] = {"score": score_macro, "adx": adx, "dist": dist}
            
    return macro_aprovados

# ==========================================
# 2. VERIFICAÇÃO 5M E 15M (VALIDADO PELO MACRO)
# ==========================================
def executar_varredura():
    macro_data = analisar_mercado_4h()
    
    lista_5m = []
    lista_15m = []
    ranking_geral = []

    print("\n--- A analisar Timeframes Menores (5m e 15m) com Filtro Macro ---")
    
    for cat, tickers in CATEGORIAS.items():
        for t in tickers:
            # Pega dados de 5m
            d_5m = download_seguro(t, "2d", "5m")
            close_5m = pegar_close(d_5m)
            
            # Pega dados de 15m
            d_15m = download_seguro(t, "7d", "15m")
            close_15m = pegar_close(d_15m)
            
            # Dados macro obtidos anteriormente
            info_macro = macro_data.get(t, {"score": 0, "adx": 0, "dist": 99})
            score_macro = info_macro["score"]
            
            # --- Processamento 5m ---
            if close_5m is not None and len(close_5m) >= 200:
                ema80_5 = close_5m.ewm(span=80, adjust=False).mean()
                ema200_5 = close_5m.ewm(span=200, adjust=False).mean()
                dist_5 = abs((ema80_5.iloc[-1] - ema200_5.iloc[-1]) / ema200_5.iloc[-1]) * 100
                cruzou_5 = (ema80_5.iloc[-2] <= ema200_5.iloc[-2]) and (ema80_5.iloc[-1] > ema200_5.iloc[-1])
                
                lista_5m.append((t, dist_5, info_macro["adx"], cruzou_5))
                
                # Se o macro aprovar (score > 0) e houver gatilho no 5m
                if score_macro > 0 and (cruzou_5 or dist_5 <= 0.08):
                    enviar_telegram(f"⚡ *SINAL 5M VALIDADO PELO MACRO ({cat})*\nAtivo: `{t}`\nDistância 5m: `{dist_5:.3f}%` | ADX Macro: `{info_macro['adx']:.1f}`")

            # --- Processamento 15m ---
            if close_15m is not None and len(close_15m) >= 200:
                ema80_15 = close_15m.ewm(span=80, adjust=False).mean()
                ema200_15 = close_15m.ewm(span=200, adjust=False).mean()
                dist_15 = abs((ema80_15.iloc[-1] - ema200_15.iloc[-1]) / ema200_15.iloc[-1]) * 100
                cruzou_15 = (ema80_15.iloc[-2] <= ema200_15.iloc[-2]) and (ema80_15.iloc[-1] > ema200_15.iloc[-1])
                
                lista_15m.append((t, dist_15, info_macro["adx"], cruzou_15))
                
                if score_macro > 0 and (cruzou_15 or dist_15 <= 0.10):
                    enviar_telegram(f"🟢 *SINAL 15M VALIDADO PELO MACRO ({cat})*\nAtivo: `{t}`\nDistância 15m: `{dist_15:.3f}%` | ADX Macro: `{info_macro['adx']:.1f}`")

            # Pontuação final para o Top 10 (Combina Força ADX Macro + Proximidade das Médias)
            potencial_alta = score_macro + (1.0 / (info_macro["dist"] + 0.1))
            ranking_geral.append((t, potencial_alta, info_macro["adx"], info_macro["dist"]))
            
            time.sleep(0.2)

    print_tabela("--- [5m] DISTANCIA EMA 80x200 ---", lista_5m)
    print_tabela("--- [15m] DISTANCIA EMA 80x200 ---", lista_15m)

    # ==========================================
    # 3. GERAÇÃO DO TOP 10 DE MAIOR POSSIBILIDADE DE ALTA
    # ==========================================
    ranking_geral = sorted(ranking_geral, key=lambda x: x[1], reverse=True)
    
    print("\n" + "="*50)
    print("🏆 TOP 10 ATIVOS COM MAIOR POSSIBILIDADE DE ALTA (Macro > Menor)")
    print("="*50)
    print(f"{'POS':<4} | {'ATIVO':<12} | {'ADX 4H':<8} | {'DIST EMA':<8}")
    print("-"*50)
    
    top_msg = "🏆 *TOP 10 OPORTUNIDADES DE ALTA (Filtro Macro)*:\n"
    for idx, (t, pot, adx, dist) in enumerate(ranking_geral[:10], 1):
        print(f"{idx:<4} | {t:<12} | {adx:8.1f} | {dist:7.3f}%")
        top_msg += f"{idx}. `{t}` (ADX: {adx:.1f} | Dist: {dist:.3f}%)\n"
        
    enviar_telegram(top_msg)
    print("="*50)

if __name__ == "__main__":
    print("Bot Jerárquico (Gráfico Maior Manda no Menor) Iniciado!")
    enviar_telegram("🤖 Bot Hierárquico Ativo: H4 filtrando M5 e M15 com Top 10 automático!")
    
    while True:
        executar_varredura()
        print("\n--- Ciclo concluído. Aguardando 15 min ---")
        time.sleep(900)
