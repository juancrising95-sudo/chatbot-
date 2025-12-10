
# app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
from urllib.parse import quote, urlencode  # quote para valores; urlencode para query

# --- Carga de variables de entorno (Render y local) ---
try:
    from dotenv import load_dotenv
    SECRET_FILE_PATH = '/etc/secrets/env'
    if os.path.exists(SECRET_FILE_PATH):
        load_dotenv(SECRET_FILE_PATH)   # En Render (archivo secreto)
    else:
        load_dotenv()                   # En tu PC (archivo .env si existe)
except Exception:
    pass
# --- Fin carga de entorno ---

# Instancia Flask y CORS
app = Flask(__name__)
CORS(app)  # abierto para la UI estática del MVP

# Rutas base de datos de empresas (JSON)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMPRESAS_DIR = os.path.join(BASE_DIR, "empresas")


def cargar_json(ruta):
    """
    Carga un archivo JSON si existe y es válido; si no, devuelve None.
    Evita que un JSON malformado rompa el endpoint y deja registro en logs.
    """
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] No se pudo parsear JSON en '{ruta}': {e}")
        return None


def leer_items(empresa_id, archivo):
    """
    Devuelve lista de items desde empresas/<empresa_id>/<archivo>.
    Acepta JSON con forma { "items": [...] } o directamente [ ... ].
    Si no existe o es inválido, devuelve [].
    """
    ruta = os.path.join(EMPRESAS_DIR, empresa_id, archivo)
    data = cargar_json(ruta)
    if data is None:
        return []
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, list):
        return data
    return []


# --------- ENDPOINTS informativos opcionales ---------
@app.route("/empresa/<empresa_id>/config", methods=["GET"])
def get_config(empresa_id):
    ruta = os.path.join(EMPRESAS_DIR, empresa_id, "config.json")
    data = cargar_json(ruta)
    if not data:
        return jsonify({"error": "Empresa no encontrada"}), 404
    return jsonify(data), 200


@app.route("/empresa/<empresa_id>/faq", methods=["GET"])
def get_faq(empresa_id):
    ruta = os.path.join(EMPRESAS_DIR, empresa_id, "faq.json")
    data = cargar_json(ruta)
    if not data:
        return jsonify({"error": "FAQ no encontrado"}), 404
    return jsonify(data), 200


@app.route("/empresa/<empresa_id>/promos", methods=["GET"])
def get_promos(empresa_id):
    ruta = os.path.join(EMPRESAS_DIR, empresa_id, "promos.json")
    data = cargar_json(ruta)
    if not data:
        return jsonify({"error": "Promos no encontradas"}), 404
    return jsonify(data), 200


# --------- CHAT (Contrato AURENSTAR) ---------
@app.route("/chat", methods=["POST"])
def chat():
    """
    Contrato AURENSTAR:
    - Listas: ACTION:PRECIOS / PRODUCTOS / PROMOS / FAQ
      Responde: {"ok": true, "reply": "<texto>", "data": {"items": [ ... ]}}
    - Ordenar: ACTION:ORDENAR, payload = { "item": "...", "qty": <int>, "email": "..." }
      Responde: {"ok": true, "reply": "Orden recibida: <item> x<qty>"}
    - Pagar: ACTION:PAGAR, payload = { "amount": <numero>, "description": "..." }
      Responde: {"ok": true, "reply": "Link de pago generado", "data": {"payment_link": "<URL>"}}
    """
    try:
        body = request.get_json(force=True) or {}
        message = (body.get("message") or "").strip()
        empresaid = (
            body.get("empresaid")
            or body.get("empresa_id")
            or request.args.get("empresaid")
            or request.args.get("empresa_id")
        )
        payload = body.get("payload") or {}

        if not message or not empresaid:
            return jsonify({"ok": False, "reply": "Faltan campos: message/empresaid"}), 400

        action = message.upper()

        # --- LISTAS ---
        if action == "ACTION:PRECIOS":
            items = leer_items(empresaid, "precios.json")
            return jsonify({"ok": True, "reply": "Lista de precios", "data": {"items": items}}), 200

        if action == "ACTION:PRODUCTOS":
            items = leer_items(empresaid, "productos.json")
            return jsonify({"ok": True, "reply": "Catálogo de productos", "data": {"items": items}}), 200

        if action == "ACTION:PROMOS":
            items = leer_items(empresaid, "promos.json")
            return jsonify({"ok": True, "reply": "Promociones vigentes", "data": {"items": items}}), 200

        if action == "ACTION:FAQ":
            items = leer_items(empresaid, "faq.json")
            return jsonify({"ok": True, "reply": "Preguntas frecuentes", "data": {"items": items}}), 200

        # --- ORDENAR ---
        if action == "ACTION:ORDENAR":
            item = str(payload.get("item", "")).strip()
            qty_raw = payload.get("qty", 0)
            try:
                qty = int(qty_raw)
            except Exception:
                qty = 0
            email = str(payload.get("email", "")).strip()

            if not item or qty <= 0:
                return jsonify({"ok": False, "reply": "Datos de la orden inválidos"}), 400

            return jsonify({"ok": True, "reply": f"Orden recibida: {item} x{qty}"}), 200

        # --- PAGAR ---
        if action == "ACTION:PAGAR":
            amount = payload.get("amount")
            description = str(payload.get("description", "")).strip()
            if amount is None or description == "":
                return jsonify({"ok": False, "reply": "Datos de pago incompletos"}), 400

            # Base del link desde config; si no existe, usar dominio por defecto
            cfg = cargar_json(os.path.join(EMPRESAS_DIR, empresaid, "config.json")) or {}
            base = cfg.get("linkPagoBase") or cfg.get("payment_base") or "https://pagos.aurenstar.com"

            # Construir query con urlencode y forzar %20 (quote_via=quote)
            monto_str = str(amount)
            query = urlencode({"monto": monto_str, "desc": description}, quote_via=quote)

            # Empresa en la ruta para distinguir
            payment_link = f"{base}/{empresaid}?{query}"
            # Guard contra escapes HTML inesperados
            payment_link = payment_link.replace("&amp;", "&")

            return jsonify({"ok": True, "reply": "Link de pago generado", "data": {"payment_link": payment_link}}), 200

        # --- Fallback ---
        return jsonify({"ok": False, "reply": f"Acción no soportada: {action}"}), 400

    except Exception as e:
        print(f"[ERROR /chat] {e}")
        return jsonify({"ok": False, "reply": "Error interno", "detail": str(e)}), 500


# --------- SALUD Y RAÍZ ---------
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@app.route("/", methods=["GET"])
def root():
    email_config = bool(os.getenv("EMAIL_USER"))
    return jsonify({"status": "Backend correcto", "email_configurado": email_config}), 200


# --------- MAIN LOCAL (en Render se usa gunicorn) ---------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
