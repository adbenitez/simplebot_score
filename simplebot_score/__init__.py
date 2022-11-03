"""hooks, filters and commands definitions."""

import os

import simplebot
from deltachat import Message
from simplebot import DeltaBot
from simplebot.bot import Replies
from sqlalchemy import func

from .orm import User, init, session_scope


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    _getdefault(bot, "score_badge", "🎖️")


@simplebot.hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    path = os.path.join(path, "sqlite.db")
    init(f"sqlite:///{path}")


@simplebot.filter
def filter_messages(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Detect messages like +1 or -1 to increase/decrease score."""
    if message.quote:
        receiver_addr = message.quote.get_sender_contact().addr
        score = _parse(message.text)
    else:
        args = message.text.split(maxsplit=2)
        if len(args) == 2 and "@" in args[0]:
            receiver_addr = args[0]
            score = _parse(args[1])
        else:
            score = 0
    if not score:
        return
    sender_addr = message.get_sender_contact().addr
    is_admin = bot.is_admin(sender_addr)
    if not is_admin and (score < 0 or sender_addr == receiver_addr):
        return

    with session_scope() as session:
        sender = session.query(User).filter_by(addr=sender_addr).first()
        if not sender:
            sender = User(addr=sender_addr)
            session.add(sender)
        if not is_admin and sender.score - score < 0:
            replies.add(text="❌ You can't give what you don't have...", quote=message)
            return

        if not is_admin:
            sender.score -= score
        sender_score = sender.score

        receiver = session.query(User).filter_by(addr=receiver_addr).first()
        if not receiver:
            receiver = User(addr=receiver_addr)
            session.add(receiver)

        receiver.score += score
        receiver_score = receiver.score

    if is_admin:
        text = "{0}: {1}{4}"
    else:
        text = "{0}: {1}{4}\n{2}: {3}{4}"
    text = text.format(
        bot.get_contact(receiver_addr).name,
        receiver_score,
        bot.get_contact(sender_addr).name,
        sender_score,
        _getdefault(bot, "score_badge"),
    )
    replies.add(text=text, quote=message)


@simplebot.command(name="/score")
def score_cmd(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Get score of given address or your current score if no address is given.

    Example: `/score`
    """
    if payload:
        addr = payload
    else:
        addr = message.get_sender_contact().addr
    with session_scope() as session:
        user = session.query(User).filter_by(addr=addr).first()
        score = user.score if user else 0
        total_score = (
            session.query(func.sum(User.score)).filter(User.score > 0).scalar()
        )
    name = bot.get_contact(addr).name
    badge = _getdefault(bot, "score_badge")
    replies.add(text=f"{name}: {score}/{total_score}{badge}")


def _getdefault(bot: DeltaBot, key: str, value: str = None) -> str:
    val = bot.get(key, scope=__name__)
    if val is None and value is not None:
        bot.set(key, value, scope=__name__)
        val = value
    return val


def _parse(score: str) -> int:
    if not score.startswith(("-", "+")):
        return 0
    try:
        return int(score)
    except ValueError:
        return 0
