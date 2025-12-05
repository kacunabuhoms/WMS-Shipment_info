import requests
import pandas as pd
import streamlit as st
from typing import Any, Dict, List, Union, Optional

# =========================
# Config
# =========================
API_BASE = "https://app.buhologistics.com/api/global/beta/shipments/"
API_VERSION = "2020-10"

# Fallback local (idealmente NO lo dejes en repo público)
DEFAULT_AUTH = ""



# =========================
# Helpers de API
# =========================
def build_url(unique_id: str) -> str:
    unique_id = str(unique_id).strip()
    return f"{API_BASE}?filter[]=unique_id:{unique_id}&expand=order"


def get_auth_token() -> str:
    try:
        return st.secrets.get("SHIPSTREAM_AUTH", DEFAULT_AUTH)  # type: ignore
    except Exception:
        return DEFAULT_AUTH


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


# =========================
# Helpers de parsing
# =========================
def get_first_shipment(data: Any) -> Optional[Dict[str, Any]]:
    if isinstance(data, dict):
        col = data.get("collection")
        if isinstance(col, list) and col:
            first = col[0]
            if isinstance(first, dict):
                return first
    return None


def fmt_weight(w: Any) -> str:
    if isinstance(w, dict):
        val = w.get("value", "")
        unit = w.get("unit", "")
        if val == "" and unit == "":
            return ""
        return f"{val} {unit}".strip()
    return str(w or "")


def count_list(x: Any) -> str:
    if isinstance(x, list):
        return str(len(x))
    return "0" if x is None else str(x)


def get_links(obj: Any) -> Dict[str, str]:
    if isinstance(obj, dict):
        links = obj.get("links")
        if isinstance(links, dict):
            # Convertimos a str por seguridad
            return {str(k): str(v) for k, v in links.items()}
    return {}


# =========================
# Helpers de UI / formateo
# =========================
def pretty_table(rows: List[Dict[str, str]]) -> pd.DataFrame:
    # Orden fijo Campo/Valor
    return pd.DataFrame(rows, columns=["Campo", "Valor"])


def add_row(rows: List[Dict[str, str]], label: str, value: Any):
    v = "" if value is None else str(value)
    rows.append({"Campo": label, "Valor": v})


def shipment_pretty(shipment: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []

    add_row(rows, "ID del Envío", shipment.get("id"))
    add_row(rows, "Unique ID del Envío", shipment.get("unique_id"))
    add_row(rows, "Estatus del Envío", shipment.get("status"))

    warehouse_id = (shipment.get("warehouse") or {}).get("id") if isinstance(shipment.get("warehouse"), dict) else ""
    add_row(rows, "ID del Almacén", warehouse_id)

    add_row(rows, "Método de Envío (Shipment)", shipment.get("shipping_method"))
    add_row(rows, "Fecha Objetivo de Envío", shipment.get("target_ship_date"))

    add_row(rows, "Peso Total", fmt_weight(shipment.get("total_weight")))
    add_row(rows, "Peso Total de Ítems", fmt_weight(shipment.get("total_item_weight")))
    add_row(rows, "Peso Enviado", fmt_weight(shipment.get("shipped_weight")))

    add_row(rows, "Cantidad de Ítems del Envío", count_list(shipment.get("items")))
    add_row(rows, "Cantidad de Paquetes", count_list(shipment.get("packages")))

    # Links útiles si existen
    links = get_links(shipment)
    if links.get("order"):
        add_row(rows, "Link del Order (API)", links.get("order"))

    return pretty_table(rows)


def order_pretty(order: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []

    add_row(rows, "ID de la Orden", order.get("id"))
    add_row(rows, "Unique ID de la Orden", order.get("unique_id"))
    add_row(rows, "Referencia de Orden", order.get("order_ref"))

    add_row(rows, "Estado", order.get("state"))
    add_row(rows, "Estatus", order.get("status"))

    add_row(rows, "Carrier Code", order.get("carrier_code"))
    add_row(rows, "Método de Envío (Order)", order.get("shipping_method"))

    add_row(rows, "Prioridad", order.get("priority"))
    add_row(rows, "Firma Requerida", order.get("signature_required"))
    add_row(rows, "Entrega en Sábado", order.get("is_saturday_delivery"))
    add_row(rows, "Requiere Overbox", order.get("is_overbox_required"))

    add_row(rows, "Servicio de Valor Declarado", order.get("is_declared_value_service"))
    add_row(rows, "Valor Declarado", order.get("declared_value"))

    # Conteos útiles
    add_row(rows, "Cantidad de Ítems de la Orden", count_list(order.get("items")))
    add_row(rows, "Cantidad de Envíos en la Orden", count_list(order.get("shipments")))

    # IDs relacionados si vienen
    merchant_id = (order.get("merchant") or {}).get("id") if isinstance(order.get("merchant"), dict) else ""
    brand_id = (order.get("brand") or {}).get("id") if isinstance(order.get("brand"), dict) else ""
    if merchant_id:
        add_row(rows, "ID del Comercio (Merchant)", merchant_id)
    if brand_id:
        add_row(rows, "ID de la Marca (Brand)", brand_id)

    return pretty_table(rows)


def merchant_pretty(merchant: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []

    add_row(rows, "Tipo", merchant.get("type"))
    add_row(rows, "ID del Comercio", merchant.get("id"))

    # Si en el futuro expandes merchant con más campos,
    # esto los mostrará de forma amistosa:
    extra_keys = [k for k in merchant.keys() if k not in {"type", "id"}]
    for k in extra_keys:
        label = str(k).replace("_", " ").strip().title()
        add_row(rows, label, merchant.get(k))

    return pretty_table(rows)


# =========================
# App
# =========================
st.set_page_config(page_title="Shipstream - Shipment Info", layout="wide")

st.title("📦 Shipstream - Consulta de Shipment por unique_id")
st.caption("Muestra Envío, Orden y Comercio en limpio, y después el JSON completo.")

unique_id = st.text_input("unique_id", value="5900008555")
go = st.button("Consultar")

if go:
    if not unique_id.strip():
        st.error("Ingresa un unique_id válido.")
        st.stop()

    auth_token = get_auth_token()
    if not auth_token.strip():
        st.error("No se encontró token. Agrega SHIPSTREAM_AUTH en secrets.")
        st.stop()

    url = build_url(unique_id)
    headers = get_headers(auth_token)

    with st.spinner("Consultando API..."):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
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
        if isinstance(data, (dict, list)):
            st.json(data)
        else:
            st.code(str(data))
        st.stop()

    # =========================
    # Secciones en limpio
    # =========================
    st.subheader("Información en limpio")

    shipment = get_first_shipment(data)

    if not shipment:
        st.warning("No se encontró información dentro de 'collection'.")
    else:
        order = shipment.get("order") if isinstance(shipment.get("order"), dict) else {}
        merchant = order.get("merchant") if isinstance(order.get("merchant"), dict) else {}

        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("### Envío")
            st.table(shipment_pretty(shipment))

        with c2:
            st.markdown("### Orden")
            st.table(order_pretty(order))

        with c3:
            st.markdown("### Comercio (Merchant)")
            if merchant:
                st.table(merchant_pretty(merchant))
            else:
                st.info("No viene información de merchant en el objeto order.")

    # =========================
    # JSON crudo completo
    # =========================
    st.subheader("JSON completo")
    if isinstance(data, (dict, list)):
        st.json(data)
    else:
        st.code(str(data))
