import os
import asyncio
import re
import discord
from discord import app_commands
from discord.ext import commands
from aiohttp import web

TOKEN = os.getenv("DISCORD_TOKEN")
DELETE_AFTER_SECONDS = 15 * 60

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
temporary_vcs = set()


def find_role(guild, text):
    text = text.strip()
    if not text:
        return None

    match = re.match(r"<@&(\d+)>", text)
    if match:
        return guild.get_role(int(match.group(1)))

    if text.isdigit():
        return guild.get_role(int(text))

    return discord.utils.get(guild.roles, name=text)


async def create_temp_vc(interaction, vc_name, selected_role=None):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    member = interaction.user

    category = None
    if member.voice and member.voice.channel:
        category = member.voice.channel.category
    elif interaction.channel:
        category = interaction.channel.category

    overwrites = None

    if selected_role:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=False
            ),
            selected_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=True
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True,
                move_members=True
            )
        }

    vc = await guild.create_voice_channel(
        name=vc_name,
        category=category,
        overwrites=overwrites,
        reason="Temporary VC created by VCMakeBot"
    )

    temporary_vcs.add(vc.id)

    moved = False
    move_reason = ""

    if member.voice and member.voice.channel:
        try:
            await member.move_to(vc)
            moved = True
        except discord.Forbidden:
            move_reason = "Botに「メンバーを移動」権限がない、またはBotのロール位置が低い可能性があります。"
        except Exception as e:
            move_reason = f"移動時にエラー：{e}"
    else:
        move_reason = "あなたがVCに入っていなかったため、自動移動できませんでした。"

    role_text = selected_role.mention if selected_role else "制限なし"

    msg = (
        f"VCを作成しました：{vc.mention}\n"
        f"ロール制限：{role_text}\n"
        f"誰もいなくなってから15分後に自動削除されます。"
    )

    if not moved:
        msg += f"\n※{move_reason}"

    await interaction.edit_original_response(
        content=msg,
        view=None
    )


class VCNameModal(discord.ui.Modal, title="VC名を入力"):
    vc_name = discord.ui.TextInput(
        label="チャンネル名",
        placeholder="例：ランク募集 / 雑談 / スクリム",
        max_length=50
    )

    async def on_submit(self, interaction):
        await interaction.response.send_message(
            f"VC名：**{self.vc_name}**\n"
            "このまま作成するか、ロール制限を設定してください。",
            view=CreateChoiceView(str(self.vc_name)),
            ephemeral=True
        )


class RoleInputModal(discord.ui.Modal, title="ロール制限を入力"):
    role_name = discord.ui.TextInput(
        label="入ってこれるロール",
        placeholder="例：Member / @Member / ロールID",
        max_length=100
    )

    def __init__(self, vc_name):
        super().__init__()
        self.vc_name = vc_name

    async def on_submit(self, interaction):
        role = find_role(interaction.guild, str(self.role_name))

        if role is None:
            await interaction.response.send_message(
                "そのロールが見つかりませんでした。\n"
                "ロール名、@メンション、ロールIDのどれかで入力してください。",
                ephemeral=True
            )
            return

        await create_temp_vc(
            interaction=interaction,
            vc_name=self.vc_name,
            selected_role=role
        )


class CreateChoiceView(discord.ui.View):
    def __init__(self, vc_name):
        super().__init__(timeout=180)
        self.vc_name = vc_name

    @discord.ui.button(label="作成", style=discord.ButtonStyle.success)
    async def create_button(self, interaction, button):
        await create_temp_vc(
            interaction=interaction,
            vc_name=self.vc_name,
            selected_role=None
        )

    @discord.ui.button(label="ロール制限", style=discord.ButtonStyle.secondary)
    async def role_button(self, interaction, button):
        await interaction.response.send_modal(
            RoleInputModal(self.vc_name)
        )


class VCPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="VCを作成",
        style=discord.ButtonStyle.primary,
        custom_id="create_vc_button"
    )
    async def create_vc(self, interaction, button):
        await interaction.response.send_modal(VCNameModal())


@bot.event
async def on_ready():
    bot.add_view(VCPanelView())

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

    print(f"Logged in as {bot.user}")


@bot.tree.command(name="vcpanel", description="VC作成ボタンを設置")
@app_commands.checks.has_permissions(manage_channels=True)
async def vcpanel(interaction):
    embed = discord.Embed(
        title="一時VC作成",
        description=(
            "ボタンからVCを作成できます。\n"
            "VC名入力後、通常作成またはロール制限を選べます。\n"
            "作成時、自動でVCへ移動します。\n"
            "15分無人で自動削除。"
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
                    temporary_vcs.discard(vc.id)
                    await vc.delete(reason="Temporary VC empty")
            except discord.NotFound:
                temporary_vcs.discard(vc.id)


async def health_check(request):
    return web.Response(text="VCMakeBot is running")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)

    port = int(os.getenv("PORT", 10000))

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    await start_web_server()
    await bot.start(TOKEN)


asyncio.run(main())
