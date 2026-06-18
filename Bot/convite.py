import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
import os
import re
import random
from datetime import datetime

# ───────────────────────────────────────────────
#  CONFIGURAÇÕES PADRÃO
# ───────────────────────────────────────────────
DB_PATH   = os.getenv("DB_PATH", "data/invites.db")
GUILD_ID  = int(os.getenv("GUILD_ID", "1465329771696361546"))
FFZ_THUMBNAIL = "https://i.imgur.com/gLKi0lg.jpeg"

invites_cache = {}
_config_cache: dict[int, dict] = {}

DEFAULT_CONFIG = {
    "join_channel_id": None, "leave_channel_id": None, "log_channel_id": None,
    "join_title": "🔵 NOVO RECRUTA NA ÁREA",
    "join_body": "👤 **Membro**\n{member}\n`{username}`\n\n🎯 **Recrutado por**\n{inviter}\n\n📊 **Total de convites**\n`{total}`",
    "join_color": "5865F2", "join_banner": "",
    "leave_title": "😔 RECRUTA ABANDONOU O POSTO",
    "leave_body": "👤 **Membro**\n`{username}`\n\n🎯 **Foi recrutado por**\n{inviter}",
    "leave_color": "e74c3c", "leave_banner": "",
    "log_title": "📋 LOG DE CONVITES FFZ", "log_color": "5865F2",
    "emoji_join": "🔵", "emoji_leave": "😔", "emoji_inviter": "🎯",
    "emoji_stats": "📊", "emoji_member": "👤",
    "footer_text": "FFZ E-SPORTS | {count} membros",
    # Anti-Raid
    "antilink_enabled": 0,
    "antilink_msg": "🚫 {member}, links não são permitidos aqui!",
    "antilink_log_channel_id": None,
    "bad_words_enabled": 0,
    "bad_words_list": "",
    "bad_words_msg": "⚠️ {member}, esse tipo de linguagem não é permitida!",
    "antiraid_enabled": 0,
    "antiraid_joins": 5,
    "antiraid_seconds": 10,
    "antiraid_action": "kick",
    "antiraid_log_channel_id": None,
    "mod_log_channel_id": None,
}

# ── Anti-raid join tracker (em memória) ──
_raid_tracker: dict[int, list] = {}  # guild_id -> [timestamps]

# ───────────────────────────────────────────────
#  BANCO DE DADOS
# ───────────────────────────────────────────────
async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invites_data (
                guild_id   INTEGER,
                user_id    INTEGER,
                inviter_id INTEGER,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id                INTEGER PRIMARY KEY,
                join_channel_id         INTEGER,
                leave_channel_id        INTEGER,
                log_channel_id          INTEGER,
                join_title              TEXT DEFAULT '🔵 NOVO RECRUTA NA ÁREA',
                join_body               TEXT DEFAULT '👤 **Membro**\n{member}\n`{username}`\n\n🎯 **Recrutado por**\n{inviter}\n\n📊 **Total de convites**\n`{total}`',
                join_color              TEXT DEFAULT '5865F2',
                join_banner             TEXT DEFAULT '',
                leave_title             TEXT DEFAULT '😔 RECRUTA ABANDONOU O POSTO',
                leave_body              TEXT DEFAULT '👤 **Membro**\n`{username}`\n\n🎯 **Foi recrutado por**\n{inviter}',
                leave_color             TEXT DEFAULT 'e74c3c',
                leave_banner            TEXT DEFAULT '',
                log_title               TEXT DEFAULT '📋 LOG DE CONVITES FFZ',
                log_color               TEXT DEFAULT '5865F2',
                emoji_join              TEXT DEFAULT '🔵',
                emoji_leave             TEXT DEFAULT '😔',
                emoji_inviter           TEXT DEFAULT '🎯',
                emoji_stats             TEXT DEFAULT '📊',
                emoji_member            TEXT DEFAULT '👤',
                footer_text             TEXT DEFAULT 'FFZ E-SPORTS | {count} membros',
                antilink_enabled        INTEGER DEFAULT 0,
                antilink_msg            TEXT DEFAULT '🚫 {member}, links não são permitidos aqui!',
                antilink_log_channel_id INTEGER,
                bad_words_enabled       INTEGER DEFAULT 0,
                bad_words_list          TEXT DEFAULT '',
                bad_words_msg           TEXT DEFAULT '⚠️ {member}, esse tipo de linguagem não é permitida!',
                antiraid_enabled        INTEGER DEFAULT 0,
                antiraid_joins          INTEGER DEFAULT 5,
                antiraid_seconds        INTEGER DEFAULT 10,
                antiraid_action         TEXT DEFAULT 'kick',
                antiraid_log_channel_id INTEGER,
                mod_log_channel_id      INTEGER
            )
        """)
        # Auto-roles table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auto_roles (
                guild_id INTEGER,
                role_id  INTEGER,
                PRIMARY KEY (guild_id, role_id)
            )
        """)
        # Sorteios table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sorteios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER,
                channel_id  INTEGER,
                message_id  INTEGER,
                titulo      TEXT,
                descricao   TEXT,
                premio      TEXT,
                emoji       TEXT DEFAULT '🎉',
                cor         TEXT DEFAULT '5865F2',
                banner      TEXT DEFAULT '',
                vencedores  INTEGER DEFAULT 1,
                criado_por  INTEGER,
                encerrado   INTEGER DEFAULT 0,
                criado_em   TEXT
            )
        """)
        # Eventos table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER,
                channel_id  INTEGER,
                message_id  INTEGER,
                titulo      TEXT,
                descricao   TEXT,
                local       TEXT DEFAULT '',
                emoji       TEXT DEFAULT '📅',
                cor         TEXT DEFAULT '5865F2',
                banner      TEXT DEFAULT '',
                data_evento TEXT DEFAULT '',
                criado_por  INTEGER,
                encerrado   INTEGER DEFAULT 0,
                criado_em   TEXT
            )
        """)
        await db.commit()


# ───────────────────────────────────────────────
#  HELPERS DE CONFIG
# ───────────────────────────────────────────────
async def get_config(guild_id: int) -> dict:
    if guild_id in _config_cache:
        return _config_cache[guild_id]
    return await _load_config_from_db(guild_id)


