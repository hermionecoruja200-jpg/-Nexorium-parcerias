import os
import json
import time
import random

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    InlineQueryHandler
)
from telegram.error import NetworkError, TimedOut, RetryAfter, BadRequest
from uuid import uuid4


# ================= CONFIGURAÇÕES =================

TOKEN = os.getenv("BOT_TOKEN")
SEU_ID = 1130170420
ARQUIVO_DADOS = "bot_ajuda.json"

OPCOES_TEMPO = {
    "10m": 10 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "2h": 2 * 60 * 60,
    "1d": 24 * 60 * 60,
    "desligado": 0
}

EXEMPLOS_GRUPOS = [
    "📚 Área 404: Leitores Encontrados",
    "💖📚 Romance in love 📚💖",
    "Plataforma 9¾ 🚂✨📖",
    "⚔️ A Casa do Pensamento ⚔️",
    "Ebook/PDF ✨🦋",
    "✨ Resenhas Encantadas ✨",
    "Livros Proibidos 📚",
    "Livros 0.1 📚",
    "🎧 Audiobooks 🎧",
    "🏛️ Sanctum das Sombras 🕯️🌹",
    "Vibe Literaria 📚🎀",
    "Books in Secret",
    "BIBLIOTECA VIRTUAL 🎀",
    "AKOЄM BOOKS 📚",
    "Sociedade dos Poetas Mortos",
    "Teia Literária",
    "🦋 ACESSO AO LER É VOAR 🦋",
    "Leitura à Deriva 📖",
    "Clube do Livro 📚",
    "☪ Página Secreta ☪",
    "🌀 SubFluxo 🌀"
]


# ================= DADOS =================

def dados_padrao():
    return {
        "donas": [SEU_ID],
        "supremos": [],
        "editores": [],
        "comuns": [],
        "globais": {},
        "pessoais": {},
        "etapas": {},
        "perfis_ids": {},
        "tempos_por_usuario": {}
    }


def gerar_codigo_fixo(dados):
    prefixos = ["nx", "lumos", "coruja", "livro", "magia", "nex"]
    existentes = set()

    # globais
    for lista in dados.get("globais", {}).values():
        codigo = lista.get("codigo_fixo")
        if codigo:
            existentes.add(codigo)

    # pessoais
    for usuario in dados.get("pessoais", {}).values():
        for lista in usuario.values():
            codigo = lista.get("codigo_fixo")
            if codigo:
                existentes.add(codigo)

    while True:
        codigo = random.choice(prefixos) + str(random.randint(1000, 9999))

        if codigo not in existentes:
            return codigo


def carregar_dados():
    if not os.path.exists(ARQUIVO_DADOS):
        dados = dados_padrao()
        salvar_dados(dados)
        return dados

    try:
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        dados = dados_padrao()
        salvar_dados(dados)
        return dados

    mudou = False
    padrao = dados_padrao()

    for chave, valor in padrao.items():
        if chave not in dados:
            dados[chave] = valor
            mudou = True

    # Compatibilidade com código anterior que tinha config global
    if "config" in dados:
        dados.pop("config", None)
        mudou = True

    if SEU_ID not in dados["donas"]:
        dados["donas"].append(SEU_ID)
        mudou = True

    for nome, lista in dados.get("globais", {}).items():
        if "codigo_fixo" not in lista:
            lista["codigo_fixo"] = gerar_codigo_fixo(dados)
            mudou = True

    if mudou:
        salvar_dados(dados)

    return dados


def salvar_dados(dados):
    tmp = ARQUIVO_DADOS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)
    os.replace(tmp, ARQUIVO_DADOS)


def limpar_nome(nome):
    return nome.lower().strip().replace(" ", "_")


def buscar_global_por_codigo(dados, codigo):
    codigo = codigo.strip().lower().replace("@", "")

    for nome, lista in dados.get("globais", {}).items():
        if str(lista.get("codigo_fixo", "")).lower() == codigo:
            return nome, lista

    return None, None

def buscar_pessoal_por_codigo(dados, user_id, codigo):
    codigo = codigo.strip().lower().replace("@", "")

    uid = str(user_id)

    pessoais = dados.get("pessoais", {}).get(uid, {})

    for nome, lista in pessoais.items():
        if str(lista.get("codigo_fixo", "")).lower() == codigo:
            return nome, lista

    return None, None

def tempo_usuario_parceria(dados, user_id, nome_parceria):
    uid = str(user_id) if user_id else "anonimo"
    nome = limpar_nome(nome_parceria)

    if uid not in dados.get("tempos_por_usuario", {}):
        return "desligado"

    return dados["tempos_por_usuario"][uid].get(nome, "desligado")


def segundos_tempo_usuario_parceria(dados, user_id, nome_parceria):
    chave = tempo_usuario_parceria(dados, user_id, nome_parceria)
    return OPCOES_TEMPO.get(chave, 0)


def salvar_tempo_usuario_parceria(dados, user_id, nome_parceria, tempo):
    uid = str(user_id)
    nome = limpar_nome(nome_parceria)

    dados.setdefault("tempos_por_usuario", {})
    dados["tempos_por_usuario"].setdefault(uid, {})
    dados["tempos_por_usuario"][uid][nome] = tempo


# ================= PERMISSÕES =================

def nivel_usuario(user_id, dados):
    if not user_id:
        return None
    if user_id in dados["donas"]:
        return "dona"
    if user_id in dados["supremos"]:
        return "supremo"
    if user_id in dados["editores"]:
        return "editor"
    if user_id in dados["comuns"]:
        return "comum"
    return None


def status_bonito(nivel):
    return {
        "dona": "dona",
        "supremo": "supremo",
        "editor": "editor",
        "comum": "comum"
    }.get(nivel, nivel or "sem nível")


def pode_criar_global(user_id, dados):
    return nivel_usuario(user_id, dados) in ["dona", "supremo"]


def pode_liberar_ids(user_id, dados):
    return nivel_usuario(user_id, dados) in ["dona", "supremo"]


def remover_id_de_todos(dados, user_id):
    for lista in ["supremos", "editores", "comuns"]:
        if user_id in dados[lista]:
            dados[lista].remove(user_id)


def eh_admin_anonimo(update):
    if not update.message:
        return False

    if update.effective_chat.type == "private":
        return False

    sender_chat = getattr(update.message, "sender_chat", None)
    if sender_chat and sender_chat.id == update.effective_chat.id:
        return True

    user = update.effective_user
    if user and user.id == 1087968824:
        return True

    return False


def usuario_admin_do_grupo(update, context):
    if update.effective_chat.type == "private":
        return False

    if eh_admin_anonimo(update):
        return True

    user = update.effective_user
    if not user:
        return False

    try:
        membro = context.bot.get_chat_member(update.effective_chat.id, user.id)
        return membro.status in ["administrator", "creator"]
    except Exception:
        return False


def pode_usar_global_no_grupo(update, context, dados):
    chat = update.effective_chat
    user = update.effective_user
    user_id = user.id if user else None

    nivel = nivel_usuario(user_id, dados)

    # Apenas dona, supremo e comum podem usar globais
    if nivel in ["dona", "supremo", "comum"]:
        return True

    # Editor NÃO pode usar globais
    if nivel == "editor":
        return False

    if chat.type == "private":
        return False

    if usuario_admin_do_grupo(update, context):
        return True

    return False


# ================= PERFIS IDS =================

