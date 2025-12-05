import json
import requests
import pandas as pd
import streamlit as st
from typing import Any, Dict, List, Union, Optional

# =========================
# Config
# =========================
API_BASE = "https://app.buhologistics.com/api/global/beta/shipments/"
API_VERSION = "2020-10"

# Idealmente usa st.secrets, pero dejo fallback
DEFAULT_AUTH = "f9e9201450bf79a3c510a0b60c7c303d"


# =========================
# Helpers
# =========================
def build_url(unique_id: str, expand_order: bool = True) -> str:
    unique_id = str(unique_id).strip()
    if expand_order:
        return f"{API_BASE}?filter[]=unique_id:{unique_id}&expand=order"
    return f"{API_BASE}?filter[]=unique_id:{unique_id}"


def get_headers(auth_token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-ShipStream-API-Version": API_VERSION,
        "X-AutomationV1-Auth": auth_token.strip(),
    }


def safe_json(response: requests.Response) -> Union[Dict[str, Any], List[Any], str]:
    try:
        return response.json()
    except Exception:
        return response.text


def normalize_to_df(data: Any) -> pd.DataFrame:
    """
    Intenta convertir la respuesta a un DataFrame útil:
    - Si es lista de objetos -> DataFrame directo.
    - Si es dict:
        - Si tiene lista en 'collection' o similares, normaliza eso.
        - Si no, normaliza el dict completo.
    """
    if isinstance(data, list):
        return pd.json_normalize(data)

    if isinstance(data, dict):
        # Caso específico de tu API
        if "collection" in data and isinstance(data["collection"], list):
            return pd.json_normalize(data["collection"])

        # Casos genéricos
        for key in ["data", "results", "items", "shipments"]:
            if key in data and isinstance(data[key], list):
                return pd.json_normalize(data[key])

        return pd.json_normalize(data)

    return pd.DataFrame({"raw": [str(data)]})


def get_first_shipment(data: Any) -> Optional[Dict[str, Any]]:
    """
    Extrae el primer Shipment de:
    {
      "collection": [ {...shipment...} ],
      ...
    }
    """
    if isinstance(data, dict):
        col = data.get("collection")
        if isinstance(col, list) and col:
            first = col[0]
            if isinstance(first, dict):
                return first
    return None


