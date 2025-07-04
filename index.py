import asyncio
import json
import websockets
import requests
import os
import time
import random
import colorama
from colorama import Fore
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv
import httpx

with open("config.json") as f:
    config = json.load(f)

colorama.init(autoreset=True)

async def async_mass_del_channels(guild_id, channel_id):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/guilds/{guild_id}/channels", headers=HEADERS)
            channels = r.json()

            tasks = []
            for ch in channels:
                tasks.append(client.delete(f"{API_BASE}/channels/{ch['id']}", headers=HEADERS))
            
            await asyncio.gather(*tasks, return_exceptions=True)

        send_message(channel_id, "`All channels deleted.`")
    except Exception as e:
        send_message(channel_id, f"`Error: {e}`")

async def async_create_channels(guild_id, channel_id, count, name):
    try:
        async with httpx.AsyncClient() as client:
            tasks = []
            for _ in range(min(count, 50)):
                tasks.append(
                    client.post( 
                        f"{API_BASE}/guilds/{guild_id}/channels",
                        headers=HEADERS,
                        json={"name": name, "type": 0}
                    )
                )
            await asyncio.gather(*tasks, return_exceptions=True)
        send_message(channel_id, f"`Created {count} channels named '{name}'.`")
    except Exception as e:
        send_message(channel_id, f"`Error: {e}`")

async def fetch_members(guild_id):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/guilds/{guild_id}/members?limit=1000", headers=HEADERS)
        try:
            members = r.json()
            if isinstance(members, list):
                return members
            else:
                raise ValueError("Unexpected response format when fetching members.")
        except Exception as e:
            print("Failed to parse members list:", r.text)
            return []

async def async_mass_ban(guild_id, channel_id, user_id):
    try:
        members = await fetch_members(guild_id)
        async with httpx.AsyncClient() as client:
            tasks = []
            for member in members:
                if isinstance(member, dict) and 'user' in member:
                    uid = member['user']['id']
                    if uid != user_id:
                        url = f"{API_BASE}/guilds/{guild_id}/bans/{uid}"
                        tasks.append(client.put(url, headers=HEADERS))
            await asyncio.gather(*tasks, return_exceptions=True)
        send_message(channel_id, "`Mass ban executed.`")
    except Exception as e:
        send_message(channel_id, f"`Mass ban error: {e}`")

async def async_mass_kick(guild_id, channel_id, user_id):
    try:
        members = await fetch_members(guild_id)
        async with httpx.AsyncClient() as client:
            tasks = []
            for member in members:
                if isinstance(member, dict) and 'user' in member:
                    uid = member['user']['id']
                    if uid != user_id:
                        url = f"{API_BASE}/guilds/{guild_id}/members/{uid}"
                        tasks.append(client.delete(url, headers=HEADERS))
            await asyncio.gather(*tasks, return_exceptions=True)
        send_message(channel_id, "`Mass kick executed.`")
    except Exception as e:
        send_message(channel_id, f"`Mass kick error: {e}`")

async def spam_webhook(webhook_url, message):
    async with httpx.AsyncClient() as client:
        tasks = [client.post(webhook_url, json={"content": message}) for _ in range(5)]
        await asyncio.gather(*tasks)

async def create_and_spam(channel_id, headers, message, count):
    async with httpx.AsyncClient() as client:
        for _ in range(count):
            try:
                res = await client.post(
                    f"{API_BASE}/channels/{channel_id}/webhooks",
                    headers=headers,
                    json={"name": "NerdBot"}
                )
                webhook = res.json()
                webhook_url = f"https://discord.com/api/webhooks/{webhook['id']}/{webhook['token']}"
                await spam_webhook(webhook_url, message)
            except Exception:
                continue

async def handle_webhook_spam(data, args, channel_id):
    try:
        guild_id = data['guild_id']
        count = min(int(args[1]), 10)
        message = " ".join(args[2:])

        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/guilds/{guild_id}/channels", headers=HEADERS)
            channels = r.json()

        text_channels = [ch for ch in channels if ch["type"] == 0]

        # Run in parallel for each channel
        await asyncio.gather(*[
            create_and_spam(channel["id"], HEADERS, message, count)
            for channel in text_channels
        ])

        send_message(channel_id, "`Webhook spam executed.`")
    except Exception as e:
        send_message(channel_id, f"`Error: {e}`")

def fetch_waifu_single(type_, category):
    url = f"https://api.waifu.pics/{type_}/{category}"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("url")
    except Exception as e:
        print(f"[Waifu API error] {e}")
        return None

