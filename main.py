
import asyncio
import json
import os
import random
import traceback
from pathlib import Path
from datetime import date
from urllib.parse import quote_plus, urlparse

import discord
import yt_dlp
from discord.ext import commands

# =========================================================
# HELY MÜZİK - AYARLAR
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
DATA_FILE = BASE_DIR / "bot_data.json"

OWNER_ID = 1487816729336877106
ROOM_CATEGORY_ID = 1559255416788230266
PREMIUM_ROLE_ID = 1558524707752509560

DAILY_SONG_LIMIT = 10
AD_SECONDS = 20

QUALITY_FORMATS = {
    "Az": "bestaudio/best",
    "Orta": "bestaudio/best",
    "Çok": "bestaudio/best",
}

HELY_AD_TEXT = (
    "💜 **HELY PREMIUM REKLAMI**\n\n"
    "🎵 Müzik keyfine reklamsız ve sınırsız devam etmek ister misin?\n\n"
    "✨ **HELY Premium avantajları**\n"
    "🔊 Reklamsız müzik keyfi\n"
    "♾️ Sınırsız dinleme hakkı\n"
    "💜 Daha iyi bir müzik deneyimi\n\n"
    "🛒 Premium üyeliğini **HELY Destek** botunun marketinden satın al!\n\n"
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
    "takıldığınızda forum kanallarında başlık açıp çözüm alabilirsiniz.\n\n"
    "**2. Hazır Altyapılar ve Kaynaklar**\n"
    "Sunucuda paylaşılan hazır altyapılardan ve açık kaynak kodlardan "
    "yararlanabilirsiniz.\n\n"
    "**3. Projenizi ve Botunuzu Öne Çıkarın**\n"
    "Botunuzu, web sitenizi veya projenizi sergileyebilir ve geri bildirim "
    "alabilirsiniz.\n\n"
    "**4. Özel Bot Hizmetleri ve Ekip Kurma**\n"
    "Topluluktaki geliştiricilerle iletişime geçebilirsiniz.\n\n"
    "Davet bağlantısı: https://discord.gg/Fszrd9UkYG"
)

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


# =========================================================
# VERİ DOSYASI
# =========================================================

def load_data():
    defaults = {
        "users": {},
        "rooms": {},
        "unlimited_users": [],
        "banned_users": [],
        "banned_artists": [],
        "banned_songs": [],
    }

    if not DATA_FILE.exists():
        return defaults

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            loaded = json.load(file)

        for key, value in defaults.items():
            loaded.setdefault(key, value)

        return loaded

    except (OSError, json.JSONDecodeError) as exc:
        print(f"[VERİ DOSYASI] {exc}")
        return defaults


data = load_data()


def save_data():
    temporary = DATA_FILE.with_suffix(".tmp")

    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    os.replace(temporary, DATA_FILE)


def get_user_data(user_id):
    key = str(user_id)
    today = date.today().isoformat()

    user = data["users"].setdefault(
        key,
        {
            "date": today,
            "daily_remaining": DAILY_SONG_LIMIT,
            "bonus_songs": 0,
        },
    )

    user.setdefault("daily_remaining", DAILY_SONG_LIMIT)
    user.setdefault("bonus_songs", 0)

    if user.get("date") != today:
        user["date"] = today
        user["daily_remaining"] = DAILY_SONG_LIMIT

    return user


def is_bot_owner(user):
    return user.id == OWNER_ID


def is_premium(member):
    if member is None:
        return False

    return any(role.id == PREMIUM_ROLE_ID for role in member.roles)


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


def spend_song(user_id):
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


def refund_song(user_id, source):
    user = get_user_data(user_id)

    if source == "bonus":
        user["bonus_songs"] += 1
    elif source == "daily":
        user["daily_remaining"] = min(
            DAILY_SONG_LIMIT,
            user["daily_remaining"] + 1,
        )

    save_data()


def get_room(voice_channel_id):
    return data["rooms"].get(str(voice_channel_id))


def get_queue(guild_id):
    return music_queues.setdefault(guild_id, asyncio.Queue())


