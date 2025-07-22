# handlers/callbacks.py
import logging
from aiogram import Router, F, types, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold

from db.requests import get_chat_settings, update_chat_setting
from states import Settings

router = Router()

async def get_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    settings = await get_chat_settings(chat_id)
    antilink_status = "✅ Включена" if settings.get('antilink_enabled', False) else "❌ Выключена"
    captcha_status = "✅ Включена" if settings.get('captcha_enabled', False) else "❌ Выключена"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"Защита от ссылок: {antilink_status}", callback_data="toggle_antilink"),
        InlineKeyboardButton(text="Изменить лимит варнов", callback_data="change_warn_limit")
    )
    # Добавляем новую кнопку
    builder.row(
        InlineKeyboardButton(text=f"CAPTCHA для новичков: {captcha_status}", callback_data="toggle_captcha")
    )
    return builder.as_markup()


@router.callback_query(F.data == "toggle_antilink")
async def callback_toggle_antilink(callback: types.CallbackQuery, bot: Bot):
    member = await bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return await callback.answer("Это действие доступно только администраторам.", show_alert=True)

    chat_id = callback.message.chat.id
    settings = await get_chat_settings(chat_id)
    new_status = not settings.get('antilink_enabled', False)
    
    await update_chat_setting(chat_id, 'antilink_enabled', new_status)
    
    new_keyboard = await get_settings_keyboard(chat_id)
    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    await callback.answer()

@router.callback_query(F.data == "toggle_captcha")
async def callback_toggle_captcha(callback: types.CallbackQuery, bot: Bot):
    member = await bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return await callback.answer("Это действие доступно только администраторам.", show_alert=True)

    chat_id = callback.message.chat.id
    settings = await get_chat_settings(chat_id)
    new_status = not settings.get('captcha_enabled', False)
    
    await update_chat_setting(chat_id, 'captcha_enabled', new_status)
    
    new_keyboard = await get_settings_keyboard(chat_id)
    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    await callback.answer()

@router.callback_query(F.data == "change_warn_limit")
async def callback_change_warn_limit(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    member = await bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return await callback.answer("Это действие доступно только администраторам.", show_alert=True)

    await callback.message.edit_text("Пожалуйста, отправьте новое число для лимита предупреждений (например, 3).")
    await state.set_state(Settings.waiting_for_warn_limit)
    await callback.answer()

@router.message(Settings.waiting_for_warn_limit)
async def process_new_warn_limit(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 1:
        return await message.reply("Пожалуйста, введите целое число больше 0.")
    
    limit = int(message.text)
    await update_chat_setting(message.chat.id, 'warn_limit', limit)
    await message.answer(f"✅ Лимит предупреждений успешно изменен на {hbold(limit)}.", parse_mode="HTML")
    await state.clear()
    
    # Показываем обновленное меню настроек
    keyboard = await get_settings_keyboard(message.chat.id)
    await message.answer("⚙️ <b>Настройки чата</b>", parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data.startswith("verify_"))
async def callback_verify_user(callback: types.CallbackQuery, bot: Bot):
    # Извлекаем ID пользователя из callback_data (verify_123456)
    user_id_to_verify = int(callback.data.split("_")[1])
    
    # Проверяем, что кнопку нажал именно тот пользователь, для которого она предназначена
    if callback.from_user.id != user_id_to_verify:
        return await callback.answer("Это кнопка не для вас!", show_alert=True)
        
    try:
        # Возвращаем пользователю полные права
        await bot.restrict_chat_member(
            chat_id=callback.message.chat.id,
            user_id=user_id_to_verify,
            permissions=types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        # Удаляем сообщение с капчей
        await callback.message.delete()
    except Exception as e:
        # Если что-то пошло не так, сообщаем пользователю
        await callback.answer("Произошла ошибка. Пожалуйста, попросите администратора выдать вам права вручную.", show_alert=True)
        logging.error(f"Ошибка при верификации: {e}")
