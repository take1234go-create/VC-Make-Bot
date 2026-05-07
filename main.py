import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DELETE_AFTER_SECONDS = 15 * 60  # 15分

intents = discord.Intents.default()
intents.voice_states = True

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

        category = interaction.channel.category

        vc = await guild.create_voice_channel(
            name=str(self.vc_name),
            category=category,
            reason="一時VC作成"
        )

        temporary_vcs.add(vc.id)

        if member.voice and member.voice.channel:
            await member.move_to(vc)

        await interaction.response.send_message(
            f"VC「{vc.name}」を作成しました。無人になって15分後に削除されます。",
            ephemeral=True
        )


class VCPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="VCを作成",
        style=discord.ButtonStyle.primary,
        custom_id="create_temp_vc"
    )
    async def create_vc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VCNameModal())


@bot.event
async def on_ready():
    bot.add_view(VCPanelView())
    print(f"{bot.user} でログインしました")


@bot.command()
@commands.has_permissions(administrator=True)
async def voicepanel(ctx):
    view = VCPanelView()
    await ctx.send("一時VCを作成する場合は、下のボタンを押してください。", view=view)


@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None:
        return

    channel = before.channel

    if channel.id not in temporary_vcs:
        return

    if len(channel.members) == 0:
        await asyncio.sleep(DELETE_AFTER_SECONDS)

        channel = bot.get_channel(channel.id)

        if channel and len(channel.members) == 0:
            temporary_vcs.remove(channel.id)
            await channel.delete(reason="一時VCが15分間無人だったため削除")


bot.run(TOKEN)