def is_banned_track(track):
    title = track.get("title", "").casefold()
    artist = track.get("uploader", "").casefold()

    return (
        any(str(x).casefold() in title for x in data["banned_songs"])
        or any(str(x).casefold() in artist for x in data["banned_artists"])
    )


# =========================================================
# YOUTUBE ARAMA VE SES AKIŞI
# =========================================================

def is_youtube_url(value):
    host = (urlparse(value).hostname or "").lower()

    return host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    }


def yt_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 25,
        "retries": 3,
        "extractor_retries": 3,
    }


def search_youtube(query):
    query = query.strip()

    if not query:
        raise ValueError("Şarkı adı veya YouTube bağlantısı boş.")

    if query.startswith(("https://", "http://")):
        if not is_youtube_url(query):
            raise ValueError("Yalnızca YouTube bağlantıları destekleniyor.")

        url = query

        # Bağlantının gerçekten video olup olmadığını doğrula.
        with yt_dlp.YoutubeDL(yt_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise ValueError("YouTube bağlantısından video bilgisi alınamadı.")

        if info.get("_type") == "playlist":
            raise ValueError("Lütfen oynatma listesi yerine tek video bağlantısı gönder.")

        video_url = (
            info.get("webpage_url")
            or info.get("original_url")
            or url
        )

        if not is_youtube_url(video_url):
            raise ValueError("Geçerli bir YouTube video bağlantısı alınamadı.")

        return {
            "title": info.get("title") or "Bilinmeyen şarkı",
            "url": video_url,
            "uploader": info.get("uploader") or "Bilinmeyen sanatçı",
            "duration": info.get("duration") or 0,
        }

    # Önce arama sonuçlarından ilk videoyu bul.
    with yt_dlp.YoutubeDL(yt_options()) as ydl:
        result = ydl.extract_info(
            f"ytsearch1:{query}",
            download=False,
        )

    entries = result.get("entries", []) if result else []
    video = next((item for item in entries if item), None)

    if not video:
        raise ValueError("YouTube aramasında sonuç bulunamadı.")

    video_url = (
        video.get("webpage_url")
        or video.get("url")
        or ""
    )

    video_id = video.get("id")

    if video_id and not video_url.startswith("http"):
        video_url = f"https://www.youtube.com/watch?v={video_id}"

    if not is_youtube_url(video_url):
        raise ValueError("Arama sonucundan geçerli YouTube bağlantısı alınamadı.")

    return {
        "title": video.get("title") or "Bilinmeyen şarkı",
        "url": video_url,
        "uploader": video.get("uploader") or "Bilinmeyen sanatçı",
        "duration": video.get("duration") or 0,
    }


def get_audio_url(video_url, quality):
    options = yt_options()
    options["format"] = QUALITY_FORMATS.get(
        quality,
        QUALITY_FORMATS["Orta"],
    )

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(video_url, download=False)

    if not info:
        raise ValueError("YouTube ses bilgisi alınamadı.")

    audio_url = info.get("url")

    if not audio_url and info.get("requested_formats"):
        for item in info["requested_formats"]:
            if item.get("acodec") != "none" and item.get("url"):
                audio_url = item["url"]
                break

    if not audio_url:
        raise ValueError("YouTube ses akışı bağlantısı boş döndü.")

    return audio_url


def format_duration(seconds):
    if not seconds:
        return "Bilinmiyor"

    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"

    return f"{minutes}:{seconds:02}"


# =========================================================
# ÖZEL ODA İZİNLERİ
# =========================================================

def private_room_overwrites(guild, owner):
    """
    Varsayılan rolün kanalı görmesini ve bağlanmasını engeller.
    Oda sahibi ile bot için açık izin verir.
    """

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
            connect=False,
        ),
        owner: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            send_messages=True,
            read_message_history=True,
        ),
    }

    me = guild.me

    if me is not None:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            send_messages=True,
            read_message_history=True,
            embed_links=True,
            attach_files=True,
        )

    return overwrites


async def send_voice_chat(channel, **kwargs):
    try:
        return await channel.send(**kwargs)
    except Exception as exc:
        print(
            f"[KANAL SOHBETİ] {type(exc).__name__}: {exc}"
        )
        return None


