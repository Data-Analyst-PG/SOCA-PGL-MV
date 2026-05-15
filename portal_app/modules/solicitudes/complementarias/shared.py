# portal_app/modules/complementarias/shared.py
# ─────────────────────────────────────────────────────────────────────────────
# ACTUALIZADO – Abril 2026
#   • Tipos de concepto ampliados (28 opciones del Star 2.0)
#   • Conceptos (subtipos) diferenciados por plataforma
#   • Plataformas actualizadas (Lincoln y Set Logis solo Star 2.0 propio)
#   • Campos nuevos para Logismex: Tasa IVA, Tasa Retención, Retención ISR
#   • Historial JSON (igual que tickets)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from services.supabase_client import get_authed_client, get_secret


# ═══════════════════════════════════════════════════════════════════════════════
# CATÁLOGOS BASE
# ═══════════════════════════════════════════════════════════════════════════════

EMPRESAS = ["Set Freight", "Lincoln Freight", "Set Logis Plus", "Picus", "Igloo"]
MONEDAS  = ["MXN", "USD"]


def _title_case(s: str) -> str:
    return " ".join(w.capitalize() for w in str(s).strip().split())


SUCURSALES_POR_EMPRESA = {
    "Lincoln Freight": [],
    "Picus": ["Carrier RL", "Carrier RC", "Plus NLD", "Plus QRO", "Logistica"],
    "Igloo": ["Carrier", "Plus", "Logistica"],
    "Set Freight": [
        _title_case(x)
        for x in [
            "CARGAR", "CHICAGO", "CONSOLIDADO", "CONSOLIDADO QUERETARO",
            "DALLAS", "GUADALAJARA", "LEON", "LINCOLN LOGISTICS",
            "LUIS MONCAYO", "MG HAULERS", "MONTERREY", "NUEVO LAREDO",
            "QUERETARO", "RAMOS ARIZPE", "ROLANDO ALFARO", "SLP LOGISTICS",
        ]
    ],
    "Set Logis Plus": [
        _title_case(x)
        for x in [
            "BASICOS GJ", "AG FLEET (ROLANDO)", "AURA TRANSPORT",
            "JOEDAN TRANSPORT", "EFRAIN GARCIA",
        ]
    ],
}


# ─── Plataformas actualizadas ────────────────────────────────────────────────
# Lincoln  → ya solo Star 2.0 Lincoln (el Star USA anterior queda solo consulta)
# Set Logis → ya solo Star 2.0 Set Logis
# Set Freight → Star 2.0 Set Freight + Star 2.0 Logismex
# Picus / Igloo → Star 2.0 PGL + Star 2.0 Logismex
PLATAFORMAS_POR_EMPRESA = {
    "Lincoln Freight": ["STAR 2.0 LINCOLN"],
    "Set Logis Plus":  ["STAR 2.0 SET LOGIS"],
    "Set Freight": [
        "STAR 2.0 SET FREIGHT",
        "STAR 2.0 LOGISMEX",
    ],
    "Picus": [
        "STAR 2.0 PGL",
        "STAR 2.0 LOGISMEX",
    ],
    "Igloo": [
        "STAR 2.0 PGL",
        "STAR 2.0 LOGISMEX",
    ],
}


# ─── 28 Tipos de Concepto (Star 2.0 unificado) ──────────────────────────────
TIPOS_CONCEPTO = [
    "OTROS",
    "TIPO MOVIMIENTO",
    "FLETE MX",
    "AUTOPISTAS",
    "PAD",
    "FLETE USA",
    "CRUCE",
    "DOMESTICO MX",
    "DOMESTICO USA",
    "ALMACENAJE",
    "MANIOBRAS",
    "SUELDO CARGADO",
    "CARGA",
    "DESCARGA",
    "TRASBORDO",
    "BONO",
    "SUELDO",
    "GRUA",
    "REPARACION",
    "ANTICIPO",
    "IMPUESTO",
    "REEMBOLSO",
    "SUELDO VACIO",
    "IMPUESTO PATRONAL",
    "RETENCION MX",
    "MULTA",
    "PBT",
    "BASCULAS",
]


# ═══════════════════════════════════════════════════════════════════════════════
# CONCEPTOS (SUBTIPOS) POR PLATAFORMA
# ═══════════════════════════════════════════════════════════════════════════════
# Cada plataforma tiene su propio catálogo de conceptos por tipo.
# Si un tipo no aparece en el dict, significa "Sin datos para mostrar".

