import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp

TOKEN = os.environ.get("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "extract_flat": False,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Cola de canciones por servidor (guild)
queues = {}


def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]


async def search_song(query: str):
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = await loop.run_in_executor(
            None, lambda: ydl.extract_info(query, download=False)
        )
        if "entries" in info:
            info = info["entries"][0]
        return {
            "title": info.get("title", "Desconocido"),
            "url": info["url"],
            "webpage_url": info.get("webpage_url", ""),
            "duration": info.get("duration", 0),
        }


def play_next(guild, voice_client):
    queue = get_queue(guild.id)
    if len(queue) == 0:
        return

    song = queue.pop(0)
    source = discord.FFmpegPCMAudio(song["url"], **FFMPEG_OPTIONS)

    def after_play(error):
        if error:
            print(f"Error reproduciendo: {error}")
        if len(get_queue(guild.id)) > 0:
            play_next(guild, voice_client)
        else:
            asyncio.run_coroutine_threadsafe(
                voice_client.disconnect(), bot.loop
            )

    voice_client.play(source, after=after_play)


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"DJ Tiramisu conectado como {bot.user}")


@bot.tree.command(name="play", description="Reproduce una canción desde YouTube")
@app_commands.describe(busqueda="Nombre de la canción o URL de YouTube")
async def play(interaction: discord.Interaction, busqueda: str):
    await interaction.response.defer()

    if interaction.user.voice is None:
        await interaction.followup.send(
            "Tienes que estar conectado a un canal de voz primero."
        )
        return

    voice_channel = interaction.user.voice.channel
    guild = interaction.guild

    voice_client = guild.voice_client
    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    try:
        song = await search_song(busqueda)
    except Exception as e:
        await interaction.followup.send(f"No pude encontrar esa canción: {e}")
        return

    queue = get_queue(guild.id)
    queue.append(song)

    if not voice_client.is_playing() and not voice_client.is_paused():
        play_next(guild, voice_client)
        await interaction.followup.send(f"Reproduciendo ahora: **{song['title']}**")
    else:
        await interaction.followup.send(f"Agregado a la cola: **{song['title']}**")


@bot.tree.command(name="skip", description="Salta la canción actual")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None or not voice_client.is_playing():
        await interaction.response.send_message("No hay nada reproduciéndose.")
        return
    voice_client.stop()
    await interaction.response.send_message("Canción saltada.")


@bot.tree.command(name="stop", description="Detiene la música y limpia la cola")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        await interaction.response.send_message("No estoy conectado a ningún canal.")
        return
    get_queue(interaction.guild.id).clear()
    voice_client.stop()
    await voice_client.disconnect()
    await interaction.response.send_message("Música detenida y desconectado.")


@bot.tree.command(name="pause", description="Pausa la canción actual")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None or not voice_client.is_playing():
        await interaction.response.send_message("No hay nada reproduciéndose.")
        return
    voice_client.pause()
    await interaction.response.send_message("Música en pausa.")


@bot.tree.command(name="resume", description="Reanuda la canción pausada")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None or not voice_client.is_paused():
        await interaction.response.send_message("No hay nada en pausa.")
        return
    voice_client.resume()
    await interaction.response.send_message("Reanudando música.")


@bot.tree.command(name="queue", description="Muestra la cola de canciones")
async def queue_cmd(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)
    if len(queue) == 0:
        await interaction.response.send_message("La cola está vacía.")
        return
    texto = "\n".join(
        [f"{i+1}. {song['title']}" for i, song in enumerate(queue)]
    )
    await interaction.response.send_message(f"**Cola de canciones:**\n{texto}")


@bot.tree.command(name="leave", description="Desconecta al bot del canal de voz")
async def leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        await interaction.response.send_message("No estoy conectado.")
        return
    get_queue(interaction.guild.id).clear()
    await voice_client.disconnect()
    await interaction.response.send_message("Desconectado del canal de voz.")


if __name__ == "__main__":
    if TOKEN is None:
        print("ERROR: No se encontró la variable de entorno DISCORD_TOKEN")
    else:
        bot.run(TOKEN)