def atualizar_perfil_id(context, dados, user_id, nivel):
    user_id = int(user_id)
    chave = str(user_id)

    nome = "Desconhecido"
    username = "Sem usuário"

    try:
        chat = context.bot.get_chat(user_id)
        nome = chat.first_name or "Desconhecido"
        if getattr(chat, "last_name", None):
            nome = f"{nome} {chat.last_name}"
        username = chat.username or "Sem usuário"
    except Exception:
        antigo = dados.get("perfis_ids", {}).get(chave, {})
        nome = antigo.get("nome", "Desconhecido")
        username = antigo.get("username", "Sem usuário")

    dados.setdefault("perfis_ids", {})
    dados["perfis_ids"][chave] = {
        "nome": nome,
        "id": user_id,
        "username": username,
        "status": status_bonito(nivel)
    }


def pegar_info_id(context, dados, user_id, nivel):
    user_id = int(user_id)
    chave = str(user_id)

    if chave not in dados.get("perfis_ids", {}):
        atualizar_perfil_id(context, dados, user_id, nivel)

    info = dados.get("perfis_ids", {}).get(chave, {})
    info["id"] = user_id
    info["status"] = status_bonito(nivel)
    return info


def formatar_info_id(info):
    nome = info.get("nome", "Desconhecido")
    uid = info.get("id", "Sem ID")
    username = info.get("username", "Sem usuário")
    status = info.get("status", "comum")

    if username and username != "Sem usuário":
        username = "@" + username.replace("@", "")

    return (
        f"👤 Nome: {nome}\n"
        f"🆔 ID: {uid}\n"
        f"🔗 Usuário: {username}\n"
        f"📌 Status: {status}"
    )


# ================= TECLADO =================

def teclado_menu(user_id):
    dados = carregar_dados()
    nivel = nivel_usuario(user_id, dados)

    if nivel == "comum":
        return ReplyKeyboardMarkup(
            [["🆔 Meu ID", "❓ Ajuda"]],
            resize_keyboard=True
        )

    if nivel == "editor":
        return ReplyKeyboardMarkup(
            [
                ["🔒 Criar parceria pessoal"],
                ["✏️ Editar parceria", "🗑 Apagar parceria"],
                ["🔒 Minhas parcerias"],
                ["🆔 Meu ID", "❓ Ajuda"]
            ],
            resize_keyboard=True
        )

    botoes = []

    botoes.append(["🌍 Criar parceria global"])
    botoes.append(["🔒 Criar parceria pessoal"])
    botoes.append(["✏️ Editar parceria", "🗑 Apagar parceria"])
    botoes.append(["🌍 Parcerias globais", "🔒 Minhas parcerias"])
    botoes.append(["📋 Ver comandos", "🔑 Códigos fixos"])
    botoes.append(["📚 Listas completas", "⏱ Tempo por parceria"])
    botoes.append(["🆔 Meu ID", "❓ Ajuda"])

    if nivel in ["dona", "supremo"]:
        botoes.append(["👥 IDs liberados"])
        botoes.append(["👥 Liberar ID", "🗑 Apagar ID"])

    return ReplyKeyboardMarkup(botoes, resize_keyboard=True)


def teclado_edicao():
    return ReplyKeyboardMarkup(
        [
            ["📝 Editar nome"],
            ["🖼 Editar imagem", "✏️ Editar frase"],
            ["🔗 Editar botões"],
            ["🔙 Cancelar"]
        ],
        resize_keyboard=True
    )


def teclado_editar_botoes():
    return ReplyKeyboardMarkup(
        [
            ["➕ Adicionar botão"],
            ["✏️ Editar link de botão"],
            ["🗑 Apagar botão"],
            ["🔙 Cancelar"]
        ],
        resize_keyboard=True
    )


def teclado_tempo():
    return ReplyKeyboardMarkup(
        [
            ["10m", "15m", "30m"],
            ["2h", "1d", "desligado"],
            ["🔙 Cancelar"]
        ],
        resize_keyboard=True
    )


def texto_menu_normalizado(texto):
    return (texto or "").replace("️", "").strip().lower()


def eh_botao_menu(texto):
    t = texto_menu_normalizado(texto)

    palavras = [
        "criar parceria global",
        "criar parceria pessoal",
        "editar parceria",
        "apagar parceria",
        "parcerias globais",
        "minhas parcerias",
        "ver comandos",
        "códigos fixos",
        "codigos fixos",
        "listas completas",
        "tempo por parceria",
        "meu id",
        "ajuda",
        "ids liberados",
        "liberar id",
        "apagar id",
        "cancelar"
    ]

    return any(p in t for p in palavras)



# ================= ENVIO SEGURO / APAGAR AUTOMÁTICO =================

def enviar_seguro(funcao, tentativas=2, espera=1, **kwargs):
    ultimo_erro = None

    for _ in range(tentativas):
        try:
            return funcao(**kwargs)
        except RetryAfter as erro:
            time.sleep(int(erro.retry_after) + 1)
            ultimo_erro = erro
        except (TimedOut, NetworkError) as erro:
            time.sleep(espera)
            ultimo_erro = erro
        except Exception as erro:
            ultimo_erro = erro
            break

    if ultimo_erro:
        print("Erro ao enviar:", ultimo_erro)

    return None


def apagar_mensagem_depois(context):
    job_data = context.job.context

    try:
        context.bot.delete_message(
            chat_id=job_data["chat_id"],
            message_id=job_data["message_id"]
        )
    except Exception as erro:
        print("Não consegui apagar lista agendada:", erro)


def agendar_apagar_lista(context, dados, mensagem, user_id, nome_parceria):
    if not mensagem:
        return

    segundos = segundos_tempo_usuario_parceria(dados, user_id, nome_parceria)

    if segundos <= 0:
        return

    try:
        context.job_queue.run_once(
            apagar_mensagem_depois,
            when=segundos,
            context={
                "chat_id": mensagem.chat_id,
                "message_id": mensagem.message_id
            }
        )
    except Exception as erro:
        print("Não consegui agendar apagar lista:", erro)


# ================= START / AJUDA =================

def start(update, context):
    if update.effective_chat.type != "private":
        return

    dados = carregar_dados()
    user_id = update.effective_user.id
    nivel = nivel_usuario(user_id, dados)

    if not nivel:
        update.message.reply_text(
            f"🔒 Este bot é fechado.\n\n"
            f"Seu ID é:\n{user_id}\n\n"
            "Envie esse ID para a dona liberar seu acesso."
        )
        return

    atualizar_perfil_id(context, dados, user_id, nivel)
    dados["etapas"].pop(str(user_id), None)
    salvar_dados(dados)

    if nivel == "comum":
        update.message.reply_text(
            "📚✨ Nexorium — Bot Ajuda\n\n"
            "Seu nível: comum\n\n"
            "Você pode usar SOMENTE parcerias globais no grupo:\n"
            "`/parceria nome_da_lista`\n"
            "`/parcerias nome_da_lista`",
            parse_mode="Markdown",
            reply_markup=teclado_menu(user_id)
        )
        return

    update.message.reply_text(
        f"📚✨ Nexorium — Bot Ajuda\n\n"
        f"Seu nível: {nivel}",
        reply_markup=teclado_menu(user_id)
    )


def ajuda(update, context):
    if update.effective_chat.type != "private":
        return

    dados = carregar_dados()
    nivel = nivel_usuario(update.effective_user.id, dados)

    if nivel == "comum":
        update.message.reply_text(
            "📚 Nexorium — Ajuda\n\n"
            "Seu acesso é comum.\n"
            "Você só pode usar parcerias globais no grupo:\n\n"
            "`/parceria nome_da_lista`\n"
            "`/parcerias nome_da_lista`",
            parse_mode="Markdown"
        )
        return

    update.message.reply_text(
        "📚 Nexorium — Ajuda\n\n"
        "🌍 Global: apenas dona e supremo podem criar/editar.\n"
        "🔒 Pessoal: dona, supremo e editor podem criar/editar.\n"
        "👤 Comum: só dispara parceria global no grupo.\n"
        "👤 Admin anônimo: só dispara parceria global no grupo.\n\n"
        "Formato dos botões:\n"
        "`Nome do botão | https://t.me/link`\n\n"
        "Comandos no grupo:\n"
        "`/parceria nome_da_lista`\n"
        "`/parcerias nome_da_lista`\n\n"
        "Código fixo global:\n"
        "`@Nexoriumbot lumos1234`\n\n"
        "Tempo por parceria:\n"
        "Cada ID escolhe o tempo de cada parceria global separadamente.",
        parse_mode="Markdown"
    )


