
# ============================================================
# BACKTEST WAVE 34 + EMA 80 + MACD + RSI + ADX
# TIMEFRAME: 5 MINUTOS
# SOMENTE COMPRAS (LONG)
# ============================================================
#
# Instalar:
# pip install yfinance pandas numpy
#
# Executar:
# python backtest_wave.py
# ============================================================

import yfinance as yf
import pandas as pd
import numpy as np
import warnings

from datetime import time

warnings.filterwarnings("ignore")

# ============================================================
# 1. CONFIGURACAO GERAL
# ============================================================

TIMEFRAME = "5m"
PERIODO = "60d"

CAPITAL_INICIAL = 10000.0
QUANTIDADE = 1

MAX_OPERACOES_DIA = 1
MAX_PERDAS_CONSECUTIVAS = 1

CUSTO_OPERACAO = 0.0
SLIPPAGE = 0.0

# RSI
RSI_MAX_COMPRA = 68

# ATIVAR / DESATIVAR RECURSOS
USAR_DISTANCIA_EMA = False
USAR_BREAK_EVEN = False
USAR_BREAK_LOCK = False

# ============================================================
# 2. ATIVOS
# ============================================================

ATIVOS = {

    # INDICES

    "^BVSP": {
        "nome": "IBOVESPA",
        "tipo": "indice",
        "timezone": "America/Sao_Paulo",
        "inicio": "09:15",
        "fim": "16:15",
        "stop": 330,
        "alvo": 700,
        "distancia_ema": 350,
        "break_even": 300,
        "break_lock": 50,
        "trailing_inicio": 500,
        "trailing_atr": 1.5,
        "perda_diaria": 1500,
    },


    # FOREX

    "EURUSD=X": {
        "nome": "EUR/USD",
        "tipo": "forex",
        "timezone": "America/Sao_Paulo",
        "inicio": "00:00",
        "fim": "23:55",
        "pip": 0.0001,
        "stop": 20,
        "alvo": 40,
        "distancia_ema": 14,
        "break_even": 12,
        "break_lock": 2,
        "trailing_inicio": 20,
        "trailing_atr": 1.5,
        "perda_diaria": 60,
    },

    "GBPUSD=X": {
        "nome": "GBP/USD",
        "tipo": "forex",
        "timezone": "America/Sao_Paulo",
        "inicio": "00:00",
        "fim": "23:55",
        "pip": 0.0001,
        "stop": 20,
        "alvo": 40,
        "distancia_ema": 14,
        "break_even": 12,
        "break_lock": 2,
        "trailing_inicio": 20,
        "trailing_atr": 1.5,
        "perda_diaria": 60,
    },

    "USDJPY=X": {
        "nome": "USD/JPY",
        "tipo": "forex",
        "timezone": "America/Sao_Paulo",
        "inicio": "00:00",
        "fim": "23:55",
        "pip": 0.01,
        "stop": 20,
        "alvo": 40,
        "distancia_ema": 14,
        "break_even": 12,
        "break_lock": 2,
        "trailing_inicio": 20,
        "trailing_atr": 1.5,
        "perda_diaria": 60,
    },

    "USDCHF=X": {
        "nome": "USD/CHF",
        "tipo": "forex",
        "timezone": "America/Sao_Paulo",
        "inicio": "00:00",
        "fim": "23:55",
        "pip": 0.0001,
        "stop": 20,
        "alvo": 40,
        "distancia_ema": 14,
        "break_even": 12,
        "break_lock": 2,
        "trailing_inicio": 20,
        "trailing_atr": 1.5,
        "perda_diaria": 60,
    },

    "AUDUSD=X": {
        "nome": "AUD/USD",
        "tipo": "forex",
        "timezone": "America/Sao_Paulo",
        "inicio": "00:00",
        "fim": "23:55",
        "pip": 0.0001,
        "stop": 20,
        "alvo": 40,
        "distancia_ema": 14,
        "break_even": 12,
        "break_lock": 2,
        "trailing_inicio": 20,
        "trailing_atr": 1.5,
        "perda_diaria": 60,
    },

    "USDCAD=X": {
        "nome": "USD/CAD",
        "tipo": "forex",
        "timezone": "America/Sao_Paulo",
        "inicio": "00:00",
        "fim": "23:55",
        "pip": 0.0001,
        "stop": 20,
        "alvo": 40,
        "distancia_ema": 14,
        "break_even": 12,
        "break_lock": 2,
        "trailing_inicio": 20,
        "trailing_atr": 1.5,
        "perda_diaria": 60,
    },

    "NZDUSD=X": {
        "nome": "NZD/USD",
        "tipo": "forex",
        "timezone": "America/Sao_Paulo",
        "inicio": "00:00",
        "fim": "23:55",
        "pip": 0.0001,
        "stop": 20,
        "alvo": 40,
        "distancia_ema": 14,
        "break_even": 12,
        "break_lock": 2,
        "trailing_inicio": 20,
        "trailing_atr": 1.5,
        "perda_diaria": 60,
    },
}


