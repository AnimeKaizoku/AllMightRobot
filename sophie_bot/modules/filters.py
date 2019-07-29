import re

from telethon.tl.custom import Button

from aiogram.types.inline_keyboard import InlineKeyboardMarkup, InlineKeyboardButton

from sophie_bot import decorator, mongodb, redis, WHITELISTED, tbot
from sophie_bot.modules.connections import connection
from sophie_bot.modules.disable import disablable_dec
from sophie_bot.modules.helper_func.flood import flood_limit_dec
from sophie_bot.modules.language import get_string, get_strings_dec
from sophie_bot.modules.notes import send_note, button_parser
from sophie_bot.modules.bans import ban_user, kick_user, convert_time
from sophie_bot.modules.users import user_admin_dec, user_link, get_chat_admins, user_link_html
from sophie_bot.modules.warns import randomString


@decorator.AioBotDo()
async def check_message(message, **kwargs):
    chat_id = message.chat.id
    filters = redis.lrange('filters_cache_{}'.format(chat_id), 0, -1)
    if not filters:
        update_handlers_cache(chat_id)
        filters = redis.lrange('filters_cache_{}'.format(chat_id), 0, -1)
    if redis.llen('filters_cache_{}'.format(chat_id)) == 0:
        return
    text = message.text
    user_id = message.from_user.id
    msg_id = message.message_id
    for keyword in filters:
        keyword = keyword.decode("utf-8")
        keyword = re.escape(keyword)
        keyword = keyword.replace('\(\+\)', '.*')
        pattern = r"( |^|[^\w])" + keyword + r"( |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            H = mongodb.filters.find_one({'chat_id': chat_id, "handler": {'$regex': str(pattern)}})
            action = H['action']
            print(H)
            if action == 'note':
                await send_note(chat_id, chat_id, msg_id, H['arg'], show_none=True)
            elif action == 'answer':
                txt, btns = button_parser(chat_id, H['arg'])
                await tbot.send_message(
                    chat_id,
                    txt,
                    buttons=btns,
                    reply_to=msg_id
                )
            elif action == 'delete':
                await message.delete()
            elif action == 'ban':
                if await ban_user(message, user_id, chat_id, None, no_msg=True) is True:
                    text = get_string('filters', 'filter_ban_success', chat_id).format(
                        user=await user_link_html(user_id),
                        filter=H['handler']
                    )
                    await message.reply(text)
            elif action == 'tban':
                timee, unit = await convert_time(message, H['arg'])
                if await ban_user(message, user_id, chat_id, timee, no_msg=True) is True:
                    text = get_string('filters', 'filter_tban_success', chat_id).format(
                        user=await user_link_html(user_id),
                        time=H['arg'],
                        filter=H['handler']
                    )
                    await message.reply(text)
            elif action == 'kick':
                if await kick_user(message, user_id, chat_id, no_msg=True) is True:
                    text = get_string('filters', 'filter_kick_success', chat_id).format(
                        user=await user_link_html(user_id),
                        filter=H['handler']
                    )
                    await message.reply(text)
            elif action == 'warn':
                user_id = message.from_user.id
                await warn_user_filter(message, H, user_id, chat_id)
            break


@decorator.t_command("filter(?!s)", arg=True)
@flood_limit_dec("filter")
@user_admin_dec
@connection(admin=True)
@get_strings_dec("filters")
async def add_filter(event, strings, status, chat_id, chat_title):
    args = event.message.raw_text.split(" ")
    if len(args) < 3:
        await event.reply(strings["wrong_action"])
        return

    handler = args[1]
    action = args[2]
    if len(args) > 3:
        arg = args[3]
    else:
        arg = None

    custom = None

    if args[1].startswith(("'", '"')):
        custom = True
        raw = args[1:]
        _handler = []
        for x in raw:
            if x.startswith(("'", '"')):
                _handler.append(x.replace('"', '').replace("'", ''))
            elif x.endswith(("'", '"')):
                _handler.append(x.replace('"', '').replace("'", ''))
                break
            else:
                _handler.append(x)

        handler = " ".join(_handler)
        action = raw[len(_handler)]
        _arg = len(_handler) + 1
        arg = raw[_arg:]

    text = strings["filter_added"]
    text += strings["filter_keyword"].format(handler)
    if action == 'note':
        if custom:
            if not arg:
                await event.reply(strings["no_arg_note"])
                return

            arg = arg[0]
            text += strings["a_send_note"].format(arg)
        elif not len(args) > 3:
            await event.reply(strings["no_arg_note"])
            return
            text += strings["a_send_note"].format(arg)
    elif action == 'tban':
        if custom:
            if not arg:
                await event.reply(strings["no_arg_tban"])
                return
            arg = arg[0]
            text += strings["a_tban"].format(arg)
        elif not len(args) > 3:
            await event.reply(strings["no_arg_tban"])
            return
            text += strings["a_tban"].format(str(arg))
    elif action == 'answer':
        if custom:
            if not arg:
                await event.reply(strings["wrong_action"])
                return
            arg = " ".join(arg)
            text += strings["a_answer"]
        else:
            txt = event.message.raw_text.split(" ")[3]
            if len(txt) <= 2:
                await event.reply(strings["wrong_action"])
                return
            arg = txt
            text += strings["a_answer"]
    elif action == 'delete':
        text += strings["a_del"]
    elif action == 'ban':
        text += strings["a_ban"]
    elif action == 'mute':
        text += strings["a_mute"]
    elif action == 'kick':
        text += strings["a_kick"]
    elif action == 'warn':
        if custom:
            if not arg:
                arg = f"Automatic action on filter:\n{handler.lower()}."
            else:
                arg = " ".join(arg)
            text += strings["a_warn"].format(arg)
        else:
            raw_text = event.text.split(" ")
            arg = None
            if raw_text[3:]:
                arg = " ".join(raw_text[3:])
            else:
                arg = f"Automatic action on filter:\n{handler.lower()}."
            text += strings["a_warn"].format(arg)
    else:
        await event.reply(strings["wrong_action"])
        return

    exist = mongodb.filters.find_one({
        'chat_id': chat_id,
        'handler': handler.lower()
    })

    if exist:
        mongodb.filters.update_one({
            'chat_id': chat_id,
            'handler': handler,
            '_id': exist["_id"]
        }, {
            "$set": {
                'action': action,
                'arg': arg
            }
        })

        update_handlers_cache(chat_id)
        await event.reply(text.replace('added', 'updated'))
    else:
        mongodb.filters.insert_one({
            "chat_id": chat_id,
            "handler": handler.lower(),
            "action": action,
            "arg": arg
        })
        update_handlers_cache(chat_id)
        await event.reply(text)