def room_embed(room):
    owner_id = int(room["owner_id"])
    guild = bot.get_guild(int(room["guild_id"]))
    owner = guild.get_member(owner_id) if guild else None

    if owner and has_unlimited_access(owner):
        rights = "Sınırsız"
    elif is_unlimited(owner_id):
        rights = "Sınırsız"
    else:
        rights = str(remaining_songs(owner_id))

    embed = discord.Embed(
        title="🎧 HELY MÜZİK",
        description=(
            f"👑 **Oda sahibi:** <@{owner_id}>\n"
            f"🎵 **Kalan şarkı hakkı:** {rights}\n"
            f"🔊 **Kalite:** {room.get('quality', 'Orta')}\n\n"
            "**Müzik başlatmak için**\n"
            "`!Play şarkı adı`\n"
            "veya\n"
            "`!Play YouTube bağlantısı`\n\n"
            "Aşağıdaki düğmelerden ses kalitesini seçebilirsin.\n"
            "Müzik çalarken kontrol paneli açılır."
        ),
        color=discord.Color.blurple(),
    )

    embed.set_footer(
        text="Günlük 10 şarkı hakkı • Kalite seçimi hakkı değiştirmez"
    )

    return embed


async def refresh_room(voice_id):
    room = get_room(voice_id)

    if not room:
        return

    guild = bot.get_guild(int(room["guild_id"]))
    channel = guild.get_channel(int(voice_id)) if guild else None

    if channel is None:
        return

    embed = room_embed(room)
    view = QualityView(voice_id)
    message_id = room.get("status_message_id")

    if message_id:
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(embed=embed, view=view)
            return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    message = await send_voice_chat(channel, embed=embed, view=view)

    if message:
        room["status_message_id"] = message.id
        save_data()


# =========================================================
# KALİTE DÜĞMELERİ
# =========================================================

class QualityView(discord.ui.View):
    def __init__(self, voice_id):
        super().__init__(timeout=3600)
        self.voice_id = int(voice_id)

    async def change_quality(self, interaction, quality):
        room = get_room(self.voice_id)

        if not room:
            await interaction.response.send_message(
                "Bu oda artık mevcut değil.",
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
            embed=room_embed(room),
            view=self,
        )

    @discord.ui.button(label="Az", emoji="🔈", style=discord.ButtonStyle.secondary)
    async def low(self, interaction, button):
        await self.change_quality(interaction, "Az")

    @discord.ui.button(label="Orta", emoji="🔉", style=discord.ButtonStyle.primary)
    async def medium(self, interaction, button):
        await self.change_quality(interaction, "Orta")

    @discord.ui.button(label="Çok", emoji="🔊", style=discord.ButtonStyle.success)
    async def high(self, interaction, button):
        await self.change_quality(interaction, "Çok")


# =========================================================
# ODA OLUŞTURMA PANELİ
# =========================================================

class CreateRoomView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="ODA OLUŞTUR!",
        emoji="🎧",
        style=discord.ButtonStyle.success,
        custom_id="hely_music_create_room",
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
                "Kategori ID'sini kontrol et.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        channel = None

        try:
            overwrites = private_room_overwrites(
                guild,
                interaction.user,
            )

            channel = await guild.create_voice_channel(
                name=f"{interaction.user.display_name[:70]} müzik odası",
                category=category,
                overwrites=overwrites,
                reason="HELY MÜZİK özel oda oluşturma",
            )

            room = {
                "guild_id": guild.id,
                "owner_id": interaction.user.id,
                "voice_id": channel.id,
                "quality": "Orta",
                "status_message_id": None,
            }

            data["rooms"][str(channel.id)] = room
            save_data()

            message = await send_voice_chat(
                channel,
                content=f"🎉 {interaction.user.mention}, özel müzik odan hazır!",
                embed=room_embed(room),
                view=QualityView(channel.id),
            )

            if message:
                room["status_message_id"] = message.id
                save_data()

            await interaction.followup.send(
                f"🔒 **Özel müzik odan oluşturuldu:** {channel.mention}\n"
                "🎵 Müzik için `!Play şarkı adı` yaz.",
                ephemeral=True,
            )

        except Exception as exc:
            traceback.print_exc()

            if channel:
                data["rooms"].pop(str(channel.id), None)
                save_data()

                try:
                    await channel.delete()
                except discord.HTTPException:
                    pass

            await interaction.followup.send(
                "❌ Oda oluşturulamadı. Konsoldaki hatayı ve bot izinlerini kontrol et.",
                ephemeral=True,
            )