# ============================================================
# 3. FUNCOES AUXILIARES
# ============================================================

def horario_para_time(valor):
    h, m = map(int, valor.split(":"))
    return time(h, m)


def baixar_dados(ticker, timezone):

    print(f"\nBaixando {ticker}...")

    dados = yf.download(
        ticker,
        period=PERIODO,
        interval=TIMEFRAME,
        auto_adjust=False,
        progress=False,
        multi_level_index=False
    )

    if dados.empty:
        raise ValueError("Nenhum dado retornado.")

    if isinstance(dados.columns, pd.MultiIndex):
        dados.columns = dados.columns.get_level_values(0)

    dados.columns = [
        str(c).lower() for c in dados.columns
    ]

    colunas = [
        "open", "high", "low", "close", "volume"
    ]

    dados = dados[colunas].copy()

    dados.dropna(
        subset=["open", "high", "low", "close"],
        inplace=True
    )

    if dados.index.tz is None:
        dados.index = dados.index.tz_localize("UTC")

    dados.index = dados.index.tz_convert(timezone)

    return dados


# ============================================================
# 4. INDICADORES
# ============================================================

def calcular_indicadores(df):

    df = df.copy()

    # WAVE 34
    df["wave_high"] = df["high"].ewm(
        span=34, adjust=False
    ).mean()

    df["wave_close"] = df["close"].ewm(
        span=34, adjust=False
    ).mean()

    df["wave_low"] = df["low"].ewm(
        span=34, adjust=False
    ).mean()

    # EMAS
    df["ema13"] = df["close"].ewm(
        span=13, adjust=False
    ).mean()

    df["ema26"] = df["close"].ewm(
        span=26, adjust=False
    ).mean()

    df["ema80"] = df["close"].ewm(
        span=80, adjust=False
    ).mean()

    df["ema200"] = df["close"].ewm(
        span=200, adjust=False
    ).mean()

    # MACD 12 / 26 / 9
    ema12 = df["close"].ewm(
        span=12, adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26, adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9, adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"] - df["macd_signal"]
    )

    # RSI 14
    delta = df["close"].diff()

    ganho = delta.clip(lower=0)
    perda = -delta.clip(upper=0)

    media_ganho = ganho.ewm(
        alpha=1/14, adjust=False
    ).mean()

    media_perda = perda.ewm(
        alpha=1/14, adjust=False
    ).mean()

    rs = media_ganho / media_perda.replace(
        0, np.nan
    )

    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)

    # ATR 14
    high_low = df["high"] - df["low"]

    high_close = (
        df["high"] - df["close"].shift()
    ).abs()

    low_close = (
        df["low"] - df["close"].shift()
    ).abs()

    tr = pd.concat(
        [high_low, high_close, low_close],
        axis=1
    ).max(axis=1)

    df["atr"] = tr.ewm(
        alpha=1/14, adjust=False
    ).mean()

    # DMI / ADX
    movimento_alta = df["high"].diff()
    movimento_baixa = -df["low"].diff()

    plus_dm = np.where(
        (movimento_alta > movimento_baixa) &
        (movimento_alta > 0),
        movimento_alta,
        0
    )

    minus_dm = np.where(
        (movimento_baixa > movimento_alta) &
        (movimento_baixa > 0),
        movimento_baixa,
        0
    )

    atr_dmi = tr.ewm(
        alpha=1/14, adjust=False
    ).mean()

    plus_di = (
        100 *
        pd.Series(plus_dm, index=df.index).ewm(
            alpha=1/14, adjust=False
        ).mean() / atr_dmi
    )

    minus_di = (
        100 *
        pd.Series(minus_dm, index=df.index).ewm(
            alpha=1/14, adjust=False
        ).mean() / atr_dmi
    )

    dx = (
        (plus_di - minus_di).abs() /
        (plus_di + minus_di).replace(0, np.nan)
    ) * 100

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    df["adx"] = dx.ewm(
        alpha=1/14, adjust=False
    ).mean()

    # FILTRO LATERAL: cruzamentos EMA13 / EMA26
    cruzou_cima = (
        (df["ema13"] > df["ema26"]) &
        (df["ema13"].shift(1) <= df["ema26"].shift(1))
    )

    cruzou_baixo = (
        (df["ema13"] < df["ema26"]) &
        (df["ema13"].shift(1) >= df["ema26"].shift(1))
    )

    cruzamentos = (
        cruzou_cima.astype(int) +
        cruzou_baixo.astype(int)
    )

    df["cross_count"] = cruzamentos.rolling(20).sum()

    # CRUZAMENTO WAVE / EMA80
    df["wave_cross_up"] = (
        (df["wave_close"] > df["ema80"]) &
        (df["wave_close"].shift(1) <= df["ema80"].shift(1))
    )

    return df.dropna().copy()


