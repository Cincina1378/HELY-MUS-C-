main.py

import os
import json
import asyncio
import discord
import yt_dlp
from datetime import date
from urllib.parse import urlparse
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect, Select
# ==================================================
# HELY MÜZİK - AYARLAR
# ==================================================
OWNER_ID = 1487816729336877106
ROOM_CATEGORY_ID = 1559255416788230266
PREMIUM_ROLE_ID = 1558524707752509560
DAILY_SONG_LIMIT = 10
AD_SECONDS = 20
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "bot_data.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(
    command_prefix=("!!", "!"),
    intents=intents,
    help_command=None,
    case_insensitive=True
)
music_queues = {}
player_tasks = {}
current_tracks = {}
previous_tracks = {}
repeat_enabled = {}
shuffle_enabled = {}
music_volumes = {}
skip_requested = set()
stop_requested = set()
# ==================================================
# VERİLER
# ==================================================
DEFAULT_DATA = {
    "users": {},
    "rooms": {},
    "unlimited_users": [],
    "banned_users": [],
    "banned_artists": [],
    "banned_songs": [],
    "presence": {
        "status": "online",
        "activity": "HELY MÜZİK"
    }
}
def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in DEFAULT_DATA.items():
            if key not in data:
                data[key] = value
        return data
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_DATA))
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
data = load_data()
def is_owner(user):
    return user.id == OWNER_ID
def get_user_data(user_id):
    key = str(user_id)
    if key not in data["users"]:
        data["users"][key] = {
            "date": str(date.today()),
            "used": 0,
            "bonus": 0
        }
    user = data["users"][key]
    if user.get("date") != str(date.today()):
        user["date"] = str(date.today())
        user["used"] = 0
    user.setdefault("bonus", 0)
    save_data(data)
    return user
def is_unlimited(user_id):
    return (
        user_id == OWNER_ID
        or user_id in data["unlimited_users"]
    )
def remaining_songs(user_id):
    if is_unlimited(user_id):
        return float("inf")
    user = get_user_data(user_id)
    return max(0, DAILY_SONG_LIMIT - user["used"]) + user["bonus"]
def spend_song(user_id):
    if is_unlimited(user_id):
        return True
    user = get_user_data(user_id)
    if user["bonus"] > 0:
        user["bonus"] -= 1
    elif user["used"] < DAILY_SONG_LIMIT:
        user["used"] += 1
    else:
        return False
    save_data(data)
    return True
def refund_song(user_id):
    if is_unlimited(user_id):
        return
    user = get_user_data(user_id)
    if user["used"] > 0:
        user["used"] -= 1
    else:
        user["bonus"] += 1
    save_data(data)
# ==================================================
# YOUTUBE
# ==================================================
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "extract_flat": False,
    "source_address": "0.0.0.0"
}
FFMPEG_OPTIONS = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    ),
    "options": "-vn"
}
def is_youtube_url(text):
    try:
        host = (urlparse(text).hostname or "").lower()
        return host in (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
            "www.youtu.be"
        )
    except Exception:
        return False