@bot.command(name="pannels!")
async def panels(ctx):
    embed = discord.Embed(
        title="🎵 Müzik Keyfi!",
        description=(
            "Kendi özel müzik odanı oluştur ve YouTube'dan müzik dinle.\n\n"
            "🎧 **Günlük 10 şarkı hakkı**\n"
            "🔒 Özel oda erişimi\n"
            "🎛️ Butonlarla müzik kontrolü\n\n"
            "💎 **HELY Premium**\n"
            "Reklamsız ve sınırsız müzik."
        ),
        color=discord.Color.blurple(),
    )

    await ctx.send(embed=embed, view=CreateRoomView())


# =========================================================
# ŞARKI SÖZLERİ ARAMA BAĞLANTISI
# =========================================================

class LyricsView(discord.ui.View):
    def __init__(self, track):
        super().__init__(timeout=120)

        query = (
            f"{track.get('title', '')} "
            f"{track.get('uploader', '')} şarkı sözleri"
        )

        self.add_item(
            discord.ui.Button(
                label="🎤 Şarkı Sözlerini Ara",
                style=discord.ButtonStyle.link,
                url="https://www.google.com/search?q=" + quote_plus(query),
            )
        )


# =========================================================
# MÜZİK KONTROL PANELİ
# =========================================================

