"""Aplicación Flask; cada solicitud reconstruye una CPU aislada."""

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from emulator import Emulator, EmulatorError, MAX_STEPS

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100_000


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/api/execute")
def execute():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Enviá un objeto JSON válido."), 400
    try:
        result = Emulator(payload.get("code")).execute(payload.get("steps", MAX_STEPS))
    except EmulatorError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@app.errorhandler(HTTPException)
def http_error(error):
    if request.path.startswith("/api/"):
        return jsonify(error="Solicitud demasiado grande." if error.code == 413 else error.description), error.code
    return error


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
