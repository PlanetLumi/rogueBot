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
        
@bot.command(help="Notify users of new Trello tasks and updates.")
async def pingAll(ctx):
    """Check for new cards and changes on the Trello board and notify assigned users in their preferred channels."""
    server_id = str(ctx.guild.id)
    server_info = server_data.get(server_id, {})

    trello_client = get_trello_client(server_id)
    board_id = server_info.get('board_id')

    if not trello_client or not board_id:
        await ctx.send("⚠️ This server has not set a Trello API key! Use `!set_trello` (Admins only).")
        return

    # Load stored notifications to track previously notified cards
    NOTIFIED_CARDS_FILE = "notified_cards.json"
    if os.path.exists(NOTIFIED_CARDS_FILE):
        with open(NOTIFIED_CARDS_FILE, "r") as f:
            notified_cards = json.load(f)
    else:
        notified_cards = {}

    # Ensure the server has a tracking entry
    if server_id not in notified_cards:
        notified_cards[server_id] = {}

    try:
        board = trello_client.get_board(board_id)
        cards = board.open_cards()
    except Exception as e:
        await ctx.send(f"⚠️ Error accessing Trello board: {e}")
        return

    new_cards = []
    updated_cards = []

    for card in cards:
        card_id = card.id
        assigned_members = card.member_ids
        new_checklists = {}

        # Build current card state
        for checklist in card.checklists:
            checklist_name = checklist.name
            new_checklists[checklist_name] = {item["name"]: item["state"] for item in checklist.items}

        # If this card has not been seen before, mark it as new
        if card_id not in notified_cards[server_id]:
            new_cards.append(card)
            notified_cards[server_id][card_id] = {
                "desc": card.desc,
                "checklists": new_checklists
            }
        else:
            # Compare with the stored state
            previous_state = notified_cards[server_id][card_id]
            changes = []

            # Check description changes
            if previous_state.get("desc") != card.desc:
                changes.append(f"📜 **Description changed:**\n{card.desc}")

            # Compare checklists
            previous_checklists = previous_state.get("checklists", {})
            for checklist_name, items in new_checklists.items():
                if checklist_name not in previous_checklists:
                    changes.append(f"📋 **New checklist added:** {checklist_name}")
                else:
                    old_items = previous_checklists.get(checklist_name, {})
                    for item_name, state in items.items():
                        prev_state = old_items.get(item_name)
                        if prev_state is None:
                            changes.append(f"🆕 **New task added:** {item_name}")
                        elif prev_state != state:
                            if state == "complete":
                                changes.append(f"✅ **Task completed:** {item_name}")
                            elif state == "incomplete":
                                changes.append(f"🔄 **Task in progress:** {item_name}")
                    for old_item in old_items.keys():
                        if old_item not in items:
                            changes.append(f"❌ **Task removed:** {old_item}")

            if changes:
                updated_cards.append((card, changes))

            # Update stored state
            notified_cards[server_id][card_id] = {
                "desc": card.desc,
                "checklists": new_checklists
            }

    # Save updated notified cards state
    with open(NOTIFIED_CARDS_FILE, "w") as f:
        json.dump(notified_cards, f, indent=4)

    # If no new or updated cards, inform the user
    if not new_cards and not updated_cards:
        await ctx.send("✅ No new Trello tasks found.")
        return

    # Send notifications per user in their preferred channels
    for card in new_cards:
        for trello_member_id in card.member_ids:
            for uid, info in server_data[server_id].get("users", {}).items():
                if info.get('trello_id') == trello_member_id:
                    discord_user = await bot.fetch_user(uid)
                    if discord_user:
                        for channel_name in info.get('channels', []):
                            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
                            if channel:
                                await channel.send(
                                    f"{discord_user.mention}, a **new card** has been assigned to you: **{card.name}**\n{card.shortUrl}"
                                )

    for card, changes in updated_cards:
        for trello_member_id in card.member_ids:
            for uid, info in server_data[server_id].get("users", {}).items():
                if info.get('trello_id') == trello_member_id:
                    discord_user = await bot.fetch_user(uid)
                    if discord_user:
                        for channel_name in info.get('channels', []):
                            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
                            if channel:
                                await channel.send(
                                    f"{discord_user.mention}, updates on your Trello task: **{card.name}**\n{card.shortUrl}\n" +
                                    "\n".join(changes)
                                )

    await ctx.send("✅ Trello assignments and updates have been notified.")
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

