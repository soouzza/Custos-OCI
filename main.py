import oci
import pandas as pd
from datetime import datetime, timedelta
import os


# Granularidade pode ser 'HOURLY', 'DAILY', 'MONTHLY'
def DetalheUso(compartment, startTime, endTime, granularidade):
    request = oci.usage_api.models.RequestSummarizedUsagesDetails(
        tenant_id=compartment,
        time_usage_started=startTime,
        time_usage_ended=endTime,
        granularity=granularidade,
    )

    response = usage_client.request_summarized_usages(request).data.items
    return response


def MontaDF(dados):
    data = []
    for item in dados:
        data.append(
            {
                "computed_amount": item.computed_amount,
                "time_usage_started": item.time_usage_started,
                "time_usage_ended": item.time_usage_ended,
            }
        )

    return pd.DataFrame(data)


def preparaPeriodos(inicio, fim):
    blocos = []

    while inicio < fim:
        # Calcula a data de fim potencial do bloco
        data_fim_potencial = min(inicio + timedelta(days=366), fim)

        # Ajusta a data de fim para o último dia do mês
        ultimo_dia_mes_potencial = (
            data_fim_potencial.replace(day=28) + timedelta(days=4)
        ).replace(day=1) - timedelta(days=1)
        # Se o último dia do mês extrapolar os 366 dias, ajusta para o mês anterior
        if (ultimo_dia_mes_potencial - inicio).days > 366:
            data_fim = data_fim_potencial.replace(day=1) - timedelta(days=1)
        else:
            data_fim = ultimo_dia_mes_potencial

        blocos.append((inicio, data_fim))

        # Inicia o próximo bloco no dia seguinte ao fim do bloco atual
        inicio = data_fim + timedelta(days=1)

    return blocos


def carregar_config(diretorio):
    clientes = []

    for arquivo in os.listdir(diretorio):
        if arquivo.startswith("config_"):
            nome_modulo = arquivo
            clientes.append((nome_modulo))

    return clientes


def extraiConsumo(compartment_id, inicioContrato, fimContrato):
    # A API permite extração de blocos de até 366 dias, antes de buscar as informações, precisamos separar
    # as datas de início e fim de contrato em blocos de, no máximo 366 dias
    inicioContrato = datetime.strptime(inicio_contrato, "%Y-%m-%dT%H:%M:%SZ")
    fimContrato = datetime.strptime(fim_contrato, "%Y-%m-%dT%H:%M:%SZ")
    blocos = preparaPeriodos(inicioContrato, fimContrato)

    # extrai consumo mensal de cada bloco de datas
    dfConsumo = pd.DataFrame()
    for i, bloco in enumerate(blocos):
        response = DetalheUso(compartment_id, bloco[0], bloco[1], "MONTHLY")
        dfConsumoTemp = MontaDF(response)
        dfConsumo = pd.concat([dfConsumo, dfConsumoTemp])

    # organiza DF
    dfConsumo = dfConsumo.dropna(subset=["computed_amount"])
    dfConsumo = dfConsumo.sort_values(by="time_usage_started")

    return dfConsumo


def extraiDias(inicioContrato, fimContrato):
    # calcula dias utilizados do contrato
    inicioContrato = datetime.strptime(inicio_contrato, "%Y-%m-%dT%H:%M:%SZ")
    fimContrato = datetime.strptime(fim_contrato, "%Y-%m-%dT%H:%M:%SZ")
    dias = []

    fimPeriodoCalculo = datetime.now() - timedelta(days=1)
    diasPassados = (fimPeriodoCalculo - inicioContrato).days
    diasContrato = (fimContrato - inicioContrato).days
    dias.append((diasPassados, diasContrato))

    return dias


def extraiConsumoMedia(compartment_id):
    # para cálculo do forecast, extrai consumo diário com início em 2 meses atras até ontem
    start_time_calcForecast = (
        ((datetime.now() - timedelta(days=1)) - pd.DateOffset(months=2))
        .date()
        .strftime("%Y-%m-01T00:00:00Z")
    )
    end_time_calcForecast = (
        (datetime.now() - timedelta(days=1)).date().strftime("%Y-%m-01T00:00:00Z")
    )
    response = DetalheUso(
        compartment_id, start_time_calcForecast, end_time_calcForecast, "DAILY"
    )
    dfConsumoMedia = MontaDF(response)

    # organiza DF
    dfConsumoMedia = dfConsumoMedia.dropna(subset=["computed_amount"])
    dfConsumoMedia = dfConsumoMedia.sort_values(by="time_usage_started")

    return dfConsumoMedia


