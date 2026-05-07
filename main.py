import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web

TOKEN = os.getenv("DISCORD_TOKEN")
DELETE_AFTER_SECONDS = 15 * 60

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

temporary_vcs = set()


class VCNameModal(discord.ui.Modal, title="VCを作成"):
    vc_name = discord.ui.TextInput(
        label="VC名",
        placeholder="例：ランク募集 / 雑談 / スクリム",
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        category = None

        # 今いるVCと同じカテゴリ
        if member.voice and member.voice.channel:
            category = member.voice.channel.category

        # いなければ現在のチャンネルカテゴリ
        if category is None and interaction.channel:
            category = interaction.channel.category

        vc = await guild.create_voice_channel(
            name=str(self.vc_name),
            category=category,
            reason="Temporary VC created"
        )

        temporary_vcs.add(vc.id)

        await interaction.response.send_message(
            f"VCを作成しました：{vc.mention}\n誰もいなくなってから15分後に削除されます。",
            ephemeral=True
        )


class VCPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="VCを作成",
        style=discord.ButtonStyle.primary,
        custom_id="create_vc_button"
    )
    async def create_vc_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(VCNameModal())


@bot.event
async def on_ready():
    bot.add_view(VCPanelView())

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

    print(f"Logged in as {bot.user}")


@bot.tree.command(
    name="vcpanel",
    description="VC作成パネルを設置します"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def vcpanel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="VC作成パネル",
        description=(
            "下のボタンから一時VCを作成できます。\n"
            "誰もいなくなって15分経過すると自動削除されます。"
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed,
        view=VCPanelView()
    )


@bot.event
async def on_voice_state_update(member, before, after):

    if before.channel and before.channel.id in temporary_vcs:

        vc = before.channel

        if len(vc.members) == 0:

            await asyncio.sleep(DELETE_AFTER_SECONDS)

            try:
                if len(vc.members) == 0:
                    temporary_vcs.remove(vc.id)
                    await vc.delete(
                        reason="Temporary VC empty for 15 minutes"
                    )

            except discord.NotFound:
                temporary_vcs.discard(vc.id)


# Render用Webサーバー
async def health_check(request):
    return web.Response(text="VCMakeBot is running")


async def start_web_server():

    app = web.Application()
    app.router.add_get("/", health_check)

    port = int(os.getenv("PORT", 10000))

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=port
    )

    await site.start()


async def main():
    await start_web_server()
    await bot.start(TOKEN)


asyncio.run(main())
