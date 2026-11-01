
# ============================================================
# FOREX PRO - EMA 80/200 + MACD + ADX + CONSOLIDACAO
# BACKTEST EM 15 MINUTOS
# SOMENTE COMPRAS (LONG)
# ============================================================
#
# Instalar:
# pip install yfinance pandas numpy
#
# Executar:
# python backtest_forex_15m.py
#
# Dados: Yahoo Finance
# Periodo intraday: ultimos 60 dias, quando disponivel.
# ============================================================

import yfinance as yf
import pandas as pd
import numpy as np
import warnings

from datetime import time

warnings.filterwarnings("ignore")

# ============================================================
# 1. CONFIGURACOES
# ============================================================

TIMEFRAME = "15m"
PERIODO = "60d"

CAPITAL_INICIAL = 10000.0
QUANTIDADE = 1

# Horario UTC igual ao Pine Script
USAR_FILTRO_HORARIO = True

HORA_INICIO = "03:00"
HORA_FIM = "17:00"

# Filtros
USAR_MACD = True
USAR_ADX = True

ADX_PERIODO = 14
ADX_MINIMO = 15

USAR_FILTRO_LATERAL = True
CONSOLIDATION_LOOKBACK = 20
MAX_CRUZAMENTOS = 4

# Gestao de risco
STOP_PIPS = 30.0
TAKE_PIPS = 75.0

# Custos estimados por operacao completa, em pips.
# Ajuste para incluir spread, comissao e outros custos.
CUSTO_OPERACAO_PIPS = 0.0

# Slippage por lado, em pips.
SLIPPAGE_PIPS = 0.0

# Ativos Forex
ATIVOS = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "USDCHF=X": "USD/CHF",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "NZDUSD=X": "NZD/USD",
}


# ============================================================
# 2. FUNCOES AUXILIARES
# ============================================================

def converter_horario(valor):
    hora, minuto = map(int, valor.split(":"))
    return time(hora, minuto)


def obter_pip(ticker):
    """
    Forex:
    Pares com JPY: 1 pip = 0.01
    Outros pares: 1 pip = 0.0001
    """
    if "JPY" in ticker:
        return 0.01

    return 0.0001