class MusicControls(discord.ui.View):
    def __init__(self, voice_id):
        super().__init__(timeout=3600)
        self.voice_id = int(voice_id)

    async def check_owner(self, interaction):
        room = get_room(self.voice_id)

        if not room:
            await interaction.response.send_message(
                "Müzik odası artık mevcut değil.",
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

    @discord.ui.button(label="Önceki", emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        guild_id = interaction.guild.id
        history = previous_tracks.get(guild_id, [])

        if not history:
            await interaction.response.send_message(
                "Önceki şarkı bulunamadı.",
                ephemeral=True,
            )
            return

        track = history.pop()
        get_queue(guild_id)._queue.appendleft(track)

        voice = interaction.guild.voice_client

        if voice and (voice.is_playing() or voice.is_paused()):
            skip_requested.add(guild_id)
            voice.stop()

        await interaction.response.send_message(
            "⏮️ Önceki şarkı kuyruğa eklendi.",
            ephemeral=True,
        )

    @discord.ui.button(label="Duraklat / Devam", emoji="⏯️", style=discord.ButtonStyle.primary, row=0)
    async def pause_resume(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        voice = interaction.guild.voice_client

        if voice and voice.is_playing():
            voice.pause()
            text = "⏸️ Müzik duraklatıldı."
        elif voice and voice.is_paused():
            voice.resume()
            text = "▶️ Müzik devam ediyor."
        else:
            text = "Şu anda çalan şarkı yok."

        await interaction.response.send_message(text, ephemeral=True)

    @discord.ui.button(label="Sonraki", emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        guild_id = interaction.guild.id
        voice = interaction.guild.voice_client

        if voice and (voice.is_playing() or voice.is_paused()):
            skip_requested.add(guild_id)
            voice.stop()
            text = "⏭️ Şarkı atlandı."
        else:
            text = "Atlanacak şarkı yok."

        await interaction.response.send_message(text, ephemeral=True)

    @discord.ui.button(label="Karıştır", emoji="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        guild_id = interaction.guild.id
        queue = get_queue(guild_id)

        shuffle_enabled[guild_id] = not shuffle_enabled.get(guild_id, False)

        if shuffle_enabled[guild_id] and queue.qsize() > 1:
            items = list(queue._queue)
            random.shuffle(items)
            queue._queue.clear()
            queue._queue.extend(items)

        state = "açıldı" if shuffle_enabled[guild_id] else "kapatıldı"

        await interaction.response.send_message(
            f"🔀 Karıştırma {state}.",
            ephemeral=True,
        )

    @discord.ui.button(label="Döngü", emoji="🔁", style=discord.ButtonStyle.secondary, row=1)
    async def repeat(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        guild_id = interaction.guild.id
        repeat_enabled[guild_id] = not repeat_enabled.get(guild_id, False)

        state = "açıldı" if repeat_enabled[guild_id] else "kapatıldı"

        await interaction.response.send_message(
            f"🔁 Döngü {state}.",
            ephemeral=True,
        )

    @discord.ui.button(label="Kuyruk", emoji="📜", style=discord.ButtonStyle.secondary, row=1)
    async def show_queue(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        tracks = list(get_queue(interaction.guild.id)._queue)

        if not tracks:
            await interaction.response.send_message(
                "Kuyruk boş.",
                ephemeral=True,
            )
            return

        description = "\n".join(
            f"**{i}.** {item['title']}"
            for i, item in enumerate(tracks[:15], start=1)
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎶 HELY MÜZİK • Kuyruk",
                description=description,
                color=discord.Color.blurple(),
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Ses +", emoji="🔊", style=discord.ButtonStyle.secondary, row=2)
    async def volume_up(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        guild_id = interaction.guild.id
        volume = min(1.0, music_volumes.get(guild_id, 0.5) + 0.1)
        music_volumes[guild_id] = volume

        voice = interaction.guild.voice_client

        if voice and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = volume

        await interaction.response.send_message(
            f"🔊 Ses: {round(volume * 100)}%",
            ephemeral=True,
        )

    @discord.ui.button(label="Ses −", emoji="🔉", style=discord.ButtonStyle.secondary, row=2)
    async def volume_down(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        guild_id = interaction.guild.id
        volume = max(0.0, music_volumes.get(guild_id, 0.5) - 0.1)
        music_volumes[guild_id] = volume

        voice = interaction.guild.voice_client

        if voice and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = volume

        await interaction.response.send_message(
            f"🔉 Ses: {round(volume * 100)}%",
            ephemeral=True,
        )

    @discord.ui.button(label="Şarkı Sözleri", emoji="🎤", style=discord.ButtonStyle.success, row=3)
    async def lyrics(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        track = current_tracks.get(interaction.guild.id)

        if not track:
            await interaction.response.send_message(
                "Şu anda çalan şarkı yok.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🎤 **{track['title']}** için şarkı sözleri araması:",
            view=LyricsView(track),
            ephemeral=True,
        )

    @discord.ui.button(label="Yenile", emoji="🔄", style=discord.ButtonStyle.secondary, row=3)
    async def refresh(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        await refresh_room(self.voice_id)

        await interaction.response.send_message(
            "🔄 Oda bilgileri yenilendi.",
            ephemeral=True,
        )

    @discord.ui.button(label="Durdur", emoji="⏹️", style=discord.ButtonStyle.danger, row=3)
    async def stop(self, interaction, button):
        if not await self.check_owner(interaction):
            return

        guild_id = interaction.guild.id
        stop_requested.add(guild_id)
        skip_requested.discard(guild_id)

        queue = get_queue(guild_id)

        while not queue.empty():
            try:
                queue.get_nowait()
                queue.task_done()
            except asyncio.QueueEmpty:
                break

        voice = interaction.guild.voice_client

        if voice:
            if voice.is_playing() or voice.is_paused():
                voice.stop()

            try:
                await voice.disconnect(force=True)
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            "⏹️ Müzik durduruldu. Odan silinmedi.",
            ephemeral=True,
        )


# =========================================================
# REKLAM
# =========================================================

class AdvertisementView(discord.ui.View):
    def __init__(self, requester_id):
        super().__init__(timeout=180)
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
                "Bu reklamı yalnızca şarkıyı isteyen kişi onaylayabilir.",
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
                title="⏳ Reklam onaylandı",
                description="20 saniye sonra müzik devam edecek.",
                color=discord.Color.orange(),
            ),
            view=self,
        )

        self.confirmed.set()


async def play_ad(channel, requester):
    global ad_counter

    ad_counter += 1
    node_ad = ad_counter % 2 == 0

    if node_ad:
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

    message = await send_voice_chat(
        channel,
        content=requester.mention,
        embed=embed,
        view=view,
    )

    if not message:
        return

    try:
        await asyncio.wait_for(view.confirmed.wait(), timeout=180)
    except asyncio.TimeoutError:
        try:
            await message.edit(
                content=None,
                embed=discord.Embed(
                    title="⌛ Reklam onayı bekleniyor",
                    description="Reklam onaylanmadığı için sonraki şarkı bekliyor.",
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
                title="✅ Reklam sona erdi",
                description="İyi dinlemeler! 🎵",
                color=discord.Color.green(),
            ),
            view=None,
        )
    except discord.HTTPException:
        pass


# =========================================================
# MÜZİK ÇALAR
# =========================================================

async def music_player(guild_id):
    queue = get_queue(guild_id)

    while True:
        track = await queue.get()

        try:
            guild = bot.get_guild(guild_id)

            if guild is None:
                continue

            room = get_room(track["voice_channel_id"])

            if room is None:
                continue

            channel = guild.get_channel(track["voice_channel_id"])

            if channel is None:
                continue

            requester = guild.get_member(track["requester_id"])

            if requester is None:
                try:
                    requester = await guild.fetch_member(track["requester_id"])
                except discord.HTTPException:
                    continue

            if requester.id in data["banned_users"]:
                continue

            unlimited = has_unlimited_access(requester)

            if not unlimited and remaining_songs(requester.id) <= 0:
                await send_voice_chat(
                    channel,
                    content=f"{requester.mention}, günlük şarkı hakkın bitti.",
                )
                continue

            if is_banned_track(track):
                await send_voice_chat(
                    channel,
                    content="⛔ Bu şarkı veya sanatçı engellenmiş.",
                )
                continue

            quality = room.get("quality", "Orta")

            try:
                audio_url = await asyncio.to_thread(
                    get_audio_url,
                    track["url"],
                    quality,
                )
            except Exception as exc:
                print(f"[YOUTUBE SES HATASI] {type(exc).__name__}: {exc}")
                traceback.print_exc()

                await send_voice_chat(
                    channel,
                    content=(
                        "❌ YouTube ses akışı alınamadı. "
                        "FadeHost konsolunda YOUTUBE SES HATASI satırını kontrol et."
                    ),
                )
                continue

            voice = guild.voice_client

            try:
                if voice is None:
                    voice = await channel.connect()
                elif voice.channel.id != channel.id:
                    await voice.move_to(channel)
            except Exception as exc:
                print(f"[SES BAĞLANTISI HATASI] {exc}")

                await send_voice_chat(
                    channel,
                    content="❌ Ses kanalına bağlanılamadı. Bot izinlerini kontrol et.",
                )
                continue

            right_source = spend_song(requester.id)

            if right_source is None:
                await send_voice_chat(
                    channel,
                    content=f"{requester.mention}, dinleme hakkın kalmadı.",
                )
                continue

            current_tracks[guild_id] = track

            history = previous_tracks.setdefault(guild_id, [])
            history.append(track.copy())

            if len(history) > 25:
                del history[:-25]

            await refresh_room(channel.id)

            embed = discord.Embed(
                title="🎵 HELY MÜZİK",
                description=(
                    f"**Şimdi çalıyor:** [{track['title']}]({track['url']})\n"
                    f"**Sanatçı:** {track['uploader']}\n"
                    f"**Süre:** {format_duration(track['duration'])}\n"
                    f"**İsteyen:** {requester.mention}\n\n"
                    "Aşağıdaki butonlardan müziği yönetebilirsin."
                ),
                color=discord.Color.blurple(),
            )

            await send_voice_chat(
                channel,
                embed=embed,
                view=MusicControls(channel.id),
            )

            loop = asyncio.get_running_loop()
            finished = loop.create_future()

            def after_playback(error):
                def resolve():
                    if not finished.done():
                        finished.set_result(error)

                loop.call_soon_threadsafe(resolve)

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
                    volume=music_volumes.get(guild_id, 0.5),
                )

                voice.play(source, after=after_playback)
                error = await finished

                if error:
                    print(f"[FFMPEG OYNATMA HATASI] {error}")
                    refund_song(requester.id, right_source)

                    await send_voice_chat(
                        channel,
                        content="⚠️ Şarkı oynatılamadı. Dinleme hakkın iade edildi.",
                    )
                    continue

            except Exception as exc:
                print(f"[OYNATMA HATASI] {type(exc).__name__}: {exc}")
                traceback.print_exc()

                refund_song(requester.id, right_source)

                await send_voice_chat(
                    channel,
                    content="❌ Şarkı başlatılamadı. Dinleme hakkın iade edildi.",
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

            if not has_unlimited_access(requester):
                await play_ad(channel, requester)

        except Exception as exc:
            print(f"[MÜZİK DÖNGÜSÜ HATASI] {type(exc).__name__}: {exc}")
            traceback.print_exc()

        finally:
            queue.task_done()


# =========================================================
# !Play KOMUTU
# =========================================================

@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query=None):
    if ctx.guild is None:
        return

    if ctx.author.id in data["banned_users"]:
        await ctx.send("⛔ Müzik kullanman engellenmiş.")
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Önce kendi özel müzik odana katıl.")
        return

    voice_channel = ctx.author.voice.channel
    room = get_room(voice_channel.id)

    if room is None:
        await ctx.send("Bu ses kanalı HELY MÜZİK odası değil.")
        return

    if (
        ctx.author.id != int(room["owner_id"])
        and not is_bot_owner(ctx.author)
    ):
        await ctx.send("Bu odayı yalnızca oda sahibi kullanabilir.")
        return

    if not query:
        track = current_tracks.get(ctx.guild.id)

        if track:
            description = (
                f"**Şimdi çalıyor:** [{track['title']}]({track['url']})\n"
                "Müziği aşağıdaki düğmelerle yönetebilirsin."
            )
        else:
            description = (
                "Müzik başlatmak için `!Play şarkı adı` "
                "veya YouTube bağlantısı gönder."
            )

        await send_voice_chat(
            voice_channel,
            embed=discord.Embed(
                title="🎵 HELY MÜZİK",
                description=description,
                color=discord.Color.blurple(),
            ),
            view=MusicControls(voice_channel.id),
        )
        return

    if (
        not has_unlimited_access(ctx.author)
        and remaining_songs(ctx.author.id) <= 0
    ):
        await ctx.send("❌ Günlük 10 şarkı hakkın bitti.")
        return

    status = await ctx.send("🔎 YouTube aranıyor...")

    try:
        track = await asyncio.to_thread(search_youtube, query)

    except Exception as exc:
        print(f"[YOUTUBE ARAMA HATASI] {type(exc).__name__}: {exc}")
        traceback.print_exc()

        await status.edit(
            content=(
                "❌ YouTube'da şarkı bulunamadı veya YouTube isteği başarısız oldu.\n"
                "FadeHost konsolundaki **YOUTUBE ARAMA HATASI** satırını kontrol et."
            )
        )
        return

    track["requester_id"] = ctx.author.id
    track["voice_channel_id"] = voice_channel.id
    track["guild_id"] = ctx.guild.id

    await get_queue(ctx.guild.id).put(track)

    await status.edit(
        content=f"➕ **Kuyruğa eklendi:** {track['title']}"
    )

    task = player_tasks.get(ctx.guild.id)

    if task is None or task.done():
        player_tasks[ctx.guild.id] = asyncio.create_task(
            music_player(ctx.guild.id)
        )


# =========================================================
# SAHİBE ÖZEL AYARLAR
# =========================================================

class GrantSongsModal(discord.ui.Modal, title="Dinleme Hakkı Ver"):
    amount = discord.ui.TextInput(
        label="Ek şarkı sayısı veya Sınırsız",
        placeholder="Örn: 12 veya Sınırsız",
        max_length=20,
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
                "Bir sayı veya Sınırsız yaz.",
                ephemeral=True,
            )
            return

        if not 1 <= amount <= 100000:
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
            f"✅ {self.target.mention} kullanıcısına {amount} ek şarkı hakkı verildi.",
            ephemeral=True,
        )


class GrantSongsView(discord.ui.View):
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
    @discord.ui.button(
        label="Şarkı Hakkı Ver",
        emoji="🎵",
        style=discord.ButtonStyle.success,
    )
    async def grant(self, interaction, button):
        if not is_bot_owner(interaction.user):
            await interaction.response.send_message(
                "Bu panel yalnızca bot sahibine açık.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Kullanıcı seç:",
            view=GrantSongsView(),
            ephemeral=True,
        )


@bot.command(name="ayarlar")
async def settings(ctx):
    if not is_bot_owner(ctx.author):
        return

    await ctx.send(
        embed=discord.Embed(
            title="⚙️ HELY MÜZİK • Yönetim",
            description=(
                "Kullanıcıya ek şarkı hakkı veya sınırsız erişim verebilirsin."
            ),
            color=discord.Color.blurple(),
        ),
        view=SettingsView(),
    )


# =========================================================
# ENGELLEME KOMUTLARI
# =========================================================

@bot.command(name="banuser")
async def ban_user(ctx, user_id: int):
    if not is_bot_owner(ctx.author):
        return

    if user_id not in data["banned_users"]:
        data["banned_users"].append(user_id)

    save_data()
    await ctx.send(f"⛔ `{user_id}` müzikten engellendi.")


@bot.command(name="unbanuser")
async def unban_user(ctx, user_id: int):
    if not is_bot_owner(ctx.author):
        return

    if user_id in data["banned_users"]:
        data["banned_users"].remove(user_id)

    save_data()
    await ctx.send(f"✅ `{user_id}` müzik engeli kaldırıldı.")


@bot.command(name="banartist")
async def ban_artist(ctx, *, artist: str):
    if not is_bot_owner(ctx.author):
        return

    if artist.casefold() not in [
        item.casefold() for item in data["banned_artists"]
    ]:
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

    if song.casefold() not in [
        item.casefold() for item in data["banned_songs"]
    ]:
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


# =========================================================
# ODA SAHİBİ AYRILIRSA ODAYI SİL
# =========================================================

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or before.channel is None:
        return

    room = get_room(before.channel.id)

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

    voice = guild.voice_client

    if voice and voice.channel and voice.channel.id == voice_id:
        try:
            await voice.disconnect(force=True)
        except discord.HTTPException:
            pass

    channel = guild.get_channel(voice_id)

    if channel:
        try:
            await channel.delete(
                reason="Müzik odasının sahibi ayrıldı."
            )
        except discord.HTTPException as exc:
            print(f"[ODA SİLME HATASI] {exc}")


# =========================================================
# BAŞLANGIÇ VE TOKEN
# =========================================================

@bot.event
async def on_ready():
    print(f"HELY MÜZİK giriş yaptı: {bot.user} ({bot.user.id})")

    changed = False

    for voice_id, room in list(data["rooms"].items()):
        guild = bot.get_guild(int(room["guild_id"]))
        channel = guild.get_channel(int(voice_id)) if guild else None

        if channel is None:
            data["rooms"].pop(voice_id, None)
            changed = True

    if changed:
        save_data()

    bot.add_view(CreateRoomView())

    print("HELY MÜZİK hazır.")


def load_token():
    token = os.getenv("DISCORD_TOKEN")

    if token:
        return token.strip()

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                config = json.load(file)

            if config.get("token"):
                return str(config["token"]).strip()

        except (OSError, json.JSONDecodeError) as exc:
            print(f"[TOKEN DOSYASI] {exc}")

    return None


token = load_token()

if not token:
    raise RuntimeError(
        "Token bulunamadı. FadeHost ortam değişkenlerine "
        "DISCORD_TOKEN ekle."
    )

bot.run(token)