async def _load_config_from_db(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
    cfg = dict(row) if row else {"guild_id": guild_id, **DEFAULT_CONFIG}
    _config_cache[guild_id] = cfg
    return cfg


async def set_config(guild_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
        for key, value in kwargs.items():
            await db.execute(f"UPDATE guild_config SET {key} = ? WHERE guild_id = ?", (value, guild_id))
        await db.commit()
    if guild_id in _config_cache:
        _config_cache[guild_id].update(kwargs)
    else:
        await _load_config_from_db(guild_id)


def hex_to_int(hex_str: str) -> int:
    return int(hex_str.lstrip("#"), 16)

def build_footer(cfg: dict, guild: discord.Guild) -> str:
    return cfg["footer_text"].replace("{count}", str(guild.member_count))

def build_embed(title, body, color_hex, banner, footer, thumbnail_url=None):
    embed = discord.Embed(description=body, color=hex_to_int(color_hex))
    embed.set_author(name=title)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text=footer)
    return embed


# ───────────────────────────────────────────────
#  CACHE DE INVITES
# ───────────────────────────────────────────────
async def atualizar_cache(guild: discord.Guild):
    try:
        invites_cache[guild.id] = await guild.invites()
    except Exception as e:
        print(f"[CONVITE] Erro ao atualizar cache: {e}")
        invites_cache[guild.id] = []


# ───────────────────────────────────────────────
#  AUTO-ROLES HELPERS
# ───────────────────────────────────────────────
async def get_auto_roles(guild_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT role_id FROM auto_roles WHERE guild_id = ?", (guild_id,))
        rows = await cursor.fetchall()
    return [r[0] for r in rows]

async def add_auto_role(guild_id: int, role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO auto_roles (guild_id, role_id) VALUES (?, ?)", (guild_id, role_id))
        await db.commit()

async def remove_auto_role(guild_id: int, role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM auto_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
        await db.commit()


# ───────────────────────────────────────────────
#  MODALS — ORIGINAIS (sem alteração)
# ───────────────────────────────────────────────
class ModalMensagemEntrada(discord.ui.Modal, title="✏️ Mensagem de Entrada"):
    def __init__(self, cfg):
        super().__init__()
        self.join_title = discord.ui.TextInput(
            label="Título da embed",
            placeholder="Ex: 🔵 NOVO RECRUTA NA ÁREA",
            max_length=100,
            default=cfg.get("join_title", ""),
        )
        self.join_body = discord.ui.TextInput(
            label="Corpo ({member} {username} {inviter} {total})",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            default=cfg.get("join_body", ""),
        )
        self.join_color = discord.ui.TextInput(
            label="Cor da embed (hex sem #)",
            placeholder="5865F2",
            max_length=6,
            required=False,
            default=cfg.get("join_color", "5865F2"),
        )
        self.join_banner = discord.ui.TextInput(
            label="URL do banner (opcional)",
            placeholder="https://i.imgur.com/...",
            required=False,
            max_length=300,
            default=cfg.get("join_banner", ""),
        )
        self.add_item(self.join_title)
        self.add_item(self.join_body)
        self.add_item(self.join_color)
        self.add_item(self.join_banner)

    async def on_submit(self, interaction: discord.Interaction):
        await set_config(interaction.guild_id,
            join_title=self.join_title.value, join_body=self.join_body.value,
            join_color=self.join_color.value or "5865F2", join_banner=self.join_banner.value)
        await interaction.response.send_message("✅ Mensagem de **entrada** atualizada!", ephemeral=True)


class ModalMensagemSaida(discord.ui.Modal, title="✏️ Mensagem de Saída"):
    def __init__(self, cfg):
        super().__init__()
        self.leave_title = discord.ui.TextInput(
            label="Título da embed",
            placeholder="Ex: 😔 RECRUTA ABANDONOU O POSTO",
            max_length=100,
            default=cfg.get("leave_title", ""),
        )
        self.leave_body = discord.ui.TextInput(
            label="Conteúdo ({username} {inviter})",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            default=cfg.get("leave_body", ""),
        )
        self.leave_color = discord.ui.TextInput(
            label="Cor da embed (hex sem #)",
            placeholder="e74c3c",
            max_length=6,
            required=False,
            default=cfg.get("leave_color", "e74c3c"),
        )
        self.leave_banner = discord.ui.TextInput(
            label="URL do banner (opcional)",
            placeholder="https://i.imgur.com/...",
            required=False,
            max_length=300,
            default=cfg.get("leave_banner", ""),
        )
        self.add_item(self.leave_title)
        self.add_item(self.leave_body)
        self.add_item(self.leave_color)
        self.add_item(self.leave_banner)

    async def on_submit(self, interaction: discord.Interaction):
        await set_config(interaction.guild_id,
            leave_title=self.leave_title.value, leave_body=self.leave_body.value,
            leave_color=self.leave_color.value or "e74c3c", leave_banner=self.leave_banner.value)
        await interaction.response.send_message("✅ Mensagem de **saída** atualizada!", ephemeral=True)


class ModalEmojis(discord.ui.Modal, title="😀 Personalizar Emojis"):
    def __init__(self, cfg):
        super().__init__()
        self.emoji_join = discord.ui.TextInput(
            label="Emoji de Entrada",
            placeholder="🔵 ou <:nome:ID>",
            max_length=50,
            default=cfg.get("emoji_join", "🔵"),
        )
        self.emoji_leave = discord.ui.TextInput(
            label="Emoji de Saída",
            placeholder="😔 ou <:nome:ID>",
            max_length=50,
            default=cfg.get("emoji_leave", "😔"),
        )
        self.emoji_inviter = discord.ui.TextInput(
            label="Emoji de Recrutador",
            placeholder="🎯 ou <:nome:ID>",
            max_length=50,
            default=cfg.get("emoji_inviter", "🎯"),
        )
        self.emoji_stats = discord.ui.TextInput(
            label="Emoji de Estatísticas",
            placeholder="📊 ou <:nome:ID>",
            max_length=50,
            default=cfg.get("emoji_stats", "📊"),
        )
        self.emoji_member = discord.ui.TextInput(
            label="Emoji de Membro",
            placeholder="👤 ou <:nome:ID>",
            max_length=50,
            default=cfg.get("emoji_member", "👤"),
        )
        self.add_item(self.emoji_join)
        self.add_item(self.emoji_leave)
        self.add_item(self.emoji_inviter)
        self.add_item(self.emoji_stats)
        self.add_item(self.emoji_member)

    async def on_submit(self, interaction: discord.Interaction):
        await set_config(interaction.guild_id,
            emoji_join=self.emoji_join.value, emoji_leave=self.emoji_leave.value,
            emoji_inviter=self.emoji_inviter.value, emoji_stats=self.emoji_stats.value,
            emoji_member=self.emoji_member.value)
        await interaction.response.send_message("✅ Emojis atualizados!", ephemeral=True)


class ModalFooter(discord.ui.Modal, title="📝 Personalizar Rodapé"):
    def __init__(self, cfg):
        super().__init__()
        self.footer_text = discord.ui.TextInput(
            label="Rodapé (use {count} para nº de membros)",
            placeholder="FFZ E-SPORTS | {count} membros",
            max_length=100,
            default=cfg.get("footer_text", "FFZ E-SPORTS | {count} membros"),
        )
        self.add_item(self.footer_text)

    async def on_submit(self, interaction: discord.Interaction):
        await set_config(interaction.guild_id, footer_text=self.footer_text.value)
        await interaction.response.send_message("✅ Rodapé atualizado!", ephemeral=True)


# ───────────────────────────────────────────────
#  MODALS — NOVOS
# ───────────────────────────────────────────────

# ── Anti-Link ──
class ModalAntiLink(discord.ui.Modal, title="🔗 Configurar Anti-Link"):
    def __init__(self, cfg):
        super().__init__()
        self.msg = discord.ui.TextInput(
            label="Mensagem ao detectar link ({member})",
            style=discord.TextStyle.paragraph,
            placeholder="🚫 {member}, links não são permitidos aqui!",
            max_length=500,
            default=cfg.get("antilink_msg", "🚫 {member}, links não são permitidos aqui!"),
        )
        self.add_item(self.msg)

    async def on_submit(self, interaction: discord.Interaction):
        await set_config(interaction.guild_id, antilink_msg=self.msg.value)
        await interaction.response.send_message("✅ Mensagem anti-link atualizada!", ephemeral=True)


# ── Anti Palavras ──
class ModalBadWords(discord.ui.Modal, title="🤬 Configurar Anti Palavras"):
    def __init__(self, cfg):
        super().__init__()
        self.words = discord.ui.TextInput(
            label="Palavras proibidas (separadas por vírgula)",
            style=discord.TextStyle.paragraph,
            placeholder="palavra1, palavra2, palavra3",
            max_length=1000,
            required=False,
            default=cfg.get("bad_words_list", ""),
        )
        self.msg = discord.ui.TextInput(
            label="Mensagem ao detectar palavra ({member})",
            style=discord.TextStyle.paragraph,
            placeholder="⚠️ {member}, esse tipo de linguagem não é permitida!",
            max_length=500,
            default=cfg.get("bad_words_msg", "⚠️ {member}, esse tipo de linguagem não é permitida!"),
        )
        self.add_item(self.words)
        self.add_item(self.msg)

    async def on_submit(self, interaction: discord.Interaction):
        await set_config(interaction.guild_id,
            bad_words_list=self.words.value,
            bad_words_msg=self.msg.value)
        await interaction.response.send_message("✅ Anti palavras pesadas atualizado!", ephemeral=True)


# ── Anti-Raid ──
class ModalAntiRaid(discord.ui.Modal, title="🛡️ Configurar Anti-Raid"):
    def __init__(self, cfg):
        super().__init__()
        self.joins = discord.ui.TextInput(
            label="Nº de entradas para detectar raid",
            placeholder="5",
            max_length=3,
            default=str(cfg.get("antiraid_joins", 5)),
        )
        self.seconds = discord.ui.TextInput(
            label="Janela de tempo (em segundos)",
            placeholder="10",
            max_length=4,
            default=str(cfg.get("antiraid_seconds", 10)),
        )
        self.action = discord.ui.TextInput(
            label="Ação: kick ou ban",
            placeholder="kick",
            max_length=4,
            default=cfg.get("antiraid_action", "kick"),
        )
        self.add_item(self.joins)
        self.add_item(self.seconds)
        self.add_item(self.action)

    async def on_submit(self, interaction: discord.Interaction):
        action = self.action.value.lower().strip()
        if action not in ("kick", "ban"):
            action = "kick"
        try:
            joins = int(self.joins.value)
            seconds = int(self.seconds.value)
        except ValueError:
            joins, seconds = 5, 10
        await set_config(interaction.guild_id,
            antiraid_joins=joins,
            antiraid_seconds=seconds,
            antiraid_action=action)
        await interaction.response.send_message(
            f"✅ Anti-Raid configurado: **{joins}** entradas em **{seconds}s** → `{action}`", ephemeral=True)


# ── Criar Sorteio ──
class ModalCriarSorteio(discord.ui.Modal, title="🎉 Criar Sorteio"):
    def __init__(self):
        super().__init__()
        self.titulo = discord.ui.TextInput(label="Título do sorteio", placeholder="🎉 SORTEIO FFZ", max_length=100)
        self.premio = discord.ui.TextInput(label="Prêmio", placeholder="Ex: Nitro Discord, Gift Card...", max_length=200)
        self.descricao = discord.ui.TextInput(
            label="Descrição (opcional)",
            style=discord.TextStyle.paragraph,
            placeholder="Detalhes do sorteio...",
            required=False, max_length=800)
        self.vencedores = discord.ui.TextInput(label="Número de vencedores", placeholder="1", max_length=2, default="1")
        self.personalizacao = discord.ui.TextInput(
            label="Emoji | Cor hex | URL Banner (separados por |)",
            placeholder="🎉 | FF5733 | https://i.imgur.com/...",
            required=False, max_length=400)
        self.add_item(self.titulo)
        self.add_item(self.premio)
        self.add_item(self.descricao)
        self.add_item(self.vencedores)
        self.add_item(self.personalizacao)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            vencedores = max(1, int(self.vencedores.value or "1"))
        except ValueError:
            vencedores = 1

        emoji, cor, banner = "🎉", "5865F2", ""
        if self.personalizacao.value:
            partes = [p.strip() for p in self.personalizacao.value.split("|")]
            if len(partes) >= 1 and partes[0]: emoji = partes[0]
            if len(partes) >= 2 and partes[1]: cor = partes[1].lstrip("#")
            if len(partes) >= 3 and partes[2]: banner = partes[2]

        cfg = await get_config(interaction.guild_id)
        embed = discord.Embed(
            title=f"{emoji} {self.titulo.value}",
            color=hex_to_int(cor)
        )
        embed.add_field(name="🏆 Prêmio", value=self.premio.value, inline=False)
        if self.descricao.value:
            embed.add_field(name="📋 Descrição", value=self.descricao.value, inline=False)
        embed.add_field(name="🏅 Vencedores", value=f"`{vencedores}`", inline=True)
        embed.add_field(name="👤 Criado por", value=interaction.user.mention, inline=True)
        embed.add_field(name="\u200b", value=f"**Reaja com {emoji} para participar!**", inline=False)
        if banner:
            embed.set_image(url=banner)
        embed.set_footer(text=build_footer(cfg, interaction.guild))
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

        canal = interaction.channel
        await interaction.response.send_message("✅ Sorteio criado!", ephemeral=True)
        msg = await canal.send(embed=embed)
        try:
            await msg.add_reaction(emoji)
        except Exception:
            await msg.add_reaction("🎉")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO sorteios (guild_id, channel_id, message_id, titulo, descricao, premio, emoji, cor, banner, vencedores, criado_por, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (interaction.guild_id, canal.id, msg.id, self.titulo.value, self.descricao.value,
                 self.premio.value, emoji, cor, banner, vencedores, interaction.user.id,
                 datetime.utcnow().isoformat()))
            await db.commit()


# ── Encerrar Sorteio ──
class ModalEncerrarSorteio(discord.ui.Modal, title="🔚 Encerrar Sorteio"):
    def __init__(self):
        super().__init__()
        self.sorteio_id = discord.ui.TextInput(
            label="ID do sorteio (use /sorteios para ver)",
            placeholder="Ex: 1",
            max_length=10)
        self.add_item(self.sorteio_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            sid = int(self.sorteio_id.value.strip())
        except ValueError:
            await interaction.followup.send("❌ ID inválido.", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM sorteios WHERE id = ? AND guild_id = ? AND encerrado = 0",
                (sid, interaction.guild_id))
            sorteio = await cursor.fetchone()

        if not sorteio:
            await interaction.followup.send("❌ Sorteio não encontrado ou já encerrado.", ephemeral=True)
            return

        canal = interaction.guild.get_channel(sorteio["channel_id"])
        vencedor_mention = "`Nenhum participante`"
        if canal:
            try:
                msg = await canal.fetch_message(sorteio["message_id"])
                reacao = discord.utils.get(msg.reactions, emoji=sorteio["emoji"])
                if not reacao:
                    reacao = discord.utils.get(msg.reactions, emoji="🎉")
                if reacao:
                    usuarios = [u async for u in reacao.users() if not u.bot]
                    if usuarios:
                        qtd = min(sorteio["vencedores"], len(usuarios))
                        escolhidos = random.sample(usuarios, qtd)
                        vencedor_mention = " | ".join(u.mention for u in escolhidos)
            except Exception as e:
                print(f"[SORTEIO] Erro ao buscar reações: {e}")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE sorteios SET encerrado = 1 WHERE id = ?", (sid,))
            await db.commit()

        cfg = await get_config(interaction.guild_id)
        embed_resultado = discord.Embed(
            title=f"🏆 RESULTADO — {sorteio['titulo']}",
            description=f"**Prêmio:** {sorteio['premio']}\n\n🎊 **Vencedor(es):** {vencedor_mention}",
            color=hex_to_int(sorteio["cor"])
        )
        embed_resultado.set_footer(text=build_footer(cfg, interaction.guild))
        if canal:
            await canal.send(embed=embed_resultado)
        await interaction.followup.send(f"✅ Sorteio **#{sid}** encerrado! Vencedor(es): {vencedor_mention}", ephemeral=True)


# ── Criar Evento ──
class ModalCriarEvento(discord.ui.Modal, title="📅 Criar Evento"):
    def __init__(self):
        super().__init__()
        self.titulo = discord.ui.TextInput(label="Título do evento", placeholder="🏆 CAMPEONATO FFZ", max_length=100)
        self.descricao = discord.ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            placeholder="Detalhes, regras, informações...",
            max_length=800)
        self.data = discord.ui.TextInput(
            label="Data e Hora",
            placeholder="Ex: 25/12/2025 às 20:00",
            max_length=50, required=False)
        self.local = discord.ui.TextInput(
            label="Local / Plataforma",
            placeholder="Ex: Discord, Servidor FFZ, Online",
            max_length=100, required=False)
        self.personalizacao = discord.ui.TextInput(
            label="Emoji | Cor hex | URL Banner (separados por |)",
            placeholder="📅 | 5865F2 | https://i.imgur.com/...",
            required=False, max_length=400)
        self.add_item(self.titulo)
        self.add_item(self.descricao)
        self.add_item(self.data)
        self.add_item(self.local)
        self.add_item(self.personalizacao)

    async def on_submit(self, interaction: discord.Interaction):
        emoji, cor, banner = "📅", "5865F2", ""
        if self.personalizacao.value:
            partes = [p.strip() for p in self.personalizacao.value.split("|")]
            if len(partes) >= 1 and partes[0]: emoji = partes[0]
            if len(partes) >= 2 and partes[1]: cor = partes[1].lstrip("#")
            if len(partes) >= 3 and partes[2]: banner = partes[2]

        cfg = await get_config(interaction.guild_id)
        embed = discord.Embed(title=f"{emoji} {self.titulo.value}", color=hex_to_int(cor))
        embed.add_field(name="📋 Descrição", value=self.descricao.value, inline=False)
        if self.data.value:
            embed.add_field(name="🗓️ Data & Hora", value=f"`{self.data.value}`", inline=True)
        if self.local.value:
            embed.add_field(name="📍 Local", value=f"`{self.local.value}`", inline=True)
        embed.add_field(name="👤 Organizado por", value=interaction.user.mention, inline=True)
        if banner:
            embed.set_image(url=banner)
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=build_footer(cfg, interaction.guild))

        canal = interaction.channel
        await interaction.response.send_message("✅ Evento criado!", ephemeral=True)
        msg = await canal.send(embed=embed)
        try:
            await msg.add_reaction(emoji)
        except Exception:
            await msg.add_reaction("✅")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO eventos (guild_id, channel_id, message_id, titulo, descricao, local, emoji, cor, banner, data_evento, criado_por, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (interaction.guild_id, canal.id, msg.id, self.titulo.value, self.descricao.value,
                 self.local.value, emoji, cor, banner, self.data.value, interaction.user.id,
                 datetime.utcnow().isoformat()))
            await db.commit()


# ── Encerrar Evento ──
class ModalEncerrarEvento(discord.ui.Modal, title="🔚 Encerrar Evento"):
    def __init__(self):
        super().__init__()
        self.evento_id = discord.ui.TextInput(
            label="ID do evento (use /eventos para ver)",
            placeholder="Ex: 1",
            max_length=10)
        self.add_item(self.evento_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            eid = int(self.evento_id.value.strip())
        except ValueError:
            await interaction.followup.send("❌ ID inválido.", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM eventos WHERE id = ? AND guild_id = ? AND encerrado = 0",
                (eid, interaction.guild_id))
            evento = await cursor.fetchone()
            if not evento:
                await interaction.followup.send("❌ Evento não encontrado ou já encerrado.", ephemeral=True)
                return
            await db.execute("UPDATE eventos SET encerrado = 1 WHERE id = ?", (eid,))
            await db.commit()

        cfg = await get_config(interaction.guild_id)
        canal = interaction.guild.get_channel(evento["channel_id"])
        embed_fim = discord.Embed(
            title=f"🔚 EVENTO ENCERRADO — {evento['titulo']}",
            description="Este evento foi encerrado pelo organizador.",
            color=0xe74c3c
        )
        embed_fim.set_footer(text=build_footer(cfg, interaction.guild))
        if canal:
            await canal.send(embed=embed_fim)
        await interaction.followup.send(f"✅ Evento **#{eid}** encerrado!", ephemeral=True)


# ───────────────────────────────────────────────
#  SELECTS DE CANAL — ORIGINAIS (sem alteração)
# ───────────────────────────────────────────────
class SelectCanalEntrada(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📥 Selecione o canal de ENTRADA", channel_types=[discord.ChannelType.text], custom_id="ffz:select_entrada")
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, join_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **entrada** definido para {canal.mention}", ephemeral=True)

class SelectCanalSaida(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📤 Selecione o canal de SAÍDA", channel_types=[discord.ChannelType.text], custom_id="ffz:select_saida")
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, leave_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **saída** definido para {canal.mention}", ephemeral=True)

class SelectCanalLogs(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📋 Selecione o canal de LOGS", channel_types=[discord.ChannelType.text], custom_id="ffz:select_logs")
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, log_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **logs** definido para {canal.mention}", ephemeral=True)
      
# ── Selects de Canal para Moderação ──
class SelectCanalModLog(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📋 Canal de log de moderação", channel_types=[discord.ChannelType.text], custom_id="ffz:select_modlog")
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, mod_log_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **log de moderação** definido para {canal.mention}", ephemeral=True)

class SelectCanalAntiLinkLog(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="🔗 Canal de log anti-link", channel_types=[discord.ChannelType.text], custom_id="ffz:select_antilink_log")
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, antilink_log_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **log anti-link** definido para {canal.mention}", ephemeral=True)

class SelectCanalAntiRaidLog(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="🛡️ Canal de log anti-raid", channel_types=[discord.ChannelType.text], custom_id="ffz:select_antiraid_log")
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, antiraid_log_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **log anti-raid** definido para {canal.mention}", ephemeral=True)


# ── Select de Cargo para Auto-Role ──
class SelectAutoRole(discord.ui.RoleSelect):
    def __init__(self, modo: str):
        self.modo = modo
        placeholder = "➕ Selecione cargo para ADICIONAR" if modo == "add" else "➖ Selecione cargo para REMOVER"
        super().__init__(placeholder=placeholder, custom_id=f"ffz:autorole_{modo}")

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        if self.modo == "add":
            await add_auto_role(interaction.guild_id, role.id)
            await interaction.response.send_message(f"✅ Cargo {role.mention} adicionado ao auto-role!", ephemeral=True)
        else:
            await remove_auto_role(interaction.guild_id, role.id)
            await interaction.response.send_message(f"✅ Cargo {role.mention} removido do auto-role!", ephemeral=True)
# ───────────────────────────────────────────────
#  VIEW DE CANAIS — ORIGINAL (sem alteração)
# ───────────────────────────────────────────────
class ViewCanais(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SelectCanalEntrada())
        self.add_item(SelectCanalSaida())
        self.add_item(SelectCanalLogs())

    @discord.ui.button(label="◀ Voltar ao Painel", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:voltar_painel", row=3)
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        embeds, view = build_painel_principal(interaction.guild, cfg)
        await interaction.response.edit_message(embeds=embeds, view=view)

# ───────────────────────────────────────────────
#  VIEW DE MODERAÇÃO (novo)
# ───────────────────────────────────────────────
class ViewModeracao(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔗 Config Anti-Link", style=discord.ButtonStyle.danger,
                       custom_id="ffz:mod_antilink_cfg", row=0)
    async def config_antilink(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_modal(ModalAntiLink(cfg))

    @discord.ui.button(label="🤬 Config Anti-Palavras", style=discord.ButtonStyle.danger,
                       custom_id="ffz:mod_badwords_cfg", row=0)
    async def config_badwords(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_modal(ModalBadWords(cfg))

    @discord.ui.button(label="🛡️ Config Anti-Raid", style=discord.ButtonStyle.danger,
                       custom_id="ffz:mod_antiraid_cfg", row=0)
    async def config_antiraid(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_modal(ModalAntiRaid(cfg))

    @discord.ui.button(label="🔗 ON/OFF Anti-Link", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:mod_antilink_toggle", row=1)
    async def toggle_antilink(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        novo = 0 if cfg.get("antilink_enabled", 0) else 1
        await set_config(interaction.guild_id, antilink_enabled=novo)
        status = "✅ **ATIVADO**" if novo else "❌ **DESATIVADO**"
        await interaction.response.send_message(f"🔗 Anti-Link {status}!", ephemeral=True)

    @discord.ui.button(label="🤬 ON/OFF Anti-Palavras", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:mod_badwords_toggle", row=1)
    async def toggle_badwords(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        novo = 0 if cfg.get("bad_words_enabled", 0) else 1
        await set_config(interaction.guild_id, bad_words_enabled=novo)
        status = "✅ **ATIVADO**" if novo else "❌ **DESATIVADO**"
        await interaction.response.send_message(f"🤬 Anti-Palavras {status}!", ephemeral=True)

    @discord.ui.button(label="🛡️ ON/OFF Anti-Raid", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:mod_antiraid_toggle", row=1)
    async def toggle_antiraid(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        novo = 0 if cfg.get("antiraid_enabled", 0) else 1
        await set_config(interaction.guild_id, antiraid_enabled=novo)
        status = "✅ **ATIVADO**" if novo else "❌ **DESATIVADO**"
        await interaction.response.send_message(f"🛡️ Anti-Raid {status}!", ephemeral=True)

    @discord.ui.button(label="📋 Canal Log Mod", style=discord.ButtonStyle.primary,
                       custom_id="ffz:mod_canal_log", row=2)
    async def canal_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View(timeout=60)
        view.add_item(SelectCanalModLog())
        view.add_item(SelectCanalAntiLinkLog())
        view.add_item(SelectCanalAntiRaidLog())
        await interaction.response.send_message("📋 Selecione os canais de log:", view=view, ephemeral=True)

    @discord.ui.button(label="◀ Voltar ao Painel", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:mod_voltar", row=3)
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        embeds, view = build_painel_principal(interaction.guild, cfg)
        await interaction.response.edit_message(embeds=embeds, view=view)
                               

# ───────────────────────────────────────────────
#  VIEW DE AUTO-ROLE (novo)
# ───────────────────────────────────────────────
class ViewAutoRole(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Adicionar Cargo", style=discord.ButtonStyle.success,
                       custom_id="ffz:ar_add_btn", row=0)
    async def add_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View(timeout=60)
        view.add_item(SelectAutoRole("add"))
        await interaction.response.send_message("➕ Selecione o cargo para **adicionar** ao auto-role:", view=view, ephemeral=True)

    @discord.ui.button(label="➖ Remover Cargo", style=discord.ButtonStyle.danger,
                       custom_id="ffz:ar_remove_btn", row=0)
    async def remove_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles = await get_auto_roles(interaction.guild_id)
        if not roles:
            await interaction.response.send_message("❌ Nenhum cargo de auto-role configurado.", ephemeral=True)
            return
        view = discord.ui.View(timeout=60)
        view.add_item(SelectAutoRole("remove"))
        await interaction.response.send_message("➖ Selecione o cargo para **remover** do auto-role:", view=view, ephemeral=True)

    @discord.ui.button(label="📋 Ver Cargos Ativos", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:ar_list", row=0)
    async def list_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles = await get_auto_roles(interaction.guild_id)
        if not roles:
            await interaction.response.send_message("❌ Nenhum cargo configurado no auto-role.", ephemeral=True)
            return
        linhas = []
        for rid in roles:
            role = interaction.guild.get_role(rid)
            linhas.append(f"• {role.mention if role else f'`ID: {rid}`'}")
        embed = discord.Embed(title="🎭 Auto-Roles Ativos", description="\n".join(linhas), color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="◀ Voltar ao Painel", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:ar_voltar", row=1)
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        embeds, view = build_painel_principal(interaction.guild, cfg)
        await interaction.response.edit_message(embeds=embeds, view=view)

# ───────────────────────────────────────────────
#  VIEW DE SORTEIOS (novo)
# ───────────────────────────────────────────────
class ViewSorteios(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎉 Criar Sorteio", style=discord.ButtonStyle.success,
                       custom_id="ffz:sorteio_criar", row=0)
    async def criar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalCriarSorteio())

    @discord.ui.button(label="🔚 Encerrar Sorteio", style=discord.ButtonStyle.danger,
                       custom_id="ffz:sorteio_encerrar", row=0)
    async def encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalEncerrarSorteio())

    @discord.ui.button(label="📋 Ver Sorteios Ativos", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:sorteio_listar", row=0)
    async def listar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM sorteios WHERE guild_id = ? AND encerrado = 0 ORDER BY id DESC LIMIT 10",
                (interaction.guild_id,))
            rows = await cursor.fetchall()
        if not rows:
            await interaction.followup.send("❌ Nenhum sorteio ativo.", ephemeral=True)
            return
        desc = "\n".join(f"**ID {r['id']}** — {r['emoji']} {r['titulo']} | 🏆 {r['premio']}" for r in rows)
        embed = discord.Embed(title="🎉 Sorteios Ativos", description=desc, color=0x5865F2)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="◀ Voltar ao Painel", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:sorteio_voltar", row=1)
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        embeds, view = build_painel_principal(interaction.guild, cfg)
        await interaction.response.edit_message(embeds=embeds, view=view)


# ───────────────────────────────────────────────
#  VIEW DE EVENTOS (novo)
# ───────────────────────────────────────────────
class ViewEventos(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📅 Criar Evento", style=discord.ButtonStyle.success,
                       custom_id="ffz:evento_criar", row=0)
    async def criar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalCriarEvento())

    @discord.ui.button(label="🔚 Encerrar Evento", style=discord.ButtonStyle.danger,
                       custom_id="ffz:evento_encerrar", row=0)
    async def encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalEncerrarEvento())

    @discord.ui.button(label="📋 Ver Eventos Ativos", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:evento_listar", row=0)
    async def listar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM eventos WHERE guild_id = ? AND encerrado = 0 ORDER BY id DESC LIMIT 10",
                (interaction.guild_id,))
            rows = await cursor.fetchall()
        if not rows:
            await interaction.followup.send("❌ Nenhum evento ativo.", ephemeral=True)
            return
        desc = "\n".join(
            f"**ID {r['id']}** — {r['emoji']} {r['titulo']}"
            + (f" | 🗓️ {r['data_evento']}" if r['data_evento'] else "")
            for r in rows)
        embed = discord.Embed(title="📅 Eventos Ativos", description=desc, color=0x5865F2)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="◀ Voltar ao Painel", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:evento_voltar", row=1)
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        embeds, view = build_painel_principal(interaction.guild, cfg)
        await interaction.response.edit_message(embeds=embeds, view=view)


# ───────────────────────────────────────────────
#  VIEW PRINCIPAL — original + novos botões
# ───────────────────────────────────────────────
class ViewPainelPrincipal(discord.ui.View):
    def __init__(self, cfg: dict = {}):
        super().__init__(timeout=None)
        self.cfg = cfg

    # ── Row 0: Mensagens (original) ──
    @discord.ui.button(label="✏️ Msg Entrada", style=discord.ButtonStyle.success,
                       custom_id="ffz:msg_entrada", row=0)
    async def msg_entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cfg = await get_config(interaction.guild_id)
            await interaction.response.send_modal(ModalMensagemEntrada(cfg))
        except Exception as e:
            print(f"[ERRO] msg_entrada: {e}", flush=True)
            import traceback; traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="📥 Canal Entrada", style=discord.ButtonStyle.primary,
                       custom_id="ffz:canal_entrada", row=0)
    async def canal_entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            embed = discord.Embed(
                title="📥 Configurar Canais",
                description="Selecione abaixo cada canal para entrada, saída e logs de convites.",
                color=0x5865F2
            )
            await interaction.response.edit_message(embeds=[embed], view=ViewCanais())
        except Exception as e:
            print(f"[ERRO] canal_entrada: {e}", flush=True)
            import traceback; traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="✏️ Msg Saída", style=discord.ButtonStyle.danger,
                       custom_id="ffz:msg_saida", row=0)
    async def msg_saida(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cfg = await get_config(interaction.guild_id)
            await interaction.response.send_modal(ModalMensagemSaida(cfg))
        except Exception as e:
            print(f"[ERRO] msg_saida: {e}", flush=True)
            import traceback; traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    # ── Row 1: Personalização (original) ──
    @discord.ui.button(label="📝 Rodapé", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:rodape", row=1)
    async def rodape(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cfg = await get_config(interaction.guild_id)
            await interaction.response.send_modal(ModalFooter(cfg))
        except Exception as e:
            print(f"[ERRO] rodape: {e}", flush=True)
            import traceback; traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="😀 Emojis", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:emojis", row=1)
    async def emojis(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cfg = await get_config(interaction.guild_id)
            await interaction.response.send_modal(ModalEmojis(cfg))
        except Exception as e:
            print(f"[ERRO] emojis: {e}", flush=True)
            import traceback; traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="🏆 Ver Ranking", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:ranking", row=1)
    async def ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            cfg = await get_config(interaction.guild_id)
            embed = await build_ranking_embed(interaction.guild, cfg)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[ERRO] ranking: {e}", flush=True)
            import traceback; traceback.print_exc()
            await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    # ── Row 2: Preview (original) ──
    @discord.ui.button(label="👁️ Preview Entrada", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:preview_entrada", row=2)
    async def preview_entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cfg = await get_config(interaction.guild_id)
            body = (cfg["join_body"]
                .replace("{member}", interaction.user.mention)
                .replace("{username}", interaction.user.name)
                .replace("{inviter}", "**@Recrutador**")
                .replace("{total}", "5"))
            embed = build_embed(cfg["join_title"], body, cfg["join_color"],
                cfg["join_banner"] or FFZ_THUMBNAIL,
                build_footer(cfg, interaction.guild),
                interaction.user.display_avatar.url)
            await interaction.response.send_message(content="👁️ **Preview de entrada:**", embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[ERRO] preview_entrada: {e}", flush=True)
            import traceback; traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="👁️ Preview Saída", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:preview_saida", row=2)
    async def preview_saida(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cfg = await get_config(interaction.guild_id)
            body = (cfg["leave_body"]
                .replace("{username}", interaction.user.name)
                .replace("{inviter}", "**@Recrutador**"))
            embed = build_embed(cfg["leave_title"], body, cfg["leave_color"],
                cfg["leave_banner"] or FFZ_THUMBNAIL,
                build_footer(cfg, interaction.guild),
                interaction.user.display_avatar.url)
            await interaction.response.send_message(content="👁️ **Preview de saída:**", embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[ERRO] preview_saida: {e}", flush=True)
            import traceback; traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    # ── Row 3: Novos sistemas ──
    @discord.ui.button(label="🛡️ Moderação", style=discord.ButtonStyle.danger,
                       custom_id="ffz:painel_mod", row=3)
    async def painel_mod(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cfg = await get_config(interaction.guild_id)
            al_status = "✅" if cfg.get("antilink_enabled") else "❌"
            bw_status = "✅" if cfg.get("bad_words_enabled") else "❌"
            ar_status = "✅" if cfg.get("antiraid_enabled") else "❌"
            embed = discord.Embed(
                title="🛡️ PAINEL DE MODERAÇÃO",
                description="Configure os sistemas de proteção do servidor.",
                color=0xe74c3c
            )
            embed.add_field(name="🔗 Anti-Link", value=al_status, inline=True)
            embed.add_field(name="🤬 Anti-Palavras", value=bw_status, inline=True)
            embed.add_field(name="🛡️ Anti-Raid", value=ar_status, inline=True)
            embed.add_field(
                name="⚙️ Anti-Raid Config",
                value=f"Entradas: `{cfg.get('antiraid_joins',5)}` em `{cfg.get('antiraid_seconds',10)}s` → `{cfg.get('antiraid_action','kick')}`",
                inline=False
            )
            await interaction.response.edit_message(embeds=[embed], view=ViewModeracao())
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="🎭 Auto-Role", style=discord.ButtonStyle.primary,
                       custom_id="ffz:painel_autorole", row=3)
    async def painel_autorole(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            roles = await get_auto_roles(interaction.guild_id)
            linhas = []
            for rid in roles:
                role = interaction.guild.get_role(rid)
                linhas.append(f"• {role.mention if role else f'`ID: {rid}`'}")
            embed = discord.Embed(
                title="🎭 PAINEL DE AUTO-ROLE",
                description="Cargos entregues automaticamente ao entrar no servidor.\n\u200b",
                color=0x5865F2
            )
            embed.add_field(
                name=f"🎯 Cargos ativos ({len(roles)})",
                value="\n".join(linhas) if linhas else "`Nenhum cargo configurado`",
                inline=False
            )
            await interaction.response.edit_message(embeds=[embed], view=ViewAutoRole())
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="🎉 Sorteios", style=discord.ButtonStyle.success,
                       custom_id="ffz:painel_sorteios", row=4)
    async def painel_sorteios(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM sorteios WHERE guild_id = ? AND encerrado = 0",
                    (interaction.guild_id,))
                ativos = (await cursor.fetchone())[0]
            embed = discord.Embed(
                title="🎉 PAINEL DE SORTEIOS",
                description=f"Crie e gerencie sorteios com embed personalizada.\n\n🎯 **Sorteios ativos:** `{ativos}`",
                color=0xFFD700
            )
            embed.add_field(
                name="💡 Como funciona",
                value="1. Clique em **Criar Sorteio** e preencha o formulário\n2. O bot posta a embed e adiciona a reação\n3. Clique em **Encerrar** para sortear um vencedor",
                inline=False
            )
            await interaction.response.edit_message(embeds=[embed], view=ViewSorteios())
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)

    @discord.ui.button(label="📅 Eventos", style=discord.ButtonStyle.primary,
                       custom_id="ffz:painel_eventos", row=4)
    async def painel_eventos(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM eventos WHERE guild_id = ? AND encerrado = 0",
                    (interaction.guild_id,))
                ativos = (await cursor.fetchone())[0]
            embed = discord.Embed(
                title="📅 PAINEL DE EVENTOS",
                description=f"Organize eventos com data, local e embed personalizada.\n\n🎯 **Eventos ativos:** `{ativos}`",
                color=0x5865F2
            )
            embed.add_field(
                name="💡 Como funciona",
                value="1. Clique em **Criar Evento** e preencha o formulário\n2. O bot posta a embed com data, local e reação\n3. Clique em **Encerrar** quando o evento terminar",
                inline=False
            )
            await interaction.response.edit_message(embeds=[embed], view=ViewEventos())
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Erro interno: `{e}`", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ Erro interno: `{e}`", ephemeral=True)



# ───────────────────────────────────────────────
#  BUILD DO PAINEL PRINCIPAL — original + info novos
# ───────────────────────────────────────────────
def build_painel_principal(guild: discord.Guild, cfg: dict):
    def canal_str(channel_id) -> str:
        if not channel_id:
            return "`Não configurado`"
        ch = guild.get_channel(channel_id)
        return ch.mention if ch else f"`ID: {channel_id}`"

    embed1 = discord.Embed(
        title="💎 PANEL INVITES FFZ",
        description="Gerencie o sistema de convites do servidor.\nUse os botões abaixo para configurar tudo sem mexer em código.\n\u200b",
        color=0x5865F2
    )
    embed1.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed1.add_field(
        name="📡 Canais configurados",
        value=(f"📥 **Entrada:** {canal_str(cfg['join_channel_id'])}\n"
               f"📤 **Saída:** {canal_str(cfg['leave_channel_id'])}\n"
               f"📋 **Logs:** {canal_str(cfg['log_channel_id'])}"),
        inline=False,
    )
    embed1.add_field(
        name="📝 Títulos",
        value=(f"**Entrada:** {cfg['join_title'][:40]}\n"
               f"**Saída:** {cfg['leave_title'][:40]}"),
        inline=True,
    )

    embed2 = discord.Embed(color=0x5865F2)
    embed2.add_field(
        name="🎨 Personalização",
        value=(f"**Cor Entrada:** `#{cfg['join_color']}`\n"
               f"**Cor Saída:** `#{cfg['leave_color']}`\n"
               f"**Emojis:** {cfg['emoji_join']} {cfg['emoji_leave']} {cfg['emoji_inviter']} {cfg['emoji_stats']} {cfg['emoji_member']}\n"
               f"**Rodapé:** `{cfg['footer_text']}`"),
        inline=False,
    )
    embed2.add_field(
        name="🛡️ Moderação",
        value=(f"🔗 Anti-Link: {'✅' if cfg.get('antilink_enabled') else '❌'} | "
               f"🤬 Palavras: {'✅' if cfg.get('bad_words_enabled') else '❌'} | "
               f"🛡️ Anti-Raid: {'✅' if cfg.get('antiraid_enabled') else '❌'}"),
        inline=False,
    )
    embed2.set_footer(text=f"FFZ E-SPORTS • {guild.member_count} membros")

    return [embed1, embed2], ViewPainelPrincipal(cfg)

# ───────────────────────────────────────────────
#  RANKING — original (sem alteração)
# ───────────────────────────────────────────────
async def build_ranking_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT inviter_id, COUNT(*) as total FROM invites_data WHERE guild_id = ? GROUP BY inviter_id ORDER BY total DESC LIMIT 10",
            (guild.id,)
        )
        rows = await cursor.fetchall()

    medalhas = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    desc = ""
    for i, (inviter_id, total) in enumerate(rows):
        membro = guild.get_member(inviter_id)
        nome = membro.mention if membro else f"`ID: {inviter_id}`"
        desc += f"{medalhas[i]} {nome} — **{total}** convite{'s' if total != 1 else ''}\n"

    if not desc:
        desc = "Nenhum convite registrado ainda."

    embed = discord.Embed(title=f"🏆 Ranking de Convites — {guild.name}", description=desc, color=hex_to_int(cfg["log_color"]))
    embed.set_footer(text=build_footer(cfg, guild))
    return embed

# ───────────────────────────────────────────────
#  SETUP
# ───────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await init_db()

    # Registra as views persistentes para funcionar após restart
    bot.add_view(ViewPainelPrincipal())
    bot.add_view(ViewCanais())
    bot.add_view(ViewModeracao())
    bot.add_view(ViewAutoRole())
    bot.add_view(ViewSorteios())
    bot.add_view(ViewEventos())

    @bot.tree.command(
        name="painel",
        description="Abre o painel de configuração do sistema de convites",
        guild=discord.Object(id=GUILD_ID),
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def painel(interaction: discord.Interaction):
        cfg = await get_config(interaction.guild_id)
        embeds, view = build_painel_principal(interaction.guild, cfg)
        await interaction.response.send_message(embeds=embeds, view=view, ephemeral=True)

    @bot.tree.command(
        name="ranking",
        description="Mostra o ranking de quem mais convidou membros",
        guild=discord.Object(id=GUILD_ID),
    )
    async def ranking_cmd(interaction: discord.Interaction):
        cfg = await get_config(interaction.guild_id)
        embed = await build_ranking_embed(interaction.guild, cfg)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(
        name="sorteios",
        description="Lista os sorteios ativos do servidor",
        guild=discord.Object(id=GUILD_ID),
    )
    async def sorteios_cmd(interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM sorteios WHERE guild_id = ? AND encerrado = 0 ORDER BY id DESC",
                (interaction.guild_id,))
            rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("❌ Nenhum sorteio ativo no momento.", ephemeral=True)
            return
        desc = "\n".join(f"**ID {r['id']}** — {r['emoji']} {r['titulo']} | 🏆 {r['premio']}" for r in rows)
        embed = discord.Embed(title="🎉 Sorteios Ativos", description=desc, color=0xFFD700)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(
        name="eventos",
        description="Lista os eventos ativos do servidor",
        guild=discord.Object(id=GUILD_ID),
    )
    async def eventos_cmd(interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM eventos WHERE guild_id = ? AND encerrado = 0 ORDER BY id DESC",
                (interaction.guild_id,))
            rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("❌ Nenhum evento ativo no momento.", ephemeral=True)
            return
        desc = "\n".join(
            f"**ID {r['id']}** — {r['emoji']} {r['titulo']}"
            + (f" | 🗓️ {r['data_evento']}" if r['data_evento'] else "")
            for r in rows)
        embed = discord.Embed(title="📅 Eventos Ativos", description=desc, color=0x5865F2)
        await interaction.response.send_message(embed=embed)

    # ── Eventos do bot ──

    @bot.event
    async def on_invite_create(invite):
        await atualizar_cache(invite.guild)

    @bot.event
    async def on_invite_delete(invite):
        await atualizar_cache(invite.guild)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cfg = await get_config(message.guild.id)

        # ── Anti-Link ──
        if cfg.get("antilink_enabled"):
            url_pattern = re.compile(
                r"(https?://|discord\.gg/|www\.)[^\s]+", re.IGNORECASE)
            if url_pattern.search(message.content):
                try:
                    await message.delete()
                except Exception:
                    pass
                aviso = cfg.get("antilink_msg", "🚫 {member}, links não são permitidos aqui!")
                aviso = aviso.replace("{member}", message.author.mention)
                try:
                    msg_aviso = await message.channel.send(aviso)
                    await asyncio.sleep(8)
                    await msg_aviso.delete()
                except Exception:
                    pass
                log_ch_id = cfg.get("antilink_log_channel_id") or cfg.get("mod_log_channel_id")
                if log_ch_id:
                    log_ch = message.guild.get_channel(log_ch_id)
                    if log_ch:
                        embed_log = discord.Embed(
                            title="🔗 Link Bloqueado",
                            description=f"**Membro:** {message.author.mention}\n**Canal:** {message.channel.mention}\n**Conteúdo:** `{message.content[:200]}`",
                            color=0xe74c3c
                        )
                        embed_log.set_footer(text=f"ID: {message.author.id}")
                        await log_ch.send(embed=embed_log)
                return

        # ── Anti Palavras Pesadas ──
        if cfg.get("bad_words_enabled") and cfg.get("bad_words_list"):
            palavras = [p.strip().lower() for p in cfg["bad_words_list"].split(",") if p.strip()]
            conteudo = message.content.lower()
            detectada = next((p for p in palavras if p in conteudo), None)
            if detectada:
                try:
                    await message.delete()
                except Exception:
                    pass
                aviso = cfg.get("bad_words_msg", "⚠️ {member}, esse tipo de linguagem não é permitida!")
                aviso = aviso.replace("{member}", message.author.mention)
                try:
                    msg_aviso = await message.channel.send(aviso)
                    await asyncio.sleep(8)
                    await msg_aviso.delete()
                except Exception:
                    pass
                log_ch_id = cfg.get("mod_log_channel_id")
                if log_ch_id:
                    log_ch = message.guild.get_channel(log_ch_id)
                    if log_ch:
                        embed_log = discord.Embed(
                            title="🤬 Palavra Bloqueada",
                            description=f"**Membro:** {message.author.mention}\n**Palavra:** `{detectada}`\n**Canal:** {message.channel.mention}",
                            color=0xe67e22
                        )
                        embed_log.set_footer(text=f"ID: {message.author.id}")
                        await log_ch.send(embed=embed_log)

        await bot.process_commands(message)

    @bot.event
    async def on_member_join(member: discord.Member):
        if member.bot or member.guild.id != GUILD_ID:
            return
        await asyncio.sleep(2)
        cfg = await get_config(member.guild.id)

        # ── Anti-Raid ──
        if cfg.get("antiraid_enabled"):
            agora = datetime.utcnow().timestamp()
            guild_tracker = _raid_tracker.setdefault(member.guild.id, [])
            guild_tracker.append(agora)
            janela = cfg.get("antiraid_seconds", 10)
            limite = cfg.get("antiraid_joins", 5)
            guild_tracker[:] = [t for t in guild_tracker if agora - t <= janela]
            if len(guild_tracker) >= limite:
                acao = cfg.get("antiraid_action", "kick")
                try:
                    if acao == "ban":
                        await member.ban(reason="🛡️ Anti-Raid automático")
                    else:
                        await member.kick(reason="🛡️ Anti-Raid automático")
                except Exception as e:
                    print(f"[ANTIRAID] Erro ao {acao} {member}: {e}")
                log_ch_id = cfg.get("antiraid_log_channel_id") or cfg.get("mod_log_channel_id")
                if log_ch_id:
                    log_ch = member.guild.get_channel(log_ch_id)
                    if log_ch:
                        embed_log = discord.Embed(
                            title="🛡️ RAID DETECTADO",
                            description=f"**Membro:** {member.mention} (`{member.name}`)\n**Ação:** `{acao}`\n**Entradas detectadas:** `{len(guild_tracker)}` em `{janela}s`",
                            color=0xe74c3c
                        )
                        embed_log.set_footer(text=f"ID: {member.id}")
                        await log_ch.send(embed=embed_log)
                return  # não processa convite de quem foi kickado/banado

        # ── Auto-Role ──
        role_ids = await get_auto_roles(member.guild.id)
        for rid in role_ids:
            role = member.guild.get_role(rid)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-Role FFZ")
                except Exception as e:
                    print(f"[AUTOROLE] Erro ao dar cargo {rid}: {e}")

        # ── Sistema de convites original ──
        invites_antes  = invites_cache.get(member.guild.id, [])
        invites_depois = await member.guild.invites()
        invites_cache[member.guild.id] = invites_depois

        convite_usado = None
        for invite in invites_antes:
            invite_novo = discord.utils.get(invites_depois, code=invite.code)
            if invite_novo and invite_novo.uses > invite.uses:
                convite_usado = invite_novo
                break

        inviter_id = None
        total_convites = 0

        if convite_usado and convite_usado.inviter:
            inviter_id = convite_usado.inviter.id
            total_convites = sum(i.uses for i in invites_depois if i.inviter and i.inviter.id == inviter_id)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR REPLACE INTO invites_data VALUES (?,?,?)", (member.guild.id, member.id, inviter_id))
                await db.commit()

        join_channel_id = cfg.get("join_channel_id")
        if join_channel_id:
            canal = member.guild.get_channel(join_channel_id)
            if canal:
                inviter_mention = (member.guild.get_member(inviter_id).mention
                    if inviter_id and member.guild.get_member(inviter_id)
                    else "`Link direto / Não identificado`")
                body = (cfg["join_body"]
                    .replace("{member}", member.mention)
                    .replace("{username}", member.name)
                    .replace("{inviter}", inviter_mention)
                    .replace("{total}", str(total_convites)))
                embed = build_embed(cfg["join_title"], body, cfg["join_color"],
                    cfg["join_banner"] or FFZ_THUMBNAIL, build_footer(cfg, member.guild), member.display_avatar.url)
                await canal.send(embed=embed)

        log_channel_id = cfg.get("log_channel_id")
        if log_channel_id:
            canal_log = member.guild.get_channel(log_channel_id)
            if canal_log:
                inviter_obj  = member.guild.get_member(inviter_id) if inviter_id else None
                inviter_info = inviter_obj.mention if inviter_obj else "`Não identificado`"
                embed_log = discord.Embed(title=cfg["log_title"], color=hex_to_int(cfg["log_color"]))
                embed_log.set_author(name=f"{cfg['emoji_join']} ENTRADA — {member.name}", icon_url=member.display_avatar.url)
                embed_log.set_thumbnail(url=member.display_avatar.url)
                embed_log.add_field(name=f"{cfg['emoji_member']} Membro", value=f"{member.mention}\n`{member.name}`\n`ID: {member.id}`", inline=True)
                embed_log.add_field(name=f"{cfg['emoji_inviter']} Recrutado por", value=inviter_info, inline=True)
                embed_log.add_field(name=f"{cfg['emoji_stats']} Convites do recrutador", value=f"`{total_convites}`", inline=True)
                embed_log.add_field(name="📅 Conta criada em", value=f"<t:{int(member.created_at.timestamp())}:D>", inline=True)
                if cfg["join_banner"]:
                    embed_log.set_image(url=cfg["join_banner"])
                elif FFZ_THUMBNAIL:
                    embed_log.set_image(url=FFZ_THUMBNAIL)
                embed_log.set_footer(text=build_footer(cfg, member.guild))
                await canal_log.send(embed=embed_log)

    @bot.event
    async def on_member_remove(member: discord.Member):
        if member.bot or member.guild.id != GUILD_ID:
            return
        cfg = await get_config(member.guild.id)
        inviter_id = None
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT inviter_id FROM invites_data WHERE guild_id = ? AND user_id = ?",
                (member.guild.id, member.id))
            data = await cursor.fetchone()
            if data:
                inviter_id = data[0]

        inviter_obj     = member.guild.get_member(inviter_id) if inviter_id else None
        inviter_mention = inviter_obj.mention if inviter_obj else (f"`ID: {inviter_id}`" if inviter_id else "`Não identificado`")

        leave_channel_id = cfg.get("leave_channel_id")
        if leave_channel_id:
            canal = member.guild.get_channel(leave_channel_id)
            if canal:
                body = (cfg["leave_body"]
                    .replace("{username}", member.name)
                    .replace("{inviter}", inviter_mention))
                embed = build_embed(cfg["leave_title"], body, cfg["leave_color"],
                    cfg["leave_banner"] or FFZ_THUMBNAIL, build_footer(cfg, member.guild), member.display_avatar.url)
                await canal.send(embed=embed)

        log_channel_id = cfg.get("log_channel_id")
        if log_channel_id:
            canal_log = member.guild.get_channel(log_channel_id)
            if canal_log:
                embed_log = discord.Embed(title=cfg["log_title"], color=0xe74c3c)
                embed_log.set_author(name=f"{cfg['emoji_leave']} SAÍDA — {member.name}", icon_url=member.display_avatar.url)
                embed_log.set_thumbnail(url=member.display_avatar.url)
                embed_log.add_field(name=f"{cfg['emoji_member']} Membro", value=f"`{member.name}`\n`ID: {member.id}`", inline=True)
                embed_log.add_field(name=f"{cfg['emoji_inviter']} Foi recrutado por", value=inviter_mention, inline=True)
                embed_log.add_field(name="📅 Conta criada em", value=f"<t:{int(member.created_at.timestamp())}:D>", inline=True)
                if cfg["leave_banner"]:
                    embed_log.set_image(url=cfg["leave_banner"])
                elif FFZ_THUMBNAIL:
                    embed_log.set_image(url=FFZ_THUMBNAIL)
                embed_log.set_footer(text=build_footer(cfg, member.guild))
                await canal_log.send(embed=embed_log)

    print("[CONVITE] Setup finalizado com painel completo!")
