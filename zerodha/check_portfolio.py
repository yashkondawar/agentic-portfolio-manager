"""Quick script to check Zerodha portfolio."""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from zerodha.client import ZerodhaClient

REQUEST_TOKEN = os.getenv("ZERODHA_REQUEST_TOKEN", "")

try:
    client = ZerodhaClient()

    # If not authenticated, try with request token from env or CLI arg
    if not client.is_authenticated:
        token = sys.argv[1] if len(sys.argv) > 1 else REQUEST_TOKEN
        if not token:
            print("No saved token. Provide request_token as argument:")
            print("  python -m zerodha.check_portfolio <request_token>")
            sys.exit(1)
        if not client.authenticate(token):
            print("Authentication failed!")
            sys.exit(1)

    print("Authenticated! Fetching portfolio...\n")

    holdings = client.get_holdings()
    if not holdings:
        print("No holdings found (empty portfolio).")
    else:
        header = f"{'Symbol':>15} | {'Qty':>5} | {'Avg Price':>12} | {'LTP':>12} | {'P&L':>12}"
        print(header)
        print("-" * len(header))
        total_pnl = 0
        total_invested = 0
        for h in holdings:
            sym = h.get("tradingsymbol", "")
            qty = h.get("quantity", 0)
            avg = h.get("average_price", 0)
            ltp = h.get("last_price", 0)
            pnl = h.get("pnl", 0)
            total_pnl += pnl
            total_invested += avg * qty
            print(f"{sym:>15} | {qty:>5} | Rs{avg:>10,.2f} | Rs{ltp:>10,.2f} | Rs{pnl:>10,.2f}")
        print("-" * len(header))
        print(f"{'TOTAL':>15} | {'':>5} | Rs{total_invested:>10,.0f} | {'':>12} | Rs{total_pnl:>10,.2f}")

    print(f"\nAvailable cash: Rs{client.get_available_cash():,.2f}")

except ValueError as e:
    print(f"Config error: {e}")
    print("Add ZERODHA_API_KEY and ZERODHA_API_SECRET to .env")
except Exception as e:
    print(f"Error: {e}")
