import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from threading import Thread
from flask import Flask

load_dotenv()
TOKEN = os.getenv("TOKEN")

# Servidor web pra manter online
app = Flask('')

@app.route('/')
def home():
    return "Bot online"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.invites = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
