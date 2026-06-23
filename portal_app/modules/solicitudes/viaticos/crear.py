import streamlit as st
import pandas as pd

from datetime import datetime, date, timezone
from decimal import Decimal
from io import BytesIO
import base64

from PIL import Image
import resend

from services.supabase_client import (
    get_supabase_client,
    current_user,
)

from ui.components import (
    page_banner,
    alert,
    divider,
)


def render():

    page_banner(
        "💳",
        "Solicitud de Viáticos y Reembolsos",
        ""
    )

    supabase = get_supabase_client()

    if supabase is None:
        alert(
            "error",
            "No fue posible conectar a Supabase."
        )
        return

    user = current_user() or {}

    nombre_usuario = (
        user.get("name")
        or user.get("email")
        or ""
    )

    email_usuario = (
        user.get("email")
        or ""
    )

    # =================================
    # OLD CODE
    # =================================