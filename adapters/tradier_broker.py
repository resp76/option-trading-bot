# Tradier adapter stub for option-trading-bot
# Place at adapters/tradier_broker.py and implement the methods the bot expects (quote, place_order, account, cancel, etc.)

import requests
import os

BASE_URL = "https://api.tradier.com/v1"

class TradierBroker:
    def __init__(self, token=None, account_id=None, base_url=None):
        self.token = token or os.environ.get('TRADIER_TOKEN')
        self.account_id = account_id or os.environ.get('TRADIER_ACCOUNT_ID')
        self.base_url = base_url or BASE_URL

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json'
        }

    def get_quote(self, symbol):
        url = f"{self.base_url}/markets/quotes"
        r = requests.get(url, params={'symbols': symbol}, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def place_option_order(self, order_payload):
        # implement according to bot's order schema
        url = f"{self.base_url}/accounts/{self.account_id}/orders"
        r = requests.post(url, json=order_payload, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def account_balances(self):
        url = f"{self.base_url}/accounts/{self.account_id}/balances"
        r = requests.get(url, headers=self._headers())
        r.raise_for_status()
        return r.json()
