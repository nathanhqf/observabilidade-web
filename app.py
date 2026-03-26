from fastapi import FastAPI, Query, Request, Response, Depends, HTTPException, Form, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from contextlib import asynccontextmanager
from typing import Optional
import pymssql
import os
import json
import logging
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.request import urlopen, Request as UrlRequest
from urllib.error import URLError
from collections import defaultdict
from statistics import median
from dotenv import load_dotenv
from auth import hash_password, verify_password, create_session_token, SESSION_TTL_HOURS

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
    # Limpar sessões expiradas (ignora se tabela não existe ainda)
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conexreport.sessions WHERE expires_at < GETDATE()")
        conn.commit()
        conn.close()
        print("Sessões expiradas limpas")
    except Exception:
        pass
    yield


app = FastAPI(title="ConexReport - Observabilidade Call Center", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# Auth helpers (session/user validation)
# ---------------------------------------------------------------------------

def _get_current_user(request: Request) -> Optional[dict]:
    """Retorna user dict ou None se não autenticado."""
    token = request.cookies.get("session_token")
    if not token:
        return None
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT u.id, u.email, u.display_name, u.role, u.is_active
            FROM conexreport.sessions s
            JOIN conexreport.users u ON u.id = s.user_id
            WHERE s.token = %s AND s.expires_at > GETDATE()
        """, (token,))
        user = cursor.fetchone()
        if not user or not user["is_active"] or user["role"] == "pending":
            return None
        return user
    finally:
        conn.close()


def require_login(request: Request) -> dict:
    """Dependency: requer sessão válida."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


def require_admin(request: Request) -> dict:
    """Dependency: requer sessão válida + role admin."""
    user = require_login(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user


# ---------------------------------------------------------------------------
# Páginas públicas
# ---------------------------------------------------------------------------

@app.get("/")
async def landing_page():
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login")
async def login_page():
    return FileResponse("static/login.html")


@app.get("/signup")
async def signup_page():
    return FileResponse("static/signup.html")


@app.get("/dashboard")
async def dashboard_home(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse(url="/login?error=expired", status_code=303)
    return FileResponse("static/home.html")


@app.get("/dashboard/observabilidade")
async def dashboard_observabilidade(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse(url="/login?error=expired", status_code=303)
    return FileResponse("static/index.html")


@app.get("/admin")
async def admin_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse(url="/login?error=expired", status_code=303)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard", status_code=303)
    return FileResponse("static/admin.html")


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/login")
def auth_login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute(
            "SELECT id, password_hash, role, is_active, display_name "
            "FROM conexreport.users WHERE email = %s",
            (email.lower().strip(),)
        )
        user = cursor.fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return RedirectResponse(url="/login?error=credentials", status_code=303)

        if not user["is_active"]:
            return RedirectResponse(url="/login?error=inactive", status_code=303)

        if user["role"] == "pending":
            return RedirectResponse(url="/login?error=pending", status_code=303)

        # Criar sessão
        token = create_session_token()
        expires = datetime.now() + timedelta(hours=SESSION_TTL_HOURS)
        cursor.execute("""
            INSERT INTO conexreport.sessions (token, user_id, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            token, user["id"], expires,
            request.client.host if request.client else None,
            (request.headers.get("user-agent") or "")[:512],
        ))
        cursor.execute("UPDATE conexreport.users SET last_login = GETDATE() WHERE id = %s", (user["id"],))
        conn.commit()

        resp = RedirectResponse(url="/dashboard", status_code=303)
        resp.set_cookie(
            key="session_token", value=token,
            httponly=True, samesite="lax",
            max_age=SESSION_TTL_HOURS * 3600,
        )
        return resp
    finally:
        conn.close()


@app.post("/auth/signup")
def auth_signup(
    display_name: str = Body(..., embed=True),
    email: str = Body(..., embed=True),
    password: str = Body(..., embed=True),
):
    """Cria conta com role 'pending'."""
    display_name = display_name.strip()
    email = email.strip().lower()

    if not display_name or not email or len(password) < 8:
        return JSONResponse({"ok": False, "detail": "Preencha todos os campos. Senha mínima: 8 caracteres."})

    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        # Verificar se email já existe
        cursor.execute("SELECT id FROM conexreport.users WHERE email = %s", (email,))
        if cursor.fetchone():
            return JSONResponse({"ok": False, "detail": "Este email já está cadastrado."})

        pw_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO conexreport.users (email, display_name, password_hash, role)
            VALUES (%s, %s, %s, 'pending')
        """, (email, display_name, pw_hash))
        conn.commit()
        return JSONResponse({"ok": True})
    finally:
        conn.close()


@app.post("/auth/logout")
def auth_logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        try:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conexreport.sessions WHERE token = %s", (token,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session_token")
    return resp


@app.get("/api/me")
def api_me(user: dict = Depends(require_login)):
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


# ---------------------------------------------------------------------------
# Admin CRUD endpoints
# ---------------------------------------------------------------------------

@app.get("/api/admin/users")
def api_admin_users(user: dict = Depends(require_admin)):
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT id, email, display_name, role, is_active,
                   created_at, updated_at, last_login, approved_by
            FROM conexreport.users
            ORDER BY
                CASE role WHEN 'pending' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
                created_at DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


@app.put("/api/admin/users/{user_id}")
def api_admin_update_user(user_id: int, body: dict = Body(...), user: dict = Depends(require_admin)):
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        # Verificar se user existe
        cursor.execute("SELECT id, role FROM conexreport.users WHERE id = %s", (user_id,))
        target = cursor.fetchone()
        if not target:
            return JSONResponse({"ok": False, "detail": "Usuário não encontrado."}, status_code=404)

        sets = []
        params = []

        if "role" in body and body["role"] in ("pending", "viewer", "admin"):
            sets.append("role = %s")
            params.append(body["role"])
            if body["role"] in ("viewer", "admin") and target["role"] == "pending":
                sets.append("approved_by = %s")
                params.append(user["id"])

        if "is_active" in body:
            sets.append("is_active = %s")
            params.append(1 if body["is_active"] else 0)

        if not sets:
            return JSONResponse({"ok": False, "detail": "Nenhum campo para atualizar."})

        sets.append("updated_at = GETDATE()")
        params.append(user_id)

        cursor.execute(
            f"UPDATE conexreport.users SET {', '.join(sets)} WHERE id = %s",
            tuple(params)
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/admin/users/{user_id}")
def api_admin_delete_user(user_id: int, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        return JSONResponse({"ok": False, "detail": "Você não pode excluir a si mesmo."}, status_code=400)
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM conexreport.users WHERE id = %s", (user_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/volume")
def api_volume(user: dict = Depends(require_login)):
    """Volume de chamadas por DDD - dados do dia mais recente."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        # Query principal: dados de hoje + var7d + janelas de hoje (sem medianas)
        cursor.execute("""
            DECLARE @MaxDate DATE = (
                SELECT MAX(CAST(conversationStart AS DATE))
                FROM genesys.ConversationDetails
                WHERE conversationStart IS NOT NULL
            );
            DECLARE @MaxDateNext DATE = DATEADD(DAY, 1, @MaxDate);
            DECLARE @PrevDate DATE = DATEADD(DAY, -1, @MaxDate);
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
                  AND g.acd_participantNames IS NOT NULL AND g.acd_participantNames != ''
                GROUP BY CAST(g.ddd AS INT)
            ),
            prev7d_vol AS (
                SELECT CAST(ddd AS INT) AS ddd, COUNT(*) AS prev7dTotal
                FROM genesys.ConversationDetails
                WHERE conversationStart >= @Prev7d AND conversationStart < @Prev7dNext
                  AND ddd IS NOT NULL AND ddd != ''
                  AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
                GROUP BY CAST(ddd AS INT)
            ),
            vol_15m AS (
                SELECT CAST(ddd AS INT) AS ddd, COUNT(*) AS vol
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(MINUTE, -15, @Now) AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                  AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
                GROUP BY CAST(ddd AS INT)
            ),
            vol_30m AS (
                SELECT CAST(ddd AS INT) AS ddd, COUNT(*) AS vol
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(MINUTE, -30, @Now) AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                  AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
                GROUP BY CAST(ddd AS INT)
            ),
            vol_1h AS (
                SELECT CAST(ddd AS INT) AS ddd, COUNT(*) AS vol
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(HOUR, -1, @Now) AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                  AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
                GROUP BY CAST(ddd AS INT)
            ),
            vol_6h AS (
                SELECT CAST(ddd AS INT) AS ddd, COUNT(*) AS vol
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(HOUR, -6, @Now) AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                  AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
                GROUP BY CAST(ddd AS INT)
            ),
            vol_12h AS (
                SELECT CAST(ddd AS INT) AS ddd, COUNT(*) AS vol
                FROM genesys.ConversationDetails
                WHERE conversationStart >= DATEADD(HOUR, -12, @Now) AND conversationStart < @MaxDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                  AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
                GROUP BY CAST(ddd AS INT)
            ),
            tlv_max AS (
                SELECT MAX(CAST(Dt_Atendimento AS DATE)) AS tlvDate
                FROM tlv.Atendimentos_Genesys
                WHERE Dt_Atendimento IS NOT NULL
            ),
            top_motivo AS (
                SELECT ddd, Grupo_Processo AS topMotivo, Tipo_Processo AS topTipo
                FROM (
                    SELECT
                        CAST(g.ddd AS INT) AS ddd,
                        a.Grupo_Processo, a.Tipo_Processo,
                        ROW_NUMBER() OVER (PARTITION BY CAST(g.ddd AS INT) ORDER BY COUNT(*) DESC) AS rn
                    FROM genesys.ConversationDetails g
                    JOIN tlv.Atendimentos_Genesys a ON g.conversationId = a.Conversation_ID
                    CROSS JOIN tlv_max tm
                    WHERE a.Dt_Atendimento >= tm.tlvDate AND a.Dt_Atendimento < DATEADD(DAY, 1, tm.tlvDate)
                      AND a.Rank_Motivo_Principal = 1 AND g.ddd IS NOT NULL AND g.ddd != ''
                      AND g.acd_participantNames IS NOT NULL AND g.acd_participantNames != ''
                    GROUP BY CAST(g.ddd AS INT), a.Grupo_Processo, a.Tipo_Processo
                ) x WHERE rn = 1
            ),
            acw_by_ddd AS (
                SELECT CAST(g.ddd AS INT) AS ddd, AVG(a.Duracao_Tabulacao) AS acw
                FROM tlv.Atendimentos_Genesys a
                JOIN genesys.ConversationDetails g ON g.conversationId = a.Conversation_ID
                WHERE g.conversationStart >= @PrevDate
                  AND a.Duracao_Tabulacao IS NOT NULL AND g.ddd IS NOT NULL AND g.ddd != ''
                  AND g.acd_participantNames IS NOT NULL AND g.acd_participantNames != ''
                GROUP BY CAST(g.ddd AS INT)
            ),
            acw_global AS (
                SELECT AVG(Duracao_Tabulacao) AS acw
                FROM tlv.Atendimentos_Genesys
                WHERE Dt_Atendimento >= @PrevDate AND Duracao_Tabulacao IS NOT NULL
            )
            SELECT
                t.ddd,
                ISNULL(d.micro, '') AS micro, ISNULL(d.uf, '') AS uf,
                ISNULL(d.regiao, '') AS regiao,
                t.totalToday, t.ongoing,
                ISNULL(t.tma, 0) AS tma, ISNULL(t.avgIvr, 0) AS avgIvr,
                ISNULL(ad.acw, ISNULL(ag.acw, 0)) AS acw,
                ISNULL(v15.vol, 0) AS vol15m,
                ISNULL(v30.vol, 0) AS vol30m,
                ISNULL(v1.vol, 0) AS vol1h,
                ISNULL(v6.vol, 0) AS vol6h,
                ISNULL(v12.vol, 0) AS vol12h,
                ISNULL(p7.prev7dTotal, 0) AS prev7dTotal,
                CASE WHEN p7.prev7dTotal IS NULL OR p7.prev7dTotal = 0 THEN 0
                     ELSE ROUND(((CAST(t.totalToday AS FLOAT) / p7.prev7dTotal) - 1) * 100, 0)
                END AS var7d,
                ISNULL(tm.topMotivo, '') AS topMotivo,
                ISNULL(tm.topTipo, '') AS topTipo,
                DATEDIFF(SECOND, CAST(@MaxDate AS DATETIME), @Now) AS time_offset
            FROM today_vol t
            LEFT JOIN ddd_info d ON d.ddd = t.ddd
            LEFT JOIN prev7d_vol p7 ON p7.ddd = t.ddd
            LEFT JOIN vol_15m v15 ON v15.ddd = t.ddd
            LEFT JOIN vol_30m v30 ON v30.ddd = t.ddd
            LEFT JOIN vol_1h v1 ON v1.ddd = t.ddd
            LEFT JOIN vol_6h v6 ON v6.ddd = t.ddd
            LEFT JOIN vol_12h v12 ON v12.ddd = t.ddd
            LEFT JOIN top_motivo tm ON tm.ddd = t.ddd
            LEFT JOIN acw_by_ddd ad ON ad.ddd = t.ddd
            CROSS JOIN acw_global ag
            ORDER BY t.totalToday DESC
        """)
        rows = cursor.fetchall()

        # Extrair time_offset do primeiro row da query principal
        time_offset = rows[0]["time_offset"] if rows else 0

        # 4 queries de referência simples (1 por semana, cada uma é um index seek rápido)
        # Retorna totais por (ddd, janela) já agregados no SQL
        windows_def = [
            ("15m", 900), ("30m", 1800), ("1h", 3600),
            ("6h", 21600), ("12h", 43200),
        ]
        ref_vols = defaultdict(list)
        for week_offset in [7, 14, 21, 28]:
            cursor.execute("""
                DECLARE @MaxDate DATE = (
                    SELECT MAX(CAST(conversationStart AS DATE))
                    FROM genesys.ConversationDetails WHERE conversationStart IS NOT NULL
                );
                DECLARE @RefDate DATE = DATEADD(DAY, -%s, @MaxDate);
                DECLARE @RefDateNext DATE = DATEADD(DAY, 1, @RefDate);
                SELECT
                    CAST(ddd AS INT) AS ddd,
                    SUM(CASE WHEN DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             <= %s THEN 1 ELSE 0 END) AS vol24h,
                    SUM(CASE WHEN DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             > (%s - 900) AND DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             <= %s THEN 1 ELSE 0 END) AS vol15m,
                    SUM(CASE WHEN DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             > (%s - 1800) AND DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             <= %s THEN 1 ELSE 0 END) AS vol30m,
                    SUM(CASE WHEN DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             > (%s - 3600) AND DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             <= %s THEN 1 ELSE 0 END) AS vol1h,
                    SUM(CASE WHEN DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             > (%s - 21600) AND DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             <= %s THEN 1 ELSE 0 END) AS vol6h,
                    SUM(CASE WHEN DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             > (%s - 43200) AND DATEDIFF(SECOND, CAST(conversationStart AS DATE), conversationStart)
                             <= %s THEN 1 ELSE 0 END) AS vol12h
                FROM genesys.ConversationDetails
                WHERE conversationStart >= @RefDate AND conversationStart < @RefDateNext
                  AND ddd IS NOT NULL AND ddd != ''
                  AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
                GROUP BY CAST(ddd AS INT)
            """, (week_offset,
                  time_offset,
                  time_offset, time_offset,
                  time_offset, time_offset,
                  time_offset, time_offset,
                  time_offset, time_offset,
                  time_offset, time_offset))
            for rr in cursor.fetchall():
                ddd = rr["ddd"]
                ref_vols[("24h", ddd)].append(rr["vol24h"])
                if rr["vol15m"]: ref_vols[("15m", ddd)].append(rr["vol15m"])
                if rr["vol30m"]: ref_vols[("30m", ddd)].append(rr["vol30m"])
                if rr["vol1h"]:  ref_vols[("1h", ddd)].append(rr["vol1h"])
                if rr["vol6h"]:  ref_vols[("6h", ddd)].append(rr["vol6h"])
                if rr["vol12h"]: ref_vols[("12h", ddd)].append(rr["vol12h"])

        medians = {"15m": {}, "30m": {}, "1h": {}, "6h": {}, "12h": {}, "24h": {}}
        for (win, ddd), vals in ref_vols.items():
            medians[win][ddd] = median(vals)

        # Buscar hourly separadamente e montar array
        cursor.execute("""
            DECLARE @MaxDate DATE = (
                SELECT MAX(CAST(conversationStart AS DATE))
                FROM genesys.ConversationDetails
                WHERE conversationStart IS NOT NULL
            );
            SELECT
                CAST(ddd AS INT) AS ddd,
                DATEPART(HOUR, conversationStart) * 2 +
                    CASE WHEN DATEPART(MINUTE, conversationStart) >= 30 THEN 1 ELSE 0 END AS slot,
                COUNT(*) AS cnt
            FROM genesys.ConversationDetails
            WHERE conversationStart >= @MaxDate AND conversationStart < DATEADD(DAY, 1, @MaxDate)
              AND ddd IS NOT NULL AND ddd != ''
              AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
            GROUP BY CAST(ddd AS INT),
                DATEPART(HOUR, conversationStart) * 2 +
                    CASE WHEN DATEPART(MINUTE, conversationStart) >= 30 THEN 1 ELSE 0 END
        """)
        hourly_rows = cursor.fetchall()
        hourly_map = {}
        for h in hourly_rows:
            ddd = h["ddd"]
            if ddd not in hourly_map:
                hourly_map[ddd] = [0] * 48
            hourly_map[ddd][h["slot"]] = h["cnt"]

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

        def _var(vol_today, med_val):
            if not med_val or med_val == 0:
                return 0
            return round(((vol_today / med_val) - 1) * 100)

        result = []
        for r in rows:
            ddd = r["ddd"]
            vol15 = int(r["vol15m"] or 0)
            vol30 = int(r["vol30m"] or 0)
            vol1h = int(r["vol1h"] or 0)
            vol6h = int(r["vol6h"] or 0)
            vol12h = int(r["vol12h"] or 0)
            total = r["totalToday"]
            # Medianas por janela
            med15 = medians["15m"].get(ddd, 0)
            med30 = medians["30m"].get(ddd, 0)
            med1h = medians["1h"].get(ddd, 0)
            med6h = medians["6h"].get(ddd, 0)
            med12h = medians["12h"].get(ddd, 0)
            med24h = medians["24h"].get(ddd, 0)
            # Variações
            v15 = _var(vol15, med15)
            v30 = _var(vol30, med30)
            v1h = _var(vol1h, med1h)
            v6h = _var(vol6h, med6h)
            v12h = _var(vol12h, med12h)
            v24h = _var(total, med24h)
            v7d = int(r["var7d"] or 0)
            # Medianas base para filtro de falso positivo
            bp15 = int(med15)
            bp30 = int(med30)
            bp1h = int(med1h)
            bp6h = int(med6h)
            result.append({
                "ddd": ddd,
                "micro": r["micro"],
                "uf": r["uf"],
                "regiao": r["regiao"],
                "totalToday": total,
                "hourly": hourly_map.get(ddd, [0] * 48),
                "ongoing": r["ongoing"] or 0,
                "var15": v15,
                "var30": v30,
                "var1h": v1h,
                "var6h": v6h,
                "var12h": v12h,
                "var24h": v24h,
                "var7d": v7d,
                "severity": _severity(v15, v30, v1h, v6h, v12h, v24h, v7d,
                                      total, bp15, bp30, bp1h, bp6h),
                "tma": int(r["tma"] or 0),
                "avgIvr": int(r["avgIvr"] or 0),
                "acw": int(r["acw"] or 0),
                "topMotivo": r["topMotivo"],
                "topTipo": r["topTipo"],
                "vol15": vol15, "vol30": vol30, "vol1h": vol1h,
                "vol6h": vol6h, "vol12h": vol12h,
                "med15": round(med15, 1), "med30": round(med30, 1),
                "med1h": round(med1h, 1), "med6h": round(med6h, 1),
                "med12h": round(med12h, 1), "med24h": round(med24h, 1),
                "prev7d": int(r["prev7dTotal"] or 0),
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
def api_motivos(ddds: Optional[str] = Query(None, description="Comma-separated DDD list to filter"),
                user: dict = Depends(require_login)):
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
                    AVG(CASE WHEN g.conversationEnd IS NOT NULL THEN DATEDIFF(SECOND, g.conversationStart, g.conversationEnd) ELSE NULL END) AS tma
                FROM tlv.Atendimentos_Genesys a
                JOIN genesys.ConversationDetails g ON g.conversationId = a.Conversation_ID
                WHERE a.Dt_Atendimento >= @MaxDate AND a.Dt_Atendimento < DATEADD(DAY, 1, @MaxDate)
                  AND a.Rank_Motivo_Principal = 1
                  AND a.Classe_Processo IS NOT NULL
                  AND g.ddd IN ({placeholders})
                  AND g.acd_participantNames IS NOT NULL AND g.acd_participantNames != ''
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
                    AVG(CASE WHEN g.conversationEnd IS NOT NULL THEN DATEDIFF(SECOND, g.conversationStart, g.conversationEnd) ELSE NULL END) AS tma
                FROM tlv.Atendimentos_Genesys a
                JOIN genesys.ConversationDetails g ON g.conversationId = a.Conversation_ID
                WHERE a.Dt_Atendimento >= @MaxDate AND a.Dt_Atendimento < DATEADD(DAY, 1, @MaxDate)
                  AND a.Rank_Motivo_Principal = 1
                  AND a.Classe_Processo IS NOT NULL
                  AND g.acd_participantNames IS NOT NULL AND g.acd_participantNames != ''
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
def api_municipios(user: dict = Depends(require_login)):
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
def api_agentes(user: dict = Depends(require_login)):
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
    req = UrlRequest(url, headers={"User-Agent": "Mozilla/5.0"})
    kwargs = {"timeout": timeout}
    if url.startswith("https"):
        kwargs["context"] = _ssl_ctx
    with urlopen(req, **kwargs) as resp:
        return resp.read()


@app.get("/api/heatmap-sinistro")
def api_heatmap_sinistro(user: dict = Depends(require_login)):
    """Heatmap hora x data dos últimos 7 dias para Comunicação de Sinistro, agrupado por DDD."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT
                CAST(a.Dt_Atendimento AS DATE) AS dt,
                DATEPART(HOUR, g.conversationStart) AS hr,
                CAST(g.ddd AS INT) AS ddd,
                COUNT(*) AS cnt
            FROM tlv.Atendimentos_Genesys a
            JOIN genesys.ConversationDetails g ON g.conversationId = a.Conversation_ID
            WHERE a.Tipo_Processo LIKE %s
              AND a.Rank_Motivo_Principal = 1
              AND a.Dt_Atendimento >= DATEADD(DAY, -7, CAST(GETDATE() AS DATE))
              AND g.ddd IS NOT NULL AND g.ddd != ''
              AND g.acd_participantNames IS NOT NULL AND g.acd_participantNames != ''
            GROUP BY CAST(a.Dt_Atendimento AS DATE), DATEPART(HOUR, g.conversationStart), CAST(g.ddd AS INT)
            ORDER BY dt, hr
        """, ('%Comunica%Sinistro%',))
        rows = cursor.fetchall()
        # Retorna array granular; frontend agrega conforme filtros
        return {"rows": [{"dt": str(r["dt"]), "hr": r["hr"], "ddd": r["ddd"], "cnt": r["cnt"]} for r in rows]}
    finally:
        conn.close()


@app.get("/api/previsao-horaria")
def api_previsao_horaria(user: dict = Depends(require_login)):
    """Mediana de volume por hora dos últimos 4 mesmos dias da semana (previsão)."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            DECLARE @MaxDate DATE = (
                SELECT MAX(CAST(conversationStart AS DATE))
                FROM genesys.ConversationDetails
                WHERE conversationStart IS NOT NULL
            );
            DECLARE @DW INT = DATEPART(WEEKDAY, @MaxDate);
            SELECT
                DATEPART(HOUR, conversationStart) * 2 +
                    CASE WHEN DATEPART(MINUTE, conversationStart) >= 30 THEN 1 ELSE 0 END AS slot,
                CAST(conversationStart AS DATE) AS dt,
                COUNT(*) AS cnt
            FROM genesys.ConversationDetails
            WHERE conversationStart >= DATEADD(DAY, -35, @MaxDate)
              AND conversationStart < @MaxDate
              AND DATEPART(WEEKDAY, conversationStart) = @DW
              AND ddd IS NOT NULL AND ddd != ''
              AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
            GROUP BY CAST(conversationStart AS DATE),
                DATEPART(HOUR, conversationStart) * 2 +
                    CASE WHEN DATEPART(MINUTE, conversationStart) >= 30 THEN 1 ELSE 0 END
            ORDER BY dt, slot
        """)
        rows = cursor.fetchall()
        # Agrupar por slot de 30min, coletar volumes de cada data
        slot_vals = defaultdict(list)
        for r in rows:
            slot_vals[r["slot"]].append(r["cnt"])
        # Calcular mediana por slot
        result = [0] * 48
        for s in range(48):
            vals = slot_vals.get(s, [])
            result[s] = round(median(vals)) if vals else 0
        return {"forecast": result}
    finally:
        conn.close()


@app.get("/api/filas")
def api_filas(user: dict = Depends(require_login)):
    """Volumetria por fila (última fila no acd_participantNames)."""
    conn = get_conn()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
            DECLARE @MaxDate DATE = (
                SELECT MAX(CAST(conversationStart AS DATE))
                FROM genesys.ConversationDetails
                WHERE conversationStart IS NOT NULL
            );
            DECLARE @MaxDateNext DATE = DATEADD(DAY, 1, @MaxDate);
            SELECT
                RTRIM(LTRIM(
                    REVERSE(LEFT(REVERSE(acd_participantNames),
                        CHARINDEX(';', REVERSE(acd_participantNames) + ';') - 1))
                )) AS fila,
                COUNT(*) AS total,
                SUM(CASE WHEN conversationEnd IS NULL THEN 1 ELSE 0 END) AS ongoing,
                AVG(CASE WHEN conversationEnd IS NOT NULL
                     THEN DATEDIFF(SECOND, conversationStart, conversationEnd)
                     ELSE NULL END) AS tma
            FROM genesys.ConversationDetails
            WHERE conversationStart >= @MaxDate AND conversationStart < @MaxDateNext
              AND ddd IS NOT NULL AND ddd != ''
              AND acd_participantNames IS NOT NULL AND acd_participantNames != ''
            GROUP BY RTRIM(LTRIM(
                REVERSE(LEFT(REVERSE(acd_participantNames),
                    CHARINDEX(';', REVERSE(acd_participantNames) + ';') - 1))
            ))
            ORDER BY COUNT(*) DESC
        """)
        rows = cursor.fetchall()
        return [{"fila": r["fila"], "total": r["total"], "ongoing": r["ongoing"],
                 "tma": r["tma"] or 0} for r in rows]
    finally:
        conn.close()


_NEWS_URL = (
    "http://news.google.com/rss/search"
    "?q=chuva+OR+enchente+OR+tempestade+OR+alagamento+OR+vendaval"
    "+OR+deslizamento+OR+inundacao+OR+ciclone+OR+seca+OR+queimada+brasil"
    "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
)


@app.get("/api/headlines")
def api_headlines(user: dict = Depends(require_login)):
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


def _severity(v15: int, v30: int, v1h: int, v6h: int, v12h: int, v24h: int, v7d: int,
              total: int, bp15: int = 0, bp30: int = 0, bp1h: int = 0, bp6h: int = 0) -> str:
    """Calcula severidade considerando todas as janelas temporais e volume mínimo.

    Janelas curtas com mediana base menor que 5 chamadas são ignoradas
    para evitar falsos positivos por volatilidade estatística (ex: 1→7 = +600%).
    """
    # DDDs com volume diário muito baixo não devem ser críticos
    if total < 10:
        return "normal"
    # Ignorar variações de janelas curtas com mediana base < 5
    MIN_BASE = 5
    eff_v15 = max(v15, 0) if bp15 >= MIN_BASE else 0
    eff_v30 = max(v30, 0) if bp30 >= MIN_BASE else 0
    eff_v1h = max(v1h, 0) if bp1h >= MIN_BASE else 0
    eff_v6h = max(v6h, 0) if bp6h >= MIN_BASE else 0
    mx_short = max(eff_v15, eff_v30, eff_v1h, eff_v6h)
    mx_long = max(max(v12h, 0), max(v24h, 0), max(v7d, 0))
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
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "createsuperuser":
        # Criar primeiro admin via CLI: python app.py createsuperuser
        email = input("Email: ").strip().lower()
        name = input("Nome: ").strip()
        password = input("Senha: ").strip()
        if not email or not name or len(password) < 8:
            print("Erro: email e nome obrigatórios, senha mínima 8 caracteres.")
            sys.exit(1)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conexreport.users (email, display_name, password_hash, role) "
            "VALUES (%s, %s, %s, 'admin')",
            (email, name, hash_password(password))
        )
        conn.commit()
        conn.close()
        print(f"Admin '{name}' ({email}) criado com sucesso!")
        sys.exit(0)

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)