TOKEN = config['token']
USER_ID = config['id']
GATEWAY = "wss://gateway.discord.gg/?v=9&encoding=json"
API_BASE = "https://discord.com/api/v9"

HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json"
}

impersonating_user = None

def send_message(channel_id, content):
    url = f"{API_BASE}/channels/{channel_id}/messages"
    requests.post(url, headers=HEADERS, json={"content": content})

def extract_user_id(mention):
    return mention.replace("<@", "").replace("!", "").replace(">", "") if mention.startswith("<@") else None

def get_user_info(user_id):
    headers = {
        "Authorization": TOKEN,
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json"
    }
    r = requests.get(f"{API_BASE}/users/{user_id}", headers=headers)
    return r.json() if r.status_code == 200 else None

def get_user_banner(user_data):
    banner = user_data.get("banner")
    if banner:
        ext = "gif" if banner.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/banners/{user_data['id']}/{banner}.{ext}?size=1024"
    return None

def get_user_avatar(user_data):
    avatar = user_data.get("avatar")
    if avatar:
        ext = "gif" if avatar.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_data['id']}/{avatar}.{ext}?size=1024"
    else:
        discrim = int(user_data.get("discriminator", "0"))
        return f"https://cdn.discordapp.com/embed/avatars/{discrim % 5}.png"

async def heartbeat(ws, interval):
    while True:
        await asyncio.sleep(interval / 1000)
        await ws.send(json.dumps({"op": 1, "d": None}))