def meu_id(update, context):
    if update.effective_chat.type != "private":
        return

    update.message.reply_text(f"🆔 Seu ID é:\n{update.effective_user.id}")


# ================= IDS =================

def liberar(update, context):
    if update.effective_chat.type != "private":
        return

    dados = carregar_dados()
    user_id = update.effective_user.id

    if not pode_liberar_ids(user_id, dados):
        return

    if len(context.args) < 2:
        update.message.reply_text(
            "Use assim:\n\n"
            "`/liberar ID comum`\n"
            "`/liberar ID editor`\n"
            "`/liberar ID supremo`",
            parse_mode="Markdown"
        )
        return

    try:
        novo_id = int(context.args[0])
    except Exception:
        update.message.reply_text("⚠️ ID inválido.")
        return

    nivel = context.args[1].lower()

    if nivel not in ["comum", "editor", "supremo"]:
        update.message.reply_text("⚠️ Use apenas: comum, editor ou supremo.")
        return

    remover_id_de_todos(dados, novo_id)

    if nivel == "comum":
        dados["comuns"].append(novo_id)
    elif nivel == "editor":
        dados["editores"].append(novo_id)
    elif nivel == "supremo":
        dados["supremos"].append(novo_id)

    atualizar_perfil_id(context, dados, novo_id, nivel)
    salvar_dados(dados)

    update.message.reply_text(
        "✅ ID liberado!\n\n" + formatar_info_id(dados["perfis_ids"].get(str(novo_id), {}))
    )


def apagar_id(update, context):
    if update.effective_chat.type != "private":
        return

    dados = carregar_dados()
    user_id = update.effective_user.id

    if not pode_liberar_ids(user_id, dados):
        return

    if not context.args:
        update.message.reply_text("Use assim:\n`/apagarid ID`", parse_mode="Markdown")
        return

    try:
        remover_id = int(context.args[0])
    except Exception:
        update.message.reply_text("⚠️ ID inválido.")
        return

    if remover_id in dados["donas"]:
        update.message.reply_text("❌ Você não pode apagar uma dona.")
        return

    tinha_acesso = (
        remover_id in dados["supremos"]
        or remover_id in dados["editores"]
        or remover_id in dados["comuns"]
        or str(remover_id) in dados.get("perfis_ids", {})
    )

    remover_id_de_todos(dados, remover_id)
    dados.get("perfis_ids", {}).pop(str(remover_id), None)
    salvar_dados(dados)

    if tinha_acesso:
        update.message.reply_text(f"🗑 ID apagado da lista:\n{remover_id}")
    else:
        update.message.reply_text("⚠️ Esse ID não estava liberado.")


def listar_ids(update, context):
    if update.effective_chat.type != "private":
        return

    dados = carregar_dados()
    user_id = update.effective_user.id

    if not pode_liberar_ids(user_id, dados):
        return

    categorias = [
        ("👑 DONAS", "donas", "dona"),
        ("💎 SUPREMOS", "supremos", "supremo"),
        ("⭐ EDITORES", "editores", "editor"),
        ("👤 COMUNS", "comuns", "comum")
    ]

    texto = "👥 IDs liberados no Nexorium\n\n"

    for titulo, chave, nivel in categorias:
        texto += f"{titulo}\n\n"

        if not dados.get(chave):
            texto += "Nenhum\n\n"
            continue

        for uid in dados[chave]:
            info = pegar_info_id(context, dados, uid, nivel)
            texto += formatar_info_id(info) + "\n\n"

    salvar_dados(dados)
    update.message.reply_text(texto)


# ================= TEMPO POR PARCERIA =================