def baixar_dados(ticker):

    print(f"Baixando {ticker}...")

    df = yf.download(
        ticker,
        period=PERIODO,
        interval=TIMEFRAME,
        auto_adjust=False,
        progress=False,
        multi_level_index=False
    )

    if df.empty:
        raise ValueError("Yahoo Finance nao retornou dados.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [str(c).lower() for c in df.columns]

    colunas = ["open", "high", "low", "close"]

    df = df[colunas].copy()

    df.dropna(inplace=True)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    return df


# ============================================================
# 3. CALCULO DOS INDICADORES
# ============================================================

def calcular_indicadores(df):

    df = df.copy()

    # --------------------------------------------------------
    # MEDIAS MOVEIS
    # --------------------------------------------------------

    df["ema9"] = df["close"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["ema21"] = df["close"].ewm(
        span=21,
        adjust=False
    ).mean()

    df["ema80"] = df["close"].ewm(
        span=80,
        adjust=False
    ).mean()

    df["ema200"] = df["close"].ewm(
        span=200,
        adjust=False
    ).mean()

    # --------------------------------------------------------
    # WAVE 34
    # Apenas visual/calculo, sem filtro de entrada.
    # --------------------------------------------------------

    df["wave_high"] = df["high"].ewm(
        span=34,
        adjust=False
    ).mean()

    df["wave_close"] = df["close"].ewm(
        span=34,
        adjust=False
    ).mean()

    df["wave_low"] = df["low"].ewm(
        span=34,
        adjust=False
    ).mean()

    df["wave_up"] = (
        df["wave_close"] > df["wave_close"].shift(1)
    )

    # --------------------------------------------------------
    # MACD 12 / 26 / 9
    # --------------------------------------------------------

    ema12 = df["close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"] - df["macd_signal"]
    )

    # --------------------------------------------------------
    # ADX / DMI 14
    # --------------------------------------------------------

    movimento_alta = df["high"].diff()
    movimento_baixa = -df["low"].diff()

    plus_dm = np.where(
        (movimento_alta > movimento_baixa) &
        (movimento_alta > 0),
        movimento_alta,
        0.0
    )

    minus_dm = np.where(
        (movimento_baixa > movimento_alta) &
        (movimento_baixa > 0),
        movimento_baixa,
        0.0
    )

    high_low = df["high"] - df["low"]

    high_close = (
        df["high"] - df["close"].shift(1)
    ).abs()

    low_close = (
        df["low"] - df["close"].shift(1)
    ).abs()

    tr = pd.concat(
        [high_low, high_close, low_close],
        axis=1
    ).max(axis=1)

    atr = tr.ewm(
        alpha=1 / ADX_PERIODO,
        adjust=False
    ).mean()

    plus_dm_smooth = pd.Series(
        plus_dm,
        index=df.index
    ).ewm(
        alpha=1 / ADX_PERIODO,
        adjust=False
    ).mean()

    minus_dm_smooth = pd.Series(
        minus_dm,
        index=df.index
    ).ewm(
        alpha=1 / ADX_PERIODO,
        adjust=False
    ).mean()

    df["plus_di"] = 100 * plus_dm_smooth / atr.replace(0, np.nan)

    df["minus_di"] = 100 * minus_dm_smooth / atr.replace(0, np.nan)

    dx = (
        (df["plus_di"] - df["minus_di"]).abs() /
        (df["plus_di"] + df["minus_di"]).replace(0, np.nan)
    ) * 100

    df["adx"] = dx.ewm(
        alpha=1 / ADX_PERIODO,
        adjust=False
    ).mean()

    # --------------------------------------------------------
    # FILTRO DE CONSOLIDACAO EMA 9 / EMA 21
    # --------------------------------------------------------

    cruzamento = (
        (df["ema9"] > df["ema21"]) &
        (df["ema9"].shift(1) <= df["ema21"].shift(1))
    ) | (
        (df["ema9"] < df["ema21"]) &
        (df["ema9"].shift(1) >= df["ema21"].shift(1))
    )

    df["cross_count"] = (
        cruzamento.astype(int).rolling(
            CONSOLIDATION_LOOKBACK
        ).sum()
    )

    # --------------------------------------------------------
    # CRUZAMENTO EMA 80 / EMA 200
    # --------------------------------------------------------

    df["cross_80_200"] = (
        (df["ema80"] > df["ema200"]) &
        (df["ema80"].shift(1) <= df["ema200"].shift(1))
    )

    return df.dropna().copy()


# ============================================================
# 4. BACKTEST
# ============================================================

def executar_backtest(ticker, nome):

    pip = obter_pip(ticker)

    stop_distancia = STOP_PIPS * pip
    take_distancia = TAKE_PIPS * pip

    slippage = SLIPPAGE_PIPS * pip

    inicio = converter_horario(HORA_INICIO)
    fim = converter_horario(HORA_FIM)

    df = baixar_dados(ticker)

    df = calcular_indicadores(df)

    if len(df) < 250:
        raise ValueError("Historico insuficiente para EMA 200.")

    trades = []

    posicao = None

    # --------------------------------------------------------
    # LOOP PRINCIPAL
    # --------------------------------------------------------

    for i in range(1, len(df)):

        atual = df.iloc[i]

        timestamp = df.index[i]
        hora = timestamp.time()

        abertura = float(atual["open"])
        maxima = float(atual["high"])
        minima = float(atual["low"])
        fechamento = float(atual["close"])

        # ====================================================
        # GERENCIAMENTO DA POSICAO ABERTA
        # ====================================================

        if posicao is not None:

            entrada = posicao["entrada"]

            stop = posicao["stop"]
            alvo = posicao["alvo"]

            preco_saida = None
            motivo = None

            # Stop: considera gap na abertura.
            if abertura <= stop:

                preco_saida = abertura
                motivo = "STOP LOSS - GAP"

            elif minima <= stop:

                preco_saida = stop
                motivo = "STOP LOSS"

            # Take Profit
            elif abertura >= alvo:

                preco_saida = abertura
                motivo = "TAKE PROFIT - GAP"

            elif maxima >= alvo:

                preco_saida = alvo
                motivo = "TAKE PROFIT"

            # Saida pela EMA 80
            elif fechamento < atual["ema80"]:

                preco_saida = fechamento
                motivo = "FECHAMENTO ABAIXO EMA 80"

            if preco_saida is not None:

                preco_saida -= slippage

                resultado_pips = (
                    preco_saida - entrada
                ) / pip

                resultado_pips -= CUSTO_OPERACAO_PIPS

                trades.append({
                    "Ativo": nome,
                    "Ticker": ticker,
                    "Entrada": posicao["data_entrada"],
                    "Saida": timestamp,
                    "Preco_Entrada": entrada,
                    "Preco_Saida": preco_saida,
                    "Resultado_Pips": resultado_pips,
                    "Motivo": motivo,
                })

                posicao = None

        # ====================================================
        # ENTRADA SOMENTE COMPRADA
        # ====================================================

        if posicao is not None:
            continue

        # Filtro de horario UTC
        if USAR_FILTRO_HORARIO:

            if not (inicio <= hora <= fim):
                continue

        # MACD positivo
        macd_ok = (
            not USAR_MACD or
            atual["macd"] > 0
        )

        # ADX verde
        adx_ok = (
            not USAR_ADX or
            (
                atual["adx"] >= ADX_MINIMO and
                atual["plus_di"] > atual["minus_di"]
            )
        )

        # Filtro de consolidacao
        consolidado = (
            USAR_FILTRO_LATERAL and
            atual["cross_count"] >= MAX_CRUZAMENTOS
        )

        consolidacao_ok = not consolidado

        # Cruzamento EMA 80 acima da EMA 200
        cruzamento_80_200 = bool(
            atual["cross_80_200"]
        )

        # Sinal final
        sinal_compra = all([
            cruzamento_80_200,
            macd_ok,
            adx_ok,
            consolidacao_ok,
        ])

        if sinal_compra:

            # Entrada no fechamento do candle,
            # conforme process_orders_on_close = true.
            entrada = fechamento + slippage

            stop = entrada - stop_distancia
            alvo = entrada + take_distancia

            posicao = {
                "entrada": entrada,
                "stop": stop,
                "alvo": alvo,
                "data_entrada": timestamp,
            }

    # ========================================================
    # FECHAMENTO DO ULTIMO TRADE
    # ========================================================

    if posicao is not None:

        ultimo = df.iloc[-1]

        timestamp = df.index[-1]

        preco_saida = float(ultimo["close"]) - slippage

        resultado_pips = (
            preco_saida - posicao["entrada"]
        ) / pip

        resultado_pips -= CUSTO_OPERACAO_PIPS

        trades.append({
            "Ativo": nome,
            "Ticker": ticker,
            "Entrada": posicao["data_entrada"],
            "Saida": timestamp,
            "Preco_Entrada": posicao["entrada"],
            "Preco_Saida": preco_saida,
            "Resultado_Pips": resultado_pips,
            "Motivo": "FIM DOS DADOS",
        })

    return pd.DataFrame(trades)


# ============================================================
# 5. METRICAS
# ============================================================

def calcular_metricas(trades, nome):

    if trades.empty:

        return {
            "Ativo": nome,
            "Operacoes": 0,
            "Vitorias": 0,
            "Derrotas": 0,
            "Acerto (%)": 0,
            "Resultado (pips)": 0,
            "Profit Factor": 0,
            "Media (pips)": 0,
            "Drawdown Maximo (pips)": 0,
        }

    resultados = trades["Resultado_Pips"]

    ganhos = resultados[resultados > 0]
    perdas = resultados[resultados < 0]

    soma_ganhos = ganhos.sum()
    soma_perdas = abs(perdas.sum())

    if soma_perdas > 0:
        profit_factor = soma_ganhos / soma_perdas
    elif soma_ganhos > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0

    curva = resultados.cumsum()

    drawdown = curva - curva.cummax()

    return {
        "Ativo": nome,
        "Operacoes": len(trades),
        "Vitorias": len(ganhos),
        "Derrotas": len(perdas),
        "Acerto (%)": round(
            len(ganhos) / len(trades) * 100, 2
        ),
        "Resultado (pips)": round(
            resultados.sum(), 2
        ),
        "Profit Factor": round(
            profit_factor, 2
        ),
        "Media (pips)": round(
            resultados.mean(), 2
        ),
        "Drawdown Maximo (pips)": round(
            abs(drawdown.min()), 2
        ),
    }


# ============================================================
# 6. EXECUTAR TODOS OS PARES
# ============================================================

def main():

    todos_trades = []
    relatorios = []

    print("=" * 75)
    print("FOREX PRO - EMA 80/200 + ADX DINAMICO")
    print("BACKTEST 15 MINUTOS | SOMENTE LONG")
    print("=" * 75)

    print(f"Stop: {STOP_PIPS} pips")
    print(f"Alvo: {TAKE_PIPS} pips")
    print(f"ADX minimo: {ADX_MINIMO}")
    print(f"Horario UTC: {HORA_INICIO} - {HORA_FIM}")

    for ticker, nome in ATIVOS.items():

        print("\n" + "-" * 60)
        print(f"TESTANDO {nome}")
        print("-" * 60)

        try:

            trades = executar_backtest(
                ticker,
                nome
            )

            if not trades.empty:
                todos_trades.append(trades)

            metricas = calcular_metricas(
                trades,
                nome
            )

            relatorios.append(metricas)

            print(f"Operacoes: {metricas['Operacoes']}")
            print(f"Acerto: {metricas['Acerto (%)']}%")
            print(
                f"Resultado: {metricas['Resultado (pips)']} pips"
            )
            print(
                f"Profit Factor: {metricas['Profit Factor']}"
            )
            print(
                f"Drawdown: {metricas['Drawdown Maximo (pips)']} pips"
            )

        except Exception as erro:

            print(f"ERRO: {erro}")

            relatorios.append({
                "Ativo": nome,
                "Erro": str(erro),
            })

    # ========================================================
    # RELATORIO FINAL
    # ========================================================

    relatorio_df = pd.DataFrame(relatorios)

    print("\n")
    print("=" * 90)
    print("RESULTADO FINAL")
    print("=" * 90)

    print(relatorio_df.to_string(index=False))

    relatorio_df.to_csv(
        "relatorio_forex_15m.csv",
        index=False,
        encoding="utf-8-sig"
    )

    if todos_trades:

        trades_df = pd.concat(
            todos_trades,
            ignore_index=True
        )

        trades_df.to_csv(
            "operacoes_forex_15m.csv",
            index=False,
            encoding="utf-8-sig"
        )

        print("\nArquivos gerados:")
        print("1. relatorio_forex_15m.csv")
        print("2. operacoes_forex_15m.csv")

    else:

        print("\nNenhuma operacao encontrada.")

    print("\nBacktest finalizado.")


if __name__ == "__main__":
    main()