def extraiConsumoMediaDia(mediaConsumo):
    # monta DF com média de consumo por dia da semana
    dfMediaConsumo = mediaConsumo.copy()
    dfMediaConsumo["time_usage_started"] = pd.to_datetime(
        dfMediaConsumo["time_usage_started"]
    )
    dfMediaConsumo["dia_da_semana"] = dfMediaConsumo["time_usage_started"].dt.dayofweek
    dias_da_semana = {
        0: "Segunda",
        1: "Terça",
        2: "Quarta",
        3: "Quinta",
        4: "Sexta",
        5: "Sábado",
        6: "Domingo",
    }
    dfMediaConsumo["dia_da_semana"] = dfMediaConsumo["dia_da_semana"].map(
        dias_da_semana
    )
    dfForecastMedia = (
        dfMediaConsumo.groupby("dia_da_semana")["computed_amount"].mean().reset_index()
    )
    dias_ordenados = [
        "Domingo",
        "Segunda",
        "Terça",
        "Quarta",
        "Quinta",
        "Sexta",
        "Sábado",
    ]
    dfForecastMedia["dia_da_semana"] = pd.Categorical(
        dfForecastMedia["dia_da_semana"], categories=dias_ordenados, ordered=True
    )
    dfForecastMedia = dfForecastMedia.sort_values("dia_da_semana")

    return dfForecastMedia


def extraiForecastDiasSemana(fimContrato):
    # calcula quantos dias da semana faltam até o final do contrato
    data_inicial_forecast = (datetime.now()).strftime("%Y-%m-%dT00:00:00Z")
    data_final_forecast = fimContrato
    datas = pd.date_range(start=data_inicial_forecast, end=data_final_forecast)
    dias_da_semana = datas.strftime("%A")
    contagem_dias = dias_da_semana.value_counts().reindex(
        ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        fill_value=0,
    )
    df_dias_da_semana = pd.DataFrame(contagem_dias).reset_index()
    df_dias_da_semana.columns = ["dia_da_semana", "quantidade"]
    dias_traduzidos = {
        "Sunday": "Domingo",
        "Monday": "Segunda",
        "Tuesday": "Terça",
        "Wednesday": "Quarta",
        "Thursday": "Quinta",
        "Friday": "Sexta",
        "Saturday": "Sábado",
    }
    df_dias_da_semana["dia_da_semana"] = df_dias_da_semana["dia_da_semana"].map(
        dias_traduzidos
    )

    return df_dias_da_semana


def extraiForecast(ConsumoMediaDia, ForecastDiasSemana):
    # calcula forecast cruzando consumo médio dos últimos dois meses com os dias que faltam para término do contrato
    df_merged = pd.merge(ConsumoMediaDia, ForecastDiasSemana, on="dia_da_semana")
    dfForecast = pd.DataFrame(
        {
            "dia_da_semana": df_merged["dia_da_semana"],
            "consumo_total": df_merged["computed_amount"] * df_merged["quantidade"],
        }
    )

    return dfForecast


def estatisticasDiversas(valorCredito, inicioContrato, fimContrato, consumo, forecast):
    # estatísticas diversas
    diasContrato = extraiDias(inicioContrato, fimContrato)
    total_forecast = float(forecast["consumo_total"].sum())
    creditos = float(valorCredito)
    total_computed_amount = float(consumo["computed_amount"].sum())
    saldo_credito = creditos - total_computed_amount
    sobra_prevista = saldo_credito - total_forecast
    porcentagem_sobra = (sobra_prevista / creditos) * 100
    DadosCliente = []
    novoCliente = {
        "cliente": cliente,
        "creditoTotal": creditos,
        "consumo": total_computed_amount,
        "saldo": saldo_credito,
        "diaAtual": f"{diasContrato[0][0]} de {diasContrato[0][1]}",
        "diaFalta": diasContrato[0][1] - diasContrato[0][0],
        "forecast": total_forecast,
        "sobraPrevista": sobra_prevista,
        "percSobraPrev": f"{porcentagem_sobra:.2f}%",
    }
    DadosCliente.append(novoCliente)
    dfClientesEstatisticas = pd.DataFrame(DadosCliente)

    return dfClientesEstatisticas


