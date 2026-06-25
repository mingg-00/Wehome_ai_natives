from __future__ import annotations

import asyncio
from typing import Any

import discord
from discord import app_commands

from config.settings import load_settings
from orchestrator.main import run_campaign, submit_job
from shared.json_utils import read_json, utc_now_iso, write_json


def _build_embed(summary: dict[str, Any]) -> discord.Embed:
    status = summary.get("status", "unknown")
    embed = discord.Embed(
        title="Campaign Completed",
        description=f"Status: `{status}`",
        color=discord.Color.green() if status == "success" else discord.Color.orange(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Campaign ID", value=str(summary.get("campaign_id", "n/a")), inline=False)
    embed.add_field(name="Contract Version", value=str(summary.get("contract_version", "n/a")), inline=True)
    embed.add_field(name="Requested By", value=str(summary.get("requested_by", "n/a")), inline=True)

    results = summary.get("results", {})
    for stage_name in ("video", "sns", "analytics"):
        stage = results.get(stage_name, {})
        ok = stage.get("ok", False)
        runner = stage.get("runner", "unknown")
        embed.add_field(
            name=stage_name.title(),
            value=f"ok={ok}\nrunner={runner}",
            inline=True,
        )

    embed.set_footer(text="wehome-integration")
    return embed


def _build_progress_message(event: dict[str, Any]) -> str:
    stage = event.get("stage", "campaign")
    state = event.get("state", "running")
    message = event.get("message", "")
    return f"[{stage}] {state}: {message}".strip()


class CampaignBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.settings = load_settings()

    async def setup_hook(self) -> None:
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = CampaignBot()


@bot.tree.command(name="run_campaign", description="Run the full video -> SNS -> analytics pipeline.")
@app_commands.describe(notes="Optional campaign notes")
async def run_campaign_command(interaction: discord.Interaction, notes: str | None = None) -> None:
    settings = bot.settings
    await interaction.response.defer(thinking=True)

    job_id = f"campaign-{int(discord.utils.utcnow().timestamp())}"
    await interaction.followup.send(f"Starting campaign `{job_id}`.", ephemeral=False)

    loop = asyncio.get_running_loop()

    def progress(event: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(interaction.followup.send(_build_progress_message(event)), loop)

    request = {
        "campaign_id": job_id,
        "requested_by": getattr(interaction.user, "display_name", None),
        "notes": notes,
    }

    if settings.orchestrator_mode == "worker":
        job = submit_job(request, settings=settings)
        status_path = settings.runtime_dir / "status" / f"{job['job_id']}.json"
        result_path = settings.runtime_dir / "results" / f"{job['job_id']}.json"
        await interaction.followup.send("Job queued for orchestrator worker.")

        last_status: dict[str, Any] | None = None
        while True:
            if status_path.exists():
                current_status = read_json(status_path)
                if current_status != last_status:
                    last_status = current_status
                    await interaction.followup.send(_build_progress_message(current_status))
            if result_path.exists():
                summary = read_json(result_path)
                write_json(settings.data_dir / "summary.json", summary)
                await interaction.followup.send(embed=_build_embed(summary))
                return
            await asyncio.sleep(settings.job_poll_interval_seconds)

    summary = await asyncio.to_thread(run_campaign, request, settings=settings, progress_callback=progress)
    write_json(settings.data_dir / "summary.json", summary)
    await interaction.followup.send(embed=_build_embed(summary))


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} at {utc_now_iso()}")


def main() -> None:
    settings = bot.settings
    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN is required.")
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
