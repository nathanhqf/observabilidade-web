from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from typing import Optional
import pymssql
import os
import json
import logging
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError
from dotenv import load_dotenv

# Contexto SSL permissivo para redes corporativas com proxy SSL
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

logger = logging.getLogger("observabilidade")
logging.basicConfig(level=logging.INFO)

load_dotenv()

SQL_SERVER = os.getenv("SQL_SERVER", "10.206.244.39")
SQL_PORT = int(os.getenv("SQL_PORT", "1433"))
SQL_DATABASE = os.getenv("SQL_DATABASE", "INFO_CENTRAL")
SQL_USER = os.getenv("SQL_USER")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")


def get_conn():
    return pymssql.connect(
        server=SQL_SERVER,
        port=SQL_PORT,
        database=SQL_DATABASE,
        user=SQL_USER,
        password=SQL_PASSWORD,
        charset="utf8",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        conn = get_conn()
        conn.close()
        print("Conexão SQL Server OK")
    except Exception as e:
        print(f"AVISO: Falha na conexão SQL Server: {e}")
    yield


app = FastAPI(title="Observabilidade Call Center", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/volume")
def api_volume():
    """Volume de chamadas por DDD - dados do dia mais recente."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            -- Calcular datas uma vez (sargable: sem CAST na coluna)
            DECLARE @MaxDate DATE = (
                SELECT MAX(CAST(conversationStart AS DATE))
                FROM genesys.ConversationDetails
                WHERE conversationStart IS NOT NULL
            );
            DECLARE @MaxDateNext DATE = DATEADD(DAY, 1, @MaxDate);
            DECLARE @PrevDate DATE = DATEADD(DAY, -1, @MaxDate);
            DECLARE @PrevDateNext DATE = @MaxDate;
            DECLARE @Prev7d DATE = DATEADD(DAY, -7, @MaxDate);
            DECLARE @Prev7dNext DATE = DATEADD(DAY, -6, @MaxDate);
            DECLARE @Now DATETIME = (
                SELECT MAX(conversationStart)
                FROM genesys.ConversationDetails
                WHERE conversationStart >= @MaxDate AND conversationStart < @MaxDateNext
            );

            WITH ddd_info AS (
                SELECT
                    CAST(CN AS INT) AS ddd,
                    MIN(UF_CN) AS uf,
                    MIN(UF_REGIAO) AS regiao,
                    MIN([Nome-UF_CN]) AS micro
                FROM controle.Municipios_DDD_IBGE
                WHERE CN IS NOT NULL
                GROUP BY CAST(CN AS INT)
            ),
            -- Volume hoje por DDD (TMA só de chamadas finalizadas)
            today_vol AS (
                SELECT
                    CAST(g.ddd AS INT) AS ddd,
                    COUNT(*) AS totalToday,
                    SUM(CASE WHEN g.conversationEnd IS NULL THEN 1 ELSE 0 END) AS ongoing,
                    AVG(CASE WHEN g.conversationEnd IS NOT NULL
                         THEN DATEDIFF(SECOND, g.conversationStart, g.conversationEnd)
                         ELSE NULL END) AS tma,
                    AVG(g.ivr_total_duration_seconds) AS avgIvr
                FROM genesys.ConversationDetails g
                WHERE g.conversationStart >= @MaxDate AND g.conversationStart < @MaxDateNext
                  AND g.ddd IS NOT NULL AND g.ddd != ''
                GROUP BY CAST(g.ddd AS INT)
            ),
            -- Volume ontem por DDD
            prev_vol AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS prevTotal
                FROM genesys.ConversationDetails
                WHERE conversationStart >= @PrevDate AND conversationStart < @PrevDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume 7 dias atrás por DDD
            prev7d_vol AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS prev7dTotal
                FROM genesys.ConversationDetails
                WHERE conversationStart >= @Prev7d AND conversationStart < @Prev7dNext
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume últimas 12h por DDD (hoje)
            vol_12h AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol12h
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(HOUR, -12, @Now)
                  AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume 12h equivalente ontem
            vol_12h_prev AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol12hPrev
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(HOUR, -12, DATEADD(DAY, -1, @Now))
                  AND conversationStart < DATEADD(DAY, -1, @Now)
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume última 1h por DDD
            vol_1h AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol1h
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(HOUR, -1, @Now)
                  AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume 1h equivalente ontem
            vol_1h_prev AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol1hPrev
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(HOUR, -1, DATEADD(DAY, -1, @Now))
                  AND conversationStart < DATEADD(DAY, -1, @Now)
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume últimos 30min por DDD
            vol_30m AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol30m
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(MINUTE, -30, @Now)
                  AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume 30min equivalente ontem
            vol_30m_prev AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol30mPrev
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(MINUTE, -30, DATEADD(DAY, -1, @Now))
                  AND conversationStart < DATEADD(DAY, -1, @Now)
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume últimos 15min por DDD
            vol_15m AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol15m
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(MINUTE, -15, @Now)
                  AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Volume 15min equivalente ontem
            vol_15m_prev AS (
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    COUNT(*) AS vol15mPrev
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(MINUTE, -15, DATEADD(DAY, -1, @Now))
                  AND conversationStart < DATEADD(DAY, -1, @Now)
                  AND ddd IS NOT NULL AND ddd != ''
                GROUP BY CAST(ddd AS INT)
            ),
            -- Data mais recente da TLV (pode estar defasada)
            tlv_max AS (
                SELECT MAX(CAST(Dt_Atendimento AS DATE)) AS tlvDate
                FROM tlv.Atendimentos_Genesys
                WHERE Dt_Atendimento IS NOT NULL
            ),
            -- Top motivo por DDD (usa data da TLV, não do Genesys)
            top_motivo AS (
                SELECT ddd, Grupo_Processo AS topMotivo, Tipo_Processo AS topTipo
                FROM (
                    SELECT
                        CAST(g.ddd AS INT) AS ddd,
                        a.Grupo_Processo,
                        a.Tipo_Processo,
                        ROW_NUMBER() OVER (PARTITION BY CAST(g.ddd AS INT) ORDER BY COUNT(*) DESC) AS rn
                    FROM genesys.ConversationDetails g
                    JOIN tlv.Atendimentos_Genesys a ON g.conversationId = a.Conversation_ID
                    CROSS JOIN tlv_max tm
                    WHERE a.Dt_Atendimento >= tm.tlvDate AND a.Dt_Atendimento < DATEADD(DAY, 1, tm.tlvDate)
                      AND a.Rank_Motivo_Principal = 1
                      AND g.ddd IS NOT NULL AND g.ddd != ''
                    GROUP BY CAST(g.ddd AS INT), a.Grupo_Processo, a.Tipo_Processo
                ) x WHERE rn = 1
            ),
            -- ACW por DDD (via TLV)
            acw_by_ddd AS (
                SELECT
                    CAST(g.ddd AS INT) AS ddd,
                    AVG(a.Duracao_Tabulacao) AS acw
                FROM tlv.Atendimentos_Genesys a
                JOIN genesys.ConversationDetails g ON g.conversationId = a.Conversation_ID
                WHERE g.conversationStart >= @PrevDate
                  AND a.Duracao_Tabulacao IS NOT NULL
                  AND g.ddd IS NOT NULL AND g.ddd != ''
                GROUP BY CAST(g.ddd AS INT)
            ),
            -- ACW global fallback
            acw_global AS (
                SELECT AVG(Duracao_Tabulacao) AS acw
                FROM tlv.Atendimentos_Genesys
                WHERE Dt_Atendimento >= @PrevDate
                  AND Duracao_Tabulacao IS NOT NULL
            )
            SELECT
                t.ddd,
                ISNULL(d.micro, '') AS micro,
                ISNULL(d.uf, '') AS uf,
                ISNULL(d.regiao, '') AS regiao,
                t.totalToday,
                t.ongoing,
                ISNULL(t.tma, 0) AS tma,
                ISNULL(t.avgIvr, 0) AS avgIvr,
                ISNULL(ad.acw, ISNULL(ag.acw, 0)) AS acw,
                -- var24h
                CASE
                    WHEN p.prevTotal IS NULL OR p.prevTotal = 0 THEN 0
                    ELSE ROUND(((CAST(t.totalToday AS FLOAT) / p.prevTotal) - 1) * 100, 0)
                END AS var24h,
                -- var7d
                CASE
                    WHEN p7.prev7dTotal IS NULL OR p7.prev7dTotal = 0 THEN 0
                    ELSE ROUND(((CAST(t.totalToday AS FLOAT) / p7.prev7dTotal) - 1) * 100, 0)
                END AS var7d,
                -- var12h
                CASE
                    WHEN v12p.vol12hPrev IS NULL OR v12p.vol12hPrev = 0 THEN 0
                    ELSE ROUND(((CAST(ISNULL(v12.vol12h, 0) AS FLOAT) / v12p.vol12hPrev) - 1) * 100, 0)
                END AS var12h,
                -- var1h
                CASE
                    WHEN v1p.vol1hPrev IS NULL OR v1p.vol1hPrev = 0 THEN 0
                    ELSE ROUND(((CAST(ISNULL(v1.vol1h, 0) AS FLOAT) / v1p.vol1hPrev) - 1) * 100, 0)
                END AS var1h,
                -- var30m
                CASE
                    WHEN v30p.vol30mPrev IS NULL OR v30p.vol30mPrev = 0 THEN 0
                    ELSE ROUND(((CAST(ISNULL(v30.vol30m, 0) AS FLOAT) / v30p.vol30mPrev) - 1) * 100, 0)
                END AS var30m,
                -- var15m
                CASE
                    WHEN v15p.vol15mPrev IS NULL OR v15p.vol15mPrev = 0 THEN 0
                    ELSE ROUND(((CAST(ISNULL(v15.vol15m, 0) AS FLOAT) / v15p.vol15mPrev) - 1) * 100, 0)
                END AS var15m,
                -- volumes absolutos das janelas curtas (prev) para filtro de falso positivo
                ISNULL(v15p.vol15mPrev, 0) AS vol15mPrev,
                ISNULL(v30p.vol30mPrev, 0) AS vol30mPrev,
                ISNULL(v1p.vol1hPrev, 0) AS vol1hPrev,
                ISNULL(tm.topMotivo, '') AS topMotivo,
                ISNULL(tm.topTipo, '') AS topTipo
            FROM today_vol t
            LEFT JOIN ddd_info d ON d.ddd = t.ddd
            LEFT JOIN prev_vol p ON p.ddd = t.ddd
            LEFT JOIN prev7d_vol p7 ON p7.ddd = t.ddd
            LEFT JOIN vol_12h v12 ON v12.ddd = t.ddd
            LEFT JOIN vol_12h_prev v12p ON v12p.ddd = t.ddd
            LEFT JOIN vol_1h v1 ON v1.ddd = t.ddd
            LEFT JOIN vol_1h_prev v1p ON v1p.ddd = t.ddd
            LEFT JOIN vol_30m v30 ON v30.ddd = t.ddd
            LEFT JOIN vol_30m_prev v30p ON v30p.ddd = t.ddd
            LEFT JOIN vol_15m v15 ON v15.ddd = t.ddd
            LEFT JOIN vol_15m_prev v15p ON v15p.ddd = t.ddd
            LEFT JOIN top_motivo tm ON tm.ddd = t.ddd
            LEFT JOIN acw_by_ddd ad ON ad.ddd = t.ddd
            CROSS JOIN acw_global ag
            WHERE ISNULL(d.regiao, '') != ''
            ORDER BY t.totalToday DESC
        """)
        rows = cursor.fetchall()

        # Buscar hourly separadamente e montar array
        cursor.execute("""
            DECLARE @MaxDate DATE = (
                SELECT MAX(CAST(conversationStart AS DATE))
                FROM genesys.ConversationDetails
                WHERE conversationStart IS NOT NULL
            );
            SELECT
                CAST(ddd AS INT) AS ddd,
                DATEPART(HOUR, conversationStart) AS hr,
                COUNT(*) AS cnt
            FROM genesys.ConversationDetails
            WHERE conversationStart >= @MaxDate AND conversationStart < DATEADD(DAY, 1, @MaxDate)
              AND ddd IS NOT NULL AND ddd != ''
            GROUP BY CAST(ddd AS INT), DATEPART(HOUR, conversationStart)
        """)
        hourly_rows = cursor.fetchall()
        hourly_map = {}
        for h in hourly_rows:
            ddd = h["ddd"]
            if ddd not in hourly_map:
                hourly_map[ddd] = [0] * 24
            hourly_map[ddd][h["hr"]] = h["cnt"]

        # Buscar data de referência (Genesys) e data da TLV
        cursor.execute("""
            SELECT
                MAX(CAST(conversationStart AS DATE)) AS max_genesys
            FROM genesys.ConversationDetails
            WHERE conversationStart IS NOT NULL
        """)
        genesys_row = cursor.fetchone()
        genesys_date = str(genesys_row["max_genesys"]) if genesys_row and genesys_row["max_genesys"] else None

        cursor.execute("""
            SELECT MAX(CAST(Dt_Atendimento AS DATE)) AS max_tlv
            FROM tlv.Atendimentos_Genesys
            WHERE Dt_Atendimento IS NOT NULL
        """)
        tlv_row = cursor.fetchone()
        tlv_date = str(tlv_row["max_tlv"]) if tlv_row and tlv_row["max_tlv"] else None

        result = []
        for r in rows:
            ddd = r["ddd"]
            v15 = int(r["var15m"] or 0)
            v30 = int(r["var30m"] or 0)
            v1h = int(r["var1h"] or 0)
            v12h = int(r["var12h"] or 0)
            v24h = int(r["var24h"] or 0)
            v7d = int(r["var7d"] or 0)
            # Volumes base das janelas curtas (ontem na mesma janela)
            bp15 = int(r["vol15mPrev"] or 0)
            bp30 = int(r["vol30mPrev"] or 0)
            bp1h = int(r["vol1hPrev"] or 0)
            result.append({
                "ddd": ddd,
                "micro": r["micro"],
                "uf": r["uf"],
                "regiao": r["regiao"],
                "totalToday": r["totalToday"],
                "hourly": hourly_map.get(ddd, [0] * 24),
                "ongoing": r["ongoing"] or 0,
                "var15": v15,
                "var30": v30,
                "var1h": v1h,
                "var12h": v12h,
                "var24h": v24h,
                "var7d": v7d,
                "severity": _severity(v15, v30, v1h, v12h, v24h, v7d,
                                      r["totalToday"], bp15, bp30, bp1h),
                "tma": int(r["tma"] or 0),
                "avgIvr": int(r["avgIvr"] or 0),
                "acw": int(r["acw"] or 0),
                "topMotivo": r["topMotivo"],
                "topTipo": r["topTipo"],
            })

        return {
            "data": result,
            "meta": {
                "tlvDate": tlv_date,
                "dataRef": genesys_date,
            }
        }
    finally:
        conn.close()


@app.get("/api/motivos")
def api_motivos(ddds: Optional[str] = Query(None, description="Comma-separated DDD list to filter")):
    """Distribuição de motivos de atendimento, opcionalmente filtrada por DDDs."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        # Parse and validate DDDs
        ddd_filter = None
        if ddds:
            try:
                ddd_filter = [int(d.strip()) for d in ddds.split(",") if d.strip()]
            except ValueError:
                ddd_filter = None

        if ddd_filter:
            # Filtered query: JOIN with Genesys to filter by DDD
            # ddd é varchar na ConversationDetails — passar como string para sargability
            ddd_strs = [str(d) for d in ddd_filter]
            placeholders = ",".join(["%s"] * len(ddd_strs))
            cursor.execute(f"""
                DECLARE @MaxDate DATE = (
                    SELECT MAX(CAST(Dt_Atendimento AS DATE))
                    FROM tlv.Atendimentos_Genesys
                    WHERE Dt_Atendimento IS NOT NULL
                );
                SELECT
                    a.Classe_Processo AS classe,
                    ISNULL(a.Grupo_Processo, '') AS grupo,
                    ISNULL(a.Tipo_Processo, '') AS tipo,
                    COUNT(*) AS qtd,
                    AVG(a.Duracao_Interacao + ISNULL(a.Duracao_Tabulacao, 0)) AS tma
                FROM tlv.Atendimentos_Genesys a
                JOIN genesys.ConversationDetails g ON g.conversationId = a.Conversation_ID
                WHERE a.Dt_Atendimento >= @MaxDate AND a.Dt_Atendimento < DATEADD(DAY, 1, @MaxDate)
                  AND a.Rank_Motivo_Principal = 1
                  AND a.Classe_Processo IS NOT NULL
                  AND g.ddd IN ({placeholders})
                GROUP BY a.Classe_Processo, a.Grupo_Processo, a.Tipo_Processo
                ORDER BY a.Classe_Processo, COUNT(*) DESC
            """, tuple(ddd_strs))
        else:
            # Unfiltered query: all DDDs
            cursor.execute("""
                DECLARE @MaxDate DATE = (
                    SELECT MAX(CAST(Dt_Atendimento AS DATE))
                    FROM tlv.Atendimentos_Genesys
                    WHERE Dt_Atendimento IS NOT NULL
                );
                SELECT
                    a.Classe_Processo AS classe,
                    ISNULL(a.Grupo_Processo, '') AS grupo,
                    ISNULL(a.Tipo_Processo, '') AS tipo,
                    COUNT(*) AS qtd,
                    AVG(a.Duracao_Interacao + ISNULL(a.Duracao_Tabulacao, 0)) AS tma
                FROM tlv.Atendimentos_Genesys a
                WHERE a.Dt_Atendimento >= @MaxDate AND a.Dt_Atendimento < DATEADD(DAY, 1, @MaxDate)
                  AND a.Rank_Motivo_Principal = 1
                  AND a.Classe_Processo IS NOT NULL
                GROUP BY a.Classe_Processo, a.Grupo_Processo, a.Tipo_Processo
                ORDER BY a.Classe_Processo, COUNT(*) DESC
            """)
        rows = cursor.fetchall()
        tree = {}
        for r in rows:
            cl = r["classe"]
            gr = r["grupo"] or "(Sem Grupo)"
            tp = r["tipo"] or "(Sem Tipo)"
            if cl not in tree:
                tree[cl] = {"qtd": 0, "tma_sum": 0, "tma_cnt": 0, "grupos": {}}
            tree[cl]["qtd"] += r["qtd"]
            tree[cl]["tma_sum"] += (r["tma"] or 0) * r["qtd"]
            tree[cl]["tma_cnt"] += r["qtd"]
            if gr not in tree[cl]["grupos"]:
                tree[cl]["grupos"][gr] = {"qtd": 0, "tma_sum": 0, "tma_cnt": 0, "tipos": {}}
            tree[cl]["grupos"][gr]["qtd"] += r["qtd"]
            tree[cl]["grupos"][gr]["tma_sum"] += (r["tma"] or 0) * r["qtd"]
            tree[cl]["grupos"][gr]["tma_cnt"] += r["qtd"]
            tree[cl]["grupos"][gr]["tipos"][tp] = {
                "qtd": r["qtd"],
                "tma": r["tma"] or 0,
            }

        result = []
        for cl, ci in sorted(tree.items(), key=lambda x: -x[1]["qtd"]):
            classe_obj = {
                "classe": cl,
                "qtd": ci["qtd"],
                "tma": round(ci["tma_sum"] / ci["tma_cnt"]) if ci["tma_cnt"] else 0,
                "grupos": [],
            }
            for gr, gi in sorted(ci["grupos"].items(), key=lambda x: -x[1]["qtd"]):
                grupo_obj = {
                    "grupo": gr,
                    "qtd": gi["qtd"],
                    "tma": round(gi["tma_sum"] / gi["tma_cnt"]) if gi["tma_cnt"] else 0,
                    "tipos": [],
                }
                for tp, ti in sorted(gi["tipos"].items(), key=lambda x: -x[1]["qtd"]):
                    grupo_obj["tipos"].append({
                        "tipo": tp,
                        "qtd": ti["qtd"],
                        "tma": ti["tma"],
                    })
                classe_obj["grupos"].append(grupo_obj)
            result.append(classe_obj)
        return result
    finally:
        conn.close()


@app.get("/api/municipios")
def api_municipios():
    """Municípios agrupados por DDD."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT
                CAST(CN AS INT) AS ddd,
                MIN(UF_CN) AS uf,
                NO_MUNICIPIO_UF AS municipio
            FROM controle.Municipios_DDD_IBGE
            WHERE CN IS NOT NULL AND NO_MUNICIPIO_UF IS NOT NULL
            GROUP BY CAST(CN AS INT), NO_MUNICIPIO_UF
            ORDER BY CAST(CN AS INT), NO_MUNICIPIO_UF
        """)
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            ddd = str(r["ddd"])
            if ddd not in result:
                result[ddd] = {"u": r["uf"], "m": []}
            result[ddd]["m"].append(r["municipio"])
        return result
    finally:
        conn.close()


@app.get("/api/agentes")
def api_agentes():
    """Resumo de agentes por grupo de operação."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT
                ISNULL(c.name, 'Sem Grupo') AS grupo_operacao,
                COUNT(*) AS total,
                SUM(CASE WHEN a.STATUS_PERFIL = 'Ativo' THEN 1 ELSE 0 END) AS ativos
            FROM dotacao.perfil a
            LEFT JOIN sgdot.operations b ON a.operacao = b.name
            LEFT JOIN sgdot.operations_groups c ON c.id = b.group_id
            WHERE a.cargo_atual IN ('atendente', 'assistente')
              AND a.DT_DESLIGAMENTO IS NULL
            GROUP BY c.name
            ORDER BY COUNT(*) DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


_WEATHER_CODES = {
    0: "Céu limpo", 1: "Parcialmente nublado", 2: "Parcialmente nublado",
    3: "Nublado", 45: "Nevoeiro", 48: "Nevoeiro gelado",
    51: "Garoa leve", 53: "Garoa", 55: "Garoa forte",
    61: "Chuva leve", 63: "Chuva moderada", 65: "Chuva forte",
    71: "Neve leve", 73: "Neve", 75: "Neve forte",
    80: "Pancadas leves", 81: "Pancadas moderadas", 82: "Pancadas fortes",
    85: "Neve em pancadas", 86: "Neve forte em pancadas",
    95: "Tempestade", 96: "Tempestade c/ granizo", 99: "Tempestade c/ granizo forte",
}

_WEATHER_CITIES = [
    # Sudeste
    ("São Paulo", -23.55, -46.63), ("Rio de Janeiro", -22.91, -43.17),
    ("Belo Horizonte", -19.92, -43.94), ("Vitória", -20.32, -40.34),
    # Sul
    ("Porto Alegre", -30.03, -51.23), ("Florianópolis", -27.59, -48.55),
    ("Curitiba", -25.43, -49.27),
    # Centro-Oeste
    ("Brasília", -15.79, -47.88), ("Goiânia", -16.68, -49.25),
    ("Cuiabá", -15.60, -56.10), ("Campo Grande", -20.47, -54.62),
    # Nordeste
    ("Salvador", -12.97, -38.51), ("Recife", -8.05, -34.87),
    ("Fortaleza", -3.72, -38.54), ("São Luís", -2.53, -44.28),
    ("Natal", -5.79, -35.21), ("João Pessoa", -7.12, -34.86),
    ("Maceió", -9.67, -35.74), ("Aracaju", -10.91, -37.07),
    ("Teresina", -5.09, -42.80),
    # Norte
    ("Manaus", -3.12, -60.02), ("Belém", -1.46, -48.50),
    ("Porto Velho", -8.76, -63.90), ("Macapá", -2.51, -44.28),
    ("Rio Branco", -9.97, -67.81), ("Boa Vista", 2.82, -60.67),
    ("Palmas", -10.18, -48.33),
]


def _fetch_url(url: str, timeout: int = 8) -> bytes:
    """Fetch URL usando stdlib (sem dependência de requests)."""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    kwargs = {"timeout": timeout}
    if url.startswith("https"):
        kwargs["context"] = _ssl_ctx
    with urlopen(req, **kwargs) as resp:
        return resp.read()


_NEWS_URL = (
    "http://news.google.com/rss/search"
    "?q=chuva+OR+enchente+OR+tempestade+OR+alagamento+OR+vendaval"
    "+OR+deslizamento+OR+inundacao+OR+ciclone+OR+seca+OR+queimada+brasil"
    "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
)


@app.get("/api/headlines")
def api_headlines():
    """Headlines de clima/tempo para o ticker."""
    headlines = []
    weather = []

    # 1. Google News RSS — notícias de clima/desastres no Brasil
    try:
        raw = _fetch_url(_NEWS_URL)
        root = ET.fromstring(raw)
        for item in root.findall(".//item")[:20]:
            title_el = item.find("title")
            pub_el = item.find("pubDate")
            if title_el is not None and title_el.text:
                headlines.append({
                    "text": title_el.text.strip(),
                    "date": pub_el.text.strip() if pub_el is not None else "",
                })
    except Exception as e:
        print(f"[HEADLINES] News fetch error: {type(e).__name__}: {e}")

    # 2. Open-Meteo — clima atual das capitais de cada região
    try:
        lats = ",".join(str(c[1]) for c in _WEATHER_CITIES)
        lons = ",".join(str(c[2]) for c in _WEATHER_CITIES)
        raw = _fetch_url(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lats}&longitude={lons}"
            f"&current_weather=true&timezone=America/Sao_Paulo"
        )
        data = json.loads(raw)
        items = data if isinstance(data, list) else [data]
        for i, d in enumerate(items):
            cw = d.get("current_weather", {})
            uf = _WEATHER_CITIES[i][0] if i < len(_WEATHER_CITIES) else "?"
            code = cw.get("weathercode", 0)
            weather.append({
                "uf": uf,
                "temp": cw.get("temperature"),
                "wind": cw.get("windspeed"),
                "desc": _WEATHER_CODES.get(code, f"Código {code}"),
                "code": code,
            })
    except Exception as e:
        print(f"[HEADLINES] Weather fetch error: {type(e).__name__}: {e}")

    return {"news": headlines, "weather": weather}


