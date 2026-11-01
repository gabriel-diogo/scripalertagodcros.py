import os
import time
import warnings
import platform
import requests

import yfinance as yf
import pandas as pd

warnings.filterwarnings("ignore")

# =========================================================
# 1. CONFIGURAÇÕES
# =========================================================

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CATEGORIAS = {
    "FOREX": [
        "EURUSD=X", "GBPUSD=X", "AUDUSD=X",
        "USDJPY=X", "USDCAD=X", "NZDUSD=X", "EURGBP=X"
    ],
    "ÍNDICES": [
        "^GSPC", "^DJI", "^IXIC", "^BVSP"
    ]
}

TIMEFRAMES = {
    "M5": {
        "interval": "5m",
        "period": "60d",
        "segundos": 300
    },
    "M15": {
        "interval": "15m",
        "period": "60d",
        "segundos": 900
    },
    "H1": {
        "interval": "1h",
        "period": "2y",
        "segundos": 3600
    }
}

ORDEM_TENDENCIA = ["H4", "H1", "M15", "M5"]

EMA_RAPIDA = 80
EMA_LENTA = 200

ADX_PERIODO = 14
ADX_MINIMO = 15  # Ligeiramente flexibilizado para capturar o início do movimento em M5/M15

DIST_MIN_TENDENCIA = 0.05
DIST_PERTO = 0.20       # Margem de proximidade alargada para detetar em M5/M15
DIST_RESET_PERTO = 0.35
DIST_RESET_CRUZOU = 0.50

INTERVALO_VARREDURA = 900

estado = {}
cache_dados = {}


# =========================================================
# 2. ALERTAS WINDOWS + TELEGRAM
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
    partes = [mensagem_texto[i:i + 3900] for i in range(0, len(mensagem_texto), 3900)]

    sucesso = True
    for parte in partes:
        try:
            resposta = requests.post(url, json={"chat_id": CHAT_ID, "text": parte}, timeout=15)
            if not resposta.ok:
                sucesso = False
                print("Erro Telegram:", resposta.status_code, resposta.text[:500])
        except requests.RequestException as erro:
            sucesso = False
            print(f"Falha Telegram: {erro}")

    return sucesso


def alerta_windows(titulo, mensagem, beep_freq=1000):
    if TEM_WINSOUND:
        try:
            winsound.Beep(beep_freq, 700)
        except Exception:
            pass

    if TEM_WINOTIFY:
        try:
            Notification(app_id="Scanner EMA 80x200", title=titulo, msg=mensagem, duration="long").show()
        except Exception as erro:
            print(f"Erro notificação Windows: {erro}")

    texto_formatado = f"{titulo}\n{mensagem}"
    enviar_telegram(texto_formatado)
    print(f"\n🔔 {titulo} | {mensagem}")


# =========================================================
# 3. NORMALIZAÇÃO E DOWNLOAD DE DADOS
# =========================================================

def normalizar_colunas(df):
    if df is None or df.empty:
        return pd.DataFrame()

    resultado = {}
    campos = ["Open", "High", "Low", "Close", "Volume"]

    for coluna in df.columns:
        partes = coluna if isinstance(coluna, tuple) else (coluna,)
        nome = next((str(p) for p in partes if str(p) in campos), None)

        if nome is not None and nome not in resultado:
            serie = df[coluna]
            if isinstance(serie, pd.DataFrame):
                serie = serie.iloc[:, 0]
            resultado[nome] = pd.to_numeric(serie, errors="coerce")

    if not resultado:
        return pd.DataFrame()

    novo = pd.DataFrame(resultado, index=df.index)
    obrigatorias = ["Open", "High", "Low", "Close"]

    if not all(c in novo.columns for c in obrigatorias):
        return pd.DataFrame()

    return novo.dropna(subset=obrigatorias).sort_index()


def download_seguro(ticker, period, interval):
    periodos_tentativa = [period]
    if interval in ("5m", "15m"):
        periodos_tentativa.append("30d")
    elif interval == "1h":
        periodos_tentativa.extend(["1y", "60d"])

    for periodo in dict.fromkeys(periodos_tentativa):
        try:
            dados = yf.download(
                ticker, period=periodo, interval=interval,
                progress=False, auto_adjust=False, threads=False,
                group_by="column", timeout=20
            )
            if dados is None or dados.empty:
                continue
            dados = normalizar_colunas(dados)
            if dados.empty or len(dados) < 200:
                continue
            return dados
        except Exception as erro:
            print(f"Erro download {ticker} {interval}: {erro}")
        time.sleep(0.5)

    return pd.DataFrame()


def remover_candle_aberto(df, segundos):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    try:
        ultimo_horario = df.index[-1]
        agora = pd.Timestamp.now(tz=ultimo_horario.tz) if ultimo_horario.tz is not None else pd.Timestamp.now()
        duracao = pd.Timedelta(seconds=segundos)
        return df[(df.index + duracao) <= agora]
    except Exception:
        return df