# ============================================================
# 5. BACKTEST SOMENTE LONG
# ============================================================

def executar_backtest(ticker, config):

    dados = baixar_dados(
        ticker,
        config["timezone"]
    )

    dados = calcular_indicadores(dados)

    if len(dados) < 250:
        raise ValueError("Poucos candles para backtest.")

    inicio = horario_para_time(config["inicio"])
    fim = horario_para_time(config["fim"])

    unidade = (
        config["pip"]
        if config["tipo"] == "forex"
        else 1.0
    )

    stop_dist = config["stop"] * unidade
    alvo_dist = config["alvo"] * unidade
    distancia_ema = config["distancia_ema"] * unidade

    break_even = config["break_even"] * unidade
    break_lock = config["break_lock"] * unidade

    trailing_inicio = config["trailing_inicio"] * unidade
    perda_diaria = config["perda_diaria"] * unidade

    trades = []

    posicao = None

    resultado_diario = 0.0
    operacoes_dia = 0
    perdas_consecutivas = 0
    dia_atual = None

    for i in range(1, len(dados)):

        atual = dados.iloc[i]

        timestamp = dados.index[i]
        dia = timestamp.date()
        hora = timestamp.time()

        if dia != dia_atual:

            dia_atual = dia
            resultado_diario = 0.0
            operacoes_dia = 0
            perdas_consecutivas = 0

        abertura = float(atual["open"])
        maxima = float(atual["high"])
        minima = float(atual["low"])
        fechamento = float(atual["close"])

        # -----------------------------------------------
        # GERENCIAMENTO DA POSICAO
        # -----------------------------------------------

        if posicao is not None:

            entrada = posicao["entrada"]
            stop_atual = posicao["stop"]
            alvo = posicao["alvo"]

            melhor_preco = max(
                posicao["melhor_preco"],
                maxima
            )

            posicao["melhor_preco"] = melhor_preco

            lucro_maximo = melhor_preco - entrada

            # BREAK EVEN / BREAK LOCK DESATIVADOS
            if (
                USAR_BREAK_EVEN and
                lucro_maximo >= break_even
            ):

                protecao = entrada

                if USAR_BREAK_LOCK:
                    protecao = entrada + break_lock

                stop_atual = max(
                    stop_atual,
                    protecao
                )

            # TRAILING ATR CONTINUA ATIVO
            if lucro_maximo >= trailing_inicio:

                stop_trailing = (
                    melhor_preco -
                    atual["atr"] * config["trailing_atr"]
                )

                stop_atual = max(
                    stop_atual,
                    stop_trailing
                )

            posicao["stop"] = stop_atual

            preco_saida = None
            motivo = None

            # Criterio conservador: stop primeiro
            if minima <= stop_atual:

                preco_saida = min(
                    abertura,
                    stop_atual
                )

                motivo = "STOP / TRAILING"

            elif maxima >= alvo:

                preco_saida = max(
                    abertura,
                    alvo
                )

                motivo = "TAKE PROFIT"

            elif hora >= fim:

                preco_saida = fechamento
                motivo = "FIM DA SESSAO"

            if preco_saida is not None:

                preco_saida -= SLIPPAGE * unidade

                pontos = (
                    preco_saida - entrada
                ) / unidade

                pontos -= CUSTO_OPERACAO

                resultado_diario += pontos

                if pontos < 0:
                    perdas_consecutivas += 1
                else:
                    perdas_consecutivas = 0

                trades.append({
                    "ativo": ticker,
                    "data_entrada": posicao["data"],
                    "data_saida": timestamp,
                    "entrada": entrada,
                    "saida": preco_saida,
                    "resultado": pontos,
                    "motivo": motivo,
                })

                posicao = None

        # -----------------------------------------------
        # ENTRADA LONG
        # -----------------------------------------------

        if posicao is not None:
            continue

        if not (inicio <= hora < fim):
            continue

        if operacoes_dia >= MAX_OPERACOES_DIA:
            continue

        if perdas_consecutivas >= MAX_PERDAS_CONSECUTIVAS:
            continue

        if resultado_diario <= -perda_diaria:
            continue

        # WAVE
        filtro_wave = (
            atual["wave_cross_up"] and
            fechamento > atual["wave_high"]
        )

        # RSI MAXIMO 68
        filtro_rsi = atual["rsi"] <= RSI_MAX_COMPRA

        # MACD POSITIVO
        filtro_macd = atual["macd"] > 0

        # DISTANCIA EMA 80 DESATIVADA
        filtro_distancia = (
            not USAR_DISTANCIA_EMA or
            abs(fechamento - atual["ema80"]) <= distancia_ema
        )

        # FILTRO LATERAL
        filtro_lateral = atual["cross_count"] < 4

        # ADX E DIRECAO
        filtro_adx = (
            atual["adx"] >= 15 and
            atual["plus_di"] > atual["minus_di"]
        )

        sinal_compra = all([
            filtro_wave,
            filtro_rsi,
            filtro_macd,
            filtro_distancia,
            filtro_lateral,
            filtro_adx,
        ])

        if sinal_compra:

            entrada = fechamento + SLIPPAGE * unidade

            posicao = {
                "entrada": entrada,
                "stop": entrada - stop_dist,
                "alvo": entrada + alvo_dist,
                "melhor_preco": entrada,
                "data": timestamp,
            }

            operacoes_dia += 1

    # Fecha posicao restante no ultimo candle
    if posicao is not None:

        ultimo = dados.iloc[-1]
        timestamp = dados.index[-1]

        preco_saida = (
            float(ultimo["close"]) -
            SLIPPAGE * unidade
        )

        pontos = (
            preco_saida - posicao["entrada"]
        ) / unidade - CUSTO_OPERACAO

        trades.append({
            "ativo": ticker,
            "data_entrada": posicao["data"],
            "data_saida": timestamp,
            "entrada": posicao["entrada"],
            "saida": preco_saida,
            "resultado": pontos,
            "motivo": "FIM DOS DADOS",
        })

    return pd.DataFrame(trades)


