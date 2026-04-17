import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional, Tuple

import stripe
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, request, send_file, send_from_directory, session
from werkzeug.utils import safe_join

_base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_base_dir, ".env"))


def _resolve_client_dir() -> str:
    """
    Prefer Vite output client/dist when it exists (contains built index.html).
    If CLIENT_DIR is set in .env, it wins. Otherwise auto-pick dist over raw client/.
    """
    explicit = os.getenv("CLIENT_DIR", "").strip()
    if explicit:
        return os.path.normpath(os.path.join(_base_dir, explicit))
    dist_path = os.path.join(_base_dir, "client", "dist")
    if os.path.isfile(os.path.join(dist_path, "index.html")):
        return os.path.normpath(dist_path)
    return os.path.normpath(os.path.join(_base_dir, "client"))


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY") or "dev-insecure-set-secret-key"

CLIENT_DIR = _resolve_client_dir()
_default_db = os.path.join(_base_dir, "payments.db")
DB_PATH = os.getenv("DB_PATH", _default_db)
_db_parent = os.path.dirname(DB_PATH)
if _db_parent:
    try:
        os.makedirs(_db_parent, exist_ok=True)
    except OSError:
        pass

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

_MPA_ENTRIES = ("thanks88", "payment-failed", "refund", "privacy", "terms")


def _resolved_archive_path() -> Optional[str]:
    """
    Local zip for paid download. Priority:
    1) ARCHIVE_PATH in .env (relative to project root or absolute)
    2) private/talky.zip
    3) talky.zip in project root (legacy)
    Relative ARCHIVE_PATH must stay under project root.
    """
    raw = (os.getenv("ARCHIVE_PATH") or "").strip()
    candidates: list[str] = []
    base_norm = os.path.normpath(_base_dir)

    if raw:
        p = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(_base_dir, raw))
        if not os.path.isabs(raw):
            try:
                if os.path.commonpath([base_norm, p]) != base_norm:
                    return None
            except ValueError:
                return None
        candidates.append(p)
    else:
        candidates.append(os.path.join(_base_dir, "private", "talky.zip"))
        candidates.append(os.path.join(_base_dir, "talky.zip"))

    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.R_OK):
            return path
    return None


def _archive_available() -> bool:
    return _resolved_archive_path() is not None or bool((os.getenv("ARCHIVE_URL") or "").strip())


def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                customer_email TEXT,
                amount INTEGER,
                currency TEXT,
                status TEXT,
                created_at TIMESTAMP,
                buyer_token TEXT
            )
            """
        )
        c.execute("PRAGMA table_info(payments)")
        cols = [row[1] for row in c.fetchall()]
        if "buyer_token" not in cols:
            c.execute("ALTER TABLE payments ADD COLUMN buyer_token TEXT")
        conn.commit()
    finally:
        conn.close()


def _session_email(stripe_session: dict) -> Optional[str]:
    details = stripe_session.get("customer_details") or {}
    return details.get("email") or stripe_session.get("customer_email")


def _buyer_token_from_stripe_session(stripe_session: dict) -> Optional[str]:
    meta = stripe_session.get("metadata") or {}
    v = meta.get("buyer_token")
    return str(v) if v is not None else None


def upsert_payment(stripe_session: dict, status: Optional[str] = None) -> None:
    session_id = stripe_session["id"]
    email = _session_email(stripe_session)
    amount_total = stripe_session.get("amount_total")
    currency = stripe_session.get("currency")
    payment_status = status if status is not None else stripe_session.get("payment_status")
    buyer_token = _buyer_token_from_stripe_session(stripe_session)
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO payments (session_id, customer_email, amount, currency, status, created_at, buyer_token)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                customer_email = COALESCE(excluded.customer_email, payments.customer_email),
                amount = COALESCE(excluded.amount, payments.amount),
                currency = COALESCE(excluded.currency, payments.currency),
                status = excluded.status,
                buyer_token = COALESCE(excluded.buyer_token, payments.buyer_token)
            """,
            (session_id, email, amount_total, currency, payment_status, now, buyer_token),
        )
        conn.commit()
    finally:
        conn.close()


def _verify_paid_checkout(cs_id: Optional[str]) -> Tuple[bool, str]:
    if not cs_id:
        return False, "Не удалось подтвердить покупку: нет идентификатора сессии."
    if not _archive_available():
        return False, "Архив не настроен: добавьте private/talky.zip или задайте ARCHIVE_PATH / ARCHIVE_URL в .env."
    our_token = session.get("buyer_token")
    if not our_token:
        return False, "Не удалось подтвердить покупку: обновите страницу и попробуйте снова."
    try:
        stripe_session = stripe.checkout.Session.retrieve(cs_id)
    except Exception:
        return False, "Не удалось подтвердить покупку: сессия не найдена."
    if stripe_session.payment_status != "paid":
        return False, "Оплата ещё не подтверждена или не выполнена."
    meta_token = _buyer_token_from_stripe_session(stripe_session)
    if meta_token != our_token:
        return False, "Не удалось подтвердить покупку в этом браузере."
    return True, ""


