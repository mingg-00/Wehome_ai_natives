from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    import discord
    from discord import app_commands
    from discord.ext import commands
except ImportError as exc:  # pragma: no cover - import guard for missing dependency
    raise SystemExit("discord.py is required. Install dependencies with `pip install -r requirements.txt`.") from exc

try:
    from discord_notifier import build_report_message
    from ingest import infer_platform_from_url, prepare_records
    from instagram_client import (
        InstagramAPIError,
        InstagramConfig,
        fetch_instagram_metrics_for_account,
        fetch_instagram_metrics_from_url,
    )
    from youtube_client import (
        YouTubeAPIError,
        YouTubeConfig,
        fetch_youtube_metrics_for_account,
        fetch_youtube_metrics_from_url,
    )
    from main import build_report, load_dotenv_file
except ImportError:  # pragma: no cover - keeps script and package execution both working
    from src.discord_notifier import build_report_message
    from src.ingest import infer_platform_from_url, prepare_records
    from src.instagram_client import (
        InstagramAPIError,
        InstagramConfig,
        fetch_instagram_metrics_for_account,
        fetch_instagram_metrics_from_url,
    )
    from src.youtube_client import (
        YouTubeAPIError,
        YouTubeConfig,
        fetch_youtube_metrics_for_account,
        fetch_youtube_metrics_from_url,
    )
    from src.main import build_report, load_dotenv_file


logger = logging.getLogger("wehome.analytics_bot")

DEFAULT_ACCOUNT_LIMIT = 30
MAX_ACCOUNT_LIMIT = 100


@dataclass(frozen=True)
class BotServices:
    fetch_account_metrics: Callable[[InstagramConfig, Optional[int]], List[Dict[str, Any]]] = (
        fetch_instagram_metrics_for_account
    )
    fetch_video_metrics: Callable[[str, InstagramConfig], Dict[str, Any]] = fetch_instagram_metrics_from_url


def build_instagram_config() -> InstagramConfig:
    access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
    ig_user_id = os.getenv("META_INSTAGRAM_ACCOUNT_ID", "").strip()
    graph_api_version = os.getenv("META_GRAPH_API_VERSION", "v21.0").strip() or "v21.0"

    if not access_token:
        raise ValueError("META_ACCESS_TOKEN is required for Instagram API access.")
    if not ig_user_id:
        raise ValueError("META_INSTAGRAM_ACCOUNT_ID is required for Instagram API access.")

    return InstagramConfig(
        access_token=access_token,
        ig_user_id=ig_user_id,
        graph_api_version=graph_api_version,
    )


def build_youtube_config() -> YouTubeConfig:
    access_token = os.getenv("YOUTUBE_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()

    if not access_token and not (client_id and client_secret and refresh_token):
        raise ValueError(
            "YouTube credentials are required. Set YOUTUBE_ACCESS_TOKEN or GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
        )

    return YouTubeConfig(
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )


def _json_file(filename: str, payload: Dict[str, Any] | List[Dict[str, Any]]) -> discord.File:
    buffer = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    buffer.seek(0)
    return discord.File(buffer, filename=filename)


def _strip_angle_brackets(text: str) -> str:
    return text.strip().strip("<>").strip()


def _parse_account_limit(text: str) -> int:
    cleaned = text.strip()
    if not cleaned:
        return DEFAULT_ACCOUNT_LIMIT

    try:
        limit = int(cleaned)
    except ValueError as exc:
        raise ValueError("Account limit must be a whole number.") from exc

    if limit < 1:
        raise ValueError("Account limit must be at least 1.")
    if limit > MAX_ACCOUNT_LIMIT:
        raise ValueError(f"Account limit cannot exceed {MAX_ACCOUNT_LIMIT}.")
    return limit


def _format_help_text() -> str:
    return (
        "Usage:\n"
        f"- `/report account [limit]` evaluates the most recent {DEFAULT_ACCOUNT_LIMIT} SNS media items by default.\n"
        f"- `/report youtube [limit]` evaluates the most recent {DEFAULT_ACCOUNT_LIMIT} YouTube videos from the connected account.\n"
        f"- `/report video <url>` evaluates one SNS video URL.\n"
        f"- `!report account [limit]` and `!report video <url>` still work as prefix fallbacks.\n"
        f"- `!report youtube [limit]` evaluates the connected YouTube account.\n"
        f"- `/help` or `!help` shows this help text.\n"
        f"Account limit range: 1-{MAX_ACCOUNT_LIMIT}."
    )


def _get_sync_guild() -> Optional[discord.Object]:
    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    if not guild_id_raw:
        return None

    try:
        guild_id = int(guild_id_raw)
    except ValueError as exc:
        raise ValueError("DISCORD_GUILD_ID must be a numeric Discord server ID.") from exc

    return discord.Object(id=guild_id)


def _format_instagram_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()

    if "could not find a matching instagram media item" in lower:
        return (
            "No matching Instagram media was found in the authorized account. "
            "Check that the URL belongs to the connected account and that the post is accessible."
        )
    if "invalid oauth access token" in lower or ("oauth" in lower and "token" in lower):
        return "Instagram access token is invalid or expired. Refresh META_ACCESS_TOKEN and try again."
    if "permission" in lower or "permissions" in lower:
        return "Instagram API permission is missing for this account or media."
    if "network error" in lower:
        return f"Instagram API network error: {message}"
    return message


def _format_youtube_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()

    if "could not find the authenticated youtube channel" in lower:
        return "Could not read the authenticated YouTube channel. Check OAuth scopes and channel access."
    if "youtube access token is missing" in lower:
        return "YouTube access token is missing. Set YOUTUBE_ACCESS_TOKEN or refresh-token credentials."
    if "oauth" in lower and "token" in lower:
        return "YouTube OAuth token refresh failed. Check GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
    if "permission" in lower or "forbidden" in lower:
        return "YouTube API permission is missing for this account or video."
    if "network error" in lower:
        return f"YouTube API network error: {message}"
    return message


def _build_report_bundle(raw_records: List[Dict[str, Any]], source_dataset: str) -> tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any], List[str]]:
    records, warnings = prepare_records(raw_records, strict=False)
    bundle = build_report(records, source_dataset=source_dataset)
    report = bundle["report"]
    feedback = bundle["feedback"]
    kpi_summary = bundle["kpi_summary"]
    return report, feedback, kpi_summary, warnings


