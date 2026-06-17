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
    # ── Registra as views persistentes ANTES de qualquer interação ──
    # Isso garante que os botões funcionem mesmo após reinício do bot
    from bot.convite import ViewPainelPrincipal, ViewCanais, _load_config_from_db, atualizar_cache

    bot.add_view(ViewPainelPrincipal())  # custom_ids fixos = sobrevive ao reinício
    bot.add_view(ViewCanais())           # botão "Voltar ao Painel" também persistente

    # Pré-carrega cache de invites e config de todos os servidores
    for guild in bot.guilds:
        await atualizar_cache(guild)
        await _load_config_from_db(guild.id)

    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"[BOT] {len(synced)} slash command(s) sincronizado(s).")
    except Exception as e:
        print(f"[BOT] Erro ao sincronizar slash commands: {e}")

    print(f"[BOT] Online como {bot.user} | {len(bot.guilds)} servidor(es)")

# ── Main ──────────────────────────────────────
async def main():
    async with bot:
        await bot.load_extension("bot.convite")
        await bot.start(TOKEN)

keep_alive()
asyncio.run(main())
