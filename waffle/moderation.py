"""Moderation commands."""
import discord
from discord.ext import commands
import humanize

import waffle.config
import waffle.scheduler

CONFIG = waffle.config.CONFIG["config"]


def setup(bot):
    """Set up the cog."""
    bot.add_cog(Moderation(bot))


class Moderation(commands.Cog):
    """Commands for moderation."""

    def __init__(self, bot):
        """Initizises Moderation cog."""
        self.bot = bot

    @staticmethod
    async def on_ready():
        """Print when the cog is ready."""
        print("Moderation is ready!")

    @staticmethod
    async def mod_log(
        message_id, time, log_type, user, reason, moderator, duration=None
    ):
        """Mod logging."""
        embed = discord.Embed(
            title=f"{log_type} for user {user.id}",
            colour=discord.Colour(0xF8E71C),
            timestamp=time,
        )
        embed.set_author(
            name=moderator.name,
            url="https://discordapp.com",
            icon_url=moderator.avatar_url,
        )

        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        if duration:
            embed.add_field(
                name="Duration:", value=humanize.naturaldelta(duration), inline=True
            )
        embed.set_footer(text=f"ID: {message_id}")
        return embed

    @staticmethod
    @commands.Cog.listener()
    async def on_member_join(member):
        """Auto role."""
        if CONFIG["welcome_channel"]:
            channel = discord.utils.find(
                lambda m: m.name == CONFIG["welcome_channel"], member.guild.channels
            )
            await channel.send(f"Welcome {member.mention}!")
        if CONFIG["autorole"]:
            default_role = discord.utils.find(
                lambda m: m.name == CONFIG["autorole"], member.guild.roles
            )
            await member.add_roles(default_role)

    @commands.command(name="clear", aliases=["c"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount=1):
        """
        Clear the specified amount of messages.
        Syntax: clear <amount> <optional:user>
        """
        channel = ctx.message.channel
        messages = []
        async for message in channel.history(limit=int(amount)):
            messages.append(message)
        await channel.delete_messages(messages)

    @commands.command(name="kick", aliases=["k"])
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, user: discord.Member, *, reason):
        """
        Kicks the specified user.
        Syntax: kick <user> <reason>
        """
        author = ctx.author
        guild = ctx.guild
        channels = guild.text_channels
        reason = "None specified"
        if not author.top_role > user.top_role:
            raise commands.MissingPermissions("Is superset")
        await user.kick(reason=reason)
        embed = await self.mod_log(
            ctx.message.id, ctx.message.created_at, "Kick", user, reason, author
        )
        log_channel = discord.utils.get(channels, name=CONFIG["log_channel"])
        await log_channel.send(embed=embed)

    @commands.command(name="ban", aliases=["b"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user: discord.Member, *, reason):
        """
        Bans the specified user.
        Syntax: ban <user> <reason>
        """
        author = ctx.author
        reason = "None specified"
        channels = ctx.guild.text_channels
        if not author.top_role > user.top_role:
            raise commands.MissingPermissions("Is superset")
        await user.ban(reason=reason)
        embed = await self.mod_log(
            ctx.message.id, ctx.message.created_at, "Ban", user, reason, author
        )
        log_channel = discord.utils.get(channels, name=CONFIG["log_channel"])
        if log_channel is None:
            await ctx.send(
                ":no_entry_sign: Mod logging channel "
                "does not exist! "
                "Either create "
                "a channel named 'mod-log' "
                "or change the config file."
            )
        else:
            await log_channel.send(embed=embed)

    @commands.command(name="unban", aliases=["pardon"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user: discord.User, *, reason):
        """
        Unbans the specified user.
        Syntax: unban <user> <reason>
        """
        author = ctx.author
        guild = ctx.guild
        reason = "None specified"
        channels = guild.text_channels
        banned = await guild.fetch_ban(user)
        if banned:
            await guild.unban(user, reason=reason)
            embed = await self.mod_log(
                ctx.message.id, ctx.message.created_at, "Unban", user, reason, author
            )
            log_channel = discord.utils.get(channels, name=CONFIG["log_channel"])
            if log_channel is None:
                await ctx.send(
                    ":no_entry_sign: mod logging channel "
                    "does not exist! "
                    "either create "
                    "a channel named 'mod-log' "
                    "or change the config file."
                )
            else:
                await log_channel.send(embed=embed)

    @commands.command(name="tempban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, user: discord.Member, duration, *, reason):
        await ctx.invoke(self.ban, user=user, reason=reason)
        waffle.scheduler.set_task(
            ctx, "moderation.unban", duration, user=user, reason="Tempban"
        )

    @commands.command(name="addrole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def addrole(self, ctx, user: discord.Member, role: discord.role, *, reason):
        """
        Give the specified user a role.
        Syntax: addrole <user> <role>
        """
        author = ctx.author
        reason = "None specified"
        channels = ctx.guild.text_channels
        if not author.top_role > role:
            raise commands.missingpermissions("is superset")
        await user.add_roles(role)
        embed = await self.mod_log(
            ctx.message.id, ctx.message.created_at, "Add role", user, reason, author
        )
        log_channel = discord.utils.get(channels, name=CONFIG["log_channel"])
        if log_channel is None:
            await ctx.send(
                ":no_entry_sign: mod logging "
                "channel does not exist! "
                "either create "
                "a channel named 'mod-log' "
                "or change the config file."
            )
        else:
            await log_channel.send(embed=embed)

    @commands.command(name="removerole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def removerole(
        self, ctx, user: discord.Member, role: discord.role, *, reason
    ):
        """
        Remove a role from the specified user.
        Syntax: removerole <user> <role>
        """
        author = ctx.author
        reason = "None specified"
        channels = ctx.guild.text_channels
        if not author.top_role > role:
            raise commands.missingpermissions("is superset")
        await user.remove_roles(role)
        embed = await self.mod_log(
            ctx.message.id, ctx.message.created_at, "Remove role", user, reason, author
        )
        log_channel = discord.utils.get(channels, name=CONFIG["log_channel"])
        if log_channel is None:
            await ctx.send(
                ":no_entry_sign: mod logging "
                "channel does not exist! "
                "either create "
                "a channel named 'mod-log' "
                "or change the config file."
            )
        else:
            await log_channel.send(embed=embed)

    @commands.command(name="mute", aliases=["m"])
    @commands.guild_only()
    async def mute(self, ctx, user: discord.Member, *, reason):
        """
        Mute the specified user.
        Syntax: mute <user> <reason>
        """
        author = ctx.author
        guild = ctx.guild
        channels = ctx.guild.text_channels
        mute_role = discord.utils.get(guild.roles, name=CONFIG["mute"])
        log_channel = discord.utils.get(channels, name=CONFIG["log_channel"])
        if mute_role is None and CONFIG["mute"]:
            await guild.create_role(name=CONFIG["mute"])

        if author.top_role > user.top_role and mute_role:
            if mute_role in user.roles:
                await ctx.send(f":no_entry_sign: {user.mention} is already muted!")
                return True
            elif log_channel:
                await user.add_roles(mute_role, reason=reason)
                embed = await self.mod_log(
                    ctx.message.id, ctx.message.created_at, "Mute", user, reason, author
                )
                await log_channel.send(embed=embed)
            else:
                await ctx.send(
                    ":no_entry_sign: mod logging "
                    "channel does not exist! "
                    "either create "
                    "a channel named 'mod-log' "
                    "or change the config file."
                )
        elif not CONFIG["mute"]:
            ctx.send(":no_entry_sign: Muting is disabled!")
        else:
            raise commands.MissingPermissions("Is superset")

    @commands.command(name="unmute")
    @commands.guild_only()
    async def unmute(self, ctx, user: discord.Member, *, reason):
        """
        Unmute the specified user.
        Syntax: unmute <user> <reason>
        """
        author = ctx.author
        guild = ctx.guild
        channels = guild.text_channels
        muted = discord.utils.get(guild.roles, name=CONFIG["mute"])
        log_channel = discord.utils.get(channels, name=CONFIG["log_channel"])
        if author.top_role > user.top_role:
            if muted in user.roles:
                await user.remove_roles(muted, reason=reason)
                embed = await self.mod_log(
                    ctx.message.id,
                    ctx.message.created_at,
                    "Unmute",
                    user,
                    reason,
                    author,
                )
                if log_channel is None:
                    await ctx.send(
                        ":no_entry_sign: Mod logging "
                        "channel does not exist! "
                        "Either create "
                        "a channel named 'mod-log' "
                        "or change the config file."
                    )
                else:
                    await log_channel.send(embed=embed)
            else:
                await ctx.send(f":no_entry_sign: {user.mention} " "is not muted!")
        else:
            raise commands.MissingPermissions("Is superset")

    @commands.command(name="tempmute")
    @commands.guild_only()
    async def tempmute(self, ctx, user: discord.Member, duration, *, reason):
        await ctx.invoke(self.mute, user=user, reason=reason)
        await waffle.scheduler.set_task(
            ctx, ".moderation.unmute", duration, user=user.id, reason="Tempmute"
        )