async def _send_report(
    ctx: commands.Context,
    report_kind: str,
    raw_records: List[Dict[str, Any]],
    source_dataset: str,
) -> None:
    if not raw_records:
        raise ValueError("No media records were returned for the requested range.")

    report, feedback, kpi_summary, warnings = _build_report_bundle(raw_records, source_dataset)
    message_lines = [f"{report_kind} report ready.", build_report_message(report, feedback)]

    if warnings:
        preview = "; ".join(warnings[:3])
        suffix = "..." if len(warnings) > 3 else ""
        message_lines.append(f"Validation warnings ({len(warnings)}): {preview}{suffix}")

    files = [
        _json_file("analytics_report.json", report),
        _json_file("feedback_to_video_agent.json", feedback),
        _json_file("kpi_summary.json", kpi_summary),
    ]

    await ctx.send("\n".join(message_lines), files=files)


async def _send_report_interaction(
    interaction: discord.Interaction,
    report_kind: str,
    raw_records: List[Dict[str, Any]],
    source_dataset: str,
) -> None:
    if not raw_records:
        raise ValueError("No media records were returned for the requested range.")

    report, feedback, kpi_summary, warnings = _build_report_bundle(raw_records, source_dataset)
    message_lines = [f"{report_kind} report ready.", build_report_message(report, feedback)]

    if warnings:
        preview = "; ".join(warnings[:3])
        suffix = "..." if len(warnings) > 3 else ""
        message_lines.append(f"Validation warnings ({len(warnings)}): {preview}{suffix}")

    files = [
        _json_file("analytics_report.json", report),
        _json_file("feedback_to_video_agent.json", feedback),
        _json_file("kpi_summary.json", kpi_summary),
    ]

    payload = "\n".join(message_lines)
    if interaction.response.is_done():
        await interaction.followup.send(payload, files=files)
    else:
        await interaction.response.send_message(payload, files=files)


async def _evaluate_account(
    ctx: commands.Context,
    services: BotServices,
    account_limit: int,
) -> None:
    try:
        config = build_instagram_config()
    except ValueError as exc:
        await ctx.send(f"Configuration error: {exc}")
        return

    try:
        async with ctx.typing():
            raw_records = await asyncio.to_thread(
                services.fetch_account_metrics,
                config,
                max_items=account_limit,
            )
        await _send_report(
            ctx,
            "SNS account",
            raw_records,
            f"SNS account (most recent {account_limit} media items)",
        )
    except InstagramAPIError as exc:
        await ctx.send(f"Instagram account evaluation failed: {_format_instagram_error(exc)}")
    except ValueError as exc:
        await ctx.send(f"Instagram account evaluation failed: {exc}")