async def listen():
    global impersonating_user
    while True:
        try:
            async with websockets.connect(GATEWAY, max_size=None) as ws:
                hello = json.loads(await ws.recv())
                asyncio.create_task(heartbeat(ws, hello['d']['heartbeat_interval']))

                await ws.send(json.dumps({
                    "op": 2,
                    "d": {
                        "token": TOKEN,
                        "properties": {"$os": "windows", "$browser": "my_lib", "$device": "my_lib"}
                    }
                }))
                print(f"{Fore.LIGHTBLACK_EX}[{Fore.RED}+{Fore.LIGHTBLACK_EX}]{Fore.RESET} Connected to Gateway.")

                while True:
                    event = json.loads(await ws.recv())
                    if event.get("t") != "MESSAGE_CREATE":
                        continue

                    data = event["d"]
                    author_id = data["author"]["id"]
                    channel_id = data["channel_id"]
                    content = data.get("content", "")

                    if author_id == USER_ID and content.startswith("."):
                        args = content.strip().split()
                        cmd = args[0].lower()
                        rest = " ".join(args[1:])

                        if cmd == ".help":
                            help_text = (
"""
> ```ansi
> [2;30m[2;31mNerdBot[0m[2;30m[0m | [2;31mV0.6[0m | [2;31mHelp Menu[0m
> ```
> ```ansi
> [2;31mUtility[0m
> .help              Shows This Message
> .ping              Pong
> .latency           Returns Clients Latency
> .time              Clients Time
> .repeat x msg      Sends x Amount Of Messages
> .clear x           Clears x Amount Of Messages
> .serverinfo        Returns Server Info
> .quote             Inspiring quote
> .joke              Dad joke
> .advice            Life advice
> .define <word>     Urban dictionary
> 
> [2;31mImage[0m
> .cat, .dog, .duck, .meme
>  
> [2;31mFun[0m
> .roll,         .coinflip
> .8ball   <q>   .emojify <msg>
> .say     <msg> .saybold <msg>
> .reverse <t>   .mock    <msg>
> 
> [2;31mMisc[0m
> .pokemon <pokemon>, .timer <seconds>
> 
> [2;31mImpersonation[0m
> .impersonate @user, .stopimpersonate
>  
> [2;31mNSFW [0m[2;33m18+[0m
> .nsfwwaifu, .nsfwneko, .nsfwtrap
> .nsfwblowjob, .nsfwrandom
>  
> [2;31mNuke[0m [2;33mUse With Caution[0m
> .create x name      Create x channels
> .send x msg         Spam message to all channels
> .delchannels        Delete all channels
> .webhook x msg      Create webhooks & Spam
> .delroles           Delete all roles
> .spamroles x        Create x spam roles
> ```
"""
                            )


                            send_message(channel_id, help_text)

                        elif cmd == ".emojify" and rest:
                            emoji_map = {
                                'a': '🇦', 'b': '🇧', 'c': '🇨', 'd': '🇩', 'e': '🇪',
                                'f': '🇫', 'g': '🇬', 'h': '🇭', 'i': '🇮', 'j': '🇯',
                                'k': '🇰', 'l': '🇱', 'm': '🇲', 'n': '🇳', 'o': '🇴',
                                'p': '🇵', 'q': '🇶', 'r': '🇷', 's': '🇸', 't': '🇹',
                                'u': '🇺', 'v': '🇻', 'w': '🇼', 'x': '🇽', 'y': '🇾',
                                'z': '🇿', '0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣',
                                '4': '4️⃣', '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣',
                                '9': '9️⃣', '!': '❗', '?': '❓'
                            }
                            
                            emojified = []
                            for char in rest.lower():
                                if char in emoji_map:
                                    emojified.append(emoji_map[char])
                                elif char == ' ':
                                    emojified.append('   ')
                            
                            send_message(channel_id, ' '.join(emojified))

                        elif cmd == ".quote":
                            try:
                                data = requests.get("https://api.quotable.io/random").json()
                                send_message(channel_id, f"\"{data['content']}\" — {data['author']}")
                            except:
                                send_message(channel_id, "`Failed to fetch quote.`")

                        elif cmd == ".serverinfo":
                            if 'guild_id' in data:
                                guild_id = data['guild_id']
                                r = requests.get(f"{API_BASE}/guilds/{guild_id}?with_counts=true", headers=HEADERS)
                                if r.status_code == 200:
                                    guild = r.json()

                                    roles_req = requests.get(f"{API_BASE}/guilds/{guild_id}/roles", headers=HEADERS)
                                    roles = roles_req.json() if roles_req.status_code == 200 else []

                                    emojis_req = requests.get(f"{API_BASE}/guilds/{guild_id}/emojis", headers=HEADERS)
                                    emojis = emojis_req.json() if emojis_req.status_code == 200 else []

                                    info = f"""**Server Info: {guild['name']}**
                        > **ID:** {guild['id']}
                        > **Owner:** <@{guild['owner_id']}>
                        > **Members:** {guild.get('approximate_member_count', 'N/A')}
                        > **Online:** {guild.get('approximate_presence_count', 'N/A')}
                        > **Boosts:** {guild.get('premium_subscription_count', 'N/A')}
                        > **Roles:** {len(roles)}
                        > **Emojis:** {len(emojis)}
                        > **Verification Level:** {guild['verification_level']}
                        > **Features:** {', '.join(guild.get('features', [])) or 'None'}
                        > **Created At:** <t:{int(((int(guild['id']) >> 22) + 1420070400000) / 1000)}:F>
                        """

                                    send_message(channel_id, info)
                                else:
                                    send_message(channel_id, f"Failed to fetch server info. ({r.status_code})")
                            else:
                                send_message(channel_id, "This command must be used in a server.")

                        elif cmd == ".advice":
                            try:
                                data = requests.get("https://api.adviceslip.com/advice").json()
                                send_message(channel_id, f"`💡 {data['slip']['advice']}`")
                            except:
                                send_message(channel_id, "`No advice available.`")

                        elif cmd == ".joke":
                            try:
                                data = requests.get("https://official-joke-api.appspot.com/random_joke").json()
                                send_message(channel_id, f"`😂 {data['setup']} — {data['punchline']}`")
                            except:
                                send_message(channel_id, "`Couldn't get a joke.`")

                        elif cmd == ".define" and len(args) > 1:
                            try:
                                word = args[1]
                                r = requests.get(f"https://api.urbandictionary.com/v0/define?term={word}").json()
                                if r['list']:
                                    meaning = r['list'][0]['definition']
                                    send_message(channel_id, f"**{word}**:\n{meaning[:1800]}")
                                else:
                                    send_message(channel_id, "`No definition found.`")
                            except:
                                send_message(channel_id, "`Error fetching definition.`")

                        elif cmd == ".timer" and len(args) > 1:
                            try:
                                seconds = int(args[1])
                                send_message(channel_id, f"`Timer set for {seconds} seconds`")
                                await asyncio.sleep(seconds)
                                send_message(channel_id, f"<@{author_id}> `Timer done!`")
                            except:
                                send_message(channel_id, "`Usage: .timer <seconds>`")

                        elif cmd == ".pokemon" and rest:
                            try:
                                data = requests.get(f"https://pokeapi.co/api/v2/pokemon/{rest.lower()}").json()
                                name = data['name'].capitalize()
                                types = ", ".join([t['type']['name'] for t in data['types']])
                                sprite = data['sprites']['front_default']
                                send_message(channel_id, f"**{name}** ({types})\n{sprite}")
                            except:
                                send_message(channel_id, "`Pokemon not found`")

                        elif cmd == ".weather" and rest:
                            try:
                                data = requests.get(f"http://wttr.in/{rest}?format=%C+%t").text
                                send_message(channel_id, f"`Weather in {rest}: {data}`")
                            except:
                                send_message(channel_id, "`Failed to fetch weather`")

                        elif cmd == ".cat":
                            img = requests.get("https://api.thecatapi.com/v1/images/search").json()[0]["url"]
                            send_message(channel_id, img)

                        elif cmd == ".dog":
                            img = requests.get("https://dog.ceo/api/breeds/image/random").json()["message"]
                            send_message(channel_id, img)

                        elif cmd == ".duck":
                            img = requests.get("https://random-d.uk/api/random").json()["url"]
                            send_message(channel_id, img)

                        elif cmd == ".meme":
                            try:
                                r = requests.get("https://meme-api.com/gimme").json()
                                send_message(channel_id, r.get("url", "`Failed to load meme.`"))
                            except:
                                send_message(channel_id, "`Meme API failed.`")

                        elif cmd == ".nsfwwaifu":
                            url = fetch_waifu_single("nsfw", "waifu")
                            if url:
                                send_message(channel_id, url)
                            else:
                                send_message(channel_id, "`Failed to fetch NSFW content.`")

                        elif cmd == ".nsfwneko":
                            url = fetch_waifu_single("nsfw", "neko")
                            if url:
                                send_message(channel_id, url)
                            else:
                                send_message(channel_id, "`Failed to fetch NSFW content.`")

                        elif cmd == ".nsfwtrap":
                            url = fetch_waifu_single("nsfw", "trap")
                            if url:
                                send_message(channel_id, url)
                            else:
                                send_message(channel_id, "`Failed to fetch NSFW content.`")

                        elif cmd == ".nsfwblowjob":
                            url = fetch_waifu_single("nsfw", "blowjob")
                            if url:
                                send_message(channel_id, url)
                            else:
                                send_message(channel_id, "`Failed to fetch NSFW content.`")

                        elif cmd == ".nsfwrandom":
                            categories = ["waifu", "neko", "trap", "blowjob"]
                            category = random.choice(categories)
                            url = fetch_waifu_single("nsfw", category)
                            if url:
                                send_message(channel_id, f"({category}) {url}")
                            else:
                                send_message(channel_id, "`Failed to fetch NSFW content.`")

                        elif cmd == ".ping":
                            send_message(channel_id, "`Pong!`")

                        elif cmd == ".latency":
                            send_message(channel_id, f"`Latency: {random.randint(50, 150)}ms`")

                        elif cmd == ".time":
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            send_message(channel_id, f"`Time: {now}`")

                        elif cmd == ".userinfo":
                            user = get_user_info(USER_ID)
                            if user:
                                send_message(channel_id, f"`{user['username']}#{user['discriminator']} | ID: {user['id']}`")

                        elif cmd == ".pfp" and len(args) > 1:
                            uid = extract_user_id(args[1])
                            user = get_user_info(uid)
                            if user:
                                avatar_url = get_user_avatar(user)
                                send_message(channel_id, f"{user['username']}#{user['discriminator']}:\n{avatar_url}")

                        elif cmd == ".banner" and len(args) > 1:
                            uid = extract_user_id(args[1])
                            user = get_user_info(uid)
                            if user:
                                banner_url = get_user_banner(user)
                                if banner_url:
                                    send_message(channel_id, f"{user['username']}#{user['discriminator']}:\n{banner_url}")
                                else:
                                    send_message(channel_id, "`No banner set.`")

                        elif cmd == ".impersonate" and len(args) > 1:
                            uid = extract_user_id(args[1])
                            impersonating_user = uid
                            send_message(channel_id, f"`Now impersonating <@{uid}>`")

                        elif cmd == ".stopimpersonate":
                            impersonating_user = None
                            send_message(channel_id, "`Stopped impersonating.`")

                        elif cmd == ".roll":
                            send_message(channel_id, f"`🎲 {random.randint(1,6)}`")

                        elif cmd == ".coinflip":
                            send_message(channel_id, f"`🪙 {random.choice(['Heads', 'Tails'])}`")

                        elif cmd == ".8ball" and rest:
                            responses = [
                                "Yes", "No", "Maybe", "Definitely", "Ask again later",
                                "Absolutely", "Not likely", "Hell no", "Sure", "Possibly"
                            ]
                            send_message(channel_id, f"`🎱 {random.choice(responses)}`")

                        elif cmd == ".reverse" and rest:
                            send_message(channel_id, rest[::-1])

                        elif cmd == ".mock" and rest:
                            mocked = ''.join(c.upper() if i % 2 else c.lower() for i, c in enumerate(rest))
                            send_message(channel_id, mocked)

                        elif cmd == ".say" and rest:
                            send_message(channel_id, rest)

                        elif cmd == ".saybold" and rest:
                            send_message(channel_id, f"**{rest}**")

                        elif cmd == ".repeat" and len(args) > 2:
                            try:
                                times = int(args[1])
                                msg = " ".join(args[2:])
                                for _ in range(min(times, 5)):
                                    send_message(channel_id, msg)
                            except:
                                send_message(channel_id, "`Usage: .repeat <times> <message>`")

                        elif cmd == ".create" and len(args) > 2:
                            try:
                                count = int(args[1])
                                name = " ".join(args[2:])
                                asyncio.create_task(async_create_channels(data['guild_id'], channel_id, count, name))
                            except Exception as e:
                                send_message(channel_id, f"`Error: {e}`")

                        elif cmd == ".massban" and 'guild_id' in data:
                            asyncio.create_task(async_mass_ban(data['guild_id'], channel_id, USER_ID))
                        elif cmd == ".masskick" and 'guild_id' in data:
                            asyncio.create_task(async_mass_kick(data['guild_id'], channel_id, USER_ID))

                        elif cmd == ".delchannels" and 'guild_id' in data:
                            asyncio.create_task(async_mass_del_channels(data['guild_id'], channel_id))

                        elif cmd == ".delroles" and 'guild_id' in data:
                            try:
                                guild_id = data['guild_id']
                                roles = requests.get(f"{API_BASE}/guilds/{guild_id}/roles", headers=HEADERS).json()
                                for role in roles:
                                    try:
                                        if role['name'] != "@everyone":  # Can't delete @everyone
                                            requests.delete(f"{API_BASE}/guilds/{guild_id}/roles/{role['id']}", headers=HEADERS)
                                    except:
                                        continue
                                send_message(channel_id, "`All roles deleted.`")
                            except Exception as e:
                                send_message(channel_id, f"`Error: {e}`")

                        elif cmd == ".spamroles" and 'guild_id' in data and len(args) > 1:
                            try:
                                guild_id = data['guild_id']
                                count = min(int(args[1]), 50)
                                for i in range(count):
                                    requests.post(
                                        f"{API_BASE}/guilds/{guild_id}/roles",
                                        headers=HEADERS,
                                        json={"name": f"nerdbot-{i}", "color": random.randint(0, 0xFFFFFF)}
                                    )
                                send_message(channel_id, f"`Created {count} spam roles.`")
                            except Exception as e:
                                send_message(channel_id, f"`Error: {e}`")

                        elif cmd == ".renameall" and 'guild_id' in data and len(args) > 1:
                            try:
                                guild_id = data['guild_id']
                                new_name = " ".join(args[1:])
                                members = requests.get(f"{API_BASE}/guilds/{guild_id}/members?limit=1000", headers=HEADERS).json()
                                for member in members:
                                    try:
                                        requests.patch(
                                            f"{API_BASE}/guilds/{guild_id}/members/{member['user']['id']}",
                                            headers=HEADERS,
                                            json={"nick": new_name}
                                        )
                                    except:
                                        continue
                                send_message(channel_id, f"`Renamed all members to '{new_name}'.`")
                            except Exception as e:
                                send_message(channel_id, f"`Error: {e}`")

                        elif cmd == ".webhook" and 'guild_id' in data and len(args) > 2:
                            asyncio.create_task(handle_webhook_spam(data, args, channel_id))

                        elif cmd == ".send" and len(args) > 2:
                            try:
                                msg_count = int(args[1])
                                msg = " ".join(args[2:])
                                guild_id = data.get("guild_id")
                                if not guild_id:
                                    send_message(channel_id, "`Not in a server.`")
                                else:
                                    channels = requests.get(f"{API_BASE}/guilds/{guild_id}/channels", headers=HEADERS).json()
                                    text_channels = [ch for ch in channels if ch["type"] == 0]
                                    for ch in text_channels:
                                        for _ in range(min(msg_count, 3)):
                                            send_message(ch['id'], msg)
                                    send_message(channel_id, f"`Sent to {len(text_channels)} channels.`")
                            except Exception as e:
                                send_message(channel_id, f"`Error: {e}`")

                        elif cmd == ".id" and len(args) > 1:
                            uid = extract_user_id(args[1])
                            if uid:
                                send_message(channel_id, f"`ID: {uid}`")

                        elif cmd == ".clear" and len(args) > 1:
                            try:
                                limit = int(args[1])
                                messages = requests.get(
                                    f"{API_BASE}/channels/{channel_id}/messages?limit=100",
                                    headers=HEADERS
                                ).json()
                                count = 0
                                for msg in messages:
                                    if msg["author"]["id"] == USER_ID and count < limit:
                                        requests.delete(f"{API_BASE}/channels/{channel_id}/messages/{msg['id']}", headers=HEADERS)
                                        count += 1
                                send_message(channel_id, f"`Deleted {count} messages.`")
                            except Exception as e:
                                send_message(channel_id, f"`Clear error: {e}`")

                        elif cmd == ".meme" and ";" in rest:
                            top, bottom = map(str.strip, rest.split(";", 1))
                            meme_url = f"https://api.memegen.link/images/custom/{quote(top)}/{quote(bottom)}.png?background=https://i.imgflip.com/30b1gx.jpg"
                            send_message(channel_id, meme_url)

                    if impersonating_user and author_id == impersonating_user:
                        send_message(channel_id, f"> {content}\n<@{author_id}>")

        except websockets.ConnectionClosed as e:
            print(f"[WebSocket closed] {e.code}")
            await asyncio.sleep(5)
        except Exception as e:
            await asyncio.sleep(5)