def obter_dados(ticker, timeframe):
    chave = (ticker, timeframe)
    if chave in cache_dados:
        return cache_dados[chave]

    if timeframe == "H4":
        dados_h1 = obter_dados(ticker, "H1")
        if dados_h1.empty:
            cache_dados[chave] = pd.DataFrame()
            return cache_dados[chave]

        dados = dados_h1.resample("4h", label="left", closed="left").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last"
        }).dropna()
        dados = remover_candle_aberto(dados, 14400)
    else:
        config = TIMEFRAMES[timeframe]
        dados = download_seguro(ticker, config["period"], config["interval"])
        dados = remover_candle_aberto(dados, config["segundos"])

    cache_dados[chave] = dados
    return dados


def calcular_emas(close):
    ema80 = close.ewm(span=EMA_RAPIDA, adjust=False).mean()
    ema200 = close.ewm(span=EMA_LENTA, adjust=False).mean()
    return ema80, ema200


def calcular_adx(df, window=14):
    try:
        if df is None or df.empty:
            return None
        df = normalizar_colunas(df)
        if len(df) < window * 3:
            return None

        high, low, close = df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
        tr1, tr2, tr3 = high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        up, down = high.diff(), -low.diff()
        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)
        plus_dm[(up > down) & (up > 0)] = up
        minus_dm[(down > up) & (down > 0)] = down

        alpha = 1.0 / window
        tr_smooth = tr.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
        plus_smooth = plus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
        minus_smooth = minus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean()

        tr_smooth = tr_smooth.replace(0, float("nan"))
        plus_di = 100 * plus_smooth / tr_smooth
        minus_di = 100 * minus_smooth / tr_smooth
        denominador = (plus_di + minus_di).replace(0, float("nan"))
        dx = 100 * (plus_di - minus_di).abs() / denominador
        adx = dx.ewm(alpha=alpha, adjust=False, min_periods=window).mean()

        return {
            "adx": float(adx.iloc[-1]),
            "plus_di": float(plus_di.iloc[-1]),
            "minus_di": float(minus_di.iloc[-1])
        }
    except Exception:
        return None


def calcular_atr_percentual(df, window=14):
    try:
        if df is None or len(df) < window + 2:
            return None
        high, low, close = df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
        tr1, tr2, tr3 = high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
        return float((atr.iloc[-1] / close.iloc[-1]) * 100)
    except Exception:
        return None


# =========================================================
# 4. MONITORAMENTO AVANÇADO DE CRUZAMENTO M5 / M15
# =========================================================

def verificar_cruzamento_tempo_real(ticker, ema80, ema200, adx_info, timeframe):
    if len(ema80) < 3 or len(ema200) < 3:
        return

    atual80 = float(ema80.iloc[-1])
    atual200 = float(ema200.iloc[-1])
    anterior80 = float(ema80.iloc[-2])
    anterior200 = float(ema200.iloc[-2])

    if atual200 == 0:
        return

    dist = abs((atual80 - atual200) / atual200) * 100
    cruzou_agora = (anterior80 <= anterior200) and (atual80 > atual200)
    ja_cruzado = atual80 > atual200

    key_perto = f"{ticker}_{timeframe}_PERTO"
    key_cruzou = f"{ticker}_{timeframe}_CRUZOU"

    adx_val = adx_info["adx"] if adx_info else 0.0

    # 1. Alerta de Proximidade (Prstes a cruzar)
    if atual80 < atual200 and dist <= DIST_PERTO and not estado.get(key_perto, False):
        estado[key_perto] = True
        alerta_windows(
            f"🟡 {ticker} [{timeframe}] - EMAS QUASE A CRUZAR!",
            (
                f"Ativo: {ticker} | Timeframe: {timeframe}\n"
                f"Distância atual: {dist:.3f}%\n"
                f"ADX: {adx_val:.1f}\n"
                f"A EMA 80 está colada à EMA 200!"
            ),
            700
        )

    if dist > DIST_RESET_PERTO:
        estado[key_perto] = False

    # 2. Alerta de Cruzamento Exato ou Estado Cruzado Ativo em M5/M15
    if (cruzou_agora or (ja_cruzado and not estado.get(key_cruzou, False))) and dist <= DIST_RESET_CRUZOU:
        estado[key_cruzou] = True
        estado[key_perto] = True
        
        status_txt = "CRUZOU AGORA NESTA VELA! 🚀" if cruzou_agora else "ESTÁ CRUZADO (ACIMA) 📈"
        
        alerta_windows(
            f"🚀 {ticker} [{timeframe}] - {status_txt}",
            (
                f"Ativo: {ticker} | Timeframe: {timeframe}\n"
                f"EMA 80 ({atual80:.5f}) > EMA 200 ({atual200:.5f})\n"
                f"Distância: {dist:.3f}% | ADX: {adx_val:.1f}"
            ),
            1200
        )

    if not ja_cruzado or dist > DIST_RESET_CRUZOU:
        estado[key_cruzou] = False


