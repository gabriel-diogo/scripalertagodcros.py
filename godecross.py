
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

# Configure estas variáveis no Windows.
# Não coloque o token diretamente no código.

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

TODOS_ATIVOS = [
    ativo
    for ativos in CATEGORIAS.values()
    for ativo in ativos
]

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
ADX_MINIMO = 20

DIST_MIN_TENDENCIA = 0.10

DIST_PERTO = 0.10
DIST_RESET_PERTO = 0.15
DIST_RESET_CRUZOU = 0.30

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
    """Envia mensagens ao Telegram sem interromper o scanner."""

    if not TOKEN or not CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    # Telegram aceita até 4096 caracteres por mensagem.
    partes = [
        mensagem_texto[i:i + 3900]
        for i in range(0, len(mensagem_texto), 3900)
    ]

    sucesso = True

    for parte in partes:
        try:
            resposta = requests.post(
                url,
                json={
                    "chat_id": CHAT_ID,
                    "text": parte
                },
                timeout=15
            )

            if not resposta.ok:
                sucesso = False
                print(
                    "Erro Telegram:",
                    resposta.status_code,
                    resposta.text[:500]
                )

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
            Notification(
                app_id="Scanner EMA 80x200",
                title=titulo,
                msg=mensagem,
                duration="long"
            ).show()
        except Exception as erro:
            print(f"Erro notificação Windows: {erro}")

    texto_formatado = f"{titulo}\n{mensagem}"
    enviar_telegram(texto_formatado)

    print(f"\n🔔 {titulo} | {mensagem}")


# =========================================================
# 3. NORMALIZAÇÃO DOS DADOS
# =========================================================

def normalizar_colunas(df):

    if df is None or df.empty:
        return pd.DataFrame()

    resultado = {}
    campos = ["Open", "High", "Low", "Close", "Volume"]

    for coluna in df.columns:

        partes = coluna if isinstance(coluna, tuple) else (coluna,)

        nome = next(
            (str(p) for p in partes if str(p) in campos),
            None
        )

        if nome is not None and nome not in resultado:

            serie = df[coluna]

            if isinstance(serie, pd.DataFrame):
                serie = serie.iloc[:, 0]

            resultado[nome] = pd.to_numeric(
                serie,
                errors="coerce"
            )

    if not resultado:
        return pd.DataFrame()

    novo = pd.DataFrame(resultado, index=df.index)

    obrigatorias = ["Open", "High", "Low", "Close"]

    if not all(c in novo.columns for c in obrigatorias):
        return pd.DataFrame()

    novo = novo.dropna(subset=obrigatorias)

    return novo.sort_index()


# =========================================================
# 4. DOWNLOAD SEGURO
# =========================================================

def download_seguro(ticker, period, interval):

    periodos_tentativa = [period]

    if interval in ("5m", "15m"):
        periodos_tentativa.append("30d")

    elif interval == "1h":
        periodos_tentativa.extend(["1y", "60d"])

    for periodo in dict.fromkeys(periodos_tentativa):

        try:

            dados = yf.download(
                ticker,
                period=periodo,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
                group_by="column",
                timeout=20
            )

            if dados is None or dados.empty:
                continue

            dados = normalizar_colunas(dados)

            if dados.empty or len(dados) < 200:
                continue

            return dados

        except Exception as erro:

            print(
                f"Erro download {ticker} {interval}: {erro}"
            )

        time.sleep(0.5)

    print(f"⚠️ Sem dados suficientes: {ticker} | {interval}")

    return pd.DataFrame()


# =========================================================
# 5. REMOVER CANDLE ABERTO
# =========================================================

def remover_candle_aberto(df, segundos):

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    try:

        ultimo_horario = df.index[-1]

        if ultimo_horario.tz is not None:
            agora = pd.Timestamp.now(tz=ultimo_horario.tz)
        else:
            agora = pd.Timestamp.now()

        duracao = pd.Timedelta(seconds=segundos)

        df = df[
            (df.index + duracao) <= agora
        ]

        return df

    except Exception as erro:

        print(f"Erro ao remover candle aberto: {erro}")
        return df


# =========================================================
# 6. OBTER DADOS COM CACHE
# =========================================================

