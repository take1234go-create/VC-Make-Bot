import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
DELETE_AFTER_SECONDS = 15 * 60

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

temporary_vcs = set()


async def create_temp_vc(
    interaction: discord.Interaction,
    vc_name: str,
    selected_role: discord.Role | None = None
):
    guild = interaction.guild
    member = interaction.user

    category = None

    # 作成者がVCにいる場合、そのVCと同じカテゴリに作成
    if member.voice and member.voice.channel:
        category = member.voice.channel.category

    # VCにいない場合、パネルがあるテキストチャンネルと同じカテゴリに作成
    if category is None and interaction.channel:
        category = interaction.channel.category

    overwrites = None

    # ロール制限ありの場合
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

    # 作成者を自動で移動
    if member.voice:
        try:
            await member.move_to(vc)
            moved = True
        except Exception:
            moved = False

    role_text = selected_role.mention if selected_role else "制限なし"

    msg = (
        f"VCを作成しました：{vc.mention}\n"
        f"ロール制限：{role_text}\n"
        f"誰もいなくなってから15分後に自動削除されます。"
    )

    if not moved:
        msg += "\n※あなたがVCに入っていなかったため、自動移動はできませんでした。"

    try:
        await interaction.response.edit_message(
            content=msg,
            embed=None,
            view=None
        )
    except discord.InteractionResponded:
        await interaction.followup.send(msg, ephemeral=True)


class VCNameModal(discord.ui.Modal, title="VC名を入力"):
    vc_name = discord.ui.TextInput(
        label="チャンネル名",
        placeholder="例：ランク募集 / 雑談 / スクリム",
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"VC名：**{self.vc_name}**\n"
            "このまま作成するか、ロール制限を設定してください。",
            view=CreateChoiceView(str(self.vc_name)),
            ephemeral=True
        )


class CreateChoiceView(discord.ui.View):
    def __init__(self, vc_name: str):
        super().__init__(timeout=180)
        self.vc_name = vc_name

    @discord.ui.button(
        label="作成",
        style=discord.ButtonStyle.success
    )
    async def create_without_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await create_temp_vc(
            interaction=interaction,
            vc_name=self.vc_name,
            selected_role=None
        )

    @discord.ui.button(
        label="ロール制限",
        style=discord.ButtonStyle.secondary
    )
    async def role_limit(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=(
                f"VC名：**{self.vc_name}**\n"
                "入室できるロールを選んでください。"
            ),
            view=RoleSelectView(self.vc_name)
        )


class RoleSelectView(discord.ui.View):
    def __init__(self, vc_name: str):
        super().__init__(timeout=180)
        self.vc_name = vc_name
        self.selected_role = None

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="入ってこれるロールを選択",
        min_values=1,
        max_values=1
    )
    async def role_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.RoleSelect
    ):
        self.selected_role = select.values[0]

        await interaction.response.edit_message(
            content=(
                f"VC名：**{self.vc_name}**\n"
                f"選択中のロール：{self.selected_role.mention}\n"
                "この設定で作成しますか？"
            ),
            view=RoleConfirmView(self.vc_name, self.selected_role)
        )


class RoleConfirmView(discord.ui.View):
    def __init__(self, vc_name: str, selected_role: discord.Role):
        super().__init__(timeout=180)
        self.vc_name = vc_name
        self.selected_role = selected_role

    @discord.ui.button(
        label="作成",
        style=discord.ButtonStyle.success
    )
    async def create_with_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await create_temp_vc(
            interaction=interaction,
            vc_name=self.vc_name,
            selected_role=self.selected_role
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


@bot.tree.command(
    name="vcpanel",
    description="VC作成ボタンを設置します"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def vcpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="一時VC作成",
        description=(
            "下のボタンから一時VCを作成できます。\n"
            "VC名を入力後、ロール制限あり/なしを選べます。\n"
            "作成者がVCに入っている場合、自動で作成したVCへ移動します。\n"
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


bot.run(TOKEN)