@decorator.t_command("filters", arg=True)
@disablable_dec("filters")
@flood_limit_dec("filters")
@connection()
async def list_filters(event, status, chat_id, chat_title):
    filters = mongodb.filters.find({'chat_id': chat_id})
    text = get_string("filters", "filters_in", event.chat_id).format(chat_name=chat_title)
    H = 0

    for filter in filters:
        H += 1
        if filter['arg']:
            text += "- {} ({} - `{}`)\n".format(
                filter['handler'], filter['action'], filter['arg'])
        else:
            text += "- {} ({})\n".format(filter['handler'], filter['action'])
    if H == 0:
        text = get_string("filters", "no_filters_in", event.chat_id).format(chat_title)
    await event.reply(text)


@decorator.t_command("stop", arg=True)
@user_admin_dec
@connection(admin=True)
async def stop_filter(event, status, chat_id, chat_title):
    handler = event.message.text.split(" ", 2)[1]
    filter = mongodb.filters.find_one({'chat_id': chat_id,
                                      "handler": {'$regex': str(handler)}})
    if not filter:
        await event.reply(get_string("filters", "cant_find_filter", event.chat_id))
        return
    mongodb.filters.delete_one({'_id': filter['_id']})
    update_handlers_cache(chat_id)
    text = str(get_string("filters", "filter_deleted", event.chat_id))
    text = text.format(filter=filter['handler'], chat_name=chat_title)
    await event.reply(text)


def update_handlers_cache(chat_id):
    filters = mongodb.filters.find({'chat_id': chat_id})
    redis.delete('filters_cache_{}'.format(chat_id))
    for filter in filters:
        redis.lpush('filters_cache_{}'.format(chat_id), filter['handler'])


async def warn_user_filter(message, H, user_id, chat_id):
    if user_id in WHITELISTED:
        return

    if user_id in await get_chat_admins(chat_id):
        return

    warn_limit = mongodb.warnlimit.find_one({'chat_id': chat_id})
    db_warns = mongodb.warns.find({
        'user_id': user_id,
        'group_id': chat_id
    })

    #  to avoid adding useless another warn in db
    current_warns = 1

    for _ in db_warns:
        current_warns += 1

    if not warn_limit:
        warn_limit = 3
    else:
        warn_limit = int(warn_limit['num'])

    if current_warns >= warn_limit:
        if await ban_user(message, user_id, chat_id, None) is False:
            print(f'cannot ban user {user_id}')
            return

        await ban_user(message, user_id, chat_id, None, no_msg=False)
        mongodb.warns.delete_many({
            'user_id': user_id,
            'group_id': chat_id
        })

        resp = get_string("filters", "filter_warn_ban", chat_id).format(
            warns=warn_limit,
            user=await user_link(user_id),
            reason=H['arg']
        )

        await message.reply(resp)
        return
    else:
        rndm = randomString(15)

        mongodb.warns.insert_one({
            'warn_id': rndm,
            'user_id': user_id,
            'group_id': chat_id,
            'reason': H['arg']
        })

        buttons = InlineKeyboardMarkup().add(InlineKeyboardButton(
            "⚠️ Remove warn", callback_data='remove_warn_{}'.format(rndm)
        ))
        rules = mongodb.rules.find_one({"chat_id": chat_id})

        if rules:
            buttons.append(Button.inline("📝 Rules", 'get_note_{}_{}'.format(
                chat_id, rules['note']
            )))

        chat_title = mongodb.chat_list.find_one({'chat_id': chat_id})['chat_title']

        txt = get_string("filters", "filter_warn_warned", chat_id).format(
            user=await user_link_html(user_id),
            chat=chat_title,
            current_warns=current_warns,
            max_warns=warn_limit,
            reason=H['arg']
        )
        await message.answer(txt, reply_markup=buttons)
        return