def obter_dados(ticker, timeframe):

    chave = (ticker, timeframe)

    if chave in cache_dados:
        return cache_dados[chave]

    if timeframe == "H4":

        dados_h1 = obter_dados(ticker, "H1")

        if dados_h1.empty:

            cache_dados[chave] = pd.DataFrame()
            return cache_dados[chave]

        dados = dados_h1.resample(
            "4h",
            label="left",
            closed="left"
        ).agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last"
        })

        dados = dados.dropna()

        dados = remover_candle_aberto(
            dados,
            14400
        )

    else:

        config = TIMEFRAMES[timeframe]

        dados = download_seguro(
            ticker,
            config["period"],
            config["interval"]
        )

        dados = remover_candle_aberto(
            dados,
            config["segundos"]
        )

    cache_dados[chave] = dados

    return dados


# =========================================================
# 7. CALCULAR EMA 80 E EMA 200
# =========================================================

def calcular_emas(close):

    ema80 = close.ewm(
        span=EMA_RAPIDA,
        adjust=False
    ).mean()

    ema200 = close.ewm(
        span=EMA_LENTA,
        adjust=False
    ).mean()

    return ema80, ema200


# =========================================================
# 8. ADX WILDER
# =========================================================

def calcular_adx(df, window=14):

    try:

        if df is None or df.empty:
            return None

        df = normalizar_colunas(df)

        if len(df) < window * 3:
            return None

        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()

        tr = pd.concat(
            [tr1, tr2, tr3],
            axis=1
        ).max(axis=1)

        up = high.diff()
        down = -low.diff()

        plus_dm = pd.Series(
            0.0,
            index=df.index
        )

        minus_dm = pd.Series(
            0.0,
            index=df.index
        )

        plus_dm[(up > down) & (up > 0)] = up

        minus_dm[(down > up) & (down > 0)] = down

        alpha = 1.0 / window

        tr_smooth = tr.ewm(
            alpha=alpha,
            adjust=False,
            min_periods=window
        ).mean()

        plus_smooth = plus_dm.ewm(
            alpha=alpha,
            adjust=False,
            min_periods=window
        ).mean()

        minus_smooth = minus_dm.ewm(
            alpha=alpha,
            adjust=False,
            min_periods=window
        ).mean()

        tr_smooth = tr_smooth.replace(
            0,
            float("nan")
        )

        plus_di = 100 * plus_smooth / tr_smooth
        minus_di = 100 * minus_smooth / tr_smooth

        denominador = (
            plus_di + minus_di
        ).replace(0, float("nan"))

        dx = (
            100
            * (plus_di - minus_di).abs()
            / denominador
        )

        adx = dx.ewm(
            alpha=alpha,
            adjust=False,
            min_periods=window
        ).mean()

        ultimo_adx = adx.iloc[-1]
        ultimo_plus = plus_di.iloc[-1]
        ultimo_minus = minus_di.iloc[-1]

        if (
            pd.isna(ultimo_adx)
            or pd.isna(ultimo_plus)
            or pd.isna(ultimo_minus)
        ):
            return None

        return {
            "adx": float(ultimo_adx),
            "plus_di": float(ultimo_plus),
            "minus_di": float(ultimo_minus)
        }

    except Exception as erro:

        print(f"Erro ADX: {erro}")
        return None


# =========================================================
# 9. ATR PERCENTUAL
# =========================================================

def calcular_atr_percentual(df, window=14):

    try:

        if df is None or len(df) < window + 2:
            return None

        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()

        tr = pd.concat(
            [tr1, tr2, tr3],
            axis=1
        ).max(axis=1)

        atr = tr.ewm(
            alpha=1.0 / window,
            adjust=False,
            min_periods=window
        ).mean()

        ultimo_atr = atr.iloc[-1]
        ultimo_close = close.iloc[-1]

        if (
            pd.isna(ultimo_atr)
            or pd.isna(ultimo_close)
            or ultimo_close == 0
        ):
            return None

        return float(
            (ultimo_atr / ultimo_close) * 100
        )

    except Exception as erro:

        print(f"Erro ATR percentual: {erro}")
        return None


# =========================================================
# 10. FUNÇÃO PRINCIPAL DE TENDÊNCIA
# =========================================================

def identificar_tendencia(df):

    if df is None or len(df) < 220:
        return "INDEFINIDA"

    close = df["Close"]

    ema80, ema200 = calcular_emas(close)

    adx_info = calcular_adx(
        df,
        ADX_PERIODO
    )

    if adx_info is None:
        return "INDEFINIDA"

    valor80 = float(ema80.iloc[-1])
    valor200 = float(ema200.iloc[-1])

    if (
        pd.isna(valor80)
        or pd.isna(valor200)
        or valor200 == 0
    ):
        return "INDEFINIDA"

    distancia = (
        abs((valor80 - valor200) / valor200) * 100
    )

    if (
        adx_info["adx"] < ADX_MINIMO
        or distancia < DIST_MIN_TENDENCIA
    ):
        return "LATERAL"

    if (
        valor80 > valor200
        and adx_info["plus_di"] > adx_info["minus_di"]
    ):
        return "ALTA"

    if (
        valor80 < valor200
        and adx_info["minus_di"] > adx_info["plus_di"]
    ):
        return "BAIXA"

    return "LATERAL"


