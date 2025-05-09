from flask import Flask, request, jsonify
import pandas as pd
import json
import asyncio
import websockets
import os

app = Flask(__name__)

SYMBOLS = {
    "boom1000": "BOOM1000",
    "crash1000": "CRASH1000",
    "boom500": "BOOM500",
    "crash500": "CRASH500",
    "boom600": "BOOM600",
    "crash600": "CRASH600"
}

DERIV_TOKEN = os.environ.get("DERIV_TOKEN")

async def fetch_candles(symbol, count=30):
    url = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({ "authorize": DERIV_TOKEN }))
        await ws.recv()

        await ws.send(json.dumps({
            "ticks_history": symbol,
            "style": "candles",
            "count": count,
            "granularity": 60,
            "end": "latest"
        }))
        response = await ws.recv()
        data = json.loads(response)
        return data.get("candles", [])

def calculate_indicators(candles):
    df = pd.DataFrame(candles)
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['open'] = df['open'].astype(float)

    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['rsi_14'] = 100 - (100 / (1 + rs))

    df['bb_middle'] = df['close'].rolling(20).mean()
    df['bb_upper'] = df['bb_middle'] + 2 * df['close'].rolling(20).std()
    df['bb_lower'] = df['bb_middle'] - 2 * df['close'].rolling(20).std()

    df['atr_14'] = (df['high'] - df['low']).rolling(14).mean()
    df['body_strength'] = abs(df['close'] - df['open']) / (df['high'] - df['low'])

    df = df.iloc[-30:].fillna(0)
    return df.to_dict(orient="records")

@app.route("/boomcrash", methods=["GET"])
def boomcrash():
    symbol_key = request.args.get("symbol", "").lower()
    if symbol_key not in SYMBOLS:
        return jsonify({"error": "Invalid symbol"}), 400

    symbol = SYMBOLS[symbol_key]
    candles = asyncio.run(fetch_candles(symbol))
    if not candles:
        return jsonify({"error": "No candle data"}), 500

    enriched = calculate_indicators(candles)
    return jsonify({
        "symbol": symbol,
        "latest": enriched[-1],
        "last_30": enriched
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