# ============================================================
# 6. METRICAS
# ============================================================

def calcular_metricas(trades, ticker):

    if trades.empty:

        return {
            "Ativo": ticker,
            "Operacoes": 0,
            "Vitorias": 0,
            "Derrotas": 0,
            "Acerto (%)": 0,
            "Resultado": 0,
            "Profit Factor": 0,
            "Media por trade": 0,
        }

    resultados = trades["resultado"]

    ganhos = resultados[resultados > 0]
    perdas = resultados[resultados < 0]

    total_ganhos = ganhos.sum()
    total_perdas = abs(perdas.sum())

    if total_perdas > 0:
        profit_factor = total_ganhos / total_perdas
    elif total_ganhos > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0

    return {
        "Ativo": ticker,
        "Operacoes": len(trades),
        "Vitorias": len(ganhos),
        "Derrotas": len(perdas),
        "Acerto (%)": round(
            len(ganhos) / len(trades) * 100, 2
        ),
        "Resultado": round(resultados.sum(), 2),
        "Profit Factor": round(profit_factor, 2),
        "Media por trade": round(resultados.mean(), 2),
    }


# ============================================================
# 7. EXECUCAO
# ============================================================

def main():

    todos_trades = []
    relatorios = []

    print("=" * 70)
    print("BACKTEST WAVE 34 + EMA 80")
    print("5 MINUTOS | SOMENTE COMPRAS | RSI MAXIMO 68")
    print("=" * 70)

    for ticker, config in ATIVOS.items():

        print("\n" + "-" * 55)
        print(f"TESTANDO: {config['nome']} ({ticker})")
        print("-" * 55)

        try:

            trades = executar_backtest(ticker, config)

            if not trades.empty:
                todos_trades.append(trades)

            metricas = calcular_metricas(
                trades,
                ticker
            )

            relatorios.append(metricas)

            print(f"Operacoes: {metricas['Operacoes']}")
            print(f"Acerto: {metricas['Acerto (%)']}%")
            print(f"Resultado: {metricas['Resultado']}")
            print(f"Profit Factor: {metricas['Profit Factor']}")

        except Exception as erro:

            print(f"ERRO EM {ticker}: {erro}")

            relatorios.append({
                "Ativo": ticker,
                "Operacoes": 0,
                "Vitorias": 0,
                "Derrotas": 0,
                "Acerto (%)": 0,
                "Resultado": 0,
                "Profit Factor": 0,
                "Media por trade": 0,
                "Erro": str(erro),
            })

    relatorio_df = pd.DataFrame(relatorios)

    print("\n")
    print("=" * 85)
    print("RESULTADO FINAL POR ATIVO")
    print("=" * 85)

    print(relatorio_df.to_string(index=False))

    relatorio_df.to_csv(
        "relatorio_backtest.csv",
        index=False,
        encoding="utf-8-sig"
    )

    if todos_trades:

        trades_df = pd.concat(
            todos_trades,
            ignore_index=True
        )

        trades_df.to_csv(
            "operacoes_backtest.csv",
            index=False,
            encoding="utf-8-sig"
        )

        print("\nArquivos gerados:")
        print("1. relatorio_backtest.csv")
        print("2. operacoes_backtest.csv")

    else:
        print("\nNenhuma operacao encontrada.")

    print("\nBacktest finalizado.")


if __name__ == "__main__":
    main()
