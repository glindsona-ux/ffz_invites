import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
import os
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
}

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
                guild_id          INTEGER PRIMARY KEY,
                join_channel_id   INTEGER,
                leave_channel_id  INTEGER,
                log_channel_id    INTEGER,
                join_title        TEXT DEFAULT '🔵 NOVO RECRUTA NA ÁREA',
                join_body         TEXT DEFAULT '👤 **Membro**\n{member}\n`{username}`\n\n🎯 **Recrutado por**\n{inviter}\n\n📊 **Total de convites**\n`{total}`',
                join_color        TEXT DEFAULT '5865F2',
                join_banner       TEXT DEFAULT '',
                leave_title       TEXT DEFAULT '😔 RECRUTA ABANDONOU O POSTO',
                leave_body        TEXT DEFAULT '👤 **Membro**\n`{username}`\n\n🎯 **Foi recrutado por**\n{inviter}',
                leave_color       TEXT DEFAULT 'e74c3c',
                leave_banner      TEXT DEFAULT '',
                log_title         TEXT DEFAULT '📋 LOG DE CONVITES FFZ',
                log_color         TEXT DEFAULT '5865F2',
                emoji_join        TEXT DEFAULT '🔵',
                emoji_leave       TEXT DEFAULT '😔',
                emoji_inviter     TEXT DEFAULT '🎯',
                emoji_stats       TEXT DEFAULT '📊',
                emoji_member      TEXT DEFAULT '👤',
                footer_text       TEXT DEFAULT 'FFZ E-SPORTS | {count} membros'
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
#  MODALS — CORRIGIDOS (TextInput criado no __init__)
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
            label="Conteúdo (use {member} {username} {inviter} {total})",
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
            label="Conteúdo (use {username} {inviter})",
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
            label="Texto do rodapé (use {count} para nº de membros)",
            placeholder="FFZ E-SPORTS | {count} membros",
            max_length=100,
            default=cfg.get("footer_text", "FFZ E-SPORTS | {count} membros"),
        )
        self.add_item(self.footer_text)

    async def on_submit(self, interaction: discord.Interaction):
        await set_config(interaction.guild_id, footer_text=self.footer_text.value)
        await interaction.response.send_message("✅ Rodapé atualizado!", ephemeral=True)


# ───────────────────────────────────────────────
#  SELECTS DE CANAL
# ───────────────────────────────────────────────
class SelectCanalEntrada(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📥 Selecione o canal de ENTRADA", channel_types=[discord.ChannelType.text])
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, join_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **entrada** definido para {canal.mention}", ephemeral=True)

class SelectCanalSaida(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📤 Selecione o canal de SAÍDA", channel_types=[discord.ChannelType.text])
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, leave_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **saída** definido para {canal.mention}", ephemeral=True)

class SelectCanalLogs(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📋 Selecione o canal de LOGS", channel_types=[discord.ChannelType.text])
    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        await set_config(interaction.guild_id, log_channel_id=canal.id)
        await interaction.response.send_message(f"✅ Canal de **logs** definido para {canal.mention}", ephemeral=True)


# ───────────────────────────────────────────────
#  VIEW DE CANAIS
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
#  VIEW PRINCIPAL — persistent (custom_id fixo)
# ───────────────────────────────────────────────
class ViewPainelPrincipal(discord.ui.View):
    def __init__(self, cfg: dict = {}):
        super().__init__(timeout=None)
        self.cfg = cfg

    # ── Row 0: Mensagens ──
    @discord.ui.button(label="✏️ Msg Entrada", style=discord.ButtonStyle.success,
                       custom_id="ffz:msg_entrada", row=0)
    async def msg_entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_modal(ModalMensagemEntrada(cfg))

    @discord.ui.button(label="📥 Canal Entrada", style=discord.ButtonStyle.primary,
                       custom_id="ffz:canal_entrada", row=0)
    async def canal_entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📥 Configurar Canais",
            description="Selecione abaixo cada canal para entrada, saída e logs de convites.",
            color=0x5865F2
        )
        await interaction.response.edit_message(embeds=[embed], view=ViewCanais())

    @discord.ui.button(label="✏️ Msg Saída", style=discord.ButtonStyle.danger,
                       custom_id="ffz:msg_saida", row=0)
    async def msg_saida(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_modal(ModalMensagemSaida(cfg))

    # ── Row 1: Personalização ──
    @discord.ui.button(label="📝 Rodapé", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:rodape", row=1)
    async def rodape(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_modal(ModalFooter(cfg))

    @discord.ui.button(label="😀 Emojis", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:emojis", row=1)
    async def emojis(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_modal(ModalEmojis(cfg))

    @discord.ui.button(label="🏆 Ver Ranking", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:ranking", row=1)
    async def ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        cfg = await get_config(interaction.guild_id)
        embed = await build_ranking_embed(interaction.guild, cfg)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Row 2: Preview ──
    @discord.ui.button(label="👁️ Preview Entrada", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:preview_entrada", row=2)
    async def preview_entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
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

    @discord.ui.button(label="👁️ Preview Saída", style=discord.ButtonStyle.secondary,
                       custom_id="ffz:preview_saida", row=2)
    async def preview_saida(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_config(interaction.guild_id)
        body = (cfg["leave_body"]
            .replace("{username}", interaction.user.name)
            .replace("{inviter}", "**@Recrutador**"))
        embed = build_embed(cfg["leave_title"], body, cfg["leave_color"],
            cfg["leave_banner"] or FFZ_THUMBNAIL,
            build_footer(cfg, interaction.guild),
            interaction.user.display_avatar.url)
        await interaction.response.send_message(content="👁️ **Preview de saída:**", embed=embed, ephemeral=True)


# ───────────────────────────────────────────────
#  BUILD DO PAINEL
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
    embed2.set_footer(text=f"FFZ E-SPORTS • {guild.member_count} membros")

    return [embed1, embed2], ViewPainelPrincipal(cfg)


# ───────────────────────────────────────────────
#  RANKING
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

    @bot.event
    async def on_invite_create(invite):
        await atualizar_cache(invite.guild)

    @bot.event
    async def on_invite_delete(invite):
        await atualizar_cache(invite.guild)

    @bot.event
    async def on_member_join(member: discord.Member):
        if member.bot or member.guild.id != GUILD_ID:
            return
        await asyncio.sleep(2)
        cfg = await get_config(member.guild.id)
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
