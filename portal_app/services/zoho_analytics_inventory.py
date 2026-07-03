from __future__ import annotations

from io import BytesIO
from datetime import datetime
import pandas as pd
import requests
import time

_ACCESS_TOKEN_CACHE = {
    "token": None,
    "expires_at": 0,
}

def _ms_to_datetime(value):
    try:
        if not value:
            return ""
        return datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def get_access_token(client_id, client_secret, refresh_token, accounts_url):
    ahora = time.time()

    if _ACCESS_TOKEN_CACHE["token"] and ahora < _ACCESS_TOKEN_CACHE["expires_at"]:
        return _ACCESS_TOKEN_CACHE["token"]

    url = f"{accounts_url}/oauth/v2/token"

    params = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }

    response = requests.post(url, params=params, timeout=30)
    data = response.json()

    if "access_token" not in data:
        raise Exception(f"No se pudo obtener access token: {data}")

    _ACCESS_TOKEN_CACHE["token"] = data["access_token"]
    _ACCESS_TOKEN_CACHE["expires_at"] = ahora + 3000

    return data["access_token"]


def get_workspaces(access_token, analytics_api_url):
    url = f"{analytics_api_url}/restapi/v2/workspaces"

    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}"
    }

    response = requests.get(url, headers=headers, timeout=30)

    try:
        data = response.json()
    except Exception:
        raise Exception(
            f"Zoho no devolvió JSON.\n"
            f"Status code: {response.status_code}\n"
            f"Respuesta: {response.text}"
        )

    if data.get("status") != "success":
        raise Exception(
            f"Error al obtener workspaces.\n"
            f"Status code: {response.status_code}\n"
            f"URL usada: {url}\n"
            f"Respuesta Zoho: {data}"
        )

    owned = data.get("data", {}).get("ownedWorkspaces", [])
    shared = data.get("data", {}).get("sharedWorkspaces", [])

    return owned + shared


def get_views(access_token, analytics_api_url, workspace_id, org_id):
    url = f"{analytics_api_url}/restapi/v2/workspaces/{workspace_id}/views"

    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "ZANALYTICS-ORGID": str(org_id)
    }

    response = requests.get(url, headers=headers, timeout=30)
    data = response.json()

    if data.get("status") != "success":
        return []

    return data.get("data", {}).get("views", [])


def get_table_metadata(access_token, analytics_api_url, workspace_id, org_id, view_id):
    """
    Intenta obtener columnas de una tabla.
    Si Zoho no devuelve datos para ese tipo de vista, regresa vacío.
    """
    url = f"{analytics_api_url}/restapi/v2/workspaces/{workspace_id}/views/{view_id}/columns"

    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "ZANALYTICS-ORGID": str(org_id)
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        data = response.json()

        if data.get("status") != "success":
            return []

        return data.get("data", {}).get("columns", [])
    except Exception:
        return []


def generar_inventario_zoho(
    client_id,
    client_secret,
    refresh_token,
    accounts_url="https://accounts.zoho.com",
    analytics_api_url="https://analyticsapi.zoho.com",
    workspace_filtrado=None
):
    access_token = get_access_token(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        accounts_url=accounts_url
    )

    workspaces = get_workspaces(
        access_token=access_token,
        analytics_api_url=analytics_api_url
    )

    if workspace_filtrado:
        workspaces = [workspace_filtrado]

    rows = []

    for ws in workspaces:
        workspace_id = ws.get("workspaceId", "")
        workspace_name = ws.get("workspaceName", "")
        org_id = ws.get("orgId", "")
        workspace_created_by = ws.get("createdBy", "")

        views = get_views(
            access_token=access_token,
            analytics_api_url=analytics_api_url,
            workspace_id=workspace_id,
            org_id=org_id
        )

        for view in views:
            view_id = view.get("viewId", "")
            view_type = view.get("viewType", "")
            folder_id = view.get("folderId", "")

            columns = []
            if view_type.lower() in ["table", "querytable", "query table"]:
                columns = get_table_metadata(
                    access_token=access_token,
                    analytics_api_url=analytics_api_url,
                    workspace_id=workspace_id,
                    org_id=org_id,
                    view_id=view_id
                )

            rows.append({
                "Workspace": workspace_name,
                "Carpeta": folder_id if folder_id and folder_id != "null" else "",
                "Tipo": view_type,
                "Nombre": view.get("viewName", ""),
                "Fuente": "",
                "Actualización": "",
                "Responsable": view.get("createdBy", "") or workspace_created_by,
                "Estado": "Activo",
                "Nº de columnas": len(columns) if columns else "",
                "Nº de registros": "",
                "fecha de creación": _ms_to_datetime(view.get("createdTime", "")),
                "Última actualización": _ms_to_datetime(view.get("lastModifiedTime", "")),
                "Frecuencia de actualización": "",
                "Si tiene programación": "",
                "Fuente de datos": "",
            })

    df = pd.DataFrame(rows)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Inventario Zoho")

        ws_excel = writer.sheets["Inventario Zoho"]

        for column_cells in ws_excel.columns:
            length = max(len(str(cell.value or "")) for cell in column_cells)
            ws_excel.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 45)

    output.seek(0)

    return df, output