@bot.command(help="Notify users of new Trello tasks and updates.")
async def pingAll(ctx):
    """Check for new cards and changes on the Trello board and notify assigned users in their preferred channels."""
    server_id = str(ctx.guild.id)
    server_info = server_data.get(server_id, {})

    trello_client = get_trello_client(server_id)
    board_id = server_info.get('board_id')

    if not trello_client or not board_id:
        await ctx.send("⚠️ This server has not set a Trello API key! Use `!set_trello` (Admins only).")
        return

    # Load stored notifications to track previously notified cards
    NOTIFIED_CARDS_FILE = "notified_cards.json"
    if os.path.exists(NOTIFIED_CARDS_FILE):
        with open(NOTIFIED_CARDS_FILE, "r") as f:
            notified_cards = json.load(f)
    else:
        notified_cards = {}

    # Ensure the server has a tracking entry
    if server_id not in notified_cards:
        notified_cards[server_id] = {}

    try:
        board = trello_client.get_board(board_id)
        cards = board.open_cards()
    except Exception as e:
        await ctx.send(f"⚠️ Error accessing Trello board: {e}")
        return

    new_cards = []
    updated_cards = []

    for card in cards:
        card_id = card.id
        assigned_members = card.member_ids
        new_checklists = {}

        # Build current card state
        for checklist in card.checklists:
            checklist_name = checklist.name
            new_checklists[checklist_name] = {item["name"]: item["state"] for item in checklist.items}

        # If this card has not been seen before, mark it as new
        if card_id not in notified_cards[server_id]:
            new_cards.append(card)
            notified_cards[server_id][card_id] = {
                "desc": card.desc,
                "checklists": new_checklists
            }
        else:
            # Compare with the stored state
            previous_state = notified_cards[server_id][card_id]
            changes = []

            # Check description changes
            if previous_state.get("desc") != card.desc:
                changes.append(f"📜 **Description changed:**\n{card.desc}")

            # Compare checklists
            previous_checklists = previous_state.get("checklists", {})
            for checklist_name, items in new_checklists.items():
                if checklist_name not in previous_checklists:
                    changes.append(f"📋 **New checklist added:** {checklist_name}")
                else:
                    old_items = previous_checklists.get(checklist_name, {})
                    for item_name, state in items.items():
                        prev_state = old_items.get(item_name)
                        if prev_state is None:
                            changes.append(f"🆕 **New task added:** {item_name}")
                        elif prev_state != state:
                            if state == "complete":
                                changes.append(f"✅ **Task completed:** {item_name}")
                            elif state == "incomplete":
                                changes.append(f"🔄 **Task in progress:** {item_name}")
                    for old_item in old_items.keys():
                        if old_item not in items:
                            changes.append(f"❌ **Task removed:** {old_item}")

            if changes:
                updated_cards.append((card, changes))

            # Update stored state
            notified_cards[server_id][card_id] = {
                "desc": card.desc,
                "checklists": new_checklists
            }

    # Save updated notified cards state
    with open(NOTIFIED_CARDS_FILE, "w") as f:
        json.dump(notified_cards, f, indent=4)

    # If no new or updated cards, inform the user
    if not new_cards and not updated_cards:
        await ctx.send("✅ No new Trello tasks found.")
        return

    # Send notifications per user in their preferred channels
    for card in new_cards:
        for trello_member_id in card.member_ids:
            for uid, info in server_data[server_id].get("users", {}).items():
                if info.get('trello_id') == trello_member_id:
                    discord_user = await bot.fetch_user(uid)
                    if discord_user:
                        for channel_name in info.get('channels', []):
                            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
                            if channel:
                                await channel.send(
                                    f"{discord_user.mention}, a **new card** has been assigned to you: **{card.name}**\n{card.shortUrl}"
                                )

    for card, changes in updated_cards:
        for trello_member_id in card.member_ids:
            for uid, info in server_data[server_id].get("users", {}).items():
                if info.get('trello_id') == trello_member_id:
                    discord_user = await bot.fetch_user(uid)
                    if discord_user:
                        for channel_name in info.get('channels', []):
                            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
                            if channel:
                                await channel.send(
                                    f"{discord_user.mention}, updates on your Trello task: **{card.name}**\n{card.shortUrl}\n" +
                                    "\n".join(changes)
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