def kv_table(rows: List[Dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["Campo", "Valor"])


def build_ordered_summary(shipment: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """
    Construye tablas ordenadas para mostrar.
    Regresa dict de secciones -> DataFrame.
    """
    order = shipment.get("order") if isinstance(shipment.get("order"), dict) else {}

    # --- Sección: Shipment ---
    total_weight = shipment.get("total_weight") or {}
    total_item_weight = shipment.get("total_item_weight") or {}
    shipped_weight = shipment.get("shipped_weight") or {}

    shipment_rows = [
        {"Campo": "Shipment ID", "Valor": str(shipment.get("id", ""))},
        {"Campo": "unique_id", "Valor": str(shipment.get("unique_id", ""))},
        {"Campo": "status", "Valor": str(shipment.get("status", ""))},
        {"Campo": "warehouse_id", "Valor": str((shipment.get("warehouse") or {}).get("id", ""))},
        {"Campo": "shipping_method (shipment)", "Valor": str(shipment.get("shipping_method", ""))},
        {"Campo": "target_ship_date", "Valor": str(shipment.get("target_ship_date", ""))},
        {
            "Campo": "total_weight",
            "Valor": (
                f"{total_weight.get('value', '')} {total_weight.get('unit', '')}".strip()
                if isinstance(total_weight, dict) else str(total_weight)
            ),
        },
        {
            "Campo": "total_item_weight",
            "Valor": (
                f"{total_item_weight.get('value', '')} {total_item_weight.get('unit', '')}".strip()
                if isinstance(total_item_weight, dict) else str(total_item_weight)
            ),
        },
        {
            "Campo": "shipped_weight",
            "Valor": (
                f"{shipped_weight.get('value', '')} {shipped_weight.get('unit', '')}".strip()
                if isinstance(shipped_weight, dict) else str(shipped_weight)
            ),
        },
        {"Campo": "items_count", "Valor": str(len(shipment.get("items", []) or []))},
        {"Campo": "packages_count", "Valor": str(len(shipment.get("packages", []) or []))},
    ]

    # --- Sección: Order ---
    order_rows = [
        {"Campo": "Order ID", "Valor": str(order.get("id", ""))},
        {"Campo": "order unique_id", "Valor": str(order.get("unique_id", ""))},
        {"Campo": "order_ref", "Valor": str(order.get("order_ref", ""))},
        {"Campo": "state", "Valor": str(order.get("state", ""))},
        {"Campo": "status", "Valor": str(order.get("status", ""))},
        {"Campo": "carrier_code", "Valor": str(order.get("carrier_code", ""))},
        {"Campo": "shipping_method (order)", "Valor": str(order.get("shipping_method", ""))},
        {"Campo": "priority", "Valor": str(order.get("priority", ""))},
        {"Campo": "signature_required", "Valor": str(order.get("signature_required", ""))},
        {"Campo": "is_saturday_delivery", "Valor": str(order.get("is_saturday_delivery", ""))},
        {"Campo": "is_overbox_required", "Valor": str(order.get("is_overbox_required", ""))},
        {"Campo": "is_declared_value_service", "Valor": str(order.get("is_declared_value_service", ""))},
        {"Campo": "declared_value", "Valor": str(order.get("declared_value", ""))},
    ]

    return {
        "Shipment": kv_table(shipment_rows),
        "Order": kv_table(order_rows),
    }


# =========================
# UI
# =========================
st.set_page_config(page_title="Shipstream - Shipment Info", layout="wide")

st.title("📦 Shipstream - Consulta de Shipment por unique_id")

with st.sidebar:
    st.header("Configuración")
    auth_token = st.text_input(
        "X-AutomationV1-Auth",
        value=DEFAULT_AUTH
        if hasattr(st, "secrets")
        else DEFAULT_AUTH,
        type="password",
        help="Idealmente guárdalo en .streamlit/secrets.toml",
    )
    timeout = st.number_input("Timeout (segundos)", min_value=5, max_value=120, value=30)

st.subheader("Buscar envío")

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    unique_id = st.text_input("unique_id", value="5900008555")
with col2:
    do_expand_order = st.checkbox("expand=order", value=True)
with col3:
    go = st.button("Consultar", use_container_width=True)

if go:
    if not unique_id.strip():
        st.error("Ingresa un unique_id válido.")
        st.stop()

    if not auth_token.strip():
        st.error("Falta el token de autenticación.")
        st.stop()

    url = build_url(unique_id, expand_order=do_expand_order)
    headers = get_headers(auth_token)

    with st.spinner("Consultando API..."):
        try:
            resp = requests.get(url, headers=headers, timeout=int(timeout))
        except requests.exceptions.RequestException as e:
            st.error(f"Error de red/requests: {e}")
            st.stop()

    st.caption("URL usada:")
    st.code(url)

    st.caption("Status code:")
    st.write(resp.status_code)

    data = safe_json(resp)

    if resp.status_code >= 400:
        st.error("La API respondió con error.")
        st.subheader("Respuesta del servidor")
        if isinstance(data, (dict, list)):
            st.json(data)
        else:
            st.code(str(data))
        st.stop()

    # =========================
    # 1) Resumen ordenado
    # =========================
    st.subheader("Resumen ordenado")

    shipment = get_first_shipment(data)

    if not shipment:
        st.warning("No se encontró un Shipment dentro de 'collection'.")
    else:
        sections = build_ordered_summary(shipment)

        cA, cB = st.columns(2)
        with cA:
            st.markdown("### Shipment")
            st.table(sections["Shipment"])
        with cB:
            st.markdown("### Order")
            st.table(sections["Order"])

    # =========================
    # 2) JSON crudo
    # =========================
    st.subheader("JSON crudo")
    if isinstance(data, (dict, list)):
        st.json(data)
    else:
        st.code(str(data))

    # =========================
    # 3) Tabla aplanada (extra)
    # =========================
    st.subheader("Tabla aplanada (opcional)")
    try:
        df = normalize_to_df(data)
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar CSV",
            data=csv,
            file_name=f"shipment_{unique_id}.csv",
            mime="text/csv",
        )
    except Exception as e:
        st.warning(f"No se pudo normalizar a tabla: {e}")