# =========================================================
# 11. ANÁLISE MACRO H4
# =========================================================

def analisar_macro_h4(ticker):

    dados_h4 = obter_dados(
        ticker,
        "H4"
    )

    if len(dados_h4) < 220:
        return None

    close = dados_h4["Close"]

    ema80, ema200 = calcular_emas(close)

    adx_info = calcular_adx(
        dados_h4,
        ADX_PERIODO
    )

    atr_pct = calcular_atr_percentual(
        dados_h4,
        14
    )

    if adx_info is None or atr_pct is None:
        return None

    valor200 = float(ema200.iloc[-1])

    if valor200 == 0 or pd.isna(valor200):
        return None

    dist = (
        abs(
            (float(ema80.iloc[-1]) - valor200)
            / valor200
        ) * 100
    )

    tendencia = identificar_tendencia(dados_h4)

    return {
        "adx": adx_info["adx"],
        "plus_di": adx_info["plus_di"],
        "minus_di": adx_info["minus_di"],
        "dist": float(dist),
        "atr_pct": atr_pct,
        "tendencia": tendencia,
        "alta": tendencia == "ALTA"
    }


# =========================================================
# 12. ALERTAS PERTO E CRUZOU
# =========================================================

def checar_alerta_duplo(
    ativo,
    ema80,
    ema200,
    adx_local,
    plus_di,
    minus_di,
    timeframe
):

    if len(ema80) < 3 or len(ema200) < 3:
        return False

    atual80 = float(ema80.iloc[-1])
    atual200 = float(ema200.iloc[-1])

    anterior80 = float(ema80.iloc[-2])
    anterior200 = float(ema200.iloc[-2])

    if atual200 == 0:
        return False

    dist = (
        abs((atual80 - atual200) / atual200) * 100
    )

    cruzou_agora = (
        anterior80 <= anterior200
        and atual80 > atual200
    )

    forca_compradora = (
        adx_local is not None
        and adx_local >= ADX_MINIMO
        and plus_di is not None
        and minus_di is not None
        and plus_di > minus_di
    )

    key_perto = f"{ativo}_{timeframe}_PERTO"
    key_cruzou = f"{ativo}_{timeframe}_CRUZOU"

    perto = (
        atual80 < atual200
        and dist <= DIST_PERTO
        and forca_compradora
    )

    if perto and not estado.get(key_perto, False):

        estado[key_perto] = True

        alerta_windows(
            f"🟢 {ativo} {timeframe} PERTO",
            (
                f"ADX {adx_local:.1f} | "
                f"Distância {dist:.3f}% | "
                "EMA 80 aproximando da EMA 200"
            ),
            800
        )

    if dist > DIST_RESET_PERTO:
        estado[key_perto] = False

    cruzamento_confirmado = (
        cruzou_agora
        and forca_compradora
    )

    if (
        cruzamento_confirmado
        and not estado.get(key_cruzou, False)
    ):

        estado[key_cruzou] = True
        estado[key_perto] = True

        alerta_windows(
            f"🚀 {ativo} {timeframe} CRUZOU!",
            (
                "EMA 80 acima da EMA 200 | "
                f"ADX {adx_local:.1f} | "
                f"Distância {dist:.3f}%"
            ),
            1500
        )

        return True

    if dist > DIST_RESET_CRUZOU:
        estado[key_cruzou] = False

    return False


# =========================================================
# 13. ANALISAR UM ATIVO EM UM TIMEFRAME
# =========================================================

def analisar_timeframe(ticker, timeframe):

    dados = obter_dados(
        ticker,
        timeframe
    )

    if len(dados) < 220:
        return None

    close = dados["Close"]

    ema80, ema200 = calcular_emas(close)

    if (
        pd.isna(ema80.iloc[-1])
        or pd.isna(ema200.iloc[-1])
        or ema200.iloc[-1] == 0
    ):
        return None

    adx_info = calcular_adx(
        dados,
        ADX_PERIODO
    )

    if adx_info is None:
        return None

    dist = (
        abs(
            (ema80.iloc[-1] - ema200.iloc[-1])
            / ema200.iloc[-1]
        ) * 100
    )

    tendencia = identificar_tendencia(dados)

    cruzou = False

    if timeframe in ("M5", "M15"):

        cruzou = checar_alerta_duplo(
            ticker,
            ema80,
            ema200,
            adx_info["adx"],
            adx_info["plus_di"],
            adx_info["minus_di"],
            timeframe
        )

    return {
        "ativo": ticker,
        "timeframe": timeframe,
        "dist": float(dist),
        "adx": adx_info["adx"],
        "plus_di": adx_info["plus_di"],
        "minus_di": adx_info["minus_di"],
        "tendencia": tendencia,
        "cruzou": cruzou
    }