def get_video_id(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host.endswith("youtu.be"):
            return parsed.path.strip("/").split("/")[0]
        if "youtube.com" in host:
            if parsed.path == "/watch":
                from urllib.parse import parse_qs
                return parse_qs(parsed.query).get("v", [""])[0]
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live"):
                return parts[1]
    except Exception:
        pass
    return ""
def is_banned_track(track):
    title = str(track.get("title", "")).casefold()
    uploader = str(track.get("uploader", "")).casefold()
    url = str(track.get("webpage_url", "")).casefold()
    video_id = get_video_id(url)
    for banned in data["banned_songs"]:
        banned = str(banned).casefold().strip()
        if not banned:
            continue
        if banned == video_id or banned == url or banned in title:
            return True
    for artist in data["banned_artists"]:
        artist = str(artist).casefold().strip()
        if artist and (
            artist in uploader
            or artist in title
        ):
            return True
    return False
def extract_track(query):
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        if is_youtube_url(query):
            info = ydl.extract_info(query, download=False)
        else:
            info = ydl.extract_info(
                "ytsearch1:" + query,
                download=False
            )
            entries = info.get("entries") or []
            info = next(
                (entry for entry in entries if entry),
                None
            )
        if not info:
            return None
        if info.get("_type") == "playlist":
            return None
        url = info.get("webpage_url") or info.get("original_url") or ""
        if not is_youtube_url(url):
            return None
        track = {
            "title": info.get("title", "Bilinmeyen şarkı"),
            "url": url,
            "webpage_url": url,
            "uploader": info.get("uploader", ""),
            "duration": info.get("duration", 0),
            "requester": None
        }
        if is_banned_track(track):
            return {"banned": True, **track}
        track["audio_url"] = info.get("url")
        return track
async def search_track(query):
    return await asyncio.to_thread(extract_track, query)
async def refresh_audio_url(track):
    def extract():
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(
                track["webpage_url"],
                download=False
            )
            return info.get("url")
    return await asyncio.to_thread(extract)
# ==================================================
# ÖZEL ODA
# ==================================================
def get_room(guild_id):
    return data["rooms"].get(str(guild_id))
def get_queue(guild_id):
    return music_queues.setdefault(guild_id, [])
def is_room_owner(ctx):
    room = get_room(ctx.guild.id)
    return (
        room is not None
        and room.get("owner_id") == ctx.author.id
    )
async def create_private_room(guild, owner):
    category = guild.get_channel(ROOM_CATEGORY_ID)
    if not isinstance(category, discord.CategoryChannel):
        raise RuntimeError("Özel oda kategorisi bulunamadı.")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
            connect=False
        ),
        owner: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            manage_channels=True
        )
    }
    channel = await guild.create_voice_channel(
        name=f"{owner.display_name} • HELY",
        category=category,
        overwrites=overwrites,
        reason="HELY MÜZİK özel ses odası"
    )
    data["rooms"][str(guild.id)] = {
        "channel_id": channel.id,
        "owner_id": owner.id
    }
    save_data(data)
    return channel
# ==================================================
# MÜZİK PANELİ
# ==================================================
class MusicControls(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
    async def interaction_check(self, interaction):
        room = get_room(self.guild_id)
        if not room:
            await interaction.response.send_message(
                "Özel oda bulunamadı.",
                ephemeral=True
            )
            return False
        if (
            interaction.user.id != room["owner_id"]
            and interaction.user.id != OWNER_ID
        ):
            await interaction.response.send_message(
                "Bu müzik panelini yalnızca oda sahibi kullanabilir.",
                ephemeral=True
            )
            return False
        return True
    @discord.ui.button(
        label="Duraklat / Devam",
        emoji="⏯️",
        style=discord.ButtonStyle.primary
    )
    async def pause_resume(self, interaction, button):
        voice = interaction.guild.voice_client
        if not voice or not voice.is_playing() and not voice.is_paused():
            await interaction.response.send_message(
                "Şu anda çalan bir şarkı yok.",
                ephemeral=True
            )
            return
        if voice.is_paused():
            voice.resume()
            message = "Müzik devam ediyor."
        else:
            voice.pause()
            message = "Müzik duraklatıldı."
        await interaction.response.send_message(
            message,
            ephemeral=True
        )
    @discord.ui.button(
        label="Atla",
        emoji="⏭️",
        style=discord.ButtonStyle.secondary
    )
    async def skip(self, interaction, button):
        voice = interaction.guild.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            skip_requested.add(self.guild_id)
            voice.stop()
            await interaction.response.send_message(
                "Şarkı atlandı.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Şu anda çalan şarkı yok.",
                ephemeral=True
            )
    @discord.ui.button(
        label="Durdur",
        emoji="⏹️",
        style=discord.ButtonStyle.danger
    )
    async def stop(self, interaction, button):
        voice = interaction.guild.voice_client
        if voice:
            stop_requested.add(self.guild_id)
            music_queues[self.guild_id] = []
            if voice.is_playing() or voice.is_paused():
                voice.stop()
            await voice.disconnect()
        await interaction.response.send_message(
            "Müzik durduruldu ve kuyruk temizlendi.",
            ephemeral=True
        )
    @discord.ui.button(
        label="Kuyruk",
        emoji="📜",
        style=discord.ButtonStyle.secondary
    )
    async def queue(self, interaction, button):
        tracks = get_queue(self.guild_id)
        if not tracks:
            message = "Kuyrukta bekleyen şarkı yok."
        else:
            lines = [
                f"**{i}.** {track['title']}"
                for i, track in enumerate(tracks[:10], 1)
            ]
            message = "\n".join(lines)
        await interaction.response.send_message(
            message,
            ephemeral=True
        )
# ==================================================
# REKLAM
# ==================================================
class AdvertisementView(View):
    def __init__(self):
        super().__init__(timeout=AD_SECONDS)
        self.confirmed = False
    @discord.ui.button(
        label="Reklamı Gördüm",
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def confirm(self, interaction, button):
        self.confirmed = True
        await interaction.response.send_message(
            "Teşekkürler! Müzik devam edebilir.",
            ephemeral=True
        )
        self.stop()
async def show_advertisement(ctx):
    if is_unlimited(ctx.author.id):
        return
    embed = discord.Embed(
        title="HELY MÜZİK",
        description=(
            "Müzik hizmetini desteklemek için "
            "reklam mesajını onayla."
        ),
        color=discord.Color.blue()
    )
    view = AdvertisementView()
    await ctx.send(embed=embed, view=view)
    await view.wait()
# ==================================================
# OYNATMA MOTORU
# ==================================================
async def music_player(ctx):
    guild_id = ctx.guild.id
    while get_queue(guild_id):
        if guild_id in stop_requested:
            stop_requested.discard(guild_id)
            break
        track = get_queue(guild_id).pop(0)
        if is_banned_track(track):
            await ctx.send(
                f"🚫 **{track['title']}** yasaklandığı için atlandı."
            )
            continue
        room = get_room(guild_id)
        if not room:
            await ctx.send("Özel oda bulunamadı.")
            break
        channel = ctx.guild.get_channel(room["channel_id"])
        if not isinstance(channel, discord.VoiceChannel):
            await ctx.send("Ses kanalı bulunamadı.")
            break
        voice = ctx.guild.voice_client
        try:
            if voice is None:
                voice = await channel.connect()
            elif voice.channel != channel:
                await voice.move_to(channel)
            audio_url = await refresh_audio_url(track)
            if not audio_url:
                await ctx.send("Şarkı bağlantısı alınamadı.")
                continue
            if not spend_song(track["requester"]):
                await ctx.send(
                    f"<@{track['requester']}> günlük şarkı hakkını kullandı."
                )
                continue
            current_tracks[guild_id] = track
            embed = discord.Embed(
                title="🎵 HELY MÜZİK",
                description=(
                    f"**Şimdi çalıyor:** [{track['title']}]"
                    f"({track['webpage_url']})\n"
                    f"**İsteyen:** <@{track['requester']}>"
                ),
                color=discord.Color.blue()
            )
            await ctx.send(
                embed=embed,
                view=MusicControls(guild_id)
            )
            finished = asyncio.Event()
            error = None
            def after_playback(exc):
                nonlocal error
                error = exc
                try:
                    ctx.bot.loop.call_soon_threadsafe(finished.set)
                except RuntimeError:
                    pass
            volume = music_volumes.get(guild_id, 0.5)
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(
                    audio_url,
                    **FFMPEG_OPTIONS
                ),
                volume=volume
            )
            voice.play(source, after=after_playback)
            await finished.wait()
            if error:
                refund_song(track["requester"])
                await ctx.send("Şarkı oynatılırken hata oluştu.")
            else:
                previous_tracks[guild_id] = track
            if guild_id in stop_requested:
                stop_requested.discard(guild_id)
                break
            if guild_id in skip_requested:
                skip_requested.discard(guild_id)
                continue
            await show_advertisement(ctx)
        except Exception as exc:
            await ctx.send(
                f"Müzik hatası: `{type(exc).__name__}`"
            )
    player_tasks.pop(guild_id, None)
# ==================================================
# !PLAY - HERKES KULLANABİLİR
# ==================================================
@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query=None):
    if not query:
        await ctx.send("Kullanım: `!play şarkı adı veya YouTube bağlantısı`")
        return
    if ctx.author.id in data["banned_users"]:
        await ctx.send("Müzik kullanman engellenmiş.")
        return
    if remaining_songs(ctx.author.id) <= 0:
        await ctx.send(
            f"Günlük şarkı hakkın bitti. Günlük limit: {DAILY_SONG_LIMIT}"
        )
        return
    try:
        async with ctx.typing():
            track = await search_track(query)
        if not track:
            await ctx.send("YouTube'da şarkı bulunamadı.")
            return
        if track.get("banned"):
            await ctx.send("🚫 Bu şarkı yasaklandığı için çalınamaz.")
            return
        track["requester"] = ctx.author.id
        guild_id = ctx.guild.id
        get_queue(guild_id).append(track)
        await ctx.send(
            f"➕ **{track['title']}** kuyruğa eklendi."
        )
        if guild_id not in player_tasks:
            player_tasks[guild_id] = asyncio.create_task(
                music_player(ctx)
            )
    except Exception as exc:
        await ctx.send(
            f"Şarkı aranırken hata oluştu: `{type(exc).__name__}`"
        )
# ==================================================
# !SES - YALNIZCA BOT SAHİBİ
# ==================================================
@bot.command(name="ses")
async def ses(ctx):
    if not is_owner(ctx.author):
        await ctx.send("❌ Bu komutu yalnızca bot sahibi kullanabilir.")
        return
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(
            "Önce katılmak istediğin ses kanalına gir, sonra `!ses` yaz."
        )
        return
    channel = ctx.author.voice.channel
    voice = ctx.guild.voice_client
    try:
        if voice is None:
            await channel.connect()
        elif voice.channel != channel:
            await voice.move_to(channel)
        await ctx.send(f"✅ **{channel.name}** kanalına katıldım.")
    except Exception as exc:
        await ctx.send(
            f"Ses kanalına katılamadım: `{type(exc).__name__}`"
        )
# ==================================================
# AYARLAR MODALLARI
# ==================================================
class ActivityModal(Modal, title="Bot Etkinlik Yazısı"):
    activity = TextInput(
        label="Profilde görünecek yazı",
        placeholder="Örn. Ahmet müzik dinliyor",
        max_length=128,
        required=True
    )
    async def on_submit(self, interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "Bu ayarı yalnızca bot sahibi kullanabilir.",
                ephemeral=True
            )
            return
        data["presence"]["activity"] = self.activity.value
        save_data(data)
        await apply_presence()
        await interaction.response.send_message(
            "✅ Botun profil etkinliği güncellendi.",
            ephemeral=True
        )
class BanSongModal(Modal, title="Şarkı Yasakla"):
    url = TextInput(
        label="YouTube bağlantısı veya video kimliği",
        placeholder="https://www.youtube.com/watch?v=...",
        max_length=300,
        required=True
    )
    async def on_submit(self, interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "Bu ayarı yalnızca bot sahibi kullanabilir.",
                ephemeral=True
            )
            return
        value = self.url.value.strip()
        video_id = get_video_id(value) if is_youtube_url(value) else value
        if not video_id:
            await interaction.response.send_message(
                "Geçerli bir YouTube bağlantısı veya video kimliği gir.",
                ephemeral=True
            )
            return
        if video_id.casefold() not in [
            x.casefold() for x in data["banned_songs"]
        ]:
            data["banned_songs"].append(video_id)
        save_data(data)
        await interaction.response.send_message(
            "🚫 Şarkı yasak listesine eklendi.",
            ephemeral=True
        )
class BanArtistModal(Modal, title="Sanatçı Yasakla"):
    artist = TextInput(
        label="Sanatçı adı",
        placeholder="Sanatçı adını yaz",
        max_length=100,
        required=True
    )
    async def on_submit(self, interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "Bu ayarı yalnızca bot sahibi kullanabilir.",
                ephemeral=True
            )
            return
        name = self.artist.value.strip()
        if name.casefold() not in [
            x.casefold() for x in data["banned_artists"]
        ]:
            data["banned_artists"].append(name)
        save_data(data)
        await interaction.response.send_message(
            f"🚫 **{name}** yasaklı sanatçılara eklendi.",
            ephemeral=True
        )
class GrantLimitModal(Modal, title="Şarkı Hakkı Ver"):
    amount = TextInput(
        label="Hak sayısı veya sınırsız",
        placeholder="12 veya sınırsız",
        max_length=20,
        required=True
    )
    def __init__(self, target):
        super().__init__()
        self.target = target
    async def on_submit(self, interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "Bu ayarı yalnızca bot sahibi kullanabilir.",
                ephemeral=True
            )
            return
        value = self.amount.value.strip().casefold()
        user_id = self.target.id
        if value in ("sınırsız", "sinirsiz", "unlimited"):
            if user_id not in data["unlimited_users"]:
                data["unlimited_users"].append(user_id)
            data["users"].pop(str(user_id), None)
            save_data(data)
            message = f"✅ {self.target.mention} için sınırsız hak açıldı."
        else:
            try:
                amount = int(value)
                if amount < 0 or amount > 100000:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "0 ile 100000 arasında sayı veya `sınırsız` yaz.",
                    ephemeral=True
                )
                return
            if user_id in data["unlimited_users"]:
                data["unlimited_users"].remove(user_id)
            user = get_user_data(user_id)
            user["bonus"] += amount
            save_data(data)
            message = (
                f"✅ {self.target.mention} kullanıcısına "
                f"**{amount}** ek şarkı hakkı verildi."
            )
        await interaction.response.send_message(
            message,
            ephemeral=True
        )
# ==================================================
# AYARLAR PANELİ - SADECE BOT SAHİBİ
# ==================================================
class SettingsView(View):
    def __init__(self):
        super().__init__(timeout=300)
    async def interaction_check(self, interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ Bu paneli yalnızca bot sahibi kullanabilir.",
                ephemeral=True
            )
            return False
        return True
    @discord.ui.button(
        label="Etkinlik Yazısı",
        emoji="📝",
        style=discord.ButtonStyle.primary
    )
    async def activity_button(self, interaction, button):
        await interaction.response.send_modal(ActivityModal())
    @discord.ui.button(
        label="Bot Durumu",
        emoji="🟢",
        style=discord.ButtonStyle.primary
    )
    async def status_button(self, interaction, button):
        await interaction.response.send_message(
            "Botun durumunu seç:",
            view=PresenceSelectView(),
            ephemeral=True
        )
    @discord.ui.button(
        label="Şarkı Yasakla",
        emoji="🚫",
        style=discord.ButtonStyle.danger
    )
    async def ban_song_button(self, interaction, button):
        await interaction.response.send_modal(BanSongModal())
    @discord.ui.button(
        label="Sanatçı Yasakla",
        emoji="🎤",
        style=discord.ButtonStyle.danger
    )
    async def ban_artist_button(self, interaction, button):
        await interaction.response.send_modal(BanArtistModal())
    @discord.ui.button(
        label="Kullanıcıya Hak Ver",
        emoji="🎟️",
        style=discord.ButtonStyle.success
    )
    async def grant_button(self, interaction, button):
        await interaction.response.send_message(
            "Hak vereceğin kullanıcıyı seç:",
            view=GrantUserView(),
            ephemeral=True
        )
class PresenceSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Çevrimiçi",
                value="online",
                emoji="🟢"
            ),
            discord.SelectOption(
                label="Boşta",
                value="idle",
                emoji="🌙"
            ),
            discord.SelectOption(
                label="Rahatsız Etmeyin",
                value="dnd",
                emoji="⛔"
            ),
            discord.SelectOption(
                label="Görünmez",
                value="invisible",
                emoji="⚫"
            )
        ]
        super().__init__(
            placeholder="Yeni bot durumunu seç",
            options=options
        )
    async def callback(self, interaction):
        data["presence"]["status"] = self.values[0]
        save_data(data)
        await apply_presence()
        await interaction.response.send_message(
            "✅ Bot durumu güncellendi.",
            ephemeral=True
        )
class PresenceSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(PresenceSelect())
class GrantUserView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(GrantUserSelect())
class GrantUserSelect(UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Şarkı hakkı verilecek kullanıcı",
            min_values=1,
            max_values=1
        )
    async def callback(self, interaction):
        target = self.values[0]
        if target.bot:
            await interaction.response.send_message(
                "Botlara şarkı hakkı verilemez.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(
            GrantLimitModal(target)
        )
# ==================================================
# BOT DURUMUNU UYGULA
# ==================================================
async def apply_presence():
    status_name = data["presence"].get("status", "online")
    activity_text = data["presence"].get(
        "activity",
        "HELY MÜZİK"
    )
    statuses = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible
    }
    status = statuses.get(status_name, discord.Status.online)
    await bot.change_presence(
        status=status,
        activity=discord.Game(name=activity_text)
    )
