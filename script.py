import discord
from discord import app_commands
from discord.ext import commands
from trello import TrelloClient
import os
import json

# Enable intents
intents = discord.Intents.default()
intents.message_content = True

# Set up the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# File to store user API keys, preferences, and known Trello cards
USER_DATA_FILE = "user_data.json"
KNOWN_CARDS_FILE = "known_cards.json"

# Load existing user data from file
if os.path.exists(USER_DATA_FILE):
    with open(USER_DATA_FILE, "r") as f:
        user_data = json.load(f)
else:
    user_data = {}

# Load known Trello cards to avoid duplicate pings
if os.path.exists(KNOWN_CARDS_FILE):
    with open(KNOWN_CARDS_FILE, "r") as f:
        known_card_ids = set(json.load(f))
else:
    known_card_ids = set()

def save_user_data():
    """Save the user data to a JSON file."""
    with open(USER_DATA_FILE, "w") as f:
        json.dump(user_data, f)

def save_known_card_ids():
    """Save the known card IDs to a JSON file."""
    with open(KNOWN_CARDS_FILE, "w") as f:
        json.dump(list(known_card_ids), f)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()  # Sync slash commands
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.command(help="Set your Trello API key, token, and board ID. Input: [api_key] [token] [board ID]")
async def set_trello(ctx, api_key: str, token: str, board_id: str):
    """Set your Trello API key, token, and board ID."""
    user_id = str(ctx.author.id)
    user_data[user_id] = {
        'api_key': api_key,
        'token': token,
        'board_id': board_id
    }
    save_user_data()
    await ctx.send(f"Your Trello API credentials and board ID have been set, {ctx.author.mention}.")

@bot.command(help="Assign your Trello member ID to your Discord account. Input: [member ID from Trello]")
async def assign_trello_id(ctx, trello_id: str):
    """Assign your Trello member ID to your Discord account."""
    user_id = str(ctx.author.id)
    user_data.setdefault(user_id, {})['trello_id'] = trello_id
    save_user_data()
    await ctx.send(f"Trello ID `{trello_id}` has been assigned to {ctx.author.mention}.")

@bot.command(help="Set the channels where you want to receive notifications.")
async def set_channels(ctx, *channel_names):
    """Set the channels where you want to receive notifications."""
    user_id = str(ctx.author.id)
    user_data.setdefault(user_id, {})['channels'] = list(channel_names)
    save_user_data()
    await ctx.send(f"Notification channels have been set for {ctx.author.mention}.")

def get_trello_client(user_id):
    """Initialize a Trello client for a user."""
    user_info = user_data.get(str(user_id), {})
    api_key, token = user_info.get('api_key'), user_info.get('token')
    return TrelloClient(api_key=api_key, token=token) if api_key and token else None

@bot.command(help="Lists board users and their ID's")
async def list_board_members(ctx):
    """List all members of the user's Trello board with their usernames and IDs."""
    user_id = str(ctx.author.id)
    user_info = user_data.get(user_id, {})
    board_id = user_info.get('board_id')

    trello_client = get_trello_client(user_id)
    if not trello_client:
        await ctx.send("Set your Trello API credentials using `!set_trello`.")
        return

    try:
        board = trello_client.get_board(board_id)
        members = board.get_members()
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")
        return

    if not members:
        await ctx.send("No members found on this board.")
        return

    embed = discord.Embed(title=f"Members of Board: {board.name}", color=discord.Color.blue())
    for member in members:
        embed.add_field(name=member.username, value=f"Full Name: {member.full_name}\nTrello ID: `{member.id}`", inline=False)
    await ctx.send(embed=embed)

