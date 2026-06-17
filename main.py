import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from threading import Thread
from flask import Flask

load_dotenv()
TOKEN    = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "1465329771696361546"))

# ── Servidor web pra manter online no Render ──
app = Flask('')

@app.route('/')
def home():
    return "Bot FFZ online ✅"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# ── Intents ───────────────────────────────────
intents = discord.Intents.default()
intents.members         = True
intents.guilds          = True
intents.invites         = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[BOT] Online como {bot.user} | {len(bot.guilds)} servidor(es)")

# ── Main ──────────────────────────────────────
async def main():
    async with bot:
        await bot.load_extension("bot.convite")
        await bot.start(TOKEN)

keep_alive()
asyncio.run(main())