def analisar_timeframe(ticker, timeframe):
    dados = obter_dados(ticker, timeframe)
    if len(dados) < 220:
        return None

    close = dados["Close"]
    ema80, ema200 = calcular_emas(close)

    if pd.isna(ema80.iloc[-1]) or pd.isna(ema200.iloc[-1]) or ema200.iloc[-1] == 0:
        return None

    adx_info = calcular_adx(dados, ADX_PERIODO)
    dist = abs((ema80.iloc[-1] - ema200.iloc[-1]) / ema200.iloc[-1]) * 100

    # Executa a verificação detalhada em M5 e M15
    if timeframe in ("M5", "M15"):
        verificar_cruzamento_tempo_real(ticker, ema80, ema200, adx_info, timeframe)

    tendencia = "ALTA" if ema80.iloc[-1] > ema200.iloc[-1] else "BAIXA"

    return {
        "ativo": ticker,
        "timeframe": timeframe,
        "dist": float(dist),
        "adx": adx_info["adx"] if adx_info else 0.0,
        "tendencia": tendencia
    }


def analisar_macro_h4(ticker):
    dados_h4 = obter_dados(ticker, "H4")
    if len(dados_h4) < 220:
        return None
    ema80, ema200 = calcular_emas(dados_h4["Close"])
    adx_info = calcular_adx(dados_h4, ADX_PERIODO)
    atr_pct = calcular_atr_percentual(dados_h4, 14)

    if adx_info is None or atr_pct is None or ema200.iloc[-1] == 0:
        return None

    dist = abs((float(ema80.iloc[-1]) - float(ema200.iloc[-1])) / float(ema200.iloc[-1])) * 100
    tendencia = "ALTA" if ema80.iloc[-1] > ema200.iloc[-1] else "BAIXA"

    return {
        "adx": adx_info["adx"],
        "dist": float(dist),
        "atr_pct": atr_pct,
        "tendencia": tendencia
    }


# =========================================================
# 5. VARREDURA E EXECUÇÃO
# =========================================================

def buscar_tendencia():
    print("\n" + "=" * 75)
    print("🔎 VARREDURA EM TEMPO REAL (M5, M15, H1, H4)")
    print("=" * 75)

    for timeframe in ORDEM_TENDENCIA:
        print(f"\n--- ANALISANDO TIMEFRAME: {timeframe} ---")
        resultados = []

        for categoria, tickers in CATEGORIAS.items():
            print(f"\n{categoria}")
            for ticker in tickers:
                try:
                    res = analisar_timeframe(ticker, timeframe)
                    if res is None:
                        print(f"{ticker:<12} | SEM DADOS")
                        continue

                    print(
                        f"{ticker:<12} | "
                        f"TF: {timeframe:<3} | "
                        f"Tendência: {res['tendencia']:<5} | "
                        f"ADX: {res['adx']:5.1f} | "
                        f"Distância 80/200: {res['dist']:6.3f}%"
                    )
                    resultados.append(res)
                except Exception as erro:
                    print(f"Erro {ticker} {timeframe}: {erro}")
                time.sleep(0.2)


def calcular_ranking(macro_data):
    ranking = [
        {"ativo": t, **info} for t, info in macro_data.items() if info.get("atr_pct") is not None
    ]
    ranking.sort(key=lambda x: x["atr_pct"], reverse=True)

    print("\n" + "=" * 75)
    print("🏆 TOP 10 - ATIVOS MAIS VOLÁTEIS | ATR % H4")
    print("=" * 75)
    for pos, item in enumerate(ranking[:10], 1):
        print(f"{pos}º | {item['ativo']:<10} | ATR: {item['atr_pct']:.3f}% | ADX: {item['adx']:.1f} | Dist: {item['dist']:.3f}%")
    print("=" * 75)


def executar_varredura():
    global cache_dados
    cache_dados = {}
    macro_data = {}

    print("\n" + "=" * 75)
    print("🤖 INICIANDO NOVO CICLO DE MONITORAMENTO")
    print("=" * 75)

    for categoria, tickers in CATEGORIAS.items():
        for ticker in tickers:
            try:
                macro = analisar_macro_h4(ticker)
                if macro:
                    macro_data[ticker] = macro
            except Exception:
                pass
            time.sleep(0.2)

    buscar_tendencia()
    calcular_ranking(macro_data)


if __name__ == "__main__":
    print("=" * 60)
    print("🤖 SCANNER MULTI-TIMEFRAME (M5/M15 ATIVADOS PARA CRUZAMENTOS)")
    print("=" * 60)

    alerta_windows("Scanner Iniciado", "Monitoramento ativo para M5, M15 e H4.", 800)

    while True:
        inicio = time.time()
        try:
            executar_varredura()
        except KeyboardInterrupt:
            print("\nEncerrado pelo usuário.")
            break
        except Exception as e:
            print(f"\nErro: {e}")

        duracao = time.time() - inicio
        espera = max(1, INTERVALO_VARREDURA - duracao)
        print(f"\nCiclo concluído em {duracao:.1f}s. Próxima varredura em {espera / 60:.1f} minutos...\n")
        
        try:
            time.sleep(espera)
        except KeyboardInterrupt:
            break
