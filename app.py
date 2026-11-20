import datetime
import io
import json
import os
import time

import requests
import streamlit as st
from fpdf import FPDF

st.set_page_config(
    page_title="Generador de Informes Técnicos",
    page_icon="⚙️",
    layout="wide",
)

PROVIDERS = {
    "Groq (Gratis)": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "models_url": "https://api.groq.com/openai/v1/models",
        "model": "auto",
        "secret_key": "GROQ_API_KEY",
        "cost_note": "Capa gratuita disponible en console.groq.com sin tarjeta.",
    },
    "Google Gemini (Gratis - 3.8 Flash)": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-3.8-flash",
        "secret_key": "GEMINI_API_KEY",
        "cost_note": "Capa gratuita disponible en aistudio.google.com.",
    },
    "OpenAI (gpt-4o-mini)": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "secret_key": "OPENAI_API_KEY",
        "cost_note": "Coste estimado por reporte con GPT-4o-mini: < $0.005 USD (~$0.10 MXN).",
    },
    "DeepSeek (deepseek-chat)": {
        "url": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-chat",
        "secret_key": "DEEPSEEK_API_KEY",
        "cost_note": "Coste estimado por reporte con DeepSeek: < $0.002 USD (~$0.04 MXN).",
    },
}


def clean_pdf_text(text: str) -> str:
    """Normaliza caracteres Unicode comunes a Latin-1 para evitar errores en fuentes estándar de FPDF."""
    if not text:
        return ""
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2022": "-",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2026": "...",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


