from __future__ import annotations
from io import BytesIO

import pandas as pd
import streamlit as st

from services.supabase_client import current_user
from services.supabase_client import get_authed_client

from ui.components import (
    section_header,
    kpi_row,
    alert,
    solicitud_card,
    solicitudes_table,
    status_badge_html,
)

def render():

    st.title("Consulta Viáticos")

    st.write("Página en construcción")