async def _evaluate_youtube_account(
    ctx: commands.Context,
    account_limit: int,
) -> None:
    try:
        config = build_youtube_config()
    except ValueError as exc:
        await ctx.send(f"Configuration error: {exc}")
        return

    try:
        async with ctx.typing():
            raw_records = await asyncio.to_thread(
                fetch_youtube_metrics_for_account,
                config,
                None,
                account_limit,
            )
        await _send_report(
            ctx,
            "YouTube account",
            raw_records,
            f"YouTube account (most recent {account_limit} media items)",
        )
    except YouTubeAPIError as exc:
        await ctx.send(f"YouTube account evaluation failed: {_format_youtube_error(exc)}")
    except ValueError as exc:
        await ctx.send(f"YouTube account evaluation failed: {exc}")


async def _evaluate_video(
    ctx: commands.Context,
    services: BotServices,
    url: str,
) -> None:
    cleaned_url = _strip_angle_brackets(url)
    if not cleaned_url:
        await ctx.send("Usage: `!report video <url>`")
        return

    try:
        config = build_instagram_config()
    except ValueError as exc:
        await ctx.send(f"Configuration error: {exc}")
        return

    try:
        async with ctx.typing():
            record = await asyncio.to_thread(services.fetch_video_metrics, cleaned_url, config)
        await _send_report(ctx, "SNS video", [record], cleaned_url)
    except InstagramAPIError as exc:
        await ctx.send(f"Instagram video evaluation failed: {_format_instagram_error(exc)}")
    except ValueError as exc:
        await ctx.send(f"Instagram video evaluation failed: {exc}")


async def _evaluate_youtube_video(
    ctx: commands.Context,
    url: str,
) -> None:
    cleaned_url = _strip_angle_brackets(url)
    if not cleaned_url:
        await ctx.send("Usage: `!report video <url>`")
        return

    try:
        config = build_youtube_config()
    except ValueError as exc:
        await ctx.send(f"Configuration error: {exc}")
        return

    try:
        async with ctx.typing():
            record = await asyncio.to_thread(fetch_youtube_metrics_from_url, cleaned_url, config)
        await _send_report(ctx, "YouTube video", [record], cleaned_url)
    except YouTubeAPIError as exc:
        await ctx.send(f"YouTube video evaluation failed: {_format_youtube_error(exc)}")
    except ValueError as exc:
        await ctx.send(f"YouTube video evaluation failed: {exc}")