@bot.command(help="Notify users of new Trello tasks and updates.")
async def pingAll(ctx):
    """Check for new cards and changes on the Trello board and notify assigned users."""
    user_id = str(ctx.author.id)
    user_info = user_data.get(user_id, {})

    trello_client = get_trello_client(user_id)
    board_id = user_info.get('board_id')

    if not trello_client or not board_id:
        await ctx.send("Ensure your Trello API credentials and board ID are set using `!set_trello`.")
        return

    try:
        board = trello_client.get_board(board_id)
        cards = board.open_cards()
    except Exception as e:
        await ctx.send(f"Error accessing Trello board: {e}")
        return

    # Load stored card states
    CARD_STATES_FILE = "card_states.json"
    if os.path.exists(CARD_STATES_FILE):
        with open(CARD_STATES_FILE, "r") as f:
            card_states = json.load(f)
    else:
        card_states = {}

    new_cards = []
    updated_cards = []

    for card in cards:
        card_id = card.id
        assigned_members = card.member_id

        # Ensure checklists exist to avoid UnboundLocalError
        new_checklists = {}

        # Identify new cards
        if card_id not in known_card_ids:
            new_cards.append(card)
            known_card_ids.add(card_id)

        # Identify card changes, including checklist updates
        else:
            previous_state = card_states.get(card_id, {})
            changes = []

            # Check for description changes
            if previous_state.get("desc") != card.desc:
                changes.append(f"📜 **Description changed:**\n{card.desc}")

            # Track checklist changes
            for checklist in card.checklists:
                checklist_name = checklist.name
                new_checklists[checklist_name] = {
                    item["name"]: item["state"] for item in checklist.items
                }

            previous_checklists = previous_state.get("checklists", {})

            # Detect new, completed, and removed checklist items
            for checklist_name, items in new_checklists.items():
                if checklist_name not in previous_checklists:
                    changes.append(f"📋 **New checklist added:** {checklist_name}")
                else:
                    old_items = previous_checklists.get(checklist_name, {})

                    for item_name, state in items.items():
                        prev_state = old_items.get(item_name)

                        # New checklist item detected
                        if prev_state is None:
                            changes.append(f"🆕 **New goal added:** {item_name}")

                        # Completed checklist item
                        elif prev_state != state and state == "complete":
                            changes.append(f"✅ **Goal completed:** {item_name}")

                        # Ongoing/In-progress goal
                        elif prev_state != state and state == "incomplete":
                            changes.append(f"🔄 **Goal marked as in-progress:** {item_name}")

                    # Detect removed checklist items
                    for old_item in old_items.keys():
                        if old_item not in items:
                            changes.append(f"❌ **Goal removed:** {old_item}")

            if changes:
                updated_cards.append((card, changes))

        # Save current state
        card_states[card_id] = {
            "desc": card.desc,
            "checklists": new_checklists  # Now always exists
        }

    # Notify users about new and updated cards
    if not new_cards and not updated_cards:
        await ctx.send("No new or updated Trello tasks found.")
        return

    for card in new_cards:
        for trello_member_id in card.member_id:
            for uid, info in user_data.items():
                if info.get('trello_id') == trello_member_id:
                    discord_user = await bot.fetch_user(uid)
                    if discord_user:
                        for channel_name in info.get('channels', []):
                            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
                            if channel:
                                await channel.send(
                                    f"{discord_user.mention}, a new card has been assigned to you: **{card.name}**\n{card.shortUrl}"
                                )

    for card, changes in updated_cards:
        for trello_member_id in card.member_id:
            for uid, info in user_data.items():
                if info.get('trello_id') == trello_member_id:
                    discord_user = await bot.fetch_user(uid)
                    if discord_user:
                        for channel_name in info.get('channels', []):
                            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
                            if channel:
                                await channel.send(
                                    f"{discord_user.mention}, updates on your Trello task: **{card.name}**\n{card.shortUrl}\n"
                                    + "\n".join(changes)
                                )

    # Save updated states
    with open(CARD_STATES_FILE, "w") as f:
        json.dump(card_states, f)

    save_known_card_ids()
    await ctx.send("Trello assignments and updates have been notified.")
# Slash command with autocomplete
@bot.tree.command(name="search", description="Search for a command")
@app_commands.describe(query="Command name")
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    await interaction.followup.send(f'Searching for: {query}')

# Autocomplete handler for command names
@search.autocomplete('query')
async def search_autocomplete(interaction: discord.Interaction, current: str):
    command_list = ["set_trello", "assign_trello_id", "set_channels", "list_board_members", "pingAll"]
    suggestions = [app_commands.Choice(name=cmd, value=cmd) for cmd in command_list if current.lower() in cmd.lower()]
    return suggestions

# Run the bot
bot.run(os.getenv("DISCORD_TOKEN"))