init_db()


@app.before_request
def ensure_buyer_token():
    if request.path == "/webhook":
        return None
    if "buyer_token" not in session:
        session["buyer_token"] = str(uuid.uuid4())
    return None


@app.route("/webhook", methods=["POST"])
def webhook_received():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return jsonify({"error": "Webhook secret not configured"}), 500

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        upsert_payment(obj)
    elif event_type == "checkout.session.async_payment_succeeded":
        upsert_payment(obj)
    elif event_type == "checkout.session.async_payment_failed":
        upsert_payment(obj, status="failed")

    return jsonify({"status": "success"}), 200


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    price_id = os.getenv("STRIPE_PRICE_ID")
    if not price_id:
        return jsonify({"error": "STRIPE_PRICE_ID is not set"}), 500

    base = os.getenv("PUBLIC_BASE_URL", "http://localhost:4242").rstrip("/")
    success_url = os.getenv(
        "SUCCESS_URL",
        f"{base}/thanks?session_id={{CHECKOUT_SESSION_ID}}",
    )
    cancel_url = os.getenv("CANCEL_URL", f"{base}/payment-failed/")

    buyer_token = session.get("buyer_token")
    if not buyer_token:
        return jsonify({"error": "Session expired; refresh the page"}), 400

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"buyer_token": buyer_token},
        )
        return jsonify({"id": checkout_session.id, "url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _thanks_denied(message: str) -> tuple[str, int]:
    return (
        f"<p>{message}</p><p><a href=\"/\">На главную</a></p>",
        200,
    )


@app.route("/thanks")
def thanks():
    cs_id = request.args.get("session_id")
    ok, err = _verify_paid_checkout(cs_id)
    if not ok:
        return _thanks_denied(err)
    assert cs_id is not None
    return redirect(f"/thanks88/?session_id={cs_id}", code=302)


@app.route("/download")
def download():
    cs_id = request.args.get("session_id")
    ok, err = _verify_paid_checkout(cs_id)
    if not ok:
        return _thanks_denied(err)
    local_path = _resolved_archive_path()
    if local_path:
        dl_name = os.getenv("ARCHIVE_DOWNLOAD_NAME") or os.path.basename(local_path)
        return send_file(
            local_path,
            as_attachment=True,
            download_name=dl_name,
            mimetype="application/zip",
        )
    archive_url = (os.getenv("ARCHIVE_URL") or "").strip()
    if archive_url:
        return redirect(archive_url, code=302)
    return _thanks_denied("Архив не найден на сервере.")


@app.route("/cancel")
def cancel():
    return redirect("/payment-failed/", code=302)


@app.route("/assets/<path:filename>")
def vite_assets(filename):
    assets_dir = os.path.join(CLIENT_DIR, "assets")
    if not os.path.isdir(assets_dir):
        abort(404)
    return send_from_directory(assets_dir, filename)


def _mpa_page(name: str):
    path = safe_join(CLIENT_DIR, name, "index.html")
    if path is None or not os.path.isfile(path):
        abort(404)
    return send_from_directory(os.path.join(CLIENT_DIR, name), "index.html")


for _slug in _MPA_ENTRIES:

    def _make_mpa_handler(slug: str):
        def handler():
            return _mpa_page(slug)

        handler.__name__ = f"mpa_{slug.replace('-', '_')}"
        return handler

    app.add_url_rule(f"/{_slug}/", f"mpa_{_slug}_slash", _make_mpa_handler(_slug))
    app.add_url_rule(f"/{_slug}/index.html", f"mpa_{_slug}_html", _make_mpa_handler(_slug))


@app.route("/client/<path:filename>")
def client_files(filename):
    return send_from_directory(CLIENT_DIR, filename)


@app.route("/")
def index():
    return send_from_directory(CLIENT_DIR, "index.html")


@app.route("/<path:path>")
def dist_public_file(path):
    if path.endswith("/") or path in _MPA_ENTRIES:
        abort(404)
    full = safe_join(CLIENT_DIR, path)
    if full is None or not os.path.isfile(full):
        abort(404)
    return send_from_directory(CLIENT_DIR, path)


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "4242"))
    host = os.getenv("APP_HOST", "127.0.0.1")
    app.run(host=host, port=port)
