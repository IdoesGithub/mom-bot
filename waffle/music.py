"""Music commands."""
import asyncio
from pathlib import Path, PurePath
import os
from datetime import timedelta
from collections import deque

import discord
from discord.ext import commands
import youtube_dl
import waffle.config

CONFIG = waffle.config.CONFIG["config"]


def setup(bot):
    """Sets up the cog."""
    bot.add_cog(Music(bot))


class Song:
    """A song object to play youtube videos from."""

    def __init__(self):
        self.opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "opus",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": "cache/%(id)s.%(ext)s",
            "quiet": True,
        }
        self.youtube = youtube_dl.YoutubeDL(self.opts)

    def create(self, ctx, query):
        try:
            extracted_info = self.from_youtube(query)
            self.video_id = extracted_info.get("id", None)
            self.url = extracted_info.get("webpage_url", None)
            self.title = extracted_info.get("title", None)
            self.duration_seconds = extracted_info.get("duration", None)
            self.duration = str(timedelta(seconds=self.duration_seconds))
            self.filename = PurePath("cache/", self.video_id + ".opus")
            self.thumbnail = (
                f"https://img.youtube.com/vi/{self.video_id}/" "maxresdefault.jpg"
            )
            self.uploader = extracted_info.get("uploader", None)
            self.channel_url = extracted_info.get("channel_url", None)
            self.artist = extracted_info.get("artist", None)
            self.position = len(ctx.music_state.queue) + 1
            self.requested_by = ctx.author
            if not Path(self.filename).exists():
                try:
                    return self.youtube.extract_info(self.url, download=True)
                except youtube_dl.utils.DownloadError:
                    return None
            else:
                return self.youtube.extract_info(self.url, download=False)
        except youtube_dl.utils.DownloadError:
            return None

    def from_youtube(self, request):
        """Gets video info."""

        query = "ytsearch:" + str(request)
        info = self.youtube.extract_info(query, download=False)
        entries = info.get("entries", None)
        extracted_info = entries[0]
        return extracted_info

    def embed(self, author, action):
        embed = discord.Embed(
            title=self.title, url=self.url, colour=discord.Colour(0xFF0000)
        )
        embed.set_image(url=self.thumbnail)
        embed.set_author(name=f"{author.name} {action}", icon_url=author.avatar_url)
        embed.add_field(name="Uploader", value=self.uploader, inline=True)
        embed.add_field(name="Artist", value=self.artist, inline=True)
        embed.add_field(name="Position in queue", value=self.position, inline=True)
        embed.add_field(name="Duration:", value=self.duration, inline=True)
        return embed


class GuildMusicState:
    """Class to store music states to separate different guild's playlists"""

    def __init__(self, ctx, loop):
        self.bot = ctx.bot
        self.ctx = ctx
        self.queue = deque()
        self.queue_capacity = CONFIG["queue_capacity"]
        self.voice = ctx.guild.voice_client
        self.volume = 0.1
        self.current_song = None
        self.loop = loop
        self.mode = None

    def next_song_info(self):
        if self.mode == "repeat":
            return self.current_song
        elif self.mode == "loop":
            song = self.queue.popleft()
            self.add_to_queue(song)
            return song
        elif self.queue:
            return self.queue.popleft()
        elif not self.queue:
            return None

    async def play_next_song(self, song):
        """Plays next song."""
        if not song:
            self.current_song = None
            await asyncio.sleep(10)
            if not self.voice.is_playing() and not self.voice.is_paused():
                await self.voice.disconnect()
                await self.ctx.send("Disconnected due to timeout.")
                self.cleanup()
            return

        for i, song in enumerate(self.queue):
            self.queue[i].position = i + 1

        self.current_song = song
        self.voice.play(
            discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(song.filename), volume=self.volume
            ),
            after=lambda e: self.loop.create_task(
                self.play_next_song(self.next_song_info())
            ),
        )

    def cleanup(self):
        self.mode = None
        self.queue.clear()
        self.current_song = None
        self.voice = None

    def add_to_queue(self, song):
        if self.current_song:
            song.position = len(self.queue) + 1
        else:
            song.position = "Now playing"
        self.queue.append(song)


