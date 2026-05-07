import os
import asyncio
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


class VCNameModal(discord.ui.Modal, title="VCを作成"):
    vc_name = discord.ui.TextInput(
        label="VC名",
        placeholder="例：ランク募集 / 雑談 / スクリム",
        max_length=50
    )

    channel_status = discord.ui.TextInput(
        label="チャンネルステータス（任意）",
        placeholder="例：@2 / 募集中 / 聞き専OK",
        max_length=50,
        required=False
    )

    def __init__(self, selected_role: discord.Role | None):
        super().__init__()
        self.selected_role = selected_role

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        category = None

        if member.voice and member.voice.channel:
            category = member.voice.channel.category

        if category is None and interaction.channel:
            category = interaction.channel.category

        overwrites = None

        if self.selected_role:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=False
                ),
                self.selected_role: discord.PermissionOverwrite(
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
            name=str(self.vc_name),
            category=category,
            overwrites=overwrites,
            reason="Temporary VC created by VCMakeBot"
        )

        temporary_vcs.add(vc.id)

        status_text = str(self.channel_status).strip()
        if status_text:
            try:
                await vc.edit(status=status_text)
            except Exception:
                pass

        moved = False
        if member.voice:
            try:
                await member.move_to(vc)
                moved = True
            except Exception:
                moved = False

        role_text = self.selected_role.mention if self.selected_role else "制限なし"

        msg = (
            f"VCを作成しました：{vc.mention}\n"
            f"入室できるロール：{role_text}\n"
            f"誰もいなくなってから15分後に自動削除されます。"
        )

        if not moved:
            msg += "\n※あなたがVCに入っていなかったため、自動移動はできませんでした。"

        await interaction.response.send_message(msg, ephemeral=True)


class RoleSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.selected_role = None

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="入ってこれるロールを選択（任意）",
        min_values=0,
        max_values=1
    )
    async def role_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.RoleSelect
    ):
        if select.values:
            self.selected_role = select.values[0]
            await interaction.response.send_message(
                f"選択中のロール：{self.selected_role.mention}",
                ephemeral=True
            )
        else:
            self.selected_role = None
            await interaction.response.send_message(
                "ロール制限なしにしました。",
                ephemeral=True
            )

    @discord.ui.button(label="入力へ", style=discord.ButtonStyle.primary)
    async def open_modal(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            VCNameModal(self.selected_role)
        )


class VCPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="VCを作成",
        style=discord.ButtonStyle.primary,
        custom_id="create_vc_button"
    )
    async def create_vc(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "入ってこれるロールを選んでください。\n"
            "制限しない場合は、そのまま「入力へ」を押してください。",
            view=RoleSelectView(),
            ephemeral=True
        )


@bot.event
async def on_ready():
    bot.add_view(VCPanelView())

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

    print(f"Logged in as {bot.user}")


@bot.tree.command(
    name="vcpanel",
    description="VC作成ボタンを設置します"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def vcpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="一時VC作成",
        description=(
            "下のボタンを押すと、一時VCを作成できます。\n"
            "VC名、チャンネルステータス、入室可能ロールを設定できます。\n"
            "誰もいなくなってから15分後に自動削除されます。"
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