def _severity(v15: int, v30: int, v1h: int, v12h: int, v24h: int, v7d: int,
              total: int, bp15: int = 0, bp30: int = 0, bp1h: int = 0) -> str:
    """Calcula severidade considerando todas as janelas temporais e volume mínimo.

    Janelas curtas com volume base (ontem) menor que 5 chamadas são ignoradas
    para evitar falsos positivos por volatilidade estatística (ex: 1→7 = +600%).
    """
    # DDDs com volume diário muito baixo não devem ser críticos
    if total < 10:
        return "normal"
    # Ignorar variações de janelas curtas com base < 5 chamadas ontem
    MIN_BASE = 5
    eff_v15 = v15 if bp15 >= MIN_BASE else 0
    eff_v30 = v30 if bp30 >= MIN_BASE else 0
    eff_v1h = v1h if bp1h >= MIN_BASE else 0
    mx_short = max(abs(eff_v15), abs(eff_v30), abs(eff_v1h))
    mx_long = max(abs(v12h), abs(v24h), abs(v7d))
    mx = max(mx_short, mx_long)
    if mx_short > 150 or mx_long > 80:
        return "critical"
    if mx_short > 80 or mx_long > 50:
        return "high"
    if mx > 30:
        return "medium"
    if mx > 10:
        return "low"
    return "normal"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)
