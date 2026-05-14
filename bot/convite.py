import discord
import asyncio
import aiosqlite
from datetime import datetime
from.config import IDS, COR_FFZ, FFZ_THUMBNAIL

invites_cache = {}
DB_PATH = "invites.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invites_data (
                guild_id INTEGER,
                user_id INTEGER,
                inviter_id INTEGER,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()

async def atualizar_cache(guild):
    try:
        invites_cache[guild.id] = await guild.invites()
    except Exception as e:
        print(f"[CONVITE] ERRO ao atualizar cache: {e}")
        invites_cache[guild.id] = []

async def enviar_log_convite(guild, embed):
    canal = guild.get_channel(IDS.get("convidados"))
    if not canal:
        print(f"[CONVITE] ERRO: Canal 'convidados' não encontrado.")
        return
    try:
        await canal.send(embed=embed)
    except Exception as e:
        print(f"[CONVITE] ERRO ao enviar log: {e}")

async def setup_convite(bot):
    await init_db()

    @bot.event
    async def on_ready():
        for guild in bot.guilds:
            await atualizar_cache(guild)

    @bot.event
    async def on_invite_create(invite):
        await atualizar_cache(invite.guild)

    @bot.event
    async def on_invite_delete(invite):
        await atualizar_cache(invite.guild)

    @bot.event
    async def on_member_join(member):
        if member.bot:
            return

        await asyncio.sleep(2)
        invites_antes = invites_cache.get(member.guild.id, [])
        invites_depois = await member.guild.invites()
        invites_cache[member.guild.id] = invites_depois

        convite_usado = None
        for invite in invites_antes:
            invite_novo = discord.utils.get(invites_depois, code=invite.code)
            if invite_novo and invite_novo.uses > invite.uses:
                convite_usado = invite_novo
                break

        inviter_id = None
        if convite_usado and convite_usado.inviter:
            inviter_id = convite_usado.inviter.id
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR REPLACE INTO invites_data VALUES (?,?,?)",
                                 (member.guild.id, member.id, inviter_id))
                await db.commit()

        embed = discord.Embed(color=COR_FFZ)
        embed.set_author(name="🔵 NOVO RECRUTA NA ÁREA")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url=FFZ_THUMBNAIL)

        embed.description = f"👤 **Membro**\n{member.mention}\n`{member.name}`"

        if convite_usado and convite_usado.inviter:
            dono = convite_usado.inviter
            total = sum(i.uses for i in invites_depois if i.inviter and i.inviter.id == dono.id)
            embed.description += f"\n\n🎯 **Recrutado por**\n{dono.mention}"
            embed.description += f"\n\n📊 **Total de convites**\n`{total}`"
        else:
            embed.description += f"\n\n🎯 **Foi recrutado por**\n`Link direto / Não identificado`"
            embed.description += f"\n\n📊 **Convites do recrutador**\n`0`"

        embed.set_footer(text=f"FFZ E-SPORTS | {member.guild.member_count} membros | {datetime.now().strftime('%d/%m %H:%M')}")
        await enviar_log_convite(member.guild, embed)

    @bot.event
    async def on_member_remove(member):
        if member.bot:
            return

        inviter_id = None
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT inviter_id FROM invites_data WHERE guild_id =? AND user_id =?",
                                      (member.guild.id, member.id))
            data = await cursor.fetchone()
            if data:
                inviter_id = data[0]

        embed = discord.Embed(color=0xe74c3c)
        embed.set_author(name="😔 RECRUTA ABANDONOU O POSTO")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url=FFZ_THUMBNAIL)

        embed.description = f"👤 **Membro**\n`{member.name}`"

        if inviter_id:
            inviter = member.guild.get_member(inviter_id)
            embed.description += f"\n\n🎯 **Foi recrutado por**\n{inviter.mention if inviter else f'`ID: {inviter_id}`'}"
        else:
            embed.description += f"\n\n🎯 **Foi recrutado por**\n`Não identificado`"

        embed.set_footer(text=f"FFZ E-SPORTS | {member.guild.member_count} membros | {datetime.now().strftime('%d/%m %H:%M')}")
        await enviar_log_convite(member.guild, embed)

    print("[CONVITE] Setup finalizado!")

async def setup(bot):
    await setup_convite(bot)