CONCEPTOS_POR_PLATAFORMA = {

    # ── STAR 2.0 LINCOLN ─────────────────────────────────────────────────────
    "STAR 2.0 LINCOLN": {
        "OTROS": [
            "ADITIONAL INSURANCE/CT. SEGURO",
            "EXTRA STOP/CT. PARADA EXTRA",
            "HANDLING CHARGES/CT. MANIOBRAS",
            "LAY OVER/ CT.ESTANCIAS",
            "LOCAL MOVEMENT/CT. MOVIMIENTO LOCAL",
            "SALES EXPENSES 1/CT. GASTOS DE VENTA",
            "TNU - TRUCK NOT USED/CT. MOVIMIENTO EN FALSO",
            "TRANSLOAD/ CT. TRANSBORDO",
        ],
        "FLETE MX": ["FREIGHT MEX/CT. TRANSP MEX"],
        "FLETE USA": ["FREIGHT USA/CT. TRANSP USA"],
        "CRUCE": ["CROSS BORDER LOADED/CT. CRUCE CARGADO"],
    },

    # ── STAR 2.0 SET LOGIS ───────────────────────────────────────────────────
    "STAR 2.0 SET LOGIS": {
        "OTROS": [
            "LOCAL MOVEMENT/CT. MOVIMIENTO LOCAL",
            "LUMPER FEES/ CT. DESCARGA",
        ],
    },

    # ── STAR 2.0 SET FREIGHT (igual que el Star anterior) ────────────────────
    "STAR 2.0 SET FREIGHT": {
        "OTROS": [
            "EXTRA STOP/CT. PARADA EXTRA",
            "HANDLING CHARGES/CT. MANIOBRAS",
            "LAY OVER/CT. ESTANCIAS",
            "LOADLOCKS/ CT.GATAS/BLOQUEOS",
            "LOGISTICS COORDINATION/ CT. COORDINACION LOGISTICA",
            "LUMPER FEES/ CT. DESCARGA",
            "SALES EXPENSES 1/CT. GASTOS DE VENTA",
            "SALES EXPENSES 2/CT. GASTOS DE VENTA",
            "SALES EXPENSES 3/CT. GASTOS DE VENTA",
            "SCALE / CT. BASCULA RB",
            "STORAGE COSTS/CT. ALMACENAJES",
            "TEAM DRIVER /CT. DOBLE OPERADOR",
            "THERMO RENT/CT. RENTA DE THERMO",
            "TIRES /CT.LLANTAS",
            "TNU - TRUCK NOT USED/CT. MOVIMIENTO EN FALSO",
            "TRAILER PARTS /CT. REFACCIONES",
            "TRAILER REPAIR & OTHER EXPENSES/CT. REP. Y OTROS GASTOS DE VIAJE",
            "TRANSLOAD/ CT. TRANSBORDO",
        ],
    },

    # ── STAR 2.0 PGL ─────────────────────────────────────────────────────────
    "STAR 2.0 PGL": {
        "OTROS": [
            "ADITIONAL INSURANCE/CT. SEGURO",
            "BOND/CT. FIANZAS",
            "CANVAS/CT. LONAS",
            "CROSS BORDER EMPTY/CT. CRUCE VACIO",
            "CT. MOVIMIENTO EXTRAORDINARIO",
            "CT. MOVIMIENTO LOCAL",
            "CUSTOM BROKER FEE MX/CT. SERV A.A. MX",
            "CUSTOM BROKER FEE USA/CT. SERV A.A. USA",
            "DETENTION/CT. DEMORAS",
            "DRY VAN RENT/CT. RENTA DE CAJA",
            "EXTRA CHARGES /CT. CARGOS EXTRAS",
            "EXTRA STOP/CT. PARADA EXTRA",
            "FAH",
            "HANDLING CHARGES/CT. MANIOBRAS",
            "LAY OVER/ CT.ESTANCIAS",
            "LOADLOCKS/ CT.GATAS/BLOQUEOS",
            "LOGISTICS COORDINATION/ CT. COORDINACION LOGISTICA",
            "LUMPER FEES/ CT. DESCARGA",
        ],
        "FLETE MX": ["FREIGHT MEX/CT. TRANSP MEX"],
        "FLETE USA": ["FREIGHT USA/CT. TRANSP USA"],
        "AUTOPISTAS": ["TOLL FEE/CT. AUTOPISTAS"],
        "PAD": ["FUEL CHARGES/PAD"],
        "CRUCE": ["CROSS BORDER LOADED/CT. CRUCE CARGADO"],
        "DOMESTICO MX": ["MX LINE HAUL CT./CT. DOMESTICO MX"],
        "DOMESTICO USA": ["US LINE HAUL CT./CT. DOMESTICO USA"],
    },

    # ── STAR 2.0 LOGISMEX ────────────────────────────────────────────────────
    # Tiene los mismos conceptos que PGL + extras (Sales Expenses, Scale, etc.)
    "STAR 2.0 LOGISMEX": {
        "OTROS": [
            "ADITIONAL INSURANCE/CT. SEGURO",
            "CANVAS/CT. LONAS",
            "CROSS BORDER EMPTY/CT. CRUCE VACIO",
            "CT. MOVIMIENTO EXTRAORDINARIO",
            "CT. MOVIMIENTO LOCAL",
            "CUSTOM BROKER FEE MX/CT. SERV A.A. MX",
            "CUSTOM BROKER FEE USA/CT. SERV A.A. USA",
            "DETENTION/CT. DEMORAS",
            "DRY VAN RENT/CT. RENTA DE CAJA",
            "EXTRA CHARGES /CT. CARGOS EXTRAS",
            "EXTRA STOP / CT.REPARTO",
            "EXTRA STOP/CT. PARADA EXTRA",
            "HANDLING CHARGES/CT. MANIOBRAS",
            "LAY OVER/ CT.ESTANCIAS",
            "LOADLOCKS/ CT.GATAS/BLOQUEOS",
            "LOCAL MOVEMENT / CT. MOVIMIENTO LOCAL",
            "LUMPER FEES/ CT. DESCARGA",
            "SALES EXPENSES 1/CT. GASTOS DE VENTA",
            "SALES EXPENSES 2/CT. GASTOS DE VENTA",
            "SALES EXPENSES 3/CT. GASTOS DE VENTA",
            "SCALE / CT. BASCULA RB",
            "STORAGE COSTS/CT. ALMACENAJES",
            "TEAM DRIVER /CT. DOBLE OPERADOR",
            "TIRES /CT. LLANTAS",
            "TNU - TRUCK NOT USED/CT. MOVIMIENTO EN FALSO",
            "TRAILER PARTS /CT. REFACCIONES",
            "TRAILER REPAIR & OTHER EXPENSES/CT. REP. Y OTROS GASTOS DE VIAJE",
            "TRANSLOAD/ CT. TRANSBORDO",
        ],
        "FLETE MX": ["FREIGHT MEX/CT. TRANSP MEX"],
        "FLETE USA": ["FREIGHT USA/CT. TRANSP USA"],
        "AUTOPISTAS": ["TOLL FEE/CT. AUTOPISTAS"],
        "PAD": ["FUEL CHARGES/PAD"],
        "CRUCE": ["CROSS BORDER LOADED/CT. CRUCE CARGADO"],
        "DOMESTICO MX": ["MX LINE HAUL CT./CT. DOMESTICO MX"],
        "DOMESTICO USA": ["US LINE HAUL CT./CT. DOMESTICO USA"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# CAMPOS FISCALES DE LOGISMEX
# ═══════════════════════════════════════════════════════════════════════════════
# Estas opciones solo aparecen cuando la plataforma es "STAR 2.0 LOGISMEX"

TASAS_IVA = ["EXENTO", "IVA 0%", "IVA 8%", "IVA 11%", "IVA 16%"]

TASAS_RETENCION = ["EXENTO", "RET 4%", "RET 10%"]

RETENCIONES_ISR = ["EXENTO", "RET ISR 1.25%"]

# Mapeo tasa → porcentaje para cálculos automáticos
TASA_IVA_PORCENTAJE = {
    "EXENTO":  0.0,
    "IVA 0%":  0.0,
    "IVA 8%":  0.08,
    "IVA 11%": 0.11,
    "IVA 16%": 0.16,
}

TASA_RETENCION_PORCENTAJE = {
    "EXENTO": 0.0,
    "RET 4%": 0.04,
    "RET 10%": 0.10,
}

RETENCION_ISR_PORCENTAJE = {
    "EXENTO":        0.0,
    "RET ISR 1.25%": 0.0125,
}


def es_plataforma_logismex(plataforma: str) -> bool:
    """
    Retorna True si la plataforma contiene 'LOGISMEX' en su nombre.
    Así funciona para "STAR 2.0 LOGISMEX", "STAR 2.0 PALOS GARZA LOGISMEX",
    o cualquier variante futura que contenga la palabra LOGISMEX.
    """
    if not plataforma:
        return False
    return "LOGISMEX" in plataforma.upper()


def calcular_totales_logismex(importe: float, tasa_iva: str, tasa_ret: str, ret_isr: str) -> dict:
    """
    Calcula IVA, Retención, Retención ISR y Total como lo hace el sistema Logismex.
    Regla: si Tasa IVA = EXENTO → Tasa Retención = No Aplica (0)
    """
    pct_iva = TASA_IVA_PORCENTAJE.get(tasa_iva, 0.0)

    # Si IVA es EXENTO, la retención no aplica
    if tasa_iva == "EXENTO":
        pct_ret = 0.0
    else:
        pct_ret = TASA_RETENCION_PORCENTAJE.get(tasa_ret, 0.0)

    pct_isr = RETENCION_ISR_PORCENTAJE.get(ret_isr, 0.0)

    monto_iva = round(importe * pct_iva, 2)
    monto_ret = round(importe * pct_ret, 2)
    monto_isr = round(importe * pct_isr, 2)
    total     = round(importe + monto_iva - monto_ret - monto_isr, 2)

    return {
        "iva":           monto_iva,
        "retencion":     monto_ret,
        "retencion_isr": monto_isr,
        "total":         total,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

def get_supabase_client():
    """Siempre regresa el cliente con JWT para RLS."""
    return get_authed_client()


@st.cache_data(ttl=300)
def load_conceptos_from_supabase():
    """
    Carga conceptos desde la tabla catalogo_conceptos (si existe).
    Se usa como fuente adicional, NO reemplaza los catálogos por plataforma.
    """
    supabase = get_supabase_client()
    try:
        res = (
            supabase.table("catalogo_conceptos")
            .select("tipo_concepto, concepto, activo")
            .execute()
        )
        rows = res.data or []
        conceptos: dict[str, list[str]] = {}
        for r in rows:
            if "activo" in r and r["activo"] is False:
                continue
            t = (r.get("tipo_concepto") or "").strip()
            c = (r.get("concepto") or "").strip()
            if not t or not c:
                continue
            conceptos.setdefault(t, []).append(c)

        for t in conceptos:
            conceptos[t] = sorted(set(conceptos[t]))
        return conceptos
    except Exception:
        return {}


def get_conceptos(tipo: str, plataforma: str = "") -> list[str]:
    """
    Obtiene la lista de conceptos (subtipos) para un tipo de concepto,
    filtrando por plataforma.

    Prioridad:
    1. Catálogo de Supabase (catalogo_conceptos) si tiene datos
    2. Catálogo hardcodeado por plataforma (CONCEPTOS_POR_PLATAFORMA)
    3. Lista vacía
    """
    # 1) Intentar desde Supabase
    conceptos_db = load_conceptos_from_supabase()
    if tipo in conceptos_db and conceptos_db[tipo]:
        return conceptos_db[tipo]

    # 2) Por plataforma
    plat = (plataforma or "").strip()
    if plat in CONCEPTOS_POR_PLATAFORMA:
        return CONCEPTOS_POR_PLATAFORMA[plat].get(tipo, [])

    return []


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_profile_name(user_id: str) -> str:
    """Obtiene el full_name del usuario logueado desde la tabla profiles."""
    if not user_id:
        return ""
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("profiles")
            .select("full_name")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return (res.data or {}).get("full_name") or ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORIAL (mismo patrón que tickets)
# ═══════════════════════════════════════════════════════════════════════════════
# La columna "historial" en solicitudes_complementarias debe ser tipo JSONB.
#
# Formato de cada entrada:
# {
#     "at": "2026-04-08T12:00:00+00:00",   ← fecha ISO
#     "by": "Juan Pérez",                   ← quién hizo la acción
#     "action": "create",                   ← tipo de acción
#     "details": "Solicitud creada..."      ← descripción legible
# }

def build_historial_entry(by: str, action: str, details: str) -> dict:
    """Crea un registro de historial con timestamp UTC."""
    return {
        "at": now_utc_iso(),
        "by": by,
        "action": action,
        "details": details,
    }


def append_historial(existing: list | None, new_entry: dict) -> list:
    """Agrega una entrada al historial existente (inmutable, retorna nueva lista)."""
    hist = list(existing or [])
    hist.append(new_entry)
    return hist