def abrir_config_tempo(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id

    if nivel_usuario(user_id, dados) == "comum":
        update.message.reply_text("❌ Seu acesso comum não configura tempo.")
        return

    if not dados.get("globais"):
        update.message.reply_text("🌍 Nenhuma parceria global salva ainda.")
        return

    dados["etapas"][str(user_id)] = {"modo": "tempo_nome"}
    salvar_dados(dados)

    texto = "⏱ Tempo por parceria\n\nDigite o nome da parceria global que deseja configurar:\n\n"
    for nome in dados["globais"].keys():
        atual = tempo_usuario_parceria(dados, user_id, nome)
        texto += f"• `{nome}` — {atual}\n"

    update.message.reply_text(texto, parse_mode="Markdown")


def processar_tempo_nome(update, context, dados, uid, texto):
    user_id = update.effective_user.id
    nome = limpar_nome(texto)

    if nome not in dados.get("globais", {}):
        update.message.reply_text("❌ Não encontrei essa parceria global. Digite exatamente o nome salvo.")
        return

    dados["etapas"][uid] = {
        "modo": "tempo_valor",
        "nome_parceria": nome
    }
    salvar_dados(dados)

    atual = tempo_usuario_parceria(dados, user_id, nome)

    update.message.reply_text(
        f"⏱ Parceria: {nome}\n"
        f"Tempo atual para seu ID: {atual}\n\n"
        "Escolha o novo tempo:",
        reply_markup=teclado_tempo()
    )


def processar_tempo_valor(update, context, dados, uid, etapa, texto):
    user_id = update.effective_user.id

    if texto not in OPCOES_TEMPO:
        update.message.reply_text("⚠️ Escolha uma opção do painel.")
        return

    nome = etapa["nome_parceria"]
    salvar_tempo_usuario_parceria(dados, user_id, nome, texto)

    dados["etapas"].pop(uid, None)
    salvar_dados(dados)

    if texto == "desligado":
        update.message.reply_text(
            f"✅ Apagamento automático desligado para:\n{nome}\n\n"
            "Essa configuração vale somente para o seu ID.",
            reply_markup=teclado_menu(user_id)
        )
    else:
        update.message.reply_text(
            f"✅ Tempo configurado para {nome}: {texto}\n\n"
            "Essa configuração vale somente para o seu ID.",
            reply_markup=teclado_menu(user_id)
        )


# ================= CRIAR PARCERIA =================

def iniciar_criar_global(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id

    if not pode_criar_global(user_id, dados):
        update.message.reply_text("❌ Você não tem permissão para criar parceria global.")
        return

    dados["etapas"][str(user_id)] = {"modo": "nome", "tipo": "global"}
    salvar_dados(dados)

    update.message.reply_text(
        "🌍 Criar parceria global\n\n"
        "Digite o nome curto da lista.\n\n"
        "Exemplo:\n"
        "`parceria_nexorium`",
        parse_mode="Markdown"
    )


def iniciar_criar_pessoal(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id

    if nivel_usuario(user_id, dados) == "comum":
        update.message.reply_text("❌ Seu acesso comum só permite usar parceria global no grupo.")
        return

    if not nivel_usuario(user_id, dados):
        return

    dados["etapas"][str(user_id)] = {"modo": "nome", "tipo": "pessoal"}
    salvar_dados(dados)

    update.message.reply_text(
        "🔒 Criar parceria pessoal\n\n"
        "Digite o nome curto da lista.\n\n"
        "Exemplo:\n"
        "`meus_parceiros`",
        parse_mode="Markdown"
    )


def processar_etapa_nome(update, context, dados, uid, etapa, texto):
    etapa["nome"] = limpar_nome(texto)
    etapa["modo"] = "imagem"
    dados["etapas"][uid] = etapa
    salvar_dados(dados)

    update.message.reply_text(
        "🖼 Agora envie a imagem/banner da parceria.\n\n"
        "Se não quiser imagem, digite:\n"
        "`pular`",
        parse_mode="Markdown"
    )


def processar_etapa_imagem(update, context, dados, uid, etapa, texto):
    if update.message.photo:
        etapa["imagem"] = update.message.photo[-1].file_id
    elif texto.lower().strip() == "pular":
        etapa["imagem"] = None
    else:
        update.message.reply_text("⚠️ Envie uma imagem ou digite: pular")
        return

    etapa["modo"] = "frase"
    dados["etapas"][uid] = etapa
    salvar_dados(dados)

    update.message.reply_text(
        "✏️ Agora envie a frase/título da parceria.\n\n"
        "Exemplo:\n"
        "`📚✨ Parcerias Literárias ✨📚`",
        parse_mode="Markdown"
    )


def texto_exemplo_botoes():
    # Cada nome fica em um código separado para copiar um por um no Telegram.
    linhas = []
    for nome in EXEMPLOS_GRUPOS:
        linhas.append(f"`{nome} | `")
    return "\n".join(linhas)


def processar_etapa_frase(update, context, dados, uid, etapa, texto):
    etapa["frase"] = texto
    etapa["modo"] = "botoes"
    dados["etapas"][uid] = etapa
    salvar_dados(dados)

    update.message.reply_text(
        "🔗 Agora envie os botões, um por linha:\n\n"
        "Formato:\n"
        "`Nome do botão | https://t.me/link`\n\n"
        "Exemplo:\n"
        "`📚 Livros 0.1 | https://t.me/seulink`\n\n"
        "📌 Nomes para copiar um por um e colocar o link depois:\n"
        f"{texto_exemplo_botoes()}",
        parse_mode="Markdown"
    )


def extrair_botoes(texto):
    botoes = []

    for linha in texto.splitlines():
        if "|" not in linha:
            continue

        nome_botao, link = linha.split("|", 1)
        nome_botao = nome_botao.strip()
        link = link.strip()

        if link.startswith("t.me/"):
            link = "https://" + link

        if nome_botao and link.startswith("http"):
            botoes.append({"nome": nome_botao, "link": link})

    return botoes


def processar_etapa_botoes(update, context, dados, uid, etapa, texto):
    botoes = extrair_botoes(texto)

    if not botoes:
        update.message.reply_text(
            "⚠️ Nenhum botão válido encontrado.\n\n"
            "Use assim:\n"
            "`Nome do botão | https://t.me/link`",
            parse_mode="Markdown"
        )
        return

    lista = {
        "nome": etapa["nome"],
        "tipo": etapa["tipo"],
        "criador_id": update.effective_user.id,
        "criador_nome": update.effective_user.first_name,
        "imagem": etapa.get("imagem"),
        "frase": etapa.get("frase"),
        "botoes": botoes
    }

    if etapa["tipo"] == "global":
        lista["codigo_fixo"] = gerar_codigo_fixo(dados)
        dados["globais"][etapa["nome"]] = lista
    else:
        lista["codigo_fixo"] = gerar_codigo_fixo(dados)
        dados["pessoais"].setdefault(uid, {})
        dados["pessoais"][uid][etapa["nome"]] = lista

    dados["etapas"].pop(uid, None)
    salvar_dados(dados)

    texto_final = (
        f"✅ Parceria salva!\n\n"
        f"Tipo: {etapa['tipo']}\n"
        f"Nome: {etapa['nome']}\n"
        f"Botões: {len(botoes)}\n\n"
        f"Use no grupo:\n"
        f"/parceria {etapa['nome']}"
    )

    if etapa["tipo"] == "global":
        bot_username = context.bot.username or "Nexoriumbot"
        texto_final += (
            f"\n\n🔑 Código fixo:\n"
            f"`@{bot_username} {lista['codigo_fixo']}`"
        )

    update.message.reply_text(
        texto_final,
        parse_mode="Markdown",
        reply_markup=teclado_menu(update.effective_user.id)
    )


# ================= ENVIAR PARCERIAS =================

def link_valido(link):
    if not link:
        return False

    link = str(link).strip()

    if not (link.startswith("http://") or link.startswith("https://")):
        return False

    # Links de exemplo não entram nos botões, para não derrubar a lista inteira.
    proibidos = ["seulink", "seu_link", "link_aqui", "exemplo.com", "t.me/link"]

    for item in proibidos:
        if item.lower() in link.lower():
            return False

    if link in ["https://t.me/", "http://t.me/", "https://", "http://"]:
        return False

    return True


def montar_teclado_links(lista):
    teclado = []

    for botao in lista.get("botoes", []):
        nome = botao.get("nome", "").strip()
        link = botao.get("link", "").strip()

        # Se um botão estiver com link inválido/vencido/falso,
        # ele é ignorado e os outros continuam funcionando.
        if nome and link_valido(link):
            teclado.append([InlineKeyboardButton(nome, url=link)])

    if not teclado:
        return None

    return InlineKeyboardMarkup(teclado)


def enviar_parceria_context(context, chat_id, lista, mostrar_info=False, message_thread_id=None):
    reply_markup = montar_teclado_links(lista)
    frase = lista.get("frase", "📚✨ Parcerias ✨📚")

    if mostrar_info:
        frase += (
            f"\n\n📌 Nome salvo: {lista.get('nome')}"
            f"\n💬 Comando: /parceria {lista.get('nome')}"
            f"\n👤 Criador: {lista.get('criador_nome')}"
            f"\n🔢 Botões: {len(lista.get('botoes', []))}"
        )
        if lista.get("codigo_fixo"):
            frase += f"\n🔑 Código: {lista.get('codigo_fixo')}"

    kwargs = {
        "chat_id": chat_id,
        "reply_markup": reply_markup
    }

    if message_thread_id is not None:
        kwargs["message_thread_id"] = message_thread_id

    if lista.get("imagem"):
        kwargs.update({
            "photo": lista["imagem"],
            "caption": frase
        })
        return enviar_seguro(context.bot.send_photo, **kwargs)

    kwargs.update({"text": frase})
    return enviar_seguro(context.bot.send_message, **kwargs)


def enviar_parceria(update, context, lista, mostrar_info=False):
    thread_id = getattr(update.message, "message_thread_id", None)
    return enviar_parceria_context(
        context=context,
        chat_id=update.effective_chat.id,
        lista=lista,
        mostrar_info=mostrar_info,
        message_thread_id=thread_id
    )


def listar_globais(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id
    nivel = nivel_usuario(user_id, dados)

    if nivel == "editor":
        update.message.reply_text(
            "❌ Editores de parcerias não possuem acesso às parcerias globais."
        )
        return

    if nivel_usuario(user_id, dados) == "comum":
        update.message.reply_text("Seu acesso comum só permite usar as parcerias globais no grupo.")
        return

    if not dados["globais"]:
        update.message.reply_text("🌍 Nenhuma parceria global salva.")
        return

    update.message.reply_text("🌍 Parcerias globais salvas:")

    for lista in dados["globais"].values():
        enviar_parceria(update, context, lista, mostrar_info=True)


def listar_pessoais(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id
    uid = str(user_id)

    if nivel_usuario(user_id, dados) == "comum":
        update.message.reply_text("Seu acesso comum não possui parcerias pessoais.")
        return

    pessoais = dados["pessoais"].get(uid, {})

    if not pessoais:
        update.message.reply_text("🔒 Você ainda não tem parcerias pessoais.")
        return

    update.message.reply_text("🔒 Suas parcerias pessoais:")

    bot_username = context.bot.username or "Nexoriumbot"

    for lista in pessoais.values():

        texto = (
            f"🔒 {lista['nome']}\n"
            f"🔑 @{bot_username} {lista['codigo_fixo']}"
        )
        
        update.message.reply_text(texto)

        enviar_parceria(update, context, lista, mostrar_info=True)

# ================= VER COMANDOS / CÓDIGOS / LISTAS =================

def ver_comandos(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id
    uid = str(user_id)
    nivel = nivel_usuario(user_id, dados)

    if nivel == "editor":
        texto = "📋 Comandos disponíveis\n\n"

        pessoais = dados["pessoais"].get(uid, {})

        if pessoais:
            for nome in pessoais:
                texto += f"`/parceria {nome}`\n"
    else:
        texto += "Nenhuma parceria pessoal."

    update.message.reply_text(texto, parse_mode="Markdown")
    return

    texto = "📋 Comandos disponíveis\n\n"

    texto += "🌍 Globais:\n"
    if dados["globais"]:
        for nome in dados["globais"]:
            texto += f"`/parceria {nome}`\n"
    else:
        texto += "Nenhuma\n"

    if nivel != "comum":
        texto += "\n🔒 Suas pessoais:\n"
        pessoais = dados["pessoais"].get(uid, {})
        if pessoais:
            for nome in pessoais:
                texto += f"`/parceria {nome}`\n"
        else:
            texto += "Nenhuma\n"

    update.message.reply_text(texto, parse_mode="Markdown")


def ver_codigos_fixos(update, context):
    dados = carregar_dados()
    nivel = nivel_usuario(update.effective_user.id, dados)

    if nivel == "editor":
        update.message.reply_text(
            "❌ Editores de parcerias não possuem acesso aos códigos globais."
        )
        return

    dados = carregar_dados()
    bot_username = context.bot.username or "Nexoriumbot"

    texto = "🔑 Códigos fixos das parcerias globais\n\n"

    if not dados.get("globais"):
        texto += "Nenhuma parceria global salva."
    else:
        mudou = False

        for nome, lista in dados.get("globais", {}).items():
            if not lista.get("codigo_fixo"):
                lista["codigo_fixo"] = gerar_codigo_fixo(dados)
                mudou = True

            codigo = lista.get("codigo_fixo", "")
            tempo = tempo_usuario_parceria(dados, update.effective_user.id, nome)

            texto += (
                f"📌 {nome}\n"
                f"🔑 @{bot_username} {codigo}\n"
                f"⏱ Seu tempo: {tempo}\n\n"
            )

        if mudou:
            salvar_dados(dados)

    # Sem parse_mode para não dar erro com _, *, emoji, acentos ou símbolos.
    update.message.reply_text(texto)


def listas_completas(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id
    uid = str(user_id)
    nivel = nivel_usuario(user_id, dados)

    if nivel == "comum":
        update.message.reply_text("Seu acesso comum não vê listas administrativas.")
        return

    texto = "📚 Listas completas do bot\n\n"

    if nivel in ["dona", "supremo"]:
        texto += "🌍 GLOBAIS\n"
    if dados["globais"]:
        for nome, lista in dados["globais"].items():
            texto += (
                f"\n📌 Nome: {nome}\n"
                f"✏️ Título: {lista.get('frase', 'Sem título')}\n"
                f"👤 Criador: {lista.get('criador_nome', 'Desconhecido')}\n"
                f"🔢 Botões: {len(lista.get('botoes', []))}\n"
                f"💬 Comando: /parceria {nome}\n"
                f"🔑 Código: {lista.get('codigo_fixo', 'sem código')}\n"
                f"⏱ Seu tempo: {tempo_usuario_parceria(dados, user_id, nome)}\n"
            )
    else:
        texto += "\nNenhuma\n"

    texto += "\n🔒 PESSOAIS\n"
    pessoais = dados["pessoais"].get(uid, {})
    if pessoais:
        for nome, lista in pessoais.items():
            texto += (
                f"\n📌 Nome: {nome}\n"
                f"✏️ Título: {lista.get('frase', 'Sem título')}\n"
                f"🔢 Botões: {len(lista.get('botoes', []))}\n"
                f"💬 Comando: /parceria {nome}\n"
            )
    else:
        texto += "\nNenhuma\n"

    update.message.reply_text(texto)


# ================= EDITAR PARCERIA =================




def iniciar_editar(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id
    uid = str(user_id)

    if nivel_usuario(user_id, dados) == "comum":
        update.message.reply_text("❌ Seu acesso comum não permite editar parcerias.")
        return

    dados["etapas"][uid] = {"modo": "editar_buscar"}
    salvar_dados(dados)

    update.message.reply_text(
        "✏️ Digite o nome da parceria que deseja editar.\n\n"
        "Exemplo:\n"
        "`parceria_nexorium`",
        parse_mode="Markdown"
    )


def processar_editar_buscar(update, context, dados, uid, etapa, texto):
    nome = limpar_nome(texto)
    escopo, lista = localizar_lista(dados, uid, nome, update.effective_user.id)

    if not lista:
        dados["etapas"].pop(uid, None)
        salvar_dados(dados)
        update.message.reply_text("❌ Não encontrei essa parceria ou você não tem permissão.")
        return

    dados["etapas"][uid] = {
        "modo": "editar_opcao",
        "nome_original": nome,
        "escopo": escopo
    }
    salvar_dados(dados)

    update.message.reply_text(
        f"✏️ Editando: {nome}\n\n"
        "Escolha o que deseja alterar:",
        reply_markup=teclado_edicao()
    )


def processar_editar_opcao(update, context, dados, uid, etapa, texto):
    if texto == "🔙 Cancelar":
        dados["etapas"].pop(uid, None)
        salvar_dados(dados)
        update.message.reply_text("✅ Edição cancelada.", reply_markup=teclado_menu(update.effective_user.id))
        return

    mapa = {
        "📝 Editar nome": "editar_nome",
        "🖼 Editar imagem": "editar_imagem",
        "✏️ Editar frase": "editar_frase",
        "🔗 Editar botões": "editar_botoes_menu"
    }

    if texto not in mapa:
        update.message.reply_text("Escolha uma opção do painel.")
        return

    etapa["modo"] = mapa[texto]
    dados["etapas"][uid] = etapa
    salvar_dados(dados)

    if etapa["modo"] == "editar_nome":
        update.message.reply_text("📝 Envie o novo nome curto.")
    elif etapa["modo"] == "editar_imagem":
        update.message.reply_text("🖼 Envie a nova imagem/banner ou digite `pular` para remover.", parse_mode="Markdown")
    elif etapa["modo"] == "editar_frase":
        update.message.reply_text("✏️ Envie a nova frase/título.")
    elif etapa["modo"] == "editar_botoes_menu":
        update.message.reply_text(
            "🔗 O que deseja fazer com os botões?",
            reply_markup=teclado_editar_botoes()
        )


def salvar_lista_editada(dados, uid, etapa, lista):
    nome_original = etapa["nome_original"]
    escopo = etapa["escopo"]

    if escopo == "global":
        dados["globais"][nome_original] = lista
    else:
        dados["pessoais"].setdefault(uid, {})
        dados["pessoais"][uid][nome_original] = lista



def texto_botoes_numerados(lista):
    botoes = lista.get("botoes", [])

    if not botoes:
        return "Nenhum botão cadastrado."

    texto = ""
    for i, botao in enumerate(botoes, start=1):
        nome = botao.get("nome", "Sem nome")
        link = botao.get("link", "Sem link")
        texto += f"{i}. {nome}\n   {link}\n"

    return texto


def processar_editar_botoes_menu(update, context, dados, uid, etapa, texto):
    nome_original = etapa["nome_original"]
    _, lista = localizar_lista(dados, uid, nome_original, update.effective_user.id)

    if not lista:
        dados["etapas"].pop(uid, None)
        salvar_dados(dados)
        update.message.reply_text("❌ Não encontrei essa parceria.", reply_markup=teclado_menu(update.effective_user.id))
        return

    if texto == "🔙 Cancelar":
        dados["etapas"].pop(uid, None)
        salvar_dados(dados)
        update.message.reply_text("✅ Edição cancelada.", reply_markup=teclado_menu(update.effective_user.id))
        return

    if texto == "➕ Adicionar botão":
        etapa["modo"] = "editar_botoes_adicionar"
        dados["etapas"][uid] = etapa
        salvar_dados(dados)
        update.message.reply_text(
            "➕ Envie o novo botão assim:\n\n"
            "`Nome do botão | https://t.me/link`",
            parse_mode="Markdown"
        )
        return

    if texto == "✏️ Editar link de botão":
        etapa["modo"] = "editar_botoes_escolher_link"
        dados["etapas"][uid] = etapa
        salvar_dados(dados)
        update.message.reply_text(
            "✏️ Qual botão você quer editar?\n\n"
            "Envie apenas o número:\n\n"
            f"{texto_botoes_numerados(lista)}"
        )
        return

    if texto == "🗑 Apagar botão":
        etapa["modo"] = "editar_botoes_apagar"
        dados["etapas"][uid] = etapa
        salvar_dados(dados)
        update.message.reply_text(
            "🗑 Qual botão você quer apagar?\n\n"
            "Envie apenas o número:\n\n"
            f"{texto_botoes_numerados(lista)}"
        )
        return

    update.message.reply_text("Escolha uma opção do painel.")


def processar_adicionar_botao(update, context, dados, uid, etapa, texto):
    nome_original = etapa["nome_original"]
    _, lista = localizar_lista(dados, uid, nome_original, update.effective_user.id)

    botoes_novos = extrair_botoes(texto)

    if not botoes_novos:
        update.message.reply_text(
            "⚠️ Botão inválido.\n\nUse assim:\n"
            "`Nome do botão | https://t.me/link`",
            parse_mode="Markdown"
        )
        return

    lista.setdefault("botoes", [])
    lista["botoes"].extend(botoes_novos)

    salvar_lista_editada(dados, uid, etapa, lista)
    dados["etapas"].pop(uid, None)
    salvar_dados(dados)

    update.message.reply_text(
        f"✅ Botão adicionado com sucesso.\n\nBotões agora: {len(lista.get('botoes', []))}",
        reply_markup=teclado_menu(update.effective_user.id)
    )


def processar_escolher_link_botao(update, context, dados, uid, etapa, texto):
    nome_original = etapa["nome_original"]
    _, lista = localizar_lista(dados, uid, nome_original, update.effective_user.id)

    try:
        numero = int(texto.strip())
    except Exception:
        update.message.reply_text("⚠️ Envie apenas o número do botão.")
        return

    botoes = lista.get("botoes", [])

    if numero < 1 or numero > len(botoes):
        update.message.reply_text("⚠️ Número inválido.")
        return

    etapa["modo"] = "editar_botoes_novo_link"
    etapa["indice_botao"] = numero - 1
    dados["etapas"][uid] = etapa
    salvar_dados(dados)

    botao = botoes[numero - 1]
    update.message.reply_text(
        f"✏️ Editando link de:\n{botao.get('nome')}\n\n"
        "Envie o novo link:"
    )


def processar_novo_link_botao(update, context, dados, uid, etapa, texto):
    nome_original = etapa["nome_original"]
    _, lista = localizar_lista(dados, uid, nome_original, update.effective_user.id)

    link = texto.strip()

    if not (link.startswith("http://") or link.startswith("https://") or link.startswith("t.me/")):
        update.message.reply_text("⚠️ Link inválido. Envie um link começando com https:// ou t.me/")
        return

    if link.startswith("t.me/"):
        link = "https://" + link

    indice = etapa["indice_botao"]
    lista["botoes"][indice]["link"] = link

    salvar_lista_editada(dados, uid, etapa, lista)
    dados["etapas"].pop(uid, None)
    salvar_dados(dados)

    update.message.reply_text("✅ Link atualizado com sucesso.", reply_markup=teclado_menu(update.effective_user.id))


def processar_apagar_botao(update, context, dados, uid, etapa, texto):
    nome_original = etapa["nome_original"]
    _, lista = localizar_lista(dados, uid, nome_original, update.effective_user.id)

    try:
        numero = int(texto.strip())
    except Exception:
        update.message.reply_text("⚠️ Envie apenas o número do botão.")
        return

    botoes = lista.get("botoes", [])

    if numero < 1 or numero > len(botoes):
        update.message.reply_text("⚠️ Número inválido.")
        return

    removido = botoes.pop(numero - 1)
    lista["botoes"] = botoes

    salvar_lista_editada(dados, uid, etapa, lista)
    dados["etapas"].pop(uid, None)
    salvar_dados(dados)

    update.message.reply_text(
        f"🗑 Botão apagado:\n{removido.get('nome')}",
        reply_markup=teclado_menu(update.effective_user.id)
    )



def processar_edicao_valor(update, context, dados, uid, etapa, texto):
    nome_original = etapa["nome_original"]
    escopo = etapa["escopo"]
    _, lista = localizar_lista(dados, uid, nome_original, update.effective_user.id)

    if not lista:
        dados["etapas"].pop(uid, None)
        salvar_dados(dados)
        update.message.reply_text("❌ Não encontrei essa parceria.")
        return

    modo = etapa["modo"]

    if modo == "editar_nome":
        novo_nome = limpar_nome(texto)

        if escopo == "global":
            dados["globais"].pop(nome_original, None)
            lista["nome"] = novo_nome
            dados["globais"][novo_nome] = lista
        else:
            dados["pessoais"][uid].pop(nome_original, None)
            lista["nome"] = novo_nome
            dados["pessoais"][uid][novo_nome] = lista

    elif modo == "editar_imagem":
        if update.message.photo:
            lista["imagem"] = update.message.photo[-1].file_id
        elif texto.lower().strip() == "pular":
            lista["imagem"] = None
        else:
            update.message.reply_text("⚠️ Envie uma imagem ou digite pular.")
            return
        salvar_lista_editada(dados, uid, etapa, lista)

    elif modo == "editar_frase":
        lista["frase"] = texto
        salvar_lista_editada(dados, uid, etapa, lista)

    elif modo == "editar_botoes":
        # Mantido apenas por compatibilidade com versões antigas.
        botoes = extrair_botoes(texto)
        if not botoes:
            update.message.reply_text("⚠️ Nenhum botão válido encontrado.")
            return
        lista.setdefault("botoes", [])
        lista["botoes"].extend(botoes)
        salvar_lista_editada(dados, uid, etapa, lista)

    dados["etapas"].pop(uid, None)
    salvar_dados(dados)

    update.message.reply_text("✅ Parceria editada com sucesso.", reply_markup=teclado_menu(update.effective_user.id))


# ================= APAGAR PARCERIA =================

def iniciar_apagar(update, context):
    dados = carregar_dados()
    user_id = update.effective_user.id
    uid = str(user_id)

    if nivel_usuario(user_id, dados) == "comum":
        update.message.reply_text("❌ Seu acesso comum não permite apagar parcerias.")
        return

    dados["etapas"][uid] = {"modo": "apagar"}
    salvar_dados(dados)

    update.message.reply_text("🗑 Digite o nome da parceria que deseja apagar.")


def processar_apagar(update, context, dados, uid, texto):
    nome = limpar_nome(texto)
    user_id = update.effective_user.id
    apagou = False

    pessoais = dados["pessoais"].get(uid, {})

    if nome in pessoais:
        del dados["pessoais"][uid][nome]
        apagou = True

    if nome in dados["globais"] and pode_criar_global(user_id, dados):
        del dados["globais"][nome]
        apagou = True

    dados["etapas"].pop(uid, None)
    salvar_dados(dados)

    if apagou:
        update.message.reply_text("✅ Parceria apagada.", reply_markup=teclado_menu(user_id))
    else:
        update.message.reply_text("❌ Não encontrei essa parceria.", reply_markup=teclado_menu(user_id))


# ================= LIMPAR TECLADO DO GRUPO =================

def limpar_teclado_grupo(update, context):
    """
    Remove aquele teclado/botão grande do bot que ficou aparecendo no campo de mensagem do grupo.
    O menu continua existindo no PV, mas no grupo ele some.
    """
    if update.effective_chat.type == "private":
        return

    try:
        thread_id = getattr(update.message, "message_thread_id", None)

        kwargs = {
            "chat_id": update.effective_chat.id,
            "text": ".",
            "reply_markup": ReplyKeyboardRemove()
        }

        if thread_id is not None:
            kwargs["message_thread_id"] = thread_id

        msg = context.bot.send_message(**kwargs)

        try:
            context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id
            )
        except Exception:
            pass

    except Exception as erro:
        print("Não consegui limpar teclado do grupo:", erro)


# ================= DISPARAR NO GRUPO =================

def apagar_mensagem_comando(update, context):
    try:
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except Exception as erro:
        print("Não consegui apagar comando/código:", erro)


def user_id_para_tempo(update):
    user = update.effective_user
    if user:
        return user.id
    return None


def disparar_lista_global(update, context, dados, nome_parceria, lista):
    thread_id = getattr(update.message, "message_thread_id", None)

    msg = enviar_parceria_context(
        context=context,
        chat_id=update.effective_chat.id,
        lista=lista,
        mostrar_info=False,
        message_thread_id=thread_id
    )

    if msg and update.effective_chat.type != "private":
        apagar_mensagem_comando(update, context)
        agendar_apagar_lista(context, dados, msg, user_id_para_tempo(update), nome_parceria)

    return msg


def comando_parcerias(update, context):
    dados = carregar_dados()
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        limpar_teclado_grupo(update, context)

    user_id = user.id if user else None
    nivel = nivel_usuario(user_id, dados) if user_id else None

    if not context.args:
        if chat.type == "private":
            update.message.reply_text("Use assim:\n/parceria nome_da_lista")
        return

    nome = limpar_nome(" ".join(context.args))
    uid = str(user_id) if user_id else None

    if nome in dados["globais"]:
        if not pode_usar_global_no_grupo(update, context, dados):
            return

        lista = dados["globais"][nome]

        if chat.type != "private":
            disparar_lista_global(update, context, dados, nome, lista)
            return

        enviar_parceria(update, context, lista, mostrar_info=False)
        return

    if nivel and nivel != "comum" and uid:
        pessoais = dados["pessoais"].get(uid, {})
        if nome in pessoais:
            enviar_parceria(update, context, pessoais[nome], mostrar_info=False)
            return

    if chat.type == "private":
        update.message.reply_text("❌ Parceria não encontrada.")


def comando_parcerias_texto(update, context):
    texto = update.message.text or ""
    if not (texto.startswith("//parceria") or texto.startswith("//parcerias")):
        return

    partes = texto.replace("//", "/", 1).split()
    if len(partes) < 2:
        return

    context.args = partes[1:]
    comando_parcerias(update, context)


def codigo_fixo_texto(update, context):
    texto = (update.message.text or "").strip()
    dados = carregar_dados()

    if update.effective_chat.type != "private":
        limpar_teclado_grupo(update, context)

    if not texto or not texto.startswith("@"):
        return

    partes = texto.split()
    if len(partes) < 2:
        return

    bot_username = context.bot.username or ""
    mencionado = partes[0].replace("@", "").lower()

    if mencionado != bot_username.lower():
        return

    codigo = partes[1].strip().lower()
    nome, lista = buscar_global_por_codigo(dados, codigo)

    if lista:
        if not pode_usar_global_no_grupo(update, context, dados):
            return

        if update.effective_chat.type == "private":
            enviar_parceria(update, context, lista)
            return

        disparar_lista_global(update, context, dados, nome, lista)
        return

    user_id = update.effective_user.id
    nome, lista = buscar_pessoal_por_codigo(
        dados,
        user_id,
        codigo
    )

    if lista:
        enviar_parceria(update, context, lista)

    if not pode_usar_global_no_grupo(update, context, dados):
        return

    if update.effective_chat.type == "private":
        enviar_parceria(update, context, lista, mostrar_info=False)
        return

    disparar_lista_global(update, context, dados, nome, lista)


# ================= RECEBER MENSAGENS PV =================

def receber_mensagem(update, context):
    if update.effective_chat.type != "private":
        return

    dados = carregar_dados()
    user_id = update.effective_user.id
    uid = str(user_id)
    nivel = nivel_usuario(user_id, dados)

    if not nivel:
        update.message.reply_text(f"🔒 Você não tem acesso.\n\nSeu ID é:\n{user_id}")
        return

    texto = update.message.text or ""

    if texto == "🔙 Cancelar":
        dados["etapas"].pop(uid, None)
        salvar_dados(dados)
        update.message.reply_text("✅ Cancelado.", reply_markup=teclado_menu(user_id))
        return

    if nivel == "comum":
        if texto == "🆔 Meu ID":
            meu_id(update, context)
        elif texto == "❓ Ajuda":
            ajuda(update, context)
        return

    etapa = dados["etapas"].get(uid)

    if etapa and etapa.get("modo") == "tempo_valor" and texto in OPCOES_TEMPO:
        processar_tempo_valor(update, context, dados, uid, etapa, texto)
        return

    if eh_botao_menu(texto) and texto != "🔙 Cancelar":
        dados["etapas"].pop(uid, None)
        salvar_dados(dados)
        tratar_menu(update, context)
        return

    etapa = dados["etapas"].get(uid)

    if not etapa:
        return

    modo = etapa.get("modo")

    if modo == "nome":
        processar_etapa_nome(update, context, dados, uid, etapa, texto)
    elif modo == "imagem":
        processar_etapa_imagem(update, context, dados, uid, etapa, texto)
    elif modo == "frase":
        processar_etapa_frase(update, context, dados, uid, etapa, texto)
    elif modo == "botoes":
        processar_etapa_botoes(update, context, dados, uid, etapa, texto)
    elif modo == "editar_buscar":
        processar_editar_buscar(update, context, dados, uid, etapa, texto)
    elif modo == "editar_opcao":
        processar_editar_opcao(update, context, dados, uid, etapa, texto)
    elif modo == "editar_botoes_menu":
        processar_editar_botoes_menu(update, context, dados, uid, etapa, texto)
    elif modo == "editar_botoes_adicionar":
        processar_adicionar_botao(update, context, dados, uid, etapa, texto)
    elif modo == "editar_botoes_escolher_link":
        processar_escolher_link_botao(update, context, dados, uid, etapa, texto)
    elif modo == "editar_botoes_novo_link":
        processar_novo_link_botao(update, context, dados, uid, etapa, texto)
    elif modo == "editar_botoes_apagar":
        processar_apagar_botao(update, context, dados, uid, etapa, texto)
    elif modo in ["editar_nome", "editar_imagem", "editar_frase", "editar_botoes"]:
        processar_edicao_valor(update, context, dados, uid, etapa, texto)
    elif modo == "apagar":
        processar_apagar(update, context, dados, uid, texto)
    elif modo == "tempo_nome":
        processar_tempo_nome(update, context, dados, uid, texto)


# ================= TRATAR MENU =================

def tratar_menu(update, context):
    texto = update.message.text or ""
    t = texto_menu_normalizado(texto)

    if "criar parceria global" in t:
        iniciar_criar_global(update, context)
    elif "criar parceria pessoal" in t:
        iniciar_criar_pessoal(update, context)
    elif "editar parceria" in t:
        iniciar_editar(update, context)
    elif "apagar parceria" in t:
        iniciar_apagar(update, context)
    elif "parcerias globais" in t:
        listar_globais(update, context)
    elif "minhas parcerias" in t:
        listar_pessoais(update, context)
    elif "ver comandos" in t:
        ver_comandos(update, context)
    elif "códigos fixos" in t or "codigos fixos" in t:
        ver_codigos_fixos(update, context)
    elif "listas completas" in t:
        listas_completas(update, context)
    elif "tempo por parceria" in t:
        abrir_config_tempo(update, context)
    elif "meu id" in t:
        meu_id(update, context)
    elif "ajuda" in t:
        ajuda(update, context)
    elif "ids liberados" in t:
        listar_ids(update, context)
    elif "liberar id" in t:
        update.message.reply_text(
            "Use assim:\n\n"
            "`/liberar ID comum`\n"
            "`/liberar ID editor`\n"
            "`/liberar ID supremo`",
            parse_mode="Markdown"
        )
    elif "apagar id" in t:
        update.message.reply_text("Use assim:\n`/apagarid ID`", parse_mode="Markdown")



# ================= MODO INLINE =================
# Permite usar em qualquer grupo:
# @Nexoriumbot codigo
# @Nexoriumbot nome_da_parceria
#
# Nesse modo:
# ✅ não precisa colocar o bot no grupo
# ✅ não precisa o bot ser admin
# ✅ não precisa liberar ID da pessoa
# ✅ funciona apenas para parcerias globais
# ❌ não apaga automaticamente, porque o bot não está no grupo

def montar_resultados_inline(query, dados, usar_foto=True):
    resultados = []
    globais = dados.get("globais", {})

    if not query:
        itens = list(globais.items())[:10]
    else:
        itens = []
        for nome, lista in globais.items():
            codigo = str(lista.get("codigo_fixo", "")).lower()
            nome_limpo = limpar_nome(nome).lower()
            frase = str(lista.get("frase", "")).lower()

            if (
                query in codigo
                or query in nome_limpo
                or query in nome.lower()
                or query in frase
            ):
                itens.append((nome, lista))

    for nome, lista in itens[:20]:
        frase = lista.get("frase") or "📚✨ Parcerias ✨📚"
        codigo = lista.get("codigo_fixo", "sem_codigo")

        teclado = []
        for botao in lista.get("botoes", []):
            nome_botao = str(botao.get("nome", "")).strip()
            link = str(botao.get("link", "")).strip()

            if nome_botao and link_valido(link):
                teclado.append([InlineKeyboardButton(nome_botao, url=link)])

        reply_markup = InlineKeyboardMarkup(teclado) if teclado else None
        descricao = f"Código: {codigo} • Botões: {len(teclado)}"
        imagem_file_id = lista.get("imagem")

        if usar_foto and imagem_file_id:
            resultados.append(
                InlineQueryResultCachedPhoto(
                    id=str(uuid4()),
                    photo_file_id=imagem_file_id,
                    title=f"📚 {nome}",
                    description=descricao,
                    caption=frase,
                    reply_markup=reply_markup
                )
            )
        else:
            resultados.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"📚 {nome}",
                    description=descricao,
                    input_message_content=InputTextMessageContent(frase),
                    reply_markup=reply_markup
                )
            )

    if not resultados and query:
        resultados.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="❌ Nenhuma parceria encontrada",
                description="Confira o código ou nome da parceria.",
                input_message_content=InputTextMessageContent(
                    "❌ Nenhuma parceria encontrada para esse código."
                )
            )
        )

    return resultados


def inline_query(update, context):
    query = (update.inline_query.query or "").strip().lower()
    dados = carregar_dados()

    # ===== LISTAS PESSOAIS =====
    if query == "minhas":
        uid = str(update.inline_query.from_user.id)

        resultados = []

        pessoais = dados.get("pessoais", {}).get(uid, {})

        for nome, lista in pessoais.items():

            frase = lista.get("frase") or "📚✨ Parcerias ✨📚"

            teclado = []

            for botao in lista.get("botoes", []):
                nome_botao = botao.get("nome", "").strip()
                link = botao.get("link", "").strip()

                if nome_botao and link_valido(link):
                    teclado.append([
                        InlineKeyboardButton(
                            nome_botao,
                            url=link
                        )
                    ])

            reply_markup = InlineKeyboardMarkup(teclado) if teclado else None

            if lista.get("imagem"):

                resultados.append(
                    InlineQueryResultCachedPhoto(
                        id=str(uuid4()),
                        photo_file_id=lista["imagem"],
                        caption=frase,
                        reply_markup=reply_markup
                    )
                )

            else:

                resultados.append(
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"🔒 {nome}",
                        description="Parceria pessoal",
                        input_message_content=InputTextMessageContent(frase),
                        reply_markup=reply_markup
                    )
                )

        if not resultados:
            resultados.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="🔒 Nenhuma parceria pessoal",
                    description="Você ainda não possui listas pessoais.",
                    input_message_content=InputTextMessageContent(
                        "Você ainda não possui listas pessoais."
                    )
                )
            )

        update.inline_query.answer(
            resultados,
            cache_time=1,
            is_personal=True
        )
        return

    # ===== GLOBAIS =====
    resultados = montar_resultados_inline(
        query,
        dados,
        usar_foto=True
    )

    try:
        update.inline_query.answer(
            resultados,
            cache_time=1,
            is_personal=True
        )

    except BadRequest as erro:

        print("Inline com foto falhou:", erro)

        resultados = montar_resultados_inline(
            query,
            dados,
            usar_foto=False
        )

        update.inline_query.answer(
            resultados,
            cache_time=1,
            is_personal=True
        )

