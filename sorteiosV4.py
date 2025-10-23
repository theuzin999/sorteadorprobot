from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import random
import threading

TOKEN = "8279020962:AAEM2KJiNXLYcskJnJOeL1U-udBTnqV7aY4"

# ✅ THREAD-SAFE: Lock para concorrência
lock = threading.Lock()

# Variáveis globais
sorteio_ativo = False
num_vencedores = 1
participantes = []
mensagem_id = None
chat_id_global = None
vencedores_texto = ""
mostrando_todos = False  # Controla estado toggle

# ✅ FUNÇÃO PARA CRIAR LINK CLICÁVEL DO PERFIL
def criar_link_usuario(user):
    """Cria link clicável para perfil do usuário"""
    if user.username:
        return f'<a href="tg://user?id={user.id}">@{user.username}</a>'
    else:
        nome = f"{user.first_name}"
        if user.last_name:
            nome += f" {user.last_name}"
        return f'<a href="tg://user?id={user.id}">{nome}</a>'

# ✅ VERIFICA SE É ADMIN (RÁPIDO)
async def is_admin(chat, user_id):
    try:
        admins = await chat.get_administrators()
        return user_id in [admin.user.id for admin in admins]
    except:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Olá! Use /sorteio para iniciar um sorteio épico! 🚀")

async def sorteio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sorteio_ativo, participantes, mensagem_id, chat_id_global, num_vencedores
    chat = update.effective_chat
    user = update.effective_user

    if not await is_admin(chat, user.id):
        await update.message.reply_text("❌ Apenas administradores podem criar sorteios! ❌")
        return

    keyboard = [
        [InlineKeyboardButton("1", callback_data="num_1"),
         InlineKeyboardButton("10", callback_data="num_10"),
         InlineKeyboardButton("20", callback_data="num_20")],
        [InlineKeyboardButton("30", callback_data="num_30"),
         InlineKeyboardButton("50", callback_data="num_50")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚡ Quantos vencedores esse sorteio terá? ⚡", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sorteio_ativo, num_vencedores, participantes, mensagem_id, chat_id_global, lock, vencedores_texto, mostrando_todos
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    chat = query.message.chat
    eh_admin = await is_admin(chat, user.id)

    # Criar sorteio
    if data.startswith("num_") and eh_admin:
        with lock:
            num_vencedores = int(data.split("_")[1])
            sorteio_ativo = True
            participantes = []
            chat_id_global = chat.id
            mostrando_todos = False

        keyboard = [
            [InlineKeyboardButton("🎟️ Entrar no Sorteio!", callback_data="participar")],
            [InlineKeyboardButton("🛑 Cancelar Sorteio", callback_data="cancelar"),
             InlineKeyboardButton("🎲 Realizar Sorteio", callback_data="sortear")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        mensagem = await query.edit_message_text(
            f"🔥 Sorteio Iniciado para {num_vencedores} Vencedor(es)! 🔥\n\n👥 Participantes:\n<i>Nenhum ainda</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        mensagem_id = mensagem.message_id

    # Participar
    elif data == "participar":
        if not sorteio_ativo:
            await query.answer("🚫 Nenhum sorteio ativo no momento!")
            return
        
        with lock:
            if user.id not in [p.id for p in participantes]:
                participantes.append(user)
                await query.answer("✅ Você foi adicionado ao sorteio com sucesso!")
                
                # ✅ CONSTRÓI LISTA COM LINKS CLICÁVEIS
                texto = f"🔥 Sorteio Iniciado para {num_vencedores} Vencedor(es)! 🔥\n\n👥 Participantes:\n"
                for p in participantes:
                    texto += f"• {criar_link_usuario(p)}\n"
                
                await context.bot.edit_message_text(
                    chat_id=chat_id_global,
                    message_id=mensagem_id,
                    text=texto,
                    reply_markup=query.message.reply_markup,
                    parse_mode='HTML'
                )
            else:
                await query.answer("❗ Você já está participando do sorteio!")

    # Sortear
    elif data == "sortear" and eh_admin:
        with lock:
            if not sorteio_ativo or not participantes:
                await query.answer("🚫 Nenhum sorteio ativo ou sem participantes suficientes!")
                return
            random.shuffle(participantes)
            vencedores = random.sample(participantes, min(num_vencedores, len(participantes)))

        # ✅ VENCEDORES COM LINKS CLICÁVEIS
        vencedores_texto = "🏆 <b>SORTEIO FINALIZADO COM SUCESSO!</b> 🏆\n\n👑 <b>VENCEDORES:</b>\n"
        for i, vencedor in enumerate(vencedores, start=1):
            link = criar_link_usuario(vencedor)
            vencedores_texto += f"{i}️⃣ {link}\n"

        # ✅ BOTÃO VISÍVEL PARA TODOS, MAS SÓ ADMIN PODE USAR
        keyboard = [[InlineKeyboardButton("📋 Mostrar Todos Participantes", callback_data="mostrar_todos")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.edit_message_text(
            chat_id=chat_id_global,
            message_id=mensagem_id,
            text=vencedores_texto,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        with lock:
            sorteio_ativo = False
            mostrando_todos = False

    # Cancelar
    elif data == "cancelar" and eh_admin:
        with lock:
            sorteio_ativo = False
            participantes.clear()
            mostrando_todos = False
            if mensagem_id and chat_id_global:
                await context.bot.edit_message_text(
                    chat_id=chat_id_global,
                    message_id=mensagem_id,
                    text="❌ <b>Sorteio Cancelado pelo Administrador!</b> ❌",
                    parse_mode='HTML'
                )
            mensagem_id = None
            chat_id_global = None
        await query.answer("Sorteio cancelado com sucesso. 🔒")

    # Mostrar todos participantes (APENAS ADMIN PODE CLICAR)
    elif data == "mostrar_todos":
        if not eh_admin:
            await query.answer("🔒 Apenas administradores podem ver a lista completa!", show_alert=True)
            return
        
        # ✅ LISTA COMPLETA COM LINKS CLICÁVEIS
        texto_part = f"\n\n📜 <b>LISTA COMPLETA DE PARTICIPANTES ({len(participantes)}):</b>\n"
        for p in participantes:
            texto_part += f"• {criar_link_usuario(p)}\n"
        
        texto = vencedores_texto + texto_part
        keyboard = [[InlineKeyboardButton("🔙 Ocultar Participantes", callback_data="ocultar_todos")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=texto, 
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        mostrando_todos = True

    # Ocultar participantes (APENAS ADMIN PODE CLICAR)
    elif data == "ocultar_todos":
        if not eh_admin:
            await query.answer("🔒 Apenas administradores podem ocultar a lista!", show_alert=True)
            return
        
        keyboard = [[InlineKeyboardButton("📋 Mostrar Todos Participantes", callback_data="mostrar_todos")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=vencedores_texto, 
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        mostrando_todos = False

# Configuração do bot
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("sorteio", sorteio))
app.add_handler(CallbackQueryHandler(button))

print("🚀 Bot rodando ULTRA RÁPIDO - BOTÃO VISÍVEL PARA TODOS, SÓ ADMIN USA! 🚀")
app.run_polling(
    poll_interval=0.1,
    timeout=5,
    drop_pending_updates=True
)