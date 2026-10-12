
import asyncio
import json
import os
import random
from pathlib import Path
from datetime import date
from urllib.parse import urlparse, quote_plus
from concurrent.futures import ThreadPoolExecutor

import discord
import yt_dlp
from discord.ext import commands

# ============================================================
# HELY MÜZİK | main.py
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
DATA_FILE = BASE_DIR / "bot_data.json"

OWNER_ID = 1487816729336877106
ROOM_CATEGORY_ID = 1559255416788230266
PREMIUM_ROLE_ID = 1558524707752509560

DAILY_SONG_LIMIT = 10
AD_SECONDS = 20
AD_CONFIRM_TIMEOUT = 300

QUALITY_FORMATS = {
    "Az": "bestaudio[abr<=64]/bestaudio/best",
    "Orta": "bestaudio[abr<=128]/bestaudio/best",
    "Çok": "bestaudio/best",
}

# Kalite, günlük şarkı hakkını değiştirmez.
QUALITY_NAMES = ("Az", "Orta", "Çok")

HELY_AD_TEXT = (
    "💜 **HELY PREMIUM REKLAMI**\n\n"
    "🎵 Müzik keyfine reklamsız ve sınırsız devam etmek ister misin?\n\n"
    "✨ **HELY Premium avantajları**\n"
    "🔊 Reklamsız müzik keyfi\n"
    "♾️ Sınırsız dinleme hakkı\n"
    "💜 Daha iyi bir müzik deneyimi\n\n"
    "🛒 Premium üyeliğini **HELY Destek** botunun "
    "marketinden satın al!\n\n"
    "💎 **HELY Premium — Müzik keyfinin yeni seviyesi!**\n\n"
    "👇 Reklamı onaylamak için aşağıdaki butona bas."
)

NODE_PROJECT_AD_TEXT = (
    "**# Node Project**\n\n"
    "Sunucumuzun altyapı ve teknik ihtiyaçlarını Node Project destekliyor.\n\n"
    "Peki nedir bu Node Project ve neden orada olmalısınız?\n\n"
    "Node Project; yazılımla ilgilenenleri, kendi botunu geliştirmek "
    "isteyenleri ve proje sahiplerini bir araya getiren bağımsız bir "
    "geliştirici topluluğu. Amaç sadece sohbet etmek değil, ortaya "
    "gerçekten çalışan projeler koymak ve birbirine destek olmak.\n\n"
    "**Node Project Sunucusunda Sizi Neler Bekliyor?**\n\n"
    "**1. Kod Desteği ve Hata Çözümleri**\n"
    "Node.js, Discord.js veya genel yazılım konularında bir yerde "
    "takıldığınızda, forum kanallarında başlık açıp doğrudan çözüm "
    "alabilirsiniz. Kodunuzu paylaşıp nerede hata yaptığınızı anlamak "
    "burada çok daha kolay.\n\n"
    "**2. Hazır Altyapılar ve Kaynaklar**\n"
    "Sıfırdan bot yazmakla uğraşmak istemiyorsanız veya mantığını "
    "anlamak istediğiniz bir sistem varsa, sunucuda paylaşılan hazır "
    "altyapılardan ve açık kaynak kodlardan yararlanabilirsiniz.\n\n"
    "**3. Projenizi ve Botunuzu Öne Çıkarın**\n"
    "Geliştirdiğiniz bir bot, bir web sitesi veya üzerinde çalıştığınız "
    "bir proje varsa sunucudaki vitrin kanallarında sergileyebilirsiniz. "
    "Hem geri bildirim toplar hem de kitlenizi büyütür.\n\n"
    "**4. Özel Bot Hizmetleri ve Ekip Kurma**\n"
    "Kendi sunucunuz için özel bir bot yaptırmak istiyorsanız ya da "
    "projenize yazılımcı bir ortak arıyorsanız, topluluktaki "
    "geliştiricilerle doğrudan iletişime geçebilirsiniz.\n\n"
    "Yazılımla ilgileniyorsanız, bot geliştiriyorsanız ya da sadece "
    "sağlam bir altyapı arıyorsanız mutlaka göz atın:\n"
    "https://discord.gg/Fszrd9UkYG"
)

# Eski mesajında paylaştığın GIF adresi. İmza süresi dolmuş olabilir.
NODE_PROJECT_GIF = (
    "https://cdn.discordapp.com/attachments/"
    "1524889987529703544/1558794708325498920/nodeproject.gif"
)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=("!!", "!"),
    intents=intents,
    help_command=None,
    case_insensitive=True,
)

# Bir sunucuda botun tek bir aktif ses bağlantısı bulunabilir.
music_queues = {}
player_tasks = {}
current_tracks = {}
previous_tracks = {}
repeat_enabled = {}
shuffle_enabled = {}
music_volumes = {}
skip_requested = set()
stop_requested = set()
ad_counter = 0
player_locks = {}


# ============================================================
# VERİ KAYDI
# ============================================================

def load_data():
    default = {
        "users": {},
        "rooms": {},
        "unlimited_users": [],
        "banned_users": [],
        "banned_artists": [],
        "banned_songs": [],
    }

    if not DATA_FILE.exists():
        return default

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            saved = json.load(file)

        for key, value in default.items():
            if key not in saved:
                saved[key] = value

        return saved
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Veri dosyası okunamadı: {exc}")
        return default


data = load_data()


def save_data():
    temporary = DATA_FILE.with_suffix(".tmp")

    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    os.replace(temporary, DATA_FILE)


def get_user_data(user_id):
    key = str(user_id)
    today = date.today().isoformat()

    user = data["users"].setdefault(key, {
        "date": today,
        "daily_remaining": DAILY_SONG_LIMIT,
        "bonus_songs": 0,
    })

    if user.get("date") != today:
        user["date"] = today
        user["daily_remaining"] = DAILY_SONG_LIMIT

    user.setdefault("daily_remaining", DAILY_SONG_LIMIT)
    user.setdefault("bonus_songs", 0)

    return user


def is_bot_owner(user):
    return user.id == OWNER_ID


def is_premium(member):
    if member is None:
        return False

    return any(
        role.id == PREMIUM_ROLE_ID
        for role in getattr(member, "roles", [])
    )


def is_unlimited(user_id):
    return str(user_id) in data["unlimited_users"]


def has_unlimited_access(member):
    return (
        member is not None
        and (
            is_premium(member)
            or is_unlimited(member.id)
        )
    )


def remaining_songs(user_id):
    if is_unlimited(user_id):
        return "Sınırsız"

    user = get_user_data(user_id)

    return user["daily_remaining"] + user["bonus_songs"]


def spend_one_song(user_id):
    """Bir şarkı hakkı tüketir. Günlük haktan önce bonus kullanılır."""
    if is_unlimited(user_id):
        return "unlimited"

    user = get_user_data(user_id)

    if user["bonus_songs"] > 0:
        user["bonus_songs"] -= 1
        save_data()
        return "bonus"

    if user["daily_remaining"] > 0:
        user["daily_remaining"] -= 1
        save_data()
        return "daily"

    return None


def refund_one_song(user_id, source):
    if source == "bonus":
        user = get_user_data(user_id)
        user["bonus_songs"] += 1
        save_data()
    elif source == "daily":
        user = get_user_data(user_id)
        user["daily_remaining"] = min(
            DAILY_SONG_LIMIT,
            user["daily_remaining"] + 1,
        )
        save_data()


def get_room_by_voice(voice_id):
    return data["rooms"].get(str(voice_id))


def get_room_for_member(member):
    if not member or not getattr(member, "voice", None):
        return None

    if not member.voice.channel:
        return None

    return get_room_by_voice(member.voice.channel.id)


def get_queue(guild_id):
    return music_queues.setdefault(guild_id, asyncio.Queue())


def is_banned_track(track):
    title = track.get("title", "").casefold()
    artist = track.get("uploader", "").casefold()

    if any(
        str(item).casefold() in title
        for item in data["banned_songs"]
    ):
        return True

    if any(
        str(item).casefold() in artist
        for item in data["banned_artists"]
    ):
        return True

    return False


# ============================================================
# YOUTUBE
# ============================================================

def validate_youtube_url(url):
    host = (urlparse(url).hostname or "").casefold()

    return host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    }


def extract_youtube(query, quality="Orta"):
    query = query.strip()

    if not query:
        raise ValueError("Bir şarkı adı veya YouTube bağlantısı gir.")

    if query.startswith(("http://", "https://")):
        if not validate_youtube_url(query):
            raise ValueError("Yalnızca YouTube bağlantıları destekleniyor.")
        search_query = query
    else:
        search_query = f"ytsearch1:{query}"

    options = {
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["Orta"]),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": False,
        "ignoreerrors": False,
        "socket_timeout": 20,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(search_query, download=False)

    if info and info.get("entries") is not None:
        entries = info.get("entries") or []
        info = next((item for item in entries if item), None)

    if not info:
        raise ValueError("YouTube'da şarkı bulunamadı.")

    webpage_url = (
        info.get("webpage_url")
        or info.get("original_url")
        or ""
    )

    video_id = info.get("id")

    if not webpage_url and video_id:
        webpage_url = f"https://www.youtube.com/watch?v={video_id}"

    if not validate_youtube_url(webpage_url):
        raise ValueError("YouTube dışında bir kaynak kabul edilmiyor.")

    return {
        "title": info.get("title", "Bilinmeyen şarkı"),
        "url": webpage_url,
        "uploader": info.get("uploader", "Bilinmeyen sanatçı"),
        "duration": info.get("duration") or 0,
        "requester_id": None,
        "voice_channel_id": None,
        "guild_id": None,
    }


def extract_audio_stream(url, quality):
    options = {
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["Orta"]),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info or not info.get("url"):
        raise ValueError("YouTube ses akışı alınamadı.")

    return info["url"]


def format_duration(seconds):
    if not seconds:
        return "Bilinmiyor"

    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"

    return f"{minutes}:{seconds:02}"


# ============================================================
# SES KANALI SOHBETİ
# ============================================================

async def send_channel_message(channel, **kwargs):
    """
    Mesajı belirtilen kanalın sohbetine gönderir.
    Kanalın mesaj gönderme yetkisi yoksa hata kaydedilir.
    """
    try:
        return await channel.send(**kwargs)
    except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
        print(f"Kanal sohbetine mesaj gönderilemedi: {exc}")
        return None


def room_status_embed(room):
    owner_id = int(room["owner_id"])
    guild = bot.get_guild(int(room["guild_id"]))
    member = guild.get_member(owner_id) if guild else None

    unlimited = (
        has_unlimited_access(member)
        if member
        else is_unlimited(owner_id)
    )

    rights = "Sınırsız" if unlimited else str(remaining_songs(owner_id))
    quality = room.get("quality", "Orta")

    embed = discord.Embed(
        title="🎧 HELY MÜZİK • Özel Odan",
        description=(
            f"**Oda sahibi:** <@{owner_id}>\n"
            f"**Kalan şarkı hakkı:** {rights}\n"
            f"**Ses kalitesi:** {quality}\n\n"
            "🎵 **Müzik nasıl başlatılır?**\n"
            "`!Play şarkı adı veya YouTube bağlantısı`\n\n"
            "Şarkıyı başlatınca müzik kontrol paneli açılır.\n\n"
            "💜 **Premium:** Reklamsız ve sınırsız müzik."
        ),
        color=discord.Color.blurple(),
    )

    embed.set_footer(
        text="Günlük 10 şarkı hakkı • Kalite hakkı değiştirmez"
    )

    return embed


async def refresh_room_status(voice_id):
    room = get_room_by_voice(voice_id)

    if not room:
        return

    guild = bot.get_guild(int(room["guild_id"]))
    channel = guild.get_channel(int(voice_id)) if guild else None

    if channel is None:
        return

    embed = room_status_embed(room)
    view = RoomStatusView(voice_id)

    message_id = room.get("status_message_id")

    if message_id:
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(embed=embed, view=view)
            return
        except discord.NotFound:
            pass
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    message = await send_channel_message(
        channel,
        embed=embed,
        view=view,
    )

    if message:
        room["status_message_id"] = message.id
        save_data()


# ============================================================
# ŞARKI SÖZLERİ
# ============================================================

class LyricsLinkView(discord.ui.View):
    def __init__(self, track):
        super().__init__(timeout=120)

        search_text = (
            f"{track.get('title', '')} "
            f"{track.get('uploader', '')} şarkı sözleri"
        )

        self.add_item(
            discord.ui.Button(
                label="🎤 Şarkı Sözlerini Ara",
                style=discord.ButtonStyle.link,
                url="https://www.google.com/search?q=" + quote_plus(search_text),
            )
        )


# ============================================================
# MÜZİK KONTROL PANELİ
# ============================================================

class MusicControlView(discord.ui.View):
    def __init__(self, voice_channel_id):
        super().__init__(timeout=3600)
        self.voice_channel_id = int(voice_channel_id)

    async def authorized(self, interaction):
        room = get_room_by_voice(self.voice_channel_id)

        if not room:
            await interaction.response.send_message(
                "Bu müzik odası artık mevcut değil.",
                ephemeral=True,
            )
            return False

        if (
            interaction.user.id != int(room["owner_id"])
            and not is_bot_owner(interaction.user)
        ):
            await interaction.response.send_message(
                "Bu paneli yalnızca oda sahibi kullanabilir.",
                ephemeral=True,
            )
            return False

        return True

    async def send_status(self, interaction, message):
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(
        label="Önceki",
        emoji="⏮️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def previous_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        guild = interaction.guild
        voice = guild.voice_client if guild else None
        history = previous_tracks.get(guild.id, []) if guild else []

        if not history:
            await self.send_status(interaction, "Önceki şarkı bulunamadı.")
            return

        previous = history.pop()
        queue = get_queue(guild.id)
        queue._queue.appendleft(previous)

        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()

        await self.send_status(interaction, "⏮️ Önceki şarkı kuyruğa alındı.")

    @discord.ui.button(
        label="Duraklat / Devam",
        emoji="⏯️",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def pause_resume_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        voice = interaction.guild.voice_client if interaction.guild else None

        if voice and voice.is_playing():
            voice.pause()
            await self.send_status(interaction, "⏸️ Müzik duraklatıldı.")
        elif voice and voice.is_paused():
            voice.resume()
            await self.send_status(interaction, "▶️ Müzik devam ediyor.")
        else:
            await self.send_status(interaction, "Şu anda çalan şarkı yok.")

    @discord.ui.button(
        label="Sonraki",
        emoji="⏭️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def next_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        voice = interaction.guild.voice_client if interaction.guild else None

        if voice and (voice.is_playing() or voice.is_paused()):
            skip_requested.add(interaction.guild.id)
            voice.stop()
            await self.send_status(interaction, "⏭️ Şarkı atlandı.")
        else:
            await self.send_status(interaction, "Atlanacak şarkı yok.")

    @discord.ui.button(
        label="Karıştır",
        emoji="🔀",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def shuffle_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        guild_id = interaction.guild.id
        queue = get_queue(guild_id)

        shuffle_enabled[guild_id] = not shuffle_enabled.get(guild_id, False)

        if shuffle_enabled[guild_id] and queue.qsize() > 1:
            tracks = list(queue._queue)
            random.shuffle(tracks)
            queue._queue.clear()
            queue._queue.extend(tracks)

        state = "açıldı" if shuffle_enabled[guild_id] else "kapatıldı"
        await self.send_status(interaction, f"🔀 Karıştırma {state}.")

    @discord.ui.button(
        label="Döngü",
        emoji="🔁",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def repeat_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        guild_id = interaction.guild.id
        repeat_enabled[guild_id] = not repeat_enabled.get(guild_id, False)

        state = "açıldı" if repeat_enabled[guild_id] else "kapatıldı"
        await self.send_status(interaction, f"🔁 Şarkı döngüsü {state}.")

    @discord.ui.button(
        label="Kuyruk",
        emoji="📜",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def queue_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        guild_id = interaction.guild.id
        tracks = list(get_queue(guild_id)._queue)

        if not tracks:
            await self.send_status(interaction, "🎵 Kuyrukta bekleyen şarkı yok.")
            return

        description = "\n".join(
            f"**{index}.** {track['title']}"
            for index, track in enumerate(tracks[:15], start=1)
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎶 HELY MÜZİK • Kuyruk",
                description=description,
                color=discord.Color.blurple(),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Ses +",
        emoji="🔊",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def volume_up_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        guild_id = interaction.guild.id
        volume = min(1.0, music_volumes.get(guild_id, 0.5) + 0.1)
        music_volumes[guild_id] = volume

        voice = interaction.guild.voice_client
        if voice and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = volume

        await self.send_status(
            interaction,
            f"🔊 Ses seviyesi: **{round(volume * 100)}%**",
        )

    @discord.ui.button(
        label="Ses −",
        emoji="🔉",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def volume_down_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        guild_id = interaction.guild.id
        volume = max(0.0, music_volumes.get(guild_id, 0.5) - 0.1)
        music_volumes[guild_id] = volume

        voice = interaction.guild.voice_client
        if voice and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = volume

        await self.send_status(
            interaction,
            f"🔉 Ses seviyesi: **{round(volume * 100)}%**",
        )

    @discord.ui.button(
        label="Şarkı Sözleri",
        emoji="🎤",
        style=discord.ButtonStyle.success,
        row=3,
    )
    async def lyrics_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        track = current_tracks.get(interaction.guild.id)

        if not track:
            await self.send_status(interaction, "Şu anda çalan şarkı yok.")
            return

        await interaction.response.send_message(
            f"🎤 **{track['title']}** — şarkı sözlerini aramak için:",
            view=LyricsLinkView(track),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Yenile",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        row=3,
    )
    async def refresh_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        await refresh_room_status(self.voice_channel_id)
        await self.send_status(interaction, "🔄 Oda bilgileri yenilendi.")

    @discord.ui.button(
        label="Durdur",
        emoji="⏹️",
        style=discord.ButtonStyle.danger,
        row=3,
    )
    async def stop_button(self, interaction, button):
        if not await self.authorized(interaction):
            return

        guild = interaction.guild
        voice = guild.voice_client if guild else None

        if guild:
            stop_requested.add(guild.id)
            skip_requested.discard(guild.id)

            queue = get_queue(guild.id)

            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    break

        if voice:
            if voice.is_playing() or voice.is_paused():
                voice.stop()

            try:
                await voice.disconnect(force=True)
            except discord.HTTPException:
                pass

        await self.send_status(
            interaction,
            "⏹️ Müzik durduruldu. Özel odan silinmedi.",
        )


# ============================================================
# ODA KALİTESİ
# ============================================================

class RoomStatusView(discord.ui.View):
    def __init__(self, voice_channel_id):
        super().__init__(timeout=3600)
        self.voice_channel_id = int(voice_channel_id)

    async def set_quality(self, interaction, quality):
        room = get_room_by_voice(self.voice_channel_id)

        if not room:
            await interaction.response.send_message(
                "Müzik odası bulunamadı.",
                ephemeral=True,
            )
            return

        if (
            interaction.user.id != int(room["owner_id"])
            and not is_bot_owner(interaction.user)
        ):
            await interaction.response.send_message(
                "Kaliteyi yalnızca oda sahibi değiştirebilir.",
                ephemeral=True,
            )
            return

        room["quality"] = quality
        save_data()

        await interaction.response.edit_message(
            embed=room_status_embed(room),
            view=self,
        )

    @discord.ui.button(label="Az", emoji="🔈", style=discord.ButtonStyle.secondary)
    async def low(self, interaction, button):
        await self.set_quality(interaction, "Az")

    @discord.ui.button(label="Orta", emoji="🔉", style=discord.ButtonStyle.primary)
    async def medium(self, interaction, button):
        await self.set_quality(interaction, "Orta")

    @discord.ui.button(label="Çok", emoji="🔊", style=discord.ButtonStyle.success)
    async def high(self, interaction, button):
        await self.set_quality(interaction, "Çok")


# ============================================================
# ODA OLUŞTURMA PANELİ
# ============================================================

class MusicRoomCreateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="ODA OLUŞTUR!",
        emoji="🎧",
        style=discord.ButtonStyle.success,
        custom_id="hely_create_music_room",
    )
    async def create_room(self, interaction, button):
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "Bu buton yalnızca sunucuda kullanılabilir.",
                ephemeral=True,
            )
            return

        for room in data["rooms"].values():
            if (
                int(room["guild_id"]) == guild.id
                and int(room["owner_id"]) == interaction.user.id
            ):
                existing = guild.get_channel(int(room["voice_id"]))

                if existing:
                    await interaction.response.send_message(
                        f"Zaten bir müzik odan var: {existing.mention}",
                        ephemeral=True,
                    )
                    return

        category = guild.get_channel(ROOM_CATEGORY_ID)

        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Müzik odaları kategorisi bulunamadı. "
                "Kategori ID'sini ve bot izinlerini kontrol et.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        safe_name = interaction.user.display_name[:70]
        voice_channel = None

        try:
            voice_channel = await guild.create_voice_channel(
                name=f"{safe_name} müzik odası",
                category=category,
                reason=f"HELY MÜZİK oda sahibi: {interaction.user}",
            )

            room = {
                "guild_id": guild.id,
                "owner_id": interaction.user.id,
                "voice_id": voice_channel.id,
                "quality": "Orta",
                "status_message_id": None,
            }

            data["rooms"][str(voice_channel.id)] = room
            save_data()

            message = await send_channel_message(
                voice_channel,
                content=f"🎉 {interaction.user.mention} müzik odan hazır!",
                embed=room_status_embed(room),
                view=RoomStatusView(voice_channel.id),
            )

            if message:
                room["status_message_id"] = message.id
                save_data()

            await interaction.followup.send(
                f"🎉 **Müzik odan oluşturuldu!**\n"
                f"🔊 Ses kanalı: {voice_channel.mention}\n"
                "Günlük 10 şarkı hakkın var. Müzik için `!Play` kullan.",
                ephemeral=True,
            )

        except Exception as exc:
            data["rooms"].pop(str(voice_channel.id), None) if voice_channel else None
            save_data()

            if voice_channel:
                try:
                    await voice_channel.delete()
                except discord.HTTPException:
                    pass

            print(f"Oda oluşturma hatası: {type(exc).__name__}: {exc}")

            await interaction.followup.send(
                "Oda oluşturulamadı. Botun kanal oluşturma ve mesaj "
                "gönderme izinlerini kontrol et.",
                ephemeral=True,
            )


@bot.command(name="pannels!")
async def music_room_panel(ctx):
    embed = discord.Embed(
        title="🎵 Müzik Keyfi!",
        description=(
            "YouTube üzerinden müzik dinlemek için kendi özel odanı oluştur.\n\n"
            "🎧 **Günlük 10 şarkı dinleme hakkı!**\n\n"
            "💎 **HELY Premium**\n"
            "Premium rolüne sahip üyeler reklamsız ve sınırsız müzik dinler.\n\n"
            "Aşağıdaki butona basarak müzik odanı oluşturabilirsin."
        ),
        color=discord.Color.blurple(),
    )

    embed.set_footer(text="HELY MÜZİK • YouTube")

    await ctx.send(embed=embed, view=MusicRoomCreateView())


# ============================================================
# REKLAM SİSTEMİ
# ============================================================

class AdvertisementView(discord.ui.View):
    def __init__(self, requester_id):
        super().__init__(timeout=AD_CONFIRM_TIMEOUT)
        self.requester_id = int(requester_id)
        self.confirmed = asyncio.Event()

    @discord.ui.button(
        label="Reklamı Gördüm",
        emoji="✅",
        style=discord.ButtonStyle.success,
    )
    async def confirm(self, interaction, button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Bu reklamı yalnızca şarkıyı isteyen kullanıcı onaylayabilir.",
                ephemeral=True,
            )
            return

        if self.confirmed.is_set():
            await interaction.response.send_message(
                "Reklam zaten onaylandı.",
                ephemeral=True,
            )
            return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⏳ Reklam başladı!",
                description=(
                    "Reklam onaylandı.\n\n"
                    "**20 saniye sonra reklam sona erecek.**\n"
                    "Bu sırada müzik beklemede kalacak."
                ),
                color=discord.Color.orange(),
            ),
            view=self,
        )

        self.confirmed.set()


async def play_advertisement(channel, requester):
    global ad_counter

    ad_counter += 1
    use_node_ad = ad_counter % 2 == 0

    if use_node_ad:
        embed = discord.Embed(
            title="Node Project",
            description=NODE_PROJECT_AD_TEXT,
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Davet bağlantısı",
            value="https://discord.gg/Fszrd9UkYG",
            inline=False,
        )

        embed.set_image(url=NODE_PROJECT_GIF)
    else:
        embed = discord.Embed(
            title="💜 HELY Premium Reklamı",
            description=HELY_AD_TEXT,
            color=discord.Color.purple(),
        )

    view = AdvertisementView(requester.id)

    message = await send_channel_message(
        channel,
        content=requester.mention,
        embed=embed,
        view=view,
    )

    if message is None:
        return

    try:
        await asyncio.wait_for(
            view.confirmed.wait(),
            timeout=AD_CONFIRM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        try:
            await message.edit(
                content=None,
                embed=discord.Embed(
                    title="⌛ Reklam süresi doldu",
                    description=(
                        "Reklam onaylanmadığı için sıradaki şarkı "
                        "beklemeye devam ediyor."
                    ),
                    color=discord.Color.orange(),
                ),
                view=None,
            )
        except discord.HTTPException:
            pass

        return

    await asyncio.sleep(AD_SECONDS)

    try:
        await message.edit(
            content=None,
            embed=discord.Embed(
                title="✅ Reklam sona erdi!",
                description="İyi dinlemeler! 🎵",
                color=discord.Color.green(),
            ),
            view=None,
        )
    except discord.HTTPException:
        pass


# ============================================================
# MÜZİK ÇALAR
# ============================================================

async def music_player(guild_id):
    queue = get_queue(guild_id)

    try:
        while True:
            track = await queue.get()

            try:
                guild = bot.get_guild(guild_id)

                if not guild:
                    continue

                room = get_room_by_voice(track["voice_channel_id"])

                if not room:
                    continue

                voice_channel = guild.get_channel(track["voice_channel_id"])

                if voice_channel is None:
                    continue

                channel = voice_channel

                try:
                    requester = guild.get_member(track["requester_id"])
                    if requester is None:
                        requester = await guild.fetch_member(
                            track["requester_id"]
                        )
                except discord.HTTPException:
                    continue

                if requester.id in data["banned_users"]:
                    continue

                unlimited = has_unlimited_access(requester)
                quality = room.get("quality", "Orta")

                if not unlimited and remaining_songs(requester.id) <= 0:
                    await send_channel_message(
                        channel,
                        content=(
                            f"{requester.mention}, günlük 10 şarkı hakkın "
                            "bitti. Yarın tekrar dinleyebilirsin."
                        ),
                    )
                    continue

                try:
                    audio_url = await asyncio.to_thread(
                        extract_audio_stream,
                        track["url"],
                        quality,
                    )
                except Exception as exc:
                    print(f"YouTube ses akışı hatası: {exc}")
                    await send_channel_message(
                        channel,
                        content="❌ Şarkı alınamadı. Başka bir YouTube bağlantısı dene.",
                    )
                    continue

                if is_banned_track(track):
                    await send_channel_message(
                        channel,
                        content="⛔ Bu şarkı veya sanatçı engellenmiş.",
                    )
                    continue

                voice_client = guild.voice_client

                try:
                    if voice_client is None:
                        voice_client = await voice_channel.connect()
                    elif voice_client.channel.id != voice_channel.id:
                        await voice_client.move_to(voice_channel)
                except (discord.ClientException, discord.HTTPException) as exc:
                    print(f"Ses kanalına bağlanma hatası: {exc}")
                    await send_channel_message(
                        channel,
                        content="❌ Ses kanalına bağlanılamadı. Bot izinlerini kontrol et.",
                    )
                    continue

                # Hak, şarkı çalmaya hazır olduğunda tüketilir.
                right_source = spend_one_song(requester.id)

                if right_source is None:
                    await send_channel_message(
                        channel,
                        content=f"{requester.mention}, dinleme hakkın kalmadı.",
                    )
                    continue

                current_tracks[guild_id] = track

                history = previous_tracks.setdefault(guild_id, [])
                history.append(track.copy())

                if len(history) > 25:
                    del history[:-25]

                await refresh_room_status(voice_channel.id)

                volume = music_volumes.get(guild_id, 0.5)

                embed = discord.Embed(
                    title="🎵 HELY MÜZİK",
                    description=(
                        f"**Şimdi çalıyor:** [{track['title']}]({track['url']})\n"
                        f"**Sanatçı:** {track['uploader']}\n"
                        f"**Süre:** {format_duration(track['duration'])}\n"
                        f"**İsteyen:** {requester.mention}\n\n"
                        "🎛️ Aşağıdaki butonlardan müziği yönetebilirsin."
                    ),
                    color=discord.Color.blurple(),
                )

                panel_message = await send_channel_message(
                    channel,
                    embed=embed,
                    view=MusicControlView(voice_channel.id),
                )

                loop = asyncio.get_running_loop()
                finished = loop.create_future()

                def after_playback(error):
                    def complete():
                        if not finished.done():
                            finished.set_result(error)

                    loop.call_soon_threadsafe(complete)

                try:
                    source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(
                            audio_url,
                            before_options=(
                                "-reconnect 1 -reconnect_streamed 1 "
                                "-reconnect_delay_max 5"
                            ),
                            options="-vn",
                        ),
                        volume=volume,
                    )

                    voice_client.play(source, after=after_playback)
                    error = await finished

                    if error:
                        print(f"Ses oynatma hatası: {error}")
                        refund_one_song(requester.id, right_source)

                        await send_channel_message(
                            channel,
                            content="⚠️ Şarkı oynatılamadı; hakkın iade edildi.",
                        )
                        continue

                except Exception as exc:
                    print(f"Çalma hatası: {type(exc).__name__}: {exc}")
                    refund_one_song(requester.id, right_source)

                    await send_channel_message(
                        channel,
                        content="❌ Şarkı çalınamadı; hakkın iade edildi. FFmpeg kurulumunu kontrol et.",
                    )
                    continue

                if guild_id in stop_requested:
                    stop_requested.discard(guild_id)
                    continue

                if guild_id in skip_requested:
                    skip_requested.discard(guild_id)
                    continue

                if repeat_enabled.get(guild_id, False):
                    queue._queue.appendleft(track.copy())

                # Premium ve sınırsız kullanıcılar reklamsızdır.
                if not has_unlimited_access(requester):
                    await play_advertisement(channel, requester)

            except Exception as exc:
                print(f"Müzik döngüsü hatası: {type(exc).__name__}: {exc}")

            finally:
                queue.task_done()

    except asyncio.CancelledError:
        raise


# ============================================================
# TEK MÜZİK KOMUTU: !Play
# ============================================================

@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query: str = None):
    if not ctx.guild:
        return

    if ctx.author.id in data["banned_users"]:
        await ctx.send("⛔ Müzik kullanman engellenmiş.")
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Önce kendi müzik odanın ses kanalına katıl.")
        return

    voice_channel = ctx.author.voice.channel
    room = get_room_by_voice(voice_channel.id)

    if not room:
        await ctx.send("Bu ses kanalı HELY MÜZİK odası değil.")
        return

    if (
        ctx.author.id != int(room["owner_id"])
        and not is_bot_owner(ctx.author)
    ):
        await ctx.send("Bu müzik odasını yalnızca oda sahibi kullanabilir.")
        return

    # Komut tek başına yazılırsa mevcut müzik panelini göster.
    if not query:
        track = current_tracks.get(ctx.guild.id)

        if track:
            embed = discord.Embed(
                title="🎵 HELY MÜZİK",
                description=(
                    f"**Şimdi çalıyor:** [{track['title']}]({track['url']})\n"
                    "Aşağıdaki panelden müziği yönetebilirsin."
                ),
                color=discord.Color.blurple(),
            )
        else:
            embed = discord.Embed(
                title="🎵 HELY MÜZİK",
                description=(
                    "Müzik başlatmak için `!Play şarkı adı` "
                    "veya YouTube bağlantısı yaz."
                ),
                color=discord.Color.blurple(),
            )

        await send_channel_message(
            voice_channel,
            embed=embed,
            view=MusicControlView(voice_channel.id),
        )
        return

    if not has_unlimited_access(ctx.author) and remaining_songs(ctx.author.id) <= 0:
        await ctx.send(
            "❌ Günlük 10 şarkı hakkın bitti. Yarın tekrar dinleyebilirsin."
        )
        return

    await ctx.send("🔎 YouTube'da şarkı aranıyor...")

    try:
        track = await asyncio.to_thread(
            extract_youtube,
            query,
            room.get("quality", "Orta"),
        )
    except Exception as exc:
        print(f"YouTube arama hatası: {type(exc).__name__}: {exc}")
        await ctx.send(
            "❌ Şarkı bulunamadı. YouTube bağlantısını veya şarkı adını kontrol et."
        )
        return

    if is_banned_track(track):
        await ctx.send("⛔ Bu şarkı veya sanatçı engellenmiş.")
        return

    track["requester_id"] = ctx.author.id
    track["voice_channel_id"] = voice_channel.id
    track["guild_id"] = ctx.guild.id

    queue = get_queue(ctx.guild.id)
    await queue.put(track)

    await ctx.send(f"➕ **Kuyruğa eklendi:** {track['title']}")

    if (
        ctx.guild.id not in player_tasks
        or player_tasks[ctx.guild.id].done()
    ):
        player_tasks[ctx.guild.id] = asyncio.create_task(
            music_player(ctx.guild.id)
        )


# ============================================================
# BOT SAHİBİ AYARLARI
# ============================================================

class GrantSongsModal(discord.ui.Modal, title="Dinleme Hakkı Ver"):
    amount = discord.ui.TextInput(
        label="Ek şarkı sayısı veya Sınırsız",
        placeholder="Örn: 12 veya Sınırsız",
        max_length=20,
        required=True,
    )

    def __init__(self, target):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction):
        if not is_bot_owner(interaction.user):
            await interaction.response.send_message(
                "Bu işlem yalnızca bot sahibine açık.",
                ephemeral=True,
            )
            return

        value = str(self.amount.value).strip().casefold()
        target_id = str(self.target.id)

        if value in ("sınırsız", "sinirsiz", "unlimited"):
            if target_id not in data["unlimited_users"]:
                data["unlimited_users"].append(target_id)

            save_data()

            await interaction.response.send_message(
                f"♾️ {self.target.mention} için sınırsız ve reklamsız erişim verildi.",
                ephemeral=True,
            )
            return

        try:
            amount = int(value)
        except ValueError:
            await interaction.response.send_message(
                "Bir sayı veya `Sınırsız` yaz.",
                ephemeral=True,
            )
            return

        if amount < 1 or amount > 100000:
            await interaction.response.send_message(
                "Sayı 1 ile 100000 arasında olmalı.",
                ephemeral=True,
            )
            return

        if target_id in data["unlimited_users"]:
            data["unlimited_users"].remove(target_id)

        user = get_user_data(self.target.id)
        user["bonus_songs"] += amount
        save_data()

        await interaction.response.send_message(
            f"✅ {self.target.mention} kullanıcısına **{amount} ek şarkı hakkı** verildi.\n"
            f"Kalan hak: **{remaining_songs(self.target.id)}**",
            ephemeral=True,
        )


class GrantSongsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Kullanıcı seç",
        min_values=1,
        max_values=1,
    )
    async def select_user(self, interaction, select):
        if not is_bot_owner(interaction.user):
            await interaction.response.send_message(
                "Bu işlem yalnızca bot sahibine açık.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            GrantSongsModal(select.values[0])
        )


class SettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="Şarkı Hakkı Ver",
        emoji="🎵",
        style=discord.ButtonStyle.success,
    )
    async def grant_songs(self, interaction, button):
        if not is_bot_owner(interaction.user):
            await interaction.response.send_message(
                "Bu panel yalnızca bot sahibine açık.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Şarkı hakkı verilecek kullanıcıyı seç:",
            view=GrantSongsView(),
            ephemeral=True,
        )


@bot.command(name="ayarlar")
async def settings(ctx):
    if not is_bot_owner(ctx.author):
        await ctx.send("⛔ Bu komut yalnızca bot sahibine açık.")
        return

    embed = discord.Embed(
        title="⚙️ HELY MÜZİK • Yönetim",
        description=(
            "Bir kullanıcıya ek şarkı hakkı veya sınırsız erişim verebilirsin.\n\n"
            "• Sayı girersen ek şarkı hakkı verilir.\n"
            "• `Sınırsız` girersen reklamsız sınırsız erişim verilir."
        ),
        color=discord.Color.blurple(),
    )

    await ctx.send(embed=embed, view=SettingsView())


# ============================================================
# ENGELLEME KOMUTLARI
# ============================================================

@bot.command(name="banuser")
async def ban_user(ctx, user_id: int):
    if not is_bot_owner(ctx.author):
        return

    if user_id not in data["banned_users"]:
        data["banned_users"].append(user_id)

    save_data()
    await ctx.send(f"⛔ `{user_id}` kullanıcısı müzikten engellendi.")


@bot.command(name="unbanuser")
async def unban_user(ctx, user_id: int):
    if not is_bot_owner(ctx.author):
        return

    if user_id in data["banned_users"]:
        data["banned_users"].remove(user_id)

    save_data()
    await ctx.send(f"✅ `{user_id}` kullanıcısının müzik engeli kaldırıldı.")