@bot.command(name="ayarlar")
async def settings(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send(
            "❌ `!!ayarlar` komutunu yalnızca bot sahibi kullanabilir."
        )
        return
    embed = discord.Embed(
        title="⚙️ HELY MÜZİK • Yönetim Paneli",
        description=(
            "Bu panel yalnızca bot sahibine açıktır.\n\n"
            "📝 Profil etkinlik yazısını değiştir\n"
            "🟢 Çevrimiçi durumunu ayarla\n"
            "🚫 Şarkı yasakla\n"
            "🎤 Sanatçı yasakla\n"
            "🎟️ Kullanıcıya ek şarkı hakkı ver"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=SettingsView())
# ==================================================
# YASAK YÖNETİMİ - SADECE BOT SAHİBİ
# ==================================================
@bot.command(name="bansong")
async def ban_song(ctx, *, value=None):
    if not is_owner(ctx.author):
        return
    if not value:
        await ctx.send("Kullanım: `!bansong YouTube bağlantısı`")
        return
    video_id = get_video_id(value) if is_youtube_url(value) else value
    if video_id and video_id.casefold() not in [
        x.casefold() for x in data["banned_songs"]
    ]:
        data["banned_songs"].append(video_id)
        save_data(data)
    await ctx.send("🚫 Şarkı yasaklandı.")
@bot.command(name="unbansong")
async def unban_song(ctx, *, value=None):
    if not is_owner(ctx.author):
        return
    if not value:
        await ctx.send("Kullanım: `!unbansong video_id`")
        return
    video_id = get_video_id(value) if is_youtube_url(value) else value
    data["banned_songs"] = [
        x for x in data["banned_songs"]
        if x.casefold() != video_id.casefold()
    ]
    save_data(data)
    await ctx.send("✅ Şarkı yasağı kaldırıldı.")
@bot.command(name="banartist")
async def ban_artist(ctx, *, name=None):
    if not is_owner(ctx.author):
        return
    if not name:
        await ctx.send("Kullanım: `!banartist sanatçı adı`")
        return
    if name.casefold() not in [
        x.casefold() for x in data["banned_artists"]
    ]:
        data["banned_artists"].append(name)
    save_data(data)
    await ctx.send(f"🚫 **{name}** yasaklandı.")
@bot.command(name="unbanartist")
async def unban_artist(ctx, *, name=None):
    if not is_owner(ctx.author):
        return
    if not name:
        await ctx.send("Kullanım: `!unbanartist sanatçı adı`")
        return
    data["banned_artists"] = [
        x for x in data["banned_artists"]
        if x.casefold() != name.casefold()
    ]
    save_data(data)
    await ctx.send(f"✅ **{name}** yasağı kaldırıldı.")
@bot.command(name="banuser")
async def ban_user(ctx, member: discord.Member = None):
    if not is_owner(ctx.author):
        return
    if member is None:
        await ctx.send("Kullanım: `!banuser @kullanıcı`")
        return
    if member.id not in data["banned_users"]:
        data["banned_users"].append(member.id)
    save_data(data)
    await ctx.send(f"🚫 {member.mention} müzik kullanamaz.")
@bot.command(name="unbanuser")
async def unban_user(ctx, member: discord.Member = None):
    if not is_owner(ctx.author):
        return
    if member is None:
        await ctx.send("Kullanım: `!unbanuser @kullanıcı`")
        return
    data["banned_users"] = [
        user_id for user_id in data["banned_users"]
        if user_id != member.id
    ]
    save_data(data)
    await ctx.send(f"✅ {member.mention} için müzik yasağı kaldırıldı.")
# ==================================================
# SES ODASI SAHİBİ AYRILINCA
# ==================================================
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or before.channel is None:
        return
    room = get_room(member.guild.id)
    if not room:
        return
    if (
        before.channel.id == room["channel_id"]
        and member.id == room["owner_id"]
        and after.channel != before.channel
    ):
        channel = member.guild.get_channel(room["channel_id"])
        if channel:
            try:
                voice = member.guild.voice_client
                if voice and voice.channel == channel:
                    await voice.disconnect()
                await channel.delete(
                    reason="Özel oda sahibi ses kanalından ayrıldı."
                )
            except discord.HTTPException:
                pass
        data["rooms"].pop(str(member.guild.id), None)
        save_data(data)
# ==================================================
# BOT BAŞLANGICI
# ==================================================
@bot.event
async def on_ready():
    print(f"HELY MÜZİK giriş yaptı: {bot.user}")
    try:
        await apply_presence()
    except Exception as exc:
        print("Durum ayarlanamadı:", exc)
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Komutun kullanımı eksik.")
        return
    print("Komut hatası:", repr(error))
    await ctx.send("Komut çalıştırılırken bir hata oluştu.")
# ==================================================
# TOKEN
# ==================================================
token = os.getenv("DISCORD_TOKEN")
if not token and os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            token = config.get("token")
    except Exception:
        pass
if not token:
    raise RuntimeError(
        "DISCORD_TOKEN ortam değişkenini veya config.json içindeki token değerini ayarla."
    )
bot.run(token)

Gerekli paketler

FadeHost üzerindeki requirements.txt dosyasında şunlar bulunmalı:

discord.py
yt-dlp
PyNaCl

Sunucuda ayrıca FFmpeg bulunmalı. Discord Developer Portal’da Message Content Intent ve Server Members Intent ayarlarını etkinleştir.

Komutlar:

* !play şarkı adı — herkes kullanabilir.
* !ses — yalnızca sen kullanabilirsin; bulunduğun ses kanalına girer.
* !!ayarlar — yalnızca sen kullanabilirsin.
* !bansong, !unbansong, !banartist, !unbanartist, !banuser, !unbanuser — yalnızca sen kullanabilirsin.

Not: Bu, temel özellikleri birleştiren tam bir başlangıç sürümüdür; mevcut kodunun birebir korunmuş ve canlı sunucuda test edilmiş bir kopyası değildir. Özel oda oluşturma butonu, önceki müzik panelindeki tüm kontroller ve reklam akışının eski sürümdeki davranışları burada birebir korunmamıştır.