def printCliente(cliente, consumo, consumoMedia, consumoForecast, estatisticas):
    # print dos dados:
    print(f"--------------------------------------------------------")
    print(f"Cliente: {cliente}")
    print(f"--------------------------------------------------------")

    print("Consumo mensal no período:")
    print(consumo)
    print(f"--------------------------------------------------------")

    print("Média de consumo diária, últimos 2 meses:")
    print(consumoMedia)
    print(f"--------------------------------------------------------")

    print("Forecast:")
    print(consumoForecast)
    print(f"--------------------------------------------------------")

    print(f"Crédito total: {estatisticas.loc[0,'creditoTotal']}")
    print(f"Consumo: {estatisticas.loc[0,'consumo']}")
    print(f"Saldo: {estatisticas.loc[0,'saldo']}")
    print(f"Dia {estatisticas.loc[0,'diaAtual']}")
    print(f"Faltam {estatisticas.loc[0,'diaFalta']} dias")
    print(f"Forecast: {estatisticas.loc[0,'forecast']}")
    print(f"Sobra prevista: {estatisticas.loc[0,'sobraPrevista']}")
    print(
        f"Previsto sobra de {estatisticas.loc[0,'percSobraPrev']} do contrato inicial"
    )


def printClientes(clientesConsumo, clientesForecast, clientesEstatisticas):
    # relatório de todos os clientes
    print(f"--------------------------------------------------------")
    print(f"Resumo de todos os clientes:")
    print(f"--------------------------------------------------------")
    print("Consumo:")
    print(clientesConsumo)

    print(f"--------------------------------------------------------")
    print("Forecast:")
    print(clientesForecast)

    print(f"--------------------------------------------------------")
    print("Estatísticas:")
    print(clientesEstatisticas)


if __name__ == "__main__":

    diretorio_config = "."
    clientes = carregar_config(diretorio_config)

    dfClientesConsumo = pd.DataFrame()
    dfClientesForecast = pd.DataFrame()
    dfClientesEstatisticas = pd.DataFrame()

    for i, cliente in enumerate(clientes):
        config = oci.config.from_file(file_location=cliente)
        if config["ignore"] == "true":
            continue
        usage_client = oci.usage_api.UsageapiClient(config)

        compartment_id = config["tenancy"]
        inicio_contrato = config["inicio_contrato"]
        fim_contrato = config["fim_contrato"]
        valor_creditos = config["credito"]
        cliente = config["cliente"]

        # inicia extração dos dados:
        dfConsumo = extraiConsumo(compartment_id, inicio_contrato, fim_contrato)
        dfConsumoMedia = extraiConsumoMedia(compartment_id)
        dfConsumoMediaDiasSemana = extraiConsumoMediaDia(dfConsumoMedia)
        dfForecastDiasSemana = extraiForecastDiasSemana(fim_contrato)
        dfForecast = extraiForecast(dfConsumoMediaDiasSemana, dfForecastDiasSemana)
        dfEstatisticas = estatisticasDiversas(
            valor_creditos, inicio_contrato, fim_contrato, dfConsumo, dfForecast
        )

        dfConsumoForecast = pd.merge(
            dfConsumoMediaDiasSemana,
            dfForecastDiasSemana,
            on="dia_da_semana",
            how="left",
        ).merge(dfForecast, on="dia_da_semana", how="left")

        # concatena dados dos diversos clientes em um DF
        dfConsumo["cliente"] = cliente
        dfConsumoForecast["cliente"] = cliente
        dfClientesConsumo = pd.concat([dfClientesConsumo, dfConsumo], ignore_index=True)
        dfClientesForecast = pd.concat(
            [dfClientesForecast, dfConsumoForecast], ignore_index=True
        )
        dfClientesEstatisticas = pd.concat(
            [dfClientesEstatisticas, dfEstatisticas], ignore_index=True
        )

        printCliente(
            cliente, dfConsumo, dfConsumoMedia, dfConsumoForecast, dfEstatisticas
        )

    printClientes(dfClientesConsumo, dfClientesForecast, dfClientesEstatisticas)