# =========================================================
# 14. BUSCAR TENDÊNCIA H4 -> H1 -> M15 -> M5
# =========================================================

def buscar_tendencia():

    print("\n" + "=" * 75)
    print("🔎 BUSCA AUTOMÁTICA DE TENDÊNCIA")
    print("=" * 75)

    for timeframe in ORDEM_TENDENCIA:

        print(
            f"\n--- PROCURANDO TENDÊNCIAS NO {timeframe} ---"
        )

        resultados = []

        for categoria, tickers in CATEGORIAS.items():

            print(f"\n{categoria}")

            for ticker in tickers:

                try:

                    resultado = analisar_timeframe(
                        ticker,
                        timeframe
                    )

                    if resultado is None:

                        print(
                            f"{ticker:<12} | SEM DADOS"
                        )

                        continue

                    if resultado["tendencia"] in ("ALTA", "BAIXA"):

                        resultados.append(resultado)

                        print(
                            f"{ticker:<12} | "
                            f"{resultado['tendencia']:<8} | "
                            f"ADX {resultado['adx']:5.1f} | "
                            f"DIST {resultado['dist']:6.3f}%"
                        )

                    else:

                        print(
                            f"{ticker:<12} | "
                            f"{resultado['tendencia']}"
                        )

                except Exception as erro:

                    print(
                        f"Erro {ticker} {timeframe}: {erro}"
                    )

                time.sleep(0.2)

        if resultados:

            print("\n" + "=" * 75)

            print(
                f"✅ TENDÊNCIAS ENCONTRADAS NO {timeframe}"
            )

            print("=" * 75)

            resultados.sort(
                key=lambda x: x["adx"],
                reverse=True
            )

            mensagem = [
                f"📊 TENDÊNCIAS CONFIRMADAS - {timeframe}",
                ""
            ]

            for item in resultados:

                simbolo = (
                    "📈"
                    if item["tendencia"] == "ALTA"
                    else "📉"
                )

                linha = (
                    f"{simbolo} {item['ativo']} | "
                    f"{item['tendencia']} | "
                    f"ADX {item['adx']:.1f} | "
                    f"DIST {item['dist']:.3f}%"
                )

                mensagem.append(linha)

                print(linha)

            mensagem.append("")
            mensagem.append(
                f"Total de tendências: {len(resultados)}"
            )

            enviar_telegram("\n".join(mensagem))

            return timeframe, resultados

        print(
            f"\nNenhuma tendência confirmada no {timeframe}."
        )

    print(
        "\n⚠️ Nenhuma tendência encontrada de H4 até M5."
    )

    return None, []


# =========================================================
# 15. TOP 10 - ATIVOS MAIS VOLÁTEIS
# =========================================================

def calcular_ranking(macro_data):

    ranking = []

    for ticker, info in macro_data.items():

        atr_pct = info.get("atr_pct")

        if atr_pct is None:
            continue

        ranking.append({
            "ativo": ticker,
            "atr_pct": atr_pct,
            "adx": info["adx"],
            "dist": info["dist"],
            "tendencia": info["tendencia"]
        })

    ranking.sort(
        key=lambda x: x["atr_pct"],
        reverse=True
    )

    print("\n" + "=" * 75)

    print(
        "🏆 TOP 10 - ATIVOS MAIS VOLÁTEIS | ATR % H4"
    )

    print("=" * 75)

    print(
        f"{'POS':<5} | {'ATIVO':<12} | "
        f"{'ATR %':<9} | {'ADX':<7} | "
        f"{'DIST':<9} | TENDÊNCIA"
    )

    print("-" * 75)

    if not ranking:

        print("Nenhum ativo com ATR disponível.")

        enviar_telegram(
            "⚠️ TOP 10: nenhum ativo com ATR H4 disponível."
        )

        return

    mensagem = [
        "🏆 TOP 10 - ATIVOS MAIS VOLÁTEIS",
        "Base: ATR percentual H4",
        ""
    ]

    for posicao, item in enumerate(ranking[:10], 1):

        linha = (
            f"{posicao}º | {item['ativo']} | "
            f"ATR {item['atr_pct']:.3f}% | "
            f"ADX {item['adx']:.1f} | "
            f"DIST {item['dist']:.3f}% | "
            f"{item['tendencia']}"
        )

        mensagem.append(linha)

        print(
            f"{posicao:<5} | "
            f"{item['ativo']:<12} | "
            f"{item['atr_pct']:7.3f}% | "
            f"{item['adx']:5.1f} | "
            f"{item['dist']:7.3f}% | "
            f"{item['tendencia']}"
        )

    print("=" * 75)

    enviar_telegram("\n".join(mensagem))