class TechnicalReportPDF(FPDF):
    def __init__(
        self,
        department_name: str = "DEPARTAMENTO DE MANTENIMIENTO E INGENIERÍA",
        logo_bytes: bytes | None = None,
    ):
        super().__init__()
        self.department_name = clean_pdf_text(department_name)
        self.logo_bytes = logo_bytes

    def header(self):
        if self.logo_bytes:
            try:
                self.image(io.BytesIO(self.logo_bytes), x=10, y=8, h=14)
            except Exception:
                pass

        self.set_font("Helvetica", "B", 12)
        self.cell(
            0,
            8,
            clean_pdf_text("INFORME TÉCNICO DE INSPECCIÓN Y FALLA OPERATIVA"),
            border=False,
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )
        self.set_font("Helvetica", "I", 8)
        self.cell(
            0,
            4,
            self.department_name,
            border=False,
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )
        line_y = max(self.get_y() + 4, 24)
        self.line(10, line_y, 200, line_y)
        self.set_y(line_y + 4)

    def footer(self):
        self.set_y(-20)
        self.set_font("Helvetica", "", 8)
        self.cell(
            0,
            4,
            clean_pdf_text(f"Página {self.page_no()}"),
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.cell(
            0,
            4,
            clean_pdf_text("Documento generado automáticamente bajo certificación de inspección."),
            align="C",
        )


def get_secret_value(secret_name: str) -> str:
    """Obtiene un valor desde st.secrets o variables de entorno sin fallar si no existe secrets.toml."""
    try:
        if secret_name in st.secrets:
            return str(st.secrets[secret_name])
    except Exception:
        pass
    return os.getenv(secret_name, "")


def verify_gumroad_license(product_id: str, license_key: str) -> tuple[bool, str]:
    """Valida una clave de licencia contra la API oficial de Gumroad."""
    cleaned_key = license_key.strip()
    if not cleaned_key:
        return False, "Ingresa tu clave de licencia para descargar el PDF."

    cached = st.session_state.get("gumroad_cache", {})
    cache_key = f"{product_id}:{cleaned_key}"
    if cache_key in cached:
        return cached[cache_key]

    try:
        response = requests.post(
            "https://api.gumroad.com/v2/licenses/verify",
            data={
                "product_id": product_id,
                "license_key": cleaned_key,
            },
            timeout=15,
        )
        data = response.json()
    except Exception as exc:
        return False, f"No se pudo conectar con el servidor de licencias: {exc}"

    if not data.get("success"):
        result = (False, "Clave de licencia inválida o no encontrada.")
    else:
        purchase = data.get("purchase", {})
        if purchase.get("refunded") or purchase.get("chargebacked"):
            result = (False, "Esta licencia fue reembolsada o cancelada.")
        elif purchase.get("subscription_ended_at"):
            result = (False, "Tu suscripción ha finalizado. Renuévala para continuar.")
        else:
            result = (True, "Licencia activa y verificada.")

    st.session_state.setdefault("gumroad_cache", {})[cache_key] = result
    return result


def resolve_model_name(provider_cfg: dict, api_key: str) -> str:
    """Resuelve el nombre del modelo; si es 'auto', consulta los modelos disponibles en la API."""
    model = provider_cfg["model"]
    if model != "auto":
        return model

    cache = st.session_state.setdefault("resolved_models", {})
    models_url = provider_cfg.get("models_url", "")
    if models_url in cache:
        return cache[models_url]

    try:
        resp = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        ids = [m["id"] for m in resp.json().get("data", []) if "id" in m]
        # Filtrar modelos que no son de chat/texto
        excluded = ("whisper", "guard", "tts", "playai", "orpheus", "safeguard")
        chat_models = [m for m in ids if not any(ex in m.lower() for ex in excluded)]
        # Priorizar modelos Llama o Qwen grandes si existen
        for preferred in ("llama-3.3", "llama-3.1", "llama-4", "qwen", "gpt-oss", "llama"):
            for m in chat_models:
                if preferred in m.lower():
                    cache[models_url] = m
                    return m
        if chat_models:
            cache[models_url] = chat_models[0]
            return chat_models[0]
    except Exception:
        pass
    return "llama-3.1-8b-instant"


def generate_technical_analysis(
    provider_cfg: dict,
    api_key: str,
    asset_name: str,
    system: str,
    severity: str,
    rca_method: str,
    symptoms: str,
    readings: str,
    actions: str,
) -> dict | None:
    """Invoca la API del LLM para obtener la redacción técnica estandarizada en JSON."""
    rca_instruction = {
        "Causa Raíz Estándar (RCA)": (
            "Realiza un análisis técnico de causa raíz identificando causa inmediata, "
            "causa subyacente y factores contribuyentes."
        ),
        "5 Porqués": (
            "Estructura el análisis de causa raíz aplicando explícitamente la metodología "
            "de los 5 Porqués numerados del 1 al 5 hasta llegar a la causa raíz."
        ),
        "Ishikawa / 6M": (
            "Estructura el análisis de causa raíz evaluando los factores relevantes de las 6M "
            "(Maquinaria, Método, Material, Mano de Obra, Medio Ambiente, Medición)."
        ),
    }.get(rca_method, "Realiza un análisis técnico de causa raíz.")

    system_prompt = (
        "Eres un ingeniero jefe de maquinaria y perito en confiabilidad industrial. "
        "Redacta un informe técnico formal en español basado en los datos proporcionados, "
        "usando terminología técnica precisa y evitando explicaciones genéricas o relleno. "
        f"{rca_instruction} "
        "Debes responder estrictamente en formato JSON válido con las siguientes 4 claves de texto plano "
        "(valores en string, sin objetos anidados): "
        "'descripcion_falla', 'analisis_causa_raiz', 'acciones_correctivas_tomadas', 'recomendaciones_preventivas'."
    )

    user_payload = (
        f"Equipo: {asset_name}\n"
        f"Sistema: {system}\n"
        f"Severidad: {severity}\n"
        f"Método RCA solicitado: {rca_method}\n"
        f"Síntomas observados: {symptoms}\n"
        f"Lecturas de parámetros: {readings or 'No registradas'}\n"
        f"Acciones inmediatas: {actions or 'No registradas'}"
    )

    selected_model = resolve_model_name(provider_cfg, api_key)

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        for attempt in range(3):
            response = requests.post(
                provider_cfg["url"],
                headers=headers,
                json=payload,
                timeout=45,
            )
            if response.status_code in (429, 503) and attempt < 2:
                time.sleep(2)
                continue
            response.raise_for_status()
            parsed = response.json()
            content = parsed["choices"][0]["message"]["content"]
            return json.loads(content)
    except requests.exceptions.HTTPError as err:
        st.error(f"Error HTTP de la API ({err.response.status_code}): {err.response.text}")
    except Exception as exc:
        st.error(f"Error al procesar el análisis de ingeniería: {exc}")
    return None


def build_pdf(metadata: dict, content: dict, logo_bytes: bytes | None = None) -> bytes:
    """Compila el reporte final en PDF y retorna los bytes listos para descarga."""
    pdf = TechnicalReportPDF(department_name=metadata["department"], logo_bytes=logo_bytes)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    # Bloque de metadatos del equipo
    pdf.set_fill_color(240, 240, 240)
    start_y = pdf.get_y()
    pdf.rect(10, start_y, 190, 24, style="F")
    pdf.set_xy(12, start_y + 2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(95, 6, clean_pdf_text(f"EQUIPO: {metadata['asset'].upper()}"))
    pdf.cell(90, 6, clean_pdf_text(f"FECHA EVENTO: {metadata['date']}"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(12)
    pdf.cell(95, 6, clean_pdf_text(f"SISTEMA: {metadata['system'].upper()}"))
    pdf.cell(90, 6, clean_pdf_text(f"RESPONSABLE: {metadata['inspector']}"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(12)
    pdf.cell(95, 6, clean_pdf_text(f"SEVERIDAD: {metadata['severity'].upper()}"))
    pdf.cell(90, 6, clean_pdf_text(f"MÉTODO RCA: {metadata['rca_method']}"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(start_y + 28)

    sections = [
        ("1. DESCRIPCIÓN DEL EVENTO Y SÍNTOMAS", str(content.get("descripcion_falla", ""))),
        (f"2. ANÁLISIS DE CAUSA RAÍZ ({metadata['rca_method'].upper()})", str(content.get("analisis_causa_raiz", ""))),
        ("3. INTERVENCIONES Y CORRECCIONES REALIZADAS", str(content.get("acciones_correctivas_tomadas", ""))),
        ("4. ACCIONES PREVENTIVAS Y RECOMENDACIONES", str(content.get("recomendaciones_preventivas", ""))),
    ]

    for title, body in sections:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, clean_pdf_text(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)
        pdf.multi_cell(0, 5, clean_pdf_text(body))
        pdf.ln(3)

    # Verificar espacio antes de imprimir el bloque de firmas
    if pdf.get_y() > 240:
        pdf.add_page()

    pdf.ln(8)
    y_pos = pdf.get_y()
    pdf.line(20, y_pos + 14, 85, y_pos + 14)
    pdf.line(125, y_pos + 14, 190, y_pos + 14)

    pdf.set_xy(20, y_pos + 16)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(65, 4, clean_pdf_text("Firma de Quien Reporta"), align="C")

    pdf.set_xy(125, y_pos + 16)
    pdf.cell(65, 4, clean_pdf_text("Firma de Jefatura de Mantenimiento"), align="C")

    return bytes(pdf.output())


# --- Configuración de Licencia (Modo A vs Modo B) ---
GUMROAD_PRODUCT_ID = get_secret_value("GUMROAD_PRODUCT_ID").strip()
GUMROAD_CHECKOUT_URL = get_secret_value("GUMROAD_CHECKOUT_URL").strip()
license_required = bool(GUMROAD_PRODUCT_ID)

# --- Interfaz Principal ---
st.title("Generador de Reportes Técnicos con IA")
st.caption("Estandarización de partes de avería y análisis de causa raíz para ingeniería operativa.")

with st.sidebar:
    st.header("Configuración")
    provider_name = st.selectbox("Proveedor LLM:", list(PROVIDERS.keys()))
    provider_cfg = PROVIDERS[provider_name]

    default_key = get_secret_value(provider_cfg["secret_key"])
    custom_key = st.text_input(
        f"API Key de {provider_name.split(' ')[0]} (opcional si está en secrets):",
        type="password",
    )
    effective_key = custom_key.strip() if custom_key.strip() else default_key

    st.divider()
    st.subheader("Personalización del PDF")
    department_input = st.text_input(
        "Encabezado / Departamento:",
        value="DEPARTAMENTO DE MANTENIMIENTO E INGENIERÍA",
    )
    logo_upload = st.file_uploader("Logo de la empresa (PNG/JPG):", type=["png", "jpg", "jpeg"])
    logo_bytes = logo_upload.getvalue() if logo_upload else None

    if license_required:
        st.divider()
        st.subheader("Licencia de Activación")
        license_key_input = st.text_input("Clave de licencia (Gumroad):", type="password")
        is_licensed, license_msg = verify_gumroad_license(GUMROAD_PRODUCT_ID, license_key_input)
        if is_licensed:
            st.success(license_msg)
        else:
            st.warning(license_msg)
            if GUMROAD_CHECKOUT_URL:
                st.link_button("Adquirir Licencia", GUMROAD_CHECKOUT_URL)
    else:
        is_licensed = True

    st.divider()
    st.info(provider_cfg["cost_note"])

col1, col2 = st.columns(2)

with col1:
    st.subheader("Datos de la Falla")
    asset_input = st.text_input("Nombre del Activo / Máquina (*):", value="Motor Diésel Auxiliar No. 1")
    system_input = st.text_input("Sistema Afectado (*):", value="Sistema de Inyección de Combustible")
    inspector_input = st.text_input("Nombre / Cargo del Inspector:", value="Oficial de Guardia")

    subcol_a, subcol_b = st.columns(2)
    with subcol_a:
        date_input = st.date_input("Fecha de Ocurrencia:", value=datetime.date.today())
    with subcol_b:
        severity_input = st.selectbox("Severidad:", ["Alta", "Crítica", "Media", "Baja"])

    rca_method_input = st.selectbox(
        "Metodología de Análisis (RCA):",
        ["Causa Raíz Estándar (RCA)", "5 Porqués", "Ishikawa / 6M"],
    )

with col2:
    st.subheader("Detalles Operativos")
    symptoms_input = st.text_area(
        "Síntomas / Observaciones (*):",
        value="Caída repentina de RPM en carga, humo negro denso en escape, fluctuación de presión en el riel común.",
        height=110,
    )
    readings_input = st.text_input(
        "Lecturas / Parámetros anormales:",
        value="Presión de combustible a 140 bar (nominal: 220 bar), temp. escape a 480°C.",
    )
    actions_input = st.text_area(
        "Acciones ejecutadas en el sitio:",
        value="Parada manual de emergencia, purga de línea de retorno y sustitución de cartucho filtrante primario.",
        height=110,
    )

if st.button("Generar Informe Formal", type="primary"):
    missing_fields = []
    if not asset_input.strip():
        missing_fields.append("Nombre del Activo / Máquina")
    if not system_input.strip():
        missing_fields.append("Sistema Afectado")
    if not symptoms_input.strip():
        missing_fields.append("Síntomas / Observaciones")

    if missing_fields:
        st.warning(f"Completa los campos obligatorios: {', '.join(missing_fields)}.")
    elif not effective_key:
        st.warning("Se requiere una API Key para redactar el análisis técnico.")
    else:
        with st.spinner("Procesando análisis de ingeniería y estructurando documento..."):
            metadata = {
                "asset": asset_input.strip(),
                "system": system_input.strip(),
                "inspector": inspector_input.strip() or "No especificado",
                "date": str(date_input),
                "severity": severity_input,
                "rca_method": rca_method_input,
                "department": department_input.strip() or "DEPARTAMENTO DE MANTENIMIENTO E INGENIERÍA",
            }
            analysis = generate_technical_analysis(
                provider_cfg=provider_cfg,
                api_key=effective_key,
                asset_name=metadata["asset"],
                system=metadata["system"],
                severity=metadata["severity"],
                rca_method=metadata["rca_method"],
                symptoms=symptoms_input.strip(),
                readings=readings_input.strip(),
                actions=actions_input.strip(),
            )
            if analysis:
                st.session_state["last_report"] = {
                    "analysis": analysis,
                    "metadata": metadata,
                    "file_name": f"Informe_Falla_{metadata['asset'].replace(' ', '_')}_{metadata['date']}.pdf",
                }

if "last_report" in st.session_state:
    report = st.session_state["last_report"]
    analysis = report["analysis"]
    st.success("Análisis técnico generado exitosamente.")

    with st.expander("Previsualizar redacción estructurada", expanded=True):
        st.markdown(f"**1. Descripción de la Falla:**\n{analysis.get('descripcion_falla', '')}")
        st.markdown(f"**2. Análisis de Causa Raíz:**\n{analysis.get('analisis_causa_raiz', '')}")
        st.markdown(f"**3. Acciones Correctivas:**\n{analysis.get('acciones_correctivas_tomadas', '')}")
        st.markdown(f"**4. Recomendaciones Preventivas:**\n{analysis.get('recomendaciones_preventivas', '')}")

    if is_licensed:
        pdf_bytes = build_pdf(report["metadata"], analysis, logo_bytes=logo_bytes)
        st.download_button(
            label="Descargar Reporte en PDF Oficial",
            data=pdf_bytes,
            file_name=report["file_name"],
            mime="application/pdf",
        )
    else:
        st.info("Activa tu clave de licencia en la barra lateral para compilar y descargar el PDF oficial.")
