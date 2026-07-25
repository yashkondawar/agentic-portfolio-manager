"""
Flask-based auto-login server for Zerodha Kite Connect.

Starts a local server that captures the request_token from Zerodha's redirect
callback, automatically exchanges it for an access_token, and shuts down.

Usage:
    python -m zerodha.auth_server
    # Opens browser → login → callback captured → token saved → server stops

Or programmatically:
    from zerodha.auth_server import run_auth_flow
    client = run_auth_flow()  # Returns authenticated ZerodhaClient
"""

import os
import sys
import time
import logging
import threading
import webbrowser
from typing import Optional

from flask import Flask, request
from werkzeug.serving import make_server

logger = logging.getLogger(__name__)

# Default callback port
CALLBACK_PORT = int(os.getenv("ZERODHA_CALLBACK_PORT", "5678"))
CALLBACK_URL = f"http://127.0.0.1:{CALLBACK_PORT}/callback"

app = Flask(__name__)
_captured_token: Optional[str] = None
_auth_complete = threading.Event()


@app.route("/callback")
def callback():
    """Handle Zerodha redirect with request_token."""
    global _captured_token

    request_token = request.args.get("request_token")
    status = request.args.get("status")

    if status == "success" and request_token:
        _captured_token = request_token
        _auth_complete.set()
        return """
        <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h2>✅ Zerodha Login Successful!</h2>
        <p>Token captured. You can close this tab.</p>
        <script>setTimeout(function(){ window.close(); }, 2000);</script>
        </body></html>
        """
    else:
        return """
        <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h2>❌ Login Failed</h2>
        <p>Status: {}</p>
        </body></html>
        """.format(status or "unknown")


def run_auth_flow(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    timeout: int = 120,
):
    """
    Run the complete auth flow:
    1. Start Flask callback server
    2. Open browser to Kite login
    3. Wait for callback with request_token
    4. Exchange for access_token
    5. Return authenticated ZerodhaClient

    Args:
        api_key: Zerodha API key (defaults to env var)
        api_secret: Zerodha API secret (defaults to env var)
        timeout: Max seconds to wait for login (default 120)

    Returns:
        Authenticated ZerodhaClient instance
    """
    from zerodha.client import ZerodhaClient

    global _captured_token, _auth_complete
    _captured_token = None
    _auth_complete.clear()

    api_key = api_key or os.getenv("ZERODHA_API_KEY", "")
    api_secret = api_secret or os.getenv("ZERODHA_API_SECRET", "")

    if not api_key or not api_secret:
        raise ValueError("ZERODHA_API_KEY and ZERODHA_API_SECRET required")

    client = ZerodhaClient(api_key=api_key, api_secret=api_secret)

    # If already authenticated (saved token), skip login
    if client.is_authenticated:
        logger.info("[AUTH] Already authenticated with saved token")
        return client

    # Use a controllable server so the callback port is released after login.
    server = make_server("127.0.0.1", CALLBACK_PORT, app)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)  # Let server start

    try:
        # The redirect URL must match CALLBACK_URL in the Kite Connect app.
        login_url = client.login_url
        logger.info("[AUTH] Opening browser for Zerodha login...")
        logger.info("[AUTH] Redirect URL (configure in Kite app): %s", CALLBACK_URL)
        webbrowser.open(login_url)

        print(f"\nWaiting for Zerodha login (timeout: {timeout}s)...")
        print(f"   If browser didn't open, visit: {login_url}\n")

        success = _auth_complete.wait(timeout=timeout)
        if not success or not _captured_token:
            raise TimeoutError(
                f"Login timed out after {timeout}s. "
                "Ensure your Kite app redirect URL is set to: " + CALLBACK_URL
            )

        logger.info("[AUTH] Request token captured, exchanging for access token...")
        if not client.authenticate(_captured_token):
            raise RuntimeError("Failed to exchange request_token for access_token")
        print("Zerodha authentication successful!")
        return client
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def run_manual_auth(request_token: Optional[str] = None):
    """
    Manual auth flow — provide request_token directly.

    Args:
        request_token: The request_token from Zerodha redirect URL.
                      If None, reads from ZERODHA_REQUEST_TOKEN env var.
    """
    from zerodha.client import ZerodhaClient

    token = request_token or os.getenv("ZERODHA_REQUEST_TOKEN", "")
    if not token:
        raise ValueError(
            "Provide request_token or set ZERODHA_REQUEST_TOKEN env var. "
            "Get it by visiting the login URL and copying from redirect."
        )

    client = ZerodhaClient()
    if client.is_authenticated:
        logger.info("[AUTH] Already authenticated")
        return client

    if client.authenticate(token):
        return client
    else:
        raise RuntimeError("Authentication failed with provided request_token")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

    from dotenv import load_dotenv
    load_dotenv()

    try:
        client = run_auth_flow()
        profile = client.get_profile()
        print(f"\nLogged in as: {profile.get('user_name', 'N/A')}")
        print(f"Available cash: Rs {client.get_available_cash():,.2f}")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
