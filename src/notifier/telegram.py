"""Telegram video alert notification worker."""

import asyncio
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from loguru import logger
from telegram import Bot
from src.config import TelegramConfig

KST = ZoneInfo("Asia/Seoul")


class TelegramNotifier:
    """Sends video alerts and captions to Telegram."""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.is_active = bool(config.enabled and config.bot_token and config.chat_id)
        if not self.is_active:
            logger.info("Telegram notifier disabled or missing credentials (Dry-run mode).")

    async def send_video_async(self, video_path: Path, stay_duration_sec: float, start_time: float) -> bool:
        """Send video asynchronously with structured caption."""
        if not video_path.exists():
            logger.error(f"Video file not found for notification: {video_path}")
            return False

        time_str = datetime.datetime.fromtimestamp(start_time, tz=KST).strftime("%Y-%m-%d %H:%M:%S")
        caption = (
            f"[순심이 배변판 감지 알림]\n"
            f"일시: {time_str}\n"
            f"배변판 체류 시간: {stay_duration_sec:.1f}초\n"
            f"영상 파일: {video_path.name}"
        )

        if not self.is_active:
            logger.info(f"[Dry-Run Notification]\n{caption}\nVideo saved at: {video_path}")
            return True

        try:
            bot = Bot(token=self.config.bot_token)
            with open(video_path, "rb") as video_file:
                await bot.send_video(
                    chat_id=self.config.chat_id,
                    video=video_file,
                    caption=caption,
                    write_timeout=60,
                    read_timeout=60,
                )
            logger.info(f"Successfully sent video notification to Telegram chat {self.config.chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram video notification: {e}")
            return False

    def send_video(self, video_path: Path, stay_duration_sec: float, start_time: float) -> bool:
        """Synchronous wrapper for sending video."""
        try:
            return asyncio.run(self.send_video_async(video_path, stay_duration_sec, start_time))
        except Exception as e:
            logger.error(f"Error in send_video execution: {e}")
            return False