# ================= ERROS / MAIN =================

def erro_global(update, context):
    erro = context.error
    print("Erro capturado:", erro)
    if isinstance(erro, (NetworkError, TimedOut)):
        print("⚠️ Erro de rede ignorado. Bot continua rodando.")


def main():
    carregar_dados()

    request_kwargs = {"connect_timeout": 20, "read_timeout": 20}

    updater = Updater(TOKEN, use_context=True, request_kwargs=request_kwargs)
    dp = updater.dispatcher

    dp.add_handler(InlineQueryHandler(inline_query))

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("menu", start))
    dp.add_handler(CommandHandler("id", meu_id))
    dp.add_handler(CommandHandler("ajuda", ajuda))
    dp.add_handler(CommandHandler("codigos", ver_codigos_fixos))
    dp.add_handler(CommandHandler("liberar", liberar))
    dp.add_handler(CommandHandler("apagarid", apagar_id))

    dp.add_handler(CommandHandler("parceria", comando_parcerias))
    dp.add_handler(CommandHandler("parcerias", comando_parcerias))

    dp.add_handler(MessageHandler(
        Filters.text & (Filters.regex(r"^//parceria") | Filters.regex(r"^//parcerias")),
        comando_parcerias_texto
    ))

    dp.add_handler(MessageHandler(
        Filters.text & Filters.regex(r"^@"),
        codigo_fixo_texto
    ))

    dp.add_handler(MessageHandler(
        Filters.chat_type.private & (Filters.text | Filters.photo),
        receber_mensagem
    ))

    dp.add_error_handler(erro_global)

    print("📚 Nexorium Bot Ajuda rodando...")
    updater.start_polling(timeout=20, drop_pending_updates=True)
    updater.idle()


if __name__ == "__main__":
    main()