@bot.command(name="banartist")
async def ban_artist(ctx, *, artist: str):
    if not is_bot_owner(ctx.author):
        return

    if not any(item.casefold() == artist.casefold() for item in data["banned_artists"]):
        data["banned_artists"].append(artist)

    save_data()
    await ctx.send(f"⛔ Sanatçı engellendi: **{artist}**")


@bot.command(name="unbanartist")
async def unban_artist(ctx, *, artist: str):
    if not is_bot_owner(ctx.author):
        return

    data["banned_artists"] = [
        item for item in data["banned_artists"]
        if item.casefold() != artist.casefold()
    ]

    save_data()
    await ctx.send(f"✅ Sanatçı engeli kaldırıldı: **{artist}**")


@bot.command(name="bansong")
async def ban_song(ctx, *, song: str):
    if not is_bot_owner(ctx.author):
        return

    if not any(item.casefold() == song.casefold() for item in data["banned_songs"]):
        data["banned_songs"].append(song)

    save_data()
    await ctx.send(f"⛔ Şarkı engellendi: **{song}**")


@bot.command(name="unbansong")
async def unban_song(ctx, *, song: str):
    if not is_bot_owner(ctx.author):
        return

    data["banned_songs"] = [
        item for item in data["banned_songs"]
        if item.casefold() != song.casefold()
    ]

    save_data()
    await ctx.send(f"✅ Şarkı engeli kaldırıldı: **{song}**")