class Music(commands.Cog):
    """Main music cog"""

    def __init__(self, bot):

        self.bot = bot
        self.states = {}

    def is_dj():
        """Check if a specifed channel exists."""

        async def predicate(ctx):
            if "dj" in CONFIG:
                author = ctx.author
                converter = commands.RoleConverter()
                dj_role = await converter.convert(ctx, CONFIG["dj"])
                if dj_role in author.roles:
                    return True
                else:
                    return False
            else:
                return True

        return commands.check(predicate)

    async def cog_before_invoke(self, ctx):
        ctx.music_state = self.states.setdefault(
            ctx.guild.id, GuildMusicState(ctx, self.bot.loop)
        )
        ctx.music_state.voice = ctx.guild.voice_client

    @staticmethod
    async def on_ready():
        """Prints a message when the cog is ready."""
        print("Music is ready!")

    @staticmethod
    def clear_song_cache():
        """Clears downloaded songs."""
        songs = Path.iterdir("cache")
        for item in songs:
            if item.endswith(".opus"):
                os.remove(item)

    @commands.command(name="play", aliases=["p"])
    @commands.guild_only()
    @is_dj()
    async def play(self, ctx, *, request):
        """Plays or adds a song to queue. Args: <search terms/url>"""
        author = ctx.author
        music_state = ctx.music_state

        if len(request) == 0:
            await ctx.send(f":no_entry_sign: please enter a song.")
            return

        if not author.voice:
            await ctx.send(
                f":no_entry_sign: {ctx.author.mention}, you are "
                "not connected to any voice channel."
            )
            return

        voice_channel = author.voice.channel
        if not music_state.voice or voice_channel != music_state.voice.channel:
            music_state.voice = await voice_channel.connect()

        song = Song()
        if not song.create(ctx, request):
            await ctx.send(":no_entry_sign: Song not found!")
            return

        if not music_state.voice.is_playing():
            music_state.add_to_queue(song)
            await music_state.play_next_song(music_state.next_song_info())
            await ctx.send(embed=song.embed(author, "added to queue"))
        elif len(music_state.queue) >= music_state.queue_capacity:
            await ctx.send(
                ":no_entry_sign: " "The queue is full! Please try again later."
            )
        else:
            music_state.add_to_queue(song)
            await ctx.send(embed=song.embed(author, "added to queue"))

    @commands.command(name="stop", aliases=["disconnect"])
    @commands.guild_only()
    @is_dj()
    async def stop(self, ctx):
        """Stops the voice client."""
        music_state = ctx.music_state

        if music_state.voice:
            if music_state.voice.is_playing():
                await music_state.voice.disconnect()
                music_state.cleanup()
                await ctx.send(":eject: Disconnected!")
        else:
            await ctx.send(":no_entry_sign: I'm not connected to voice!")

    @commands.command(name="pause")
    @commands.guild_only()
    @is_dj()
    async def pause(self, ctx):
        """Pauses the voice client."""
        music_state = ctx.music_state

        if music_state.voice is not None:
            if music_state.voice.is_paused():
                await music_state.send(":no_entry_sign: I'm already paused!")
            else:
                music_state.voice.pause()
                await music_state.send(":pause_button: Paused!")
        else:
            await ctx.send(":no_entry_sign: I'm not connected to voice!")

    @commands.command(name="resume")
    @commands.guild_only()
    @is_dj()
    async def resume(self, ctx):
        """Resumes the voice client."""
        music_state = ctx.music_state

        if music_state.voice is not None:
            if not music_state.voice.is_paused():
                await ctx.send(":no_entry_sign: I'm not paused!")
            else:
                music_state.voice.resume()
                await ctx.send(":arrow_forward: Resumed!")
        else:
            await ctx.send(":no_entry_sign: I'm not connected to voice!")

    @commands.command(name="volume")
    @commands.guild_only()
    @is_dj()
    async def volume(self, ctx, volume: float):
        """Changes voice client volume. Args: <0.0-100>"""
        if volume > 100:
            await ctx.send(":no_entry_sign: Volume over 100 is prohibited.")
        else:
            music_state = ctx.music_state
            music_state.volume = volume / 1000

            if music_state.voice:
                music_state.voice.source.volume = music_state.volume
                await ctx.send(f":loud_sound: Changed volume to {music_state.volume}")
            else:
                await ctx.send(":no_entry_sign: I'm not connected to voice!")

    @commands.command(name="skip", aliases=["s"])
    @commands.guild_only()
    @is_dj()
    async def skip(self, ctx):
        """Skips to the next song."""
        ctx.music_state.voice.stop()
        await ctx.send(":track_next: Skipped!")

    @commands.command(name="repeat", aliases=["r"])
    @commands.guild_only()
    @is_dj()
    async def repeat(self, ctx):
        music_state = ctx.music_state
        if music_state.mode != "repeat":
            music_state.mode = "repeat"
            await ctx.send(":repeat_one: Repeat on!")
        else:
            music_state.mode = None
            await ctx.send(":repeat_one: Repeat off!")

    @commands.command(name="loop", aliases=["l"])
    @commands.guild_only()
    @is_dj()
    async def loop(self, ctx):
        music_state = ctx.music_state
        if music_state.mode != "loop":
            music_state.mode = "loop"
            music_state.add_to_queue(music_state.current_song)
            await ctx.send(":repeat: Loop on!")
        else:
            music_state.mode = None
            await ctx.send(":repeat: Loop off!")

    @commands.command(name="queue", aliases=["q"])
    @commands.guild_only()
    async def queue(self, ctx):
        music_state = ctx.music_state
        queue = music_state.queue
        if len(queue) < 1 and not music_state.current_song:
            await ctx.send(":no_entry_sign: Queue is empty!")
            return
        song = music_state.current_song

        if not music_state.mode:
            mode = ":play_pause:"
        elif music_state.mode == "loop":
            mode = ":repeat:"
        elif music_state.mode == "repeat":
            mode = ":repeat_one:"

        embed = discord.Embed(
            title=f"Queue for {ctx.guild}",
            colour=discord.Colour(0xF8E71C),
            description=f"{mode} Now Playing:\n "
            f"[{song.title}]({song.url}) "
            f"| {song.duration} Requested by "
            f"{song.requested_by.mention}\n\n\n"
            f":arrow_down: Up next :arrow_down:",
        )
        for i, song in enumerate(queue):
            music_state.queue[i].position = i + 1
            embed.add_field(
                name=f"{song.position}.",
                value=f"[{song.title}]({song.url}) "
                f"| {song.duration} "
                f"Requested by {song.requested_by.mention}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="remove")
    @commands.guild_only()
    async def remove(self, ctx, position: int):
        music_state = ctx.music_state
        song = music_state.queue[position - 1]
        try:
            del music_state.queue[position - 1]
            await ctx.send(embed=song.embed(ctx.author, "removed from queue"))
        except IndexError:
            await ctx.send(":no_entry_sign: Position out of range!")

    @commands.command(name="playnext")
    @commands.guild_only()
    async def play_next(self, ctx, position: int):
        music_state = ctx.music_state
        song = music_state.queue[position - 1]
        try:
            del music_state.queue[position - 1]
            music_state.queue.appendleft(song)
            await ctx.send(embed=song.embed(ctx.author, "moved next in queue"))
        except IndexError:
            await ctx.send(":no_entry_sign: Position out of range!")

    @commands.command(name="playlater")
    @commands.guild_only()
    async def play_later(self, ctx, position: int):
        music_state = ctx.music_state
        song = music_state.queue[position - 1]
        try:
            del music_state.queue[position - 1]
            music_state.queue.append(song)
            await ctx.send(embed=song.embed(ctx.author, "moved later in queue"))
        except IndexError:
            await ctx.send(":no_entry_sign: Position out of range!")
