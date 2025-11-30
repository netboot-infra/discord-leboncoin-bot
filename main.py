import discord
from discord.ext import tasks
from discord import app_commands
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import os
from fake_useragent import UserAgent
from dateutil import parser

# ============ CONFIGURATION ============
BOT_TOKEN               = os.environ.get('BOT_TOKEN')
CHECK_INTERVAL          = os.getenv("CHECK_INTERVAL", 10)
STORAGE_DIR             = os.getenv("STORAGE_DIR", "")
SEARCHES_FILE           = os.path.join(STORAGE_DIR, "searches.json")
SEEN_ADS_FILE           = os.path.join(STORAGE_DIR, "seen_ads.json")

# ============ DISCORD BOT ============
intents = discord.Intents.default()
intents.message_content = False
intents.guilds = True 

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

searches = {}
seen_ads = set()

# ============ DATA MANAGEMENT ============
def load_searches():
    try:
        with open(SEARCHES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_searches(data):
    with open(SEARCHES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_seen_ads():
    try:
        with open(SEEN_ADS_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen_ads(data):
    with open(SEEN_ADS_FILE, "w") as f:
        json.dump(list(data), f)


# ============ LEBONCOIN FUNCTIONS ============
def search_ads(search_url):
    """Fetch and parse ads from a search URL."""
    
    user_agent = UserAgent().random
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        session = requests.Session()
        response = session.get(search_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        scripts = soup.find_all("script")
        annonces = []

        for script in scripts:
            content = script.string
            if not content or '"list_id"' not in content:
                continue

            try:
                # Locate the JSON part containing ads
                start = content.find('"ads":[')
                if start == -1:
                    continue

                json_part = content[start:]
                bracket_count = 0

                # Determine the end index of the ads array
                for i, char in enumerate(json_part):
                    if char == "[":
                        bracket_count += 1
                    elif char == "]":
                        bracket_count -= 1
                        if bracket_count == 0:
                            json_str = "{" + json_part[: i + 1] + "}"
                            data = json.loads(json_str)
                            annonces = data.get("ads", [])
                            break

            except Exception:
                continue

        return annonces

    except Exception as e:
        print("Search error:", e)
        return []

def extract_price(price_data):
    if isinstance(price_data, list) and price_data:
        return price_data[0]
    if isinstance(price_data, int):
        return price_data
    return None


def time_since(date_str):
    try:
        published = parser.parse(date_str)
        now = datetime.now(published.tzinfo)
        delta = now - published

        if delta.days > 0:
            return f"{delta.days} day(s)"
        if delta.seconds >= 3600:
            return f"{delta.seconds // 3600} hour(s)"
        if delta.seconds >= 60:
            return f"{delta.seconds // 60} minute(s)"
        return "seconds ago"
    except:
        return "recently"


# ============ SLASH COMMANDS ============

@tree.command(name="help", description="Show the bot guide")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Leboncoin Bot Guide",
        description="Automatically monitor Leboncoin search results!",
        color=discord.Color.blue()
    )

    embed.add_field(name="/add <link>", value="Add a search to this channel", inline=False)
    embed.add_field(name="/remove <number>", value="Remove a search from this channel", inline=False)
    embed.add_field(name="/list", value="List all searches in this channel", inline=False)
    embed.add_field(name="/check", value="Force an immediate check", inline=False)
    embed.add_field(name="/stats", value="Show bot statistics", inline=False)

    embed.set_footer(text=f"Automatic check every {CHECK_INTERVAL} minute(s)")
    await interaction.response.send_message(embed=embed)


@tree.command(name="add", description="Add a Leboncoin search link")
async def add_cmd(interaction: discord.Interaction, url: str):
    if not url.startswith("https://www.leboncoin.fr/recherche"):
        await interaction.response.send_message("❌ Invalid Leboncoin search link!", ephemeral=True)
        return

    channel_id = str(interaction.channel.id)

    if channel_id not in searches:
        searches[channel_id] = []

    for s in searches[channel_id]:
        if s["url"] == url:
            await interaction.response.send_message("⚠️ This search already exists in this channel!")
            return

    searches[channel_id].append({
        "url": url,
        "added_on": datetime.now().strftime("%d/%m/%Y %H:%M")
    })

    save_searches(searches)

    embed = discord.Embed(
        title="✅ Search added!",
        description=f"The bot will monitor this search in {interaction.channel.mention}",
        color=discord.Color.green()
    )

    embed.add_field(name="🔗 Link", value=url, inline=False)
    embed.add_field(name="📊 Total searches", value=len(searches[channel_id]), inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="remove", description="Remove a search from this channel")
async def remove_cmd(interaction: discord.Interaction, number: int):
    channel_id = str(interaction.channel.id)

    if channel_id not in searches or not searches[channel_id]:
        await interaction.response.send_message("❌ No searches in this channel!", ephemeral=True)
        return

    if number < 1 or number > len(searches[channel_id]):
        await interaction.response.send_message(
            f"❌ Invalid number! Choose between 1 and {len(searches[channel_id])}.",
            ephemeral=True
        )
        return

    searches[channel_id].pop(number - 1)

    if not searches[channel_id]:
        del searches[channel_id]

    save_searches(searches)

    await interaction.response.send_message(f"✅ Search #{number} removed!")

@tree.command(name="list", description="List all searches in this channel")
async def list_cmd(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)

    if channel_id not in searches or not searches[channel_id]:
        await interaction.response.send_message("📋 No searches configured in this channel.")
        return

    embed = discord.Embed(
        title=f"📋 Searches monitored in #{interaction.channel.name}",
        color=discord.Color.blue()
    )

    for i, s in enumerate(searches[channel_id], 1):
        embed.add_field(
            name=f"#{i}",
            value=f"🔗 {s['url']}\n📅 Added on {s['added_on']}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@tree.command(name="stats", description="Show bot statistics")
async def stats_cmd(interaction: discord.Interaction):
    total_searches = sum(len(s) for s in searches.values())
    total_channels = len(searches)

    embed = discord.Embed(
        title="📊 Bot Statistics",
        color=discord.Color.gold()
    )

    embed.add_field(name="🔍 Active searches", value=total_searches)
    embed.add_field(name="📺 Channels monitored", value=total_channels)
    embed.add_field(name="👀 Seen ads", value=len(seen_ads))
    embed.add_field(name="⏱️ Interval", value=f"{CHECK_INTERVAL} min")

    await interaction.response.send_message(embed=embed)

@tree.command(name="check", description="Force an immediate check")
async def check_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🔄 Checking now...")
    await check_all_searches()
    await interaction.followup.send("✅ Check completed!")


# ============ BACKGROUND TASK ============
@tasks.loop(minutes=CHECK_INTERVAL)
async def check_ads():
    await check_all_searches()

async def check_all_searches():
    global seen_ads

    print(f"\n🔄 Checking - {datetime.now().strftime('%H:%M:%S')}")

    for channel_id, search_list in searches.items():
        channel = client.get_channel(int(channel_id))

        if not channel:
            continue

        for search in search_list:
            url = search["url"]
            ads = search_ads(url)

            for ad in ads:
                ad_id = str(ad.get("list_id", ""))

                if not ad_id or ad_id in seen_ads:
                    continue

                title = ad.get("subject", "")
                price = extract_price(ad.get("price"))
                ad_url = ad.get("url", "")

                if ad_url and not ad_url.startswith("http"):
                    ad_url = f"https://www.leboncoin.fr{ad_url}"

                location = ad.get("location", {})
                city = location.get("city_label", "")

                images = ad.get("images", {}).get("urls", [])
                attributes = ad.get("attributes", [])
                body = ad.get("body", "")

                embed = discord.Embed(
                    title=f"🔥 {title}",
                    url=ad_url,
                    description=body[:300] + "..." if len(body) > 300 else body,
                    color=0xFF6B35,
                    timestamp=datetime.now()
                )

                if price:
                    embed.add_field(name="💰 Price", value=f"{price} €", inline=True)

                if city:
                    embed.add_field(name="📍 Location", value=city, inline=True)

                index_date = ad.get("index_date", "")
                if index_date:
                    embed.add_field(name="🕐 Published", value=f"{time_since(index_date)} ago", inline=True)

                extra_info = []
                for attr in attributes:
                    key = attr.get("key")
                    value = attr.get("value")
                    if key == "regdate":
                        extra_info.append(f"📅 Year: {value}")
                    elif key == "mileage":
                        extra_info.append(f"🚗 Mileage: {value} km")
                    elif key == "fuel":
                        extra_info.append(f"⛽ Fuel: {value}")

                if extra_info:
                    embed.add_field(name="ℹ️ Info", value="\n".join(extra_info), inline=False)

                if images:
                    embed.set_image(url=images[0])

                if len(images) > 1:
                    embed.add_field(name="📸 Photos", value=f"{len(images)} photo(s)", inline=False)

                embed.set_footer(text="Leboncoin", icon_url="https://www.leboncoin.fr/favicon.ico")

                try:
                    await channel.send(embed=embed)
                    seen_ads.add(ad_id)
                    print(f"New ad sent to #{channel.name}")
                except Exception as e:
                    print("Send error:", e)

    save_seen_ads(seen_ads)

# ============ STARTING THE BOT ============
@client.event
async def on_ready():
    global searches, seen_ads
    searches = load_searches()
    seen_ads = load_seen_ads()

    print(f"✅ Bot connected as {client.user}")
    print(f"📋 {len(searches)} search(es) loaded")
    print(f"⏱️ Interval: {CHECK_INTERVAL} minutes")

    await tree.sync()

    if not check_ads.is_running():
        check_ads.start()

if __name__ == "__main__":
    print("🚀 Starting bot...")
    client.run(BOT_TOKEN)