# ============================================================
# ODA SAHİBİ AYRILIRSA ODAYI SİL
# ============================================================

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or before.channel is None:
        return

    room = get_room_by_voice(before.channel.id)

    if not room:
        return

    if member.id != int(room["owner_id"]):
        return

    if after.channel and after.channel.id == before.channel.id:
        return

    voice_id = int(room["voice_id"])
    guild = member.guild

    data["rooms"].pop(str(voice_id), None)
    save_data()

    voice_channel = guild.get_channel(voice_id)

    # Bot yalnızca bu odaya bağlıysa bağlantıyı kes.
    voice = guild.voice_client

    if voice and voice.channel and voice.channel.id == voice_id:
        try:
            await voice.disconnect(force=True)
        except discord.HTTPException:
            pass

    if voice_channel:
        try:
            await voice_channel.delete(
                reason="Müzik odasının sahibi ses kanalından ayrıldı."
            )
        except discord.HTTPException as exc:
            print(f"Oda silinemedi: {exc}")


# ============================================================
# BAŞLANGIÇ
# ============================================================

@bot.event
async def on_ready():
    print(f"HELY MÜZİK giriş yaptı: {bot.user} ({bot.user.id})")

    # Geçersiz oda kayıtlarını temizle.
    changed = False

    for voice_id, room in list(data["rooms"].items()):
        guild = bot.get_guild(int(room["guild_id"]))
        channel = guild.get_channel(int(voice_id)) if guild else None

        if channel is None:
            data["rooms"].pop(voice_id, None)
            changed = True

    if changed:
        save_data()

    # Ana oda oluşturma panelinin butonu yeniden başlatmada da çalışır.
    bot.add_view(MusicRoomCreateView())

    print("HELY MÜZİK hazır.")


# ============================================================
# TOKEN
# ============================================================

def load_token():
    token = os.getenv("DISCORD_TOKEN")

    if token:
        return token.strip()

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                config = json.load(file)

            token = config.get("token")

            if token:
                return str(token).strip()

        except (OSError, json.JSONDecodeError) as exc:
            print(f"config.json okunamadı: {exc}")

    return None


token = load_token()

if not token:
    raise RuntimeError(
        "Discord bot tokeni bulunamadı. FadeHost ortam değişkenlerine "
        "DISCORD_TOKEN ekle veya config.json dosyasında token alanını tanımla."
    )

bot.run(token)
