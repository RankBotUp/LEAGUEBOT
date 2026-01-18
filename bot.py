import discord
from discord.ext import commands
from discord import app_commands
from collections import Counter

HOST_CHANNEL_ID = 1462109920705904887
RESULTS_CHANNEL_ID = 1462482146672381952
LEAGUE_HOSTER_ROLE_ID = 1462109141752610858
# =========================================

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_leagues = {}  # thread_id -> league data
active_buttons = {}  # message_id -> league thread id


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ League Bot online as {bot.user}")


# ---------- DISPLAY NAME MODAL ----------
class DisplayNameModal(discord.ui.Modal, title="Join League"):
    display_name = discord.ui.TextInput(
        label="Enter your display name",
        placeholder="Example: PlayerOne",
        max_length=32
    )

    def __init__(self, league, thread):
        super().__init__()
        self.league = league
        self.thread = thread

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.bot:
            return

        if interaction.user.id in self.league["players"]:
            await interaction.response.send_message(
                "❌ You already joined this league.",
                ephemeral=True
            )
            return

        if len(self.league["players"]) >= self.league["max_players"]:
            await interaction.response.send_message(
                "❌ League is full.",
                ephemeral=True
            )
            return

        self.league["players"][interaction.user.id] = {
            "user": interaction.user,
            "display": self.display_name.value
        }

        await interaction.response.send_message(
            f"✅ Joined as **{self.display_name.value}**",
            ephemeral=True
        )

        # Add the user to the private thread
        await self.thread.add_user(interaction.user)

        await self.thread.send(
            f"👤 **Player Joined**\n"
            f"Display: **{self.display_name.value}**\n"
            f"User: {interaction.user.mention}"
        )


# ---------- JOIN BUTTON ----------
class JoinButton(discord.ui.Button):
    def __init__(self, league, thread):
        super().__init__(label="Join League", style=discord.ButtonStyle.success)
        self.league = league
        self.thread = thread

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            DisplayNameModal(self.league, self.thread)
        )


class JoinView(discord.ui.View):
    def __init__(self, league, thread):
        super().__init__(timeout=None)
        self.add_item(JoinButton(league, thread))


# ---------- SLASH COMMAND ----------
@bot.tree.command(name="hostleague", description="Host a league match")
@app_commands.choices(
    match_type=[
        app_commands.Choice(name="1v1", value="1v1"),
        app_commands.Choice(name="2v2", value="2v2"),
        app_commands.Choice(name="3v3", value="3v3"),
    ],
    league_type=[
        app_commands.Choice(name="DL", value="DL"),
        app_commands.Choice(name="SDL", value="SDL"),
        app_commands.Choice(name="CL", value="CL"),
    ]
)
async def hostleague(
    interaction: discord.Interaction,
    match_type: app_commands.Choice[str],
    league_type: app_commands.Choice[str]
):
    if interaction.channel_id != HOST_CHANNEL_ID:
        await interaction.response.send_message(
            "❌ You cannot host leagues in this channel.",
            ephemeral=True
        )
        return

    if LEAGUE_HOSTER_ROLE_ID not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message(
            "❌ You need the **League Hoster** role.",
            ephemeral=True
        )
        return

    max_players = {"1v1": 2, "2v2": 4, "3v3": 6}[match_type.value]

    # Create private thread
    thread = await interaction.channel.create_thread(
        name=f"{league_type.value} {match_type.value} League - {interaction.user.name}",
        type=discord.ChannelType.private_thread
    )

    # Add host to thread
    await thread.add_user(interaction.user)

    league = {
        "host": interaction.user,
        "match_type": match_type.value,
        "league_type": league_type.value,
        "max_players": max_players,
        "players": {}
    }

    active_leagues[thread.id] = league

    # Send join button in main channel (not in thread)
    msg = await interaction.channel.send(
        f"🏆 **{league_type.value} {match_type.value} League**\n"
        f"Host: {interaction.user.mention}\n\n"
        f"Click join to enter the private thread.",
        view=JoinView(league, thread)
    )

    # link button to thread
    active_buttons[msg.id] = thread.id

    await interaction.response.send_message(
        f"✅ League created. Private thread made for you: {thread.mention}",
        ephemeral=True
    )


# ---------- MATCH RESULTS ----------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id not in active_leagues:
        return

    league = active_leagues[message.channel.id]

    if message.author != league["host"]:
        return

    if not message.content.lower().startswith("match"):
        return

    winners = []
    for line in message.content.splitlines():
        if "won" in line.lower():
            name = line.split("won")[0].replace("Match", "").strip(": ").strip()
            winners.append(name)

    if len(winners) != 3:
        await message.channel.send("❌ Submit exactly **3 match results**.")
        return

    counts = Counter(winners)
    results_channel = bot.get_channel(RESULTS_CHANNEL_ID)

    output = "🏁 **League Results**\n"
    for display, wins in counts.items():
        losses = 3 - wins
        ping = ""
        for p in league["players"].values():
            if p["display"] == display:
                ping = p["user"].mention
        output += f"{ping} **{display}** — {wins}W / {losses}L\n"

    await results_channel.send(output)
    await message.channel.send("✅ Results posted. League closed.")

    del active_leagues[message.channel.id]


bot.run(BOT_TOKEN)