# =========================================================
# 16. EXECUTAR VARREDURA COMPLETA
# =========================================================

def executar_varredura():

    global cache_dados

    cache_dados = {}

    macro_data = {}

    print("\n" + "=" * 75)

    print(
        "🤖 SCANNER EMA 80/200 - "
        "TENDÊNCIA + VOLATILIDADE"
    )

    print("=" * 75)

    print("\n--- COLETANDO VOLATILIDADE H4 ---")

    for categoria, tickers in CATEGORIAS.items():

        print(f"\n{categoria}")

        for ticker in tickers:

            try:

                macro = analisar_macro_h4(ticker)

                if macro is not None:

                    macro_data[ticker] = macro

                    print(
                        f"{ticker:<12} | "
                        f"ATR {macro['atr_pct']:6.3f}% | "
                        f"ADX {macro['adx']:5.1f} | "
                        f"{macro['tendencia']}"
                    )

                else:

                    print(
                        f"{ticker:<12} | "
                        "DADOS H4 INSUFICIENTES"
                    )

            except Exception as erro:

                print(
                    f"Erro macro {ticker}: {erro}"
                )

            time.sleep(0.2)

    timeframe_encontrado, tendencias = buscar_tendencia()

    calcular_ranking(macro_data)

    print("\n" + "=" * 75)
    print("📋 RESUMO DA VARREDURA")
    print("=" * 75)

    print(
        f"Ativos com dados H4: {len(macro_data)}"
    )

    if timeframe_encontrado:

        print(
            f"Timeframe com tendências: "
            f"{timeframe_encontrado}"
        )

        print(
            f"Ativos em tendência: {len(tendencias)}"
        )

    else:

        print("Nenhuma tendência confirmada.")

    print("=" * 75)

    resumo = [
        "📋 RESUMO DA VARREDURA",
        f"Ativos com dados H4: {len(macro_data)}"
    ]

    if timeframe_encontrado:

        resumo.append(
            f"Timeframe com tendências: {timeframe_encontrado}"
        )

        resumo.append(
            f"Ativos em tendência: {len(tendencias)}"
        )

    else:

        resumo.append(
            "Nenhuma tendência confirmada."
        )

    enviar_telegram("\n".join(resumo))


# =========================================================
# 17. INICIALIZAÇÃO
# =========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("🤖 SCANNER EMA 80/200 INICIADO")
    print("=" * 60)

    print("Busca de tendência: H4 -> H1 -> M15 -> M5")
    print("EMA rápida: 80")
    print("EMA lenta: 200")
    print("ADX mínimo: 20")
    print("Distância mínima das EMAs: 0,10%")
    print("TOP 10: ATR percentual H4")
    print("Varredura: a cada 15 minutos")

    if not TOKEN or not CHAT_ID:

        print(
            "\n⚠️ Telegram não configurado. "
            "O scanner continuará funcionando."
        )

    alerta_windows(
        "Scanner EMA 80/200",
        "Robô iniciado e monitorando os ativos.",
        1000
    )

    while True:

        inicio = time.time()

        try:

            executar_varredura()

        except KeyboardInterrupt:

            print(
                "\nScanner encerrado pelo usuário."
            )

            break

        except Exception as erro:

            print(
                f"\nERRO GERAL: {erro}"
            )

            enviar_telegram(
                f"⚠️ ERRO GERAL NO SCANNER:\n{erro}"
            )

        duracao = time.time() - inicio

        espera = max(
            1,
            INTERVALO_VARREDURA - duracao
        )

        print(
            f"\n--- Ciclo concluído em {duracao:.1f}s ---"
        )

        print(
            f"Aguardando {espera / 60:.1f} minutos..."
        )

        try:

            time.sleep(espera)

        except KeyboardInterrupt:

            print(
                "\nScanner encerrado."
            )

            break