def run():
    asyncio.run(listen())

def get_discord_user_info():
    try:
        r = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': TOKEN})
        if r.status_code == 200:
            u = r.json()
            return {'id': u['id'], 'username': u['username'], 'discriminator': u['discriminator']}
    except:
        return None

def index():
    os.system("title NerdBot V0.6")
    os.system("mode con: cols=55 lines=26")
    print(Fore.RED + r"""

     ███▄▄▄▄      ▄████████    ▄████████ ████████▄  
     ███▀▀▀██▄   ███    ███   ███    ███ ███   ▀███ 
     ███   ███   ███    █▀    ███    ███ ███    ███ 
     ███   ███  ▄███▄▄▄      ▄███▄▄▄▄██▀ ███    ███ 
     ███   ███ ▀▀███▀▀▀     ▀▀███▀▀▀▀▀   ███    ███ 
     ███   ███   ███    █▄  ▀███████████ ███    ███ 
     ███   ███   ███    ███   ███    ███ ███   ▄███ 
      ▀█   █▀    ██████████   ███    ███ ████████▀  
                              ███    ███            
          ▀█████████▄   ▄██████▄      ███           
            ███    ███ ███    ███ ▀█████████▄       
            ███    ███ ███    ███    ▀███▀▀██       
           ▄███▄▄▄██▀  ███    ███     ███   ▀       
          ▀▀███▀▀▀██▄  ███    ███     ███           
            ███    ██▄ ███    ███     ███           
            ███    ███ ███    ███     ███           
          ▄█████████▀   ▀██████▀     ▄████▀         
                                                                      
""")
    print(f"{Fore.LIGHTBLACK_EX}[{Fore.RED}+{Fore.LIGHTBLACK_EX}]{Fore.RESET} Establishing Connection...")
    time.sleep(2)
    user_info = get_discord_user_info()
    if user_info:
        print(f"{Fore.LIGHTBLACK_EX}[{Fore.RED}+{Fore.LIGHTBLACK_EX}]{Fore.RESET} Logged In As {user_info['username']}#{user_info['discriminator']} | {user_info['id']}")
        print(f"{Fore.LIGHTBLACK_EX}[{Fore.RED}+{Fore.LIGHTBLACK_EX}]{Fore.RESET} Gateway {Fore.LIGHTBLACK_EX}{GATEWAY[:30]}*****")
        print(f"{Fore.LIGHTBLACK_EX}[{Fore.RED}+{Fore.LIGHTBLACK_EX}]{Fore.RESET} API Base {Fore.LIGHTBLACK_EX}{API_BASE}")
    run()

index()
