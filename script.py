import discord
from discord.ext import commands
from trello import TrelloClient
import os
import json

# Enable intents
intents = discord.Intents.default()
intents.message_content = True

# Set up the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# File to store Trello API keys per server
SERVER_DATA_FILE = "server_data.json"

# Load existing server Trello data from file
if os.path.exists(SERVER_DATA_FILE):
    with open(SERVER_DATA_FILE, "r") as f:
        server_data = json.load(f)
else:
    server_data = {}

def save_server_data():
    """Save the server Trello API data to a JSON file."""
    with open(SERVER_DATA_FILE, "w") as f:
        json.dump(server_data, f, indent=4)

def get_trello_client(server_id):
    """Initialize a Trello client for a server."""
    server_info = server_data.get(str(server_id), {})
    api_key, token = server_info.get('api_key'), server_info.get('token')
    return TrelloClient(api_key=api_key, token=token) if api_key and token else None

### ✅ COMMAND: Set Trello Credentials (Admins Only)
@bot.command(help="Set Trello API key, token, and board ID for this server. (Admin Only)")
@commands.has_permissions(administrator=True)
async def set_trello(ctx, api_key: str, token: str, board_id: str):
    """Set Trello API key, token, and board ID for this Discord server."""
    server_id = str(ctx.guild.id)
    server_data[server_id] = {
        'api_key': api_key,
        'token': token,
        'board_id': board_id
    }
    save_server_data()
    await ctx.send(f"✅ Trello API credentials have been set for this server! (Set by {ctx.author.mention})")

### ✅ COMMAND: List Board Members (Uses Server's Trello API Key)
@bot.command(help="Lists all board members for this server's Trello board.")
async def list_board_members(ctx):
    """List all members of the server's Trello board."""
    server_id = str(ctx.guild.id)
    server_info = server_data.get(server_id, {})
    board_id = server_info.get('board_id')

    trello_client = get_trello_client(server_id)
    if not trello_client or not board_id:
        await ctx.send("⚠️ This server has not set a Trello API key! Use `!set_trello` (Admins only).")
        return

    try:
        board = trello_client.get_board(board_id)
        members = board.get_members()
    except Exception as e:
        await ctx.send(f"⚠️ An error occurred: {e}")
        return

    if not members:
        await ctx.send("No members found on this board.")
        return

    embed = discord.Embed(title=f"Members of Board: {board.name}", color=discord.Color.blue())
    for member in members:
        embed.add_field(name=member.username, value=f"Full Name: {member.full_name}\nTrello ID: `{member.id}`", inline=False)
    
    await ctx.send(embed=embed)

### ✅ COMMAND: Ping All Users for Trello Updates (Uses Server's Trello API Key)
@bot.command(help="Notify users of new Trello tasks and updates.")
async def pingAll(ctx):
    """Check for new cards and changes on the Trello board and notify assigned users."""
    server_id = str(ctx.guild.id)
    server_info = server_data.get(server_id, {})

    trello_client = get_trello_client(server_id)
    board_id = server_info.get('board_id')

    if not trello_client or not board_id:
        await ctx.send("⚠️ This server has not set a Trello API key! Use `!set_trello` (Admins only).")
        return

    try:
        board = trello_client.get_board(board_id)
        cards = board.open_cards()
    except Exception as e:
        await ctx.send(f"⚠️ Error accessing Trello board: {e}")
        return

    new_cards = []

    for card in cards:
        card_id = card.id

        # Identify new cards
        if card_id not in new_cards:
            new_cards.append(card)

    if not new_cards:
        await ctx.send("✅ No new Trello tasks found.")
        return

    for card in new_cards:
        await ctx.send(
            f"📢 **New Trello Card:**\n"
            f"**{card.name}**\n{card.shortUrl}"
        )

    await ctx.send("✅ Trello assignments and updates have been notified.")

### ✅ COMMAND: Display Server Trello Settings
@bot.command(help="Show the current Trello API settings for this server.")
async def show_trello_settings(ctx):
    """Displays the current Trello API settings for this server."""
    server_id = str(ctx.guild.id)
    server_info = server_data.get(server_id, {})

    if not server_info:
        await ctx.send("⚠️ This server has not set a Trello API key. Use `!set_trello` (Admins only).")
        return

    await ctx.send(
        f"**Trello Settings for {ctx.guild.name}:**\n"
        f"🔑 API Key: `{server_info['api_key']}`\n"
        f"🔑 Token: `{server_info['token']}`\n"
        f"📌 Board ID: `{server_info['board_id']}`"
    )

### ✅ RUN BOT
bot.run(os.getenv("DISCORD_TOKEN"))