async def _evaluate_account_interaction(
    interaction: discord.Interaction,
    services: BotServices,
    account_limit: int,
) -> None:
    try:
        config = build_instagram_config()
    except ValueError as exc:
        await interaction.response.send_message(f"Configuration error: {exc}", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
        raw_records = await asyncio.to_thread(
            services.fetch_account_metrics,
            config,
            max_items=account_limit,
        )
        await _send_report_interaction(
            interaction,
            "Instagram account",
            raw_records,
            f"Instagram account (most recent {account_limit} media items)",
        )
    except InstagramAPIError as exc:
        await interaction.followup.send(f"Instagram account evaluation failed: {_format_instagram_error(exc)}", ephemeral=True)
    except ValueError as exc:
        await interaction.followup.send(f"Instagram account evaluation failed: {exc}", ephemeral=True)


async def _evaluate_youtube_account_interaction(
    interaction: discord.Interaction,
    account_limit: int,
) -> None:
    try:
        config = build_youtube_config()
    except ValueError as exc:
        await interaction.response.send_message(f"Configuration error: {exc}", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
        raw_records = await asyncio.to_thread(
            fetch_youtube_metrics_for_account,
            config,
            None,
            account_limit,
        )
        await _send_report_interaction(
            interaction,
            "YouTube account",
            raw_records,
            f"YouTube account (most recent {account_limit} media items)",
        )
    except YouTubeAPIError as exc:
        await interaction.followup.send(f"YouTube account evaluation failed: {_format_youtube_error(exc)}", ephemeral=True)
    except ValueError as exc:
        await interaction.followup.send(f"YouTube account evaluation failed: {exc}", ephemeral=True)


async def _evaluate_video_interaction(
    interaction: discord.Interaction,
    services: BotServices,
    url: str,
) -> None:
    cleaned_url = _strip_angle_brackets(url)
    if not cleaned_url:
        await interaction.response.send_message("Usage: `/report video <url>`", ephemeral=True)
        return

    try:
        config = build_instagram_config()
    except ValueError as exc:
        await interaction.response.send_message(f"Configuration error: {exc}", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
        record = await asyncio.to_thread(services.fetch_video_metrics, cleaned_url, config)
        await _send_report_interaction(interaction, "SNS video", [record], cleaned_url)
    except InstagramAPIError as exc:
        await interaction.followup.send(f"Instagram video evaluation failed: {_format_instagram_error(exc)}", ephemeral=True)
    except ValueError as exc:
        await interaction.followup.send(f"Instagram video evaluation failed: {exc}", ephemeral=True)


async def _evaluate_youtube_video_interaction(
    interaction: discord.Interaction,
    url: str,
) -> None:
    cleaned_url = _strip_angle_brackets(url)
    if not cleaned_url:
        await interaction.response.send_message("Usage: `/report video <url>`", ephemeral=True)
        return

    try:
        config = build_youtube_config()
    except ValueError as exc:
        await interaction.response.send_message(f"Configuration error: {exc}", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
        record = await asyncio.to_thread(fetch_youtube_metrics_from_url, cleaned_url, config)
        await _send_report_interaction(interaction, "YouTube video", [record], cleaned_url)
    except YouTubeAPIError as exc:
        await interaction.followup.send(f"YouTube video evaluation failed: {_format_youtube_error(exc)}", ephemeral=True)
    except ValueError as exc:
        await interaction.followup.send(f"YouTube video evaluation failed: {exc}", ephemeral=True)


def create_bot(services: BotServices | None = None) -> commands.Bot:
    services = services or BotServices()
    prefix = os.getenv("DISCORD_BOT_PREFIX", "!").strip() or "!"
    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix=prefix, intents=intents, help_command=None)
    report_group = app_commands.Group(name="report", description="Generate SNS analytics reports.")
    sync_guild = _get_sync_guild()

    @bot.event
    async def on_ready() -> None:
        logger.info("Logged in as %s", bot.user)
        if not getattr(bot, "_tree_synced", False):
            if sync_guild is not None:
                bot.tree.copy_global_to(guild=sync_guild)
                synced_commands = await bot.tree.sync(guild=sync_guild)
                logger.info("Synced %d application commands to guild %s.", len(synced_commands), sync_guild.id)
            else:
                synced_commands = await bot.tree.sync()
                logger.info("Synced %d global application commands.", len(synced_commands))
            bot._tree_synced = True  # type: ignore[attr-defined]

    @bot.command(name="help")
    async def help_command(ctx: commands.Context) -> None:
        await ctx.send(_format_help_text())

    @bot.command(name="report")
    async def report_command(ctx: commands.Context, scope: str = "", *, target: str = "") -> None:
        normalized_scope = scope.strip().lower()
        cleaned_target = target.strip()

        if normalized_scope in {"", "help", "?"}:
            await ctx.send(_format_help_text())
            return

        if normalized_scope in {"account", "all"}:
            try:
                limit = _parse_account_limit(cleaned_target)
            except ValueError as exc:
                await ctx.send(f"Invalid account limit: {exc}")
                return
            await _evaluate_account(ctx, services, limit)
            return

        if normalized_scope in {"youtube", "yt"}:
            try:
                limit = _parse_account_limit(cleaned_target)
            except ValueError as exc:
                await ctx.send(f"Invalid account limit: {exc}")
                return
            await _evaluate_youtube_account(ctx, limit)
            return

        if normalized_scope in {"video", "url", "one"}:
            platform = infer_platform_from_url(cleaned_target)
            if platform == "YouTube":
                await _evaluate_youtube_video(ctx, cleaned_target)
            else:
                await _evaluate_video(ctx, services, cleaned_target)
            return

        await ctx.send(_format_help_text())

    @report_group.command(name="account", description="Evaluate recent SNS media for the connected account.")
    async def report_account(interaction: discord.Interaction, limit: app_commands.Range[int, 1, MAX_ACCOUNT_LIMIT] = DEFAULT_ACCOUNT_LIMIT) -> None:
        await _evaluate_account_interaction(interaction, services, int(limit))

    @report_group.command(name="youtube", description="Evaluate the connected YouTube account.")
    async def report_youtube(interaction: discord.Interaction, limit: app_commands.Range[int, 1, MAX_ACCOUNT_LIMIT] = DEFAULT_ACCOUNT_LIMIT) -> None:
        await _evaluate_youtube_account_interaction(interaction, int(limit))

    @report_group.command(name="video", description="Evaluate one SNS video URL.")
    async def report_video(interaction: discord.Interaction, url: str) -> None:
        platform = infer_platform_from_url(url)
        if platform == "YouTube":
            await _evaluate_youtube_video_interaction(interaction, url)
        else:
            await _evaluate_video_interaction(interaction, services, url)

    @bot.tree.command(name="help", description="Show available report commands.")
    async def slash_help(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(_format_help_text(), ephemeral=True)

    bot.tree.add_command(report_group)

    return bot


def main() -> None:
    load_dotenv_file()
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is required. Set it in .env or export it in the shell.")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    bot = create_bot()
    bot.run(token)


if __name__ == "__main__":
    main()
