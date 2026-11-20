# Generador de Reportes de Falla e Inspección con IA

Aplicación web en **Streamlit** que transforma notas rápidas, síntomas operativos y lecturas de parámetros en un **Informe Técnico de Mantenimiento y Análisis de Causa Raíz (RCA)** en formato **PDF** listo para entrega y firma.

## Estructura del Proyecto

```text
report-generator/
├── app.py
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── secrets.toml
└── README.md
```

## Instalación y Ejecución Local (Windows)

1. Crear y activar el entorno virtual:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. Instalar dependencias:
   ```powershell
   pip install -r requirements.txt
   ```

3. Configurar tu API Key en `.streamlit/secrets.toml` (o ingresarla directamente en la barra lateral de la app):
   ```toml
   OPENAI_API_KEY = "sk-..."
   # Opcional si usas DeepSeek:
   DEEPSEEK_API_KEY = "sk-..."

   # Opcional para monetización con Gumroad (Modo A):
   # Si GUMROAD_PRODUCT_ID está vacío, la descarga PDF queda abierta (Modo B).
   GUMROAD_PRODUCT_ID = ""
   GUMROAD_CHECKOUT_URL = ""
   ```

4. Ejecutar la aplicación:
   ```powershell
   streamlit run app.py
   ```

## Despliegue en Streamlit Community Cloud

1. Sube el repositorio a GitHub (asegúrate de que `.streamlit/secrets.toml` y `venv/` permanezcan en `.gitignore`).
2. Entra a [share.streamlit.io](https://share.streamlit.io) y selecciona **New app**.
3. Elige tu repositorio, la rama `main` y el archivo principal `app.py`.
4. En **Advanced settings -> Secrets**, pega tu clave (`OPENAI_API_KEY` o `DEEPSEEK_API_KEY`).
5. Haz clic en **Deploy**.
