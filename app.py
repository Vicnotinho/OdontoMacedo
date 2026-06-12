# -*- coding: utf-8 -*-
# ============================================================================
# ODONTO MACEDO — Versão Web (Streamlit) — PARTE 1: PRONTUÁRIO
# ----------------------------------------------------------------------------
# Esta é a primeira parte do sistema migrado para web.
# Cobre: login, lista/busca de pacientes, cadastro, anamnese, evolução clínica
# (com o sistema de histórico "|||" do programa original), modelos de
# procedimento, orçamento e retorno.
#
# Usa o MESMO banco de dados do programa antigo (pacientes.db). Se você colocar
# o seu "pacientes.db" atual na mesma pasta deste arquivo, todos os seus
# pacientes já aparecem aqui.
#
# Para rodar:  streamlit run app.py
# ============================================================================

import io
import os
import uuid
import unicodedata
from datetime import datetime, date
from zoneinfo import ZoneInfo

import streamlit as st
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

st.set_page_config(page_title="Odonto Macedo", page_icon="🦷", layout="wide")

# Fuso horário de Brasília (o servidor roda em UTC, então fixamos o nosso)
TZ = ZoneInfo("America/Sao_Paulo")


def agora_br():
    return datetime.now(TZ)

# ----------------------------------------------------------------------------
# CONFIGURAÇÕES GERAIS
# ----------------------------------------------------------------------------
USUARIOS = ["Dr. Valter", "Dr. Victor", "Dra. Natalia"]

SEPARADOR = "|||"  # mesmo separador do programa antigo
LINHA_VISUAL = "\n\n" + "_" * 50 + "\n\n"

# Todos os campos do paciente (mesma estrutura do banco antigo)
CAMPOS = [
    "nome", "cpf", "telefone", "email", "data_nascimento",
    "endereco", "profissao", "como_conheceu", "observacoes",
    "motivo", "historico", "evolucao", "orcamento",
    "precisa_retorno", "data_retorno", "texto_retorno",
]
# A evolução é gravada separadamente (botão Gravar), então o "Salvar" geral
# não mexe nela:
CAMPOS_SALVAR = [c for c in CAMPOS if c != "evolucao"]

# ----------------------------------------------------------------------------
# MODELOS PADRÃO (iguais ao programa original)
# ----------------------------------------------------------------------------
MODELO_MOTIVO = (
    "O que levou à consulta:\n"
    "Sintomas atuais e há quanto tempo:\n"
    "Grau da dor:\n"
    "Necessidade estética:"
)
MODELO_HISTORICO = (
    "Doenças sistêmicas:\n"
    "Medicamentos em uso:\n"
    "Histórico Odontológico Anterior:\n"
    "Traumas Faciais:\n"
    "Cirurgias:"
)
MODELO_FINANCEIRO = (
    "Tipo de atendimento: Particular\n"
    "Valor:\n"
    "Forma de pagamento:\n"
    "Pendente:\n"
    "Observação:"
)
MODELO_RETORNO = (
    "Motivo do retorno:\n"
    "Status do tratamento:"
)

TEMPLATES_ENDO = {
    "Abertura Coronária": (
        "• Anestesia local com anestésico ??? pela técnica ???\n"
        "• Isolamento absoluto com grampo ???\n"
        "• Abertura coronária realizada com broca ??? na face ???\n"
        "• Localização dos canais radiculares\n"
        "• Irrigação com NaCl 2%\n"
    ),
    "Reabertura Coronária": (
        "• Anestesia local com anestésico ??? pela técnica ???\n"
        "• Isolamento absoluto com grampo ???\n"
        "• Remoção da restauração provisória com broca ??? na face ???\n"
        "• Localização dos canais radiculares\n"
        "• Irrigação com NaCl 2,5%\n"
        "• Remoção do medicamento intracanal\n"
    ),
    "Odontometria": (
        "• Odontometria realizada por método eletrônico e radiográfico\n"
        "• Comprimento de trabalho estabelecido sendo ???\n"
    ),
    "PQM": (
        "• Preparo químico-mecânico com lima mecanizada ??? no(s) canal(is)\n"
        "• Irrigação com NaCl 2,5%\n"
    ),
    "Medicamento Intracanal": (
        "• Aplicação de medicamento intracanal Ultracall\n"
        "• Selamento com mecha de algodão\n"
    ),
    "Troca de Medicamento Intracanal": (
        "• Isolamento absoluto\n"
        "• Remoção da restauração provisória\n"
        "• Toalete final com ativação de ??? com NaCl 2,5% e EDTA 17%\n"
        "• Secagem dos canais\n"
        "• Nova aplicação de medicamento intracanal Ultracall + mecha de algodão\n"
        "• Selamento provisório com restaurador provisório + ionômero de vidro\n"
        "• Ajuste oclusal\n"
    ),
    "Toalete Final": (
        "• Toalete final com ativação de ??? com NaCl 2,5% e EDTA 17%\n"
        "• Secagem dos canais\n"
    ),
    "Obturação": (
        "• Conometria realizada\n"
        "• Obturação dos canais radiculares com técnica de ??? e cimento AH Plus\n"
        "• Radiografia de controle com adequada qualidade\n"
    ),
    "Desobturação": (
        "• Realizada desobturação dos canais radiculares com limas manuais e solvente\n"
        "• Repreparo com lima mecanizada ???\n"
    ),
    "Restauração Provisória": (
        "• Restauração provisória realizada com Coltosol + ionômero de vidro\n"
        "• Ajuste oclusal realizado\n"
        "• Paciente orientado a retornar em ??? para continuação ou finalização\n"
    ),
}
TEMPLATES_GERAL = {
    "Avaliação Clínica Inicial": (
        "• Código 221 Uniodonto\n"
        "• Consulta Odontológica Inicial\n"
        "• Profilaxia: Polimento Coronário\n"
        "• Aplicação Tópica de Flúor\n"
        "• Remoção dos Fatores de Retenção do Biofilme Dental (Placa Bacteriana)\n"
        "• Controle de Cárie Incipiente\n"
        "• Atividade Educativa em Saúde Bucal\n"
    ),
    "Restauração": (
        "• Restauração do dente ??? na face ???\n"
        "• Com isolamento ???\n"
        "• Resina ???\n"
        "• Polimento e acabamento\n"
        "• Ajuste Oclusal\n"
    ),
    "Clareamento": (
        "• Escolha do abridor bucal sendo ???\n"
        "• Primeira - Segunda - Terceira\n"
        "• Proteção gengival com top dam\n"
        "• Aplicação dos líquidos de proporção 3 para 1 whiteness 35%\n"
        "• Ativação em 3 de um minuto e meio e tempo de 5 minutos durante as ativações\n"
        "• Remoção da proteção gengival\n"
    ),
}
# Junta tudo num dicionário só, com prefixo pra saber a categoria
TEMPLATES = {}
for k, v in TEMPLATES_ENDO.items():
    TEMPLATES[f"[Endo] {k}"] = v
for k, v in TEMPLATES_GERAL.items():
    TEMPLATES[f"[Geral] {k}"] = v


# ----------------------------------------------------------------------------
# BANCO DE DADOS
# ----------------------------------------------------------------------------
@st.cache_resource
def _get_pool():
    """Cria uma vez só um 'pool' de conexões com o banco na nuvem (Supabase)."""
    return ThreadedConnectionPool(
        1, 10,
        host=st.secrets["db_host"],
        port=st.secrets.get("db_port", "5432"),
        dbname=st.secrets.get("db_name", "postgres"),
        user=st.secrets["db_user"],
        password=st.secrets["db_password"],
        sslmode="require",
    )


def _exec(statements, fetch=None, commit=False):
    """Executa um ou mais comandos numa ÚNICA ida ao banco.
    statements: lista de (sql, params). fetch: 'one' ou 'all' (do último comando).
    Se a conexão tiver morrido (Supabase fecha as ociosas), tenta de novo 1 vez."""
    erro = None
    for tentativa in range(2):
        pool = _get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            for sql, params in statements:
                cur.execute(sql, params or ())
            data = None
            if fetch == "one":
                data = cur.fetchone()
            elif fetch == "all":
                data = cur.fetchall()
            if commit:
                conn.commit()
            cur.close()
            pool.putconn(conn)
            return data
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # conexão morta: descarta, recria o pool e tenta mais uma vez
            erro = e
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            _get_pool.clear()
            continue
        except Exception:
            try:
                conn.rollback()
                pool.putconn(conn)
            except Exception:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
            raise
    raise erro


@st.cache_resource
def inicializar_banco():
    """Cria as tabelas se não existirem. Roda UMA vez por sessão do servidor."""
    _exec([
        ("""CREATE TABLE IF NOT EXISTS pacientes (
                uuid TEXT PRIMARY KEY,
                nome TEXT, cpf TEXT, telefone TEXT, email TEXT,
                data_nascimento TEXT, endereco TEXT, profissao TEXT,
                como_conheceu TEXT, observacoes TEXT, motivo TEXT,
                historico TEXT, evolucao TEXT, orcamento TEXT,
                precisa_retorno INTEGER DEFAULT 0, data_retorno TEXT, texto_retorno TEXT
            )""", None),
        ("""CREATE TABLE IF NOT EXISTS livro_caixa (
                id SERIAL PRIMARY KEY, dentista TEXT, data TEXT, descricao TEXT,
                tipo TEXT, forma TEXT, valor REAL
            )""", None),
        ("""CREATE TABLE IF NOT EXISTS devedores (
                paciente_uuid TEXT PRIMARY KEY, falta TEXT
            )""", None),
        ("""CREATE TABLE IF NOT EXISTS estoque (
                id SERIAL PRIMARY KEY, nome TEXT, categoria TEXT,
                quantidade INTEGER, validade TEXT
            )""", None),
    ], commit=True)
    return True


def carregar_lista_cache():
    """Busca a lista (uuid, nome, precisa_retorno) uma vez e guarda na sessão."""
    cache = st.session_state.get("lista_cache_v2")
    if cache is None:
        cache = _exec(
            [("SELECT uuid, nome, COALESCE(precisa_retorno, 0) "
              "FROM pacientes ORDER BY LOWER(nome)", None)],
            fetch="all",
        )
        st.session_state.lista_cache_v2 = cache
    return cache


def invalidar_cache_lista():
    st.session_state.lista_cache_v2 = None


def listar_pacientes(filtro=""):
    """Retorna lista de (uuid, nome, precisa_retorno), com busca que ignora acentos."""
    todos = carregar_lista_cache()
    if not filtro:
        return todos
    palavras = remover_acentos(filtro).split()
    resultado = []
    for uid, nome, ret in todos:
        if not nome:
            continue
        nome_limpo = remover_acentos(nome)
        if all(p in nome_limpo for p in palavras):
            resultado.append((uid, nome, ret))
    return resultado


def carregar_paciente(uid):
    row = _exec(
        [(f"SELECT {','.join(CAMPOS)} FROM pacientes WHERE uuid=%s", (uid,))],
        fetch="one",
    )
    if not row:
        return None
    return dict(zip(CAMPOS, row))


def salvar_paciente(uid, dados):
    """Insere (uid None) ou atualiza. Não mexe na evolução. Retorna (uid, erro)."""
    try:
        if uid:
            sets = ", ".join(f"{k}=%s" for k in CAMPOS_SALVAR)
            valores = [dados[k] for k in CAMPOS_SALVAR] + [uid]
            _exec([(f"UPDATE pacientes SET {sets} WHERE uuid=%s", valores)], commit=True)
        else:
            uid = str(uuid.uuid4())
            cols = ["uuid"] + CAMPOS_SALVAR
            ph = ", ".join(["%s"] * len(cols))
            valores = [uid] + [dados[k] for k in CAMPOS_SALVAR]
            _exec(
                [(f"INSERT INTO pacientes ({', '.join(cols)}) VALUES ({ph})", valores)],
                commit=True,
            )
        invalidar_cache_lista()
        return uid, None
    except Exception as e:
        return uid, str(e)


def gravar_evolucao(uid, texto_novo):
    """Acrescenta uma nova evolução ao histórico (separador |||), numa só ida ao banco."""
    _exec([(
        "UPDATE pacientes SET evolucao = "
        "CASE WHEN evolucao IS NULL OR evolucao = '' THEN %s "
        "ELSE evolucao || %s END WHERE uuid = %s",
        (texto_novo, SEPARADOR + texto_novo, uid),
    )], commit=True)


def salvar_historico_editado(uid, texto_visual):
    """Salva o histórico inteiro depois de editado na tela."""
    texto_banco = texto_visual.replace(LINHA_VISUAL, SEPARADOR)
    _exec([("UPDATE pacientes SET evolucao=%s WHERE uuid=%s", (texto_banco, uid))],
          commit=True)


def excluir_paciente(uid):
    _exec([
        ("DELETE FROM devedores WHERE paciente_uuid=%s", (uid,)),
        ("DELETE FROM pacientes WHERE uuid=%s", (uid,)),
    ], commit=True)
    invalidar_cache_lista()


def listar_retornos():
    """Pacientes que precisam de retorno, com data e anotação, ordenados por data."""
    return _exec([(
        "SELECT uuid, nome, data_retorno, texto_retorno FROM pacientes "
        "WHERE COALESCE(precisa_retorno, 0) = 1 "
        "ORDER BY data_retorno NULLS LAST, LOWER(nome)", None,
    )], fetch="all")


# ----------------------------------------------------------------------------
# GERAÇÃO DE PDF  (prontuário completo / histórico clínico / orçamento)
# ----------------------------------------------------------------------------
def _assinatura_profissional(usuario):
    u = (usuario or "").lower()
    if "valter" in u:
        return "Dr. Valter Macedo - CRO/RS 9357"
    if "victor" in u:
        return "Dr. Victor Rodrigues Macedo - CRO/RS 30750"
    if "natalia" in u:
        return "Dra. Natalia Macedo - CRO/RS 33912"
    return "Cirurgião-Dentista"


def gerar_pdf(tipo, dados, usuario):
    """Gera um PDF em memória. tipo: 'completo' | 'historico' | 'orcamento'.
    dados: dict com os campos do paciente."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as ImageRL, PageBreak,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2 * cm,
                            leftMargin=2 * cm, topMargin=1 * cm, bottomMargin=2 * cm)
    elementos = []
    estilos = getSampleStyleSheet()
    verde = colors.HexColor("#00897B")
    estilo_titulo = ParagraphStyle("T", parent=estilos["Heading1"], fontSize=20,
                                   textColor=verde, spaceAfter=2)
    estilo_sub = ParagraphStyle("S", parent=estilos["Heading2"], fontSize=12,
                                spaceBefore=14, textColor=colors.darkblue)
    estilo_normal = ParagraphStyle("N", parent=estilos["Normal"], fontSize=10, leading=14)

    # Cabeçalho com logo (se existir logo.png na pasta)
    titulo_txt = {"completo": "Prontuário Clínico",
                  "historico": "Histórico Clínico",
                  "orcamento": "Orçamento"}.get(tipo, "Documento")
    cabecalho_dir = [Paragraph("<b>ODONTO MACEDO</b>", estilo_titulo),
                     Paragraph(titulo_txt, estilo_normal)]
    if os.path.exists("logo.png"):
        try:
            ir = ImageReader("logo.png")
            lw, lh = ir.getSize()
            larg = 4.5 * cm
            alt = larg * (lh / float(lw))
            img = ImageRL("logo.png", width=larg, height=alt)
            t = Table([[img, cabecalho_dir]], colWidths=[5 * cm, 11 * cm])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            elementos.append(t)
        except Exception:
            elementos.extend(cabecalho_dir)
    else:
        elementos.extend(cabecalho_dir)
    elementos.append(Spacer(1, 14))

    # Dados do paciente
    def p(label, valor):
        return Paragraph(f"<b>{label}:</b> {valor or ''}", estilo_normal)

    linhas_dados = [
        [p("Paciente", dados.get("nome")), p("CPF", dados.get("cpf"))],
        [p("Nascimento", dados.get("nascimento")), p("Telefone", dados.get("telefone"))],
        [p("Endereço", dados.get("endereco")), p("Profissão", dados.get("profissao"))],
    ]
    td = Table(linhas_dados, colWidths=[10 * cm, 7 * cm])
    td.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(td)

    def bloco(titulo, texto):
        elementos.append(Paragraph(titulo, estilo_sub))
        txt = (texto or "").strip() or "—"
        elementos.append(Paragraph(txt.replace("\n", "<br/>"), estilo_normal))

    if tipo in ("completo", "historico"):
        if tipo == "completo":
            bloco("MOTIVO DA CONSULTA", dados.get("motivo"))
            bloco("HISTÓRICO DE SAÚDE", dados.get("historico_saude"))
        bloco("EVOLUÇÃO CLÍNICA", dados.get("evolucao"))

    if tipo in ("completo", "orcamento"):
        bloco("ORÇAMENTO / PLANO DE TRATAMENTO", dados.get("orcamento"))

    # Assinatura
    elementos.append(Spacer(1, 40))
    t_ass = Table([
        ["_______________________________", "_______________________________"],
        ["Assinatura do Paciente", _assinatura_profissional(usuario)],
    ], colWidths=[8 * cm, 8 * cm])
    t_ass.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"),
                               ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    elementos.append(t_ass)

    if tipo == "orcamento":
        elementos.append(Spacer(1, 20))
        elementos.append(Paragraph(
            "Este orçamento tem validade de 15 dias. Valores sujeitos a alteração "
            "conforme evolução clínica.",
            ParagraphStyle("sm", parent=estilos["Normal"], fontSize=8,
                           textColor=colors.grey, alignment=1)))

    doc.build(elementos)
    buffer.seek(0)
    return buffer.getvalue()


# ----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ----------------------------------------------------------------------------
def remover_acentos(texto):
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def cpf_valido(cpf):
    cpf = "".join(filter(str.isdigit, cpf or ""))
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = (soma * 10) % 11
    d1 = 0 if d1 == 10 else d1
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = (soma * 10) % 11
    d2 = 0 if d2 == 10 else d2
    return cpf[-2:] == f"{d1}{d2}"


def status_cpf(cpf_raw):
    cpf = "".join(filter(str.isdigit, cpf_raw or ""))
    if not cpf:
        return None
    if len(cpf) < 11:
        return ("warning", "CPF incompleto")
    if not cpf_valido(cpf):
        return ("error", "CPF inválido")
    return ("ok", "CPF válido")


def calcular_idade(d):
    """Retorna a idade em anos a partir de uma data de nascimento (date)."""
    if not d:
        return None
    hoje = date.today()
    idade = hoje.year - d.year - ((hoje.month, hoje.day) < (d.month, d.day))
    return idade if 0 <= idade <= 130 else None


def parse_data(s, padrao=None):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return padrao or date.today()


# ----------------------------------------------------------------------------
# CALLBACKS (rodam ANTES da tela ser redesenhada — por isso podem mexer
# nos campos do formulário com segurança)
# ----------------------------------------------------------------------------
def preencher_form(dados, uid):
    st.session_state.paciente_id = uid
    st.session_state.f_nome = dados.get("nome") or ""
    st.session_state.f_cpf = dados.get("cpf") or ""
    st.session_state.f_telefone = dados.get("telefone") or ""
    st.session_state.f_email = dados.get("email") or ""
    st.session_state.f_data_nascimento = parse_data(dados.get("data_nascimento"))
    st.session_state.f_endereco = dados.get("endereco") or ""
    st.session_state.f_profissao = dados.get("profissao") or ""
    st.session_state.f_como_conheceu = dados.get("como_conheceu") or ""
    st.session_state.f_observacoes = dados.get("observacoes") or ""
    st.session_state.f_motivo = dados.get("motivo") or ""
    st.session_state.f_historico = dados.get("historico") or ""
    st.session_state.f_orcamento = dados.get("orcamento") or ""
    st.session_state.f_precisa_retorno = bool(dados.get("precisa_retorno"))
    st.session_state.f_data_retorno = parse_data(dados.get("data_retorno"))
    st.session_state.f_texto_retorno = dados.get("texto_retorno") or ""
    ev = dados.get("evolucao") or ""
    st.session_state.f_historico_view = ev.replace(SEPARADOR, LINHA_VISUAL)
    st.session_state.f_nova_evolucao = ""


def cb_selecionar_paciente(uid):
    dados = carregar_paciente(uid) or {}
    preencher_form(dados, uid)


def cb_novo_paciente():
    branco = {
        "motivo": MODELO_MOTIVO,
        "historico": MODELO_HISTORICO,
        "orcamento": MODELO_FINANCEIRO,
        "texto_retorno": MODELO_RETORNO,
    }
    preencher_form(branco, None)
    st.session_state.flash = ("info", "Novo paciente iniciado. Preencha e clique em Salvar.")


def cb_inserir_template():
    nome_tpl = st.session_state.get("sel_template")
    if nome_tpl and nome_tpl in TEMPLATES:
        atual = st.session_state.get("f_nova_evolucao", "")
        st.session_state.f_nova_evolucao = atual + TEMPLATES[nome_tpl]


def cb_adicionar_data():
    agora = agora_br().strftime("%d/%m/%Y %H:%M")
    usuario = st.session_state.get("usuario", "Usuário")
    bloco = f"\n------------------\n{agora} – {usuario}\n"
    atual = st.session_state.get("f_nova_evolucao", "")
    st.session_state.f_nova_evolucao = atual + bloco


def cb_gravar_evolucao():
    uid = st.session_state.get("paciente_id")
    texto = (st.session_state.get("f_nova_evolucao") or "").strip()
    if not uid:
        st.session_state.flash = ("warning", "Salve o paciente antes de gravar a evolução.")
        return
    if not texto:
        st.session_state.flash = ("warning", "Escreva a evolução antes de gravar.")
        return
    gravar_evolucao(uid, texto)
    dados = carregar_paciente(uid) or {}
    preencher_form(dados, uid)
    st.session_state.flash = ("success", "Evolução gravada no histórico!")


# ----------------------------------------------------------------------------
# INÍCIO
# ----------------------------------------------------------------------------
def mostrar_logo(largura=None):
    if os.path.exists("logo.png"):
        if largura:
            st.image("logo.png", width=largura)
        else:
            st.image("logo.png", use_container_width=True)


def mostrar_logo_login():
    """Logo das telas de login: tamanho moderado e centralizado."""
    if os.path.exists("logo.png"):
        c = st.columns([1, 2, 1])
        with c[1]:
            st.image("logo.png", use_container_width=True)


# --- TELA DE SENHA (login simples) ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    mostrar_logo_login()
    st.title("🦷 Odonto Macedo")
    st.markdown("#### Acesso ao sistema")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        if senha and senha == st.secrets.get("app_password", ""):
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()

# Cria as tabelas uma única vez (não a cada tela) — isso já acelera bastante
inicializar_banco()

if "usuario" not in st.session_state:
    st.session_state.usuario = None

# --- ESCOLHA DO DENTISTA ---
if not st.session_state.usuario:
    mostrar_logo_login()
    st.title("🦷 Odonto Macedo")
    st.markdown("### Quem está usando?")
    escolha = st.selectbox("Usuário", USUARIOS)
    if st.button("Continuar", type="primary"):
        st.session_state.usuario = escolha
        cb_novo_paciente()  # começa com a ficha em branco
        st.rerun()
    st.stop()

# Garante que sempre exista uma ficha carregada
if "paciente_id" not in st.session_state:
    cb_novo_paciente()

# Processa ações pendentes (recarregar/novo paciente) ANTES de desenhar os campos.
# Isso evita o erro de "mexer num widget depois que ele já apareceu na tela".
if st.session_state.get("_acao_pendente"):
    acao = st.session_state.pop("_acao_pendente")
    if acao[0] == "recarregar":
        cb_selecionar_paciente(acao[1])
    elif acao[0] == "novo":
        cb_novo_paciente()
    fa = st.session_state.pop("_flash_apos", None)
    if fa:
        st.session_state.flash = fa

@st.dialog("🔔 Pacientes aguardando retorno")
def dialog_retornos():
    linhas = listar_retornos()
    if not linhas:
        st.write("Nenhum paciente aguardando retorno.")
        return
    st.caption(f"{len(linhas)} paciente(s):")
    for uid, nome, dret, txt in linhas:
        try:
            data_fmt = datetime.strptime(dret, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            data_fmt = ""
        rotulo = f"**{nome}**"
        if data_fmt:
            rotulo += f" — 📅 {data_fmt}"
        st.markdown(rotulo)
        if txt and txt.strip():
            st.caption(txt.strip())
        if st.button("Abrir ficha", key=f"ret_open_{uid}"):
            st.session_state._acao_pendente = ("recarregar", uid)
            st.rerun()
        st.divider()


# --- BARRA LATERAL: usuário, busca e lista de pacientes ---
with st.sidebar:
    mostrar_logo()
    st.markdown(f"**👤 {st.session_state.usuario}**")
    if st.button("Sair", use_container_width=True):
        st.session_state.usuario = None
        st.rerun()

    st.button("➕ Novo paciente", use_container_width=True, on_click=cb_novo_paciente)
    if st.button("🔄 Atualizar lista", use_container_width=True):
        invalidar_cache_lista()
        st.rerun()
    st.text_input("🔍 Buscar paciente", key="busca", placeholder="Nome ou parte do nome")
    st.divider()

    pacientes = listar_pacientes(st.session_state.get("busca", ""))
    total = len(pacientes)
    LIMITE = 40  # quantos botões mostrar por vez (evita travar com muitos pacientes)

    qtd_retorno = sum(1 for _, _, ret in carregar_lista_cache() if ret)
    st.caption(f"{total} paciente(s) encontrado(s)")
    if qtd_retorno:
        if st.button(f"🔔 {qtd_retorno} aguardando retorno", use_container_width=True):
            dialog_retornos()
    if total > LIMITE:
        st.caption(f"Mostrando os primeiros {LIMITE}. Digite na busca acima para achar os demais.")

    paciente_atual = st.session_state.get("paciente_id")
    for uid, nome, ret in pacientes[:LIMITE]:
        rotulo = f"🔔 {nome}" if ret else nome
        st.button(
            rotulo,
            key=f"pac_{uid}",
            use_container_width=True,
            type="primary" if uid == paciente_atual else "secondary",
            on_click=cb_selecionar_paciente,
            args=(uid,),
        )

# --- MENSAGENS (flash) ---
flash = st.session_state.pop("flash", None)
if flash:
    tipo, msg = flash
    getattr(st, tipo if tipo in ("success", "warning", "error", "info") else "info")(msg)

# --- CABEÇALHO ---
nome_atual = st.session_state.get("f_nome", "").strip()
if st.session_state.get("paciente_id"):
    st.title(nome_atual or "Paciente sem nome")
else:
    st.title("➕ Novo paciente")

# --- ABAS ---
aba_cad, aba_pront, aba_orc, aba_ret, aba_pdf = st.tabs(
    ["📋 Cadastro & Anamnese", "🦷 Prontuário / Evolução", "💰 Orçamento",
     "🔁 Retorno", "📄 Gerar PDF"]
)

# ===== ABA 1: CADASTRO & ANAMNESE =====
with aba_cad:
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nome *", key="f_nome")
        st.text_input("CPF", key="f_cpf")
        s = status_cpf(st.session_state.get("f_cpf", ""))
        if s:
            tipo, txt = s
            if tipo == "ok":
                st.caption(f"✅ {txt}")
            elif tipo == "warning":
                st.caption(f"🟠 {txt}")
            else:
                st.caption(f"🔴 {txt}")
        st.text_input("Telefone", key="f_telefone")
        st.text_input("E-mail", key="f_email")
        st.date_input(
            "Data de nascimento", key="f_data_nascimento",
            min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY",
        )
        _idade = calcular_idade(st.session_state.get("f_data_nascimento"))
        if _idade is not None:
            st.caption(f"🎂 Idade: {_idade} anos")
    with col2:
        st.text_input("Endereço", key="f_endereco")
        st.text_input("Profissão", key="f_profissao")
        st.text_input("Como conheceu", key="f_como_conheceu")
        st.text_area("Observações", key="f_observacoes", height=120)

    st.divider()
    st.markdown("#### Anamnese")
    col3, col4 = st.columns(2)
    with col3:
        st.text_area("Motivo da consulta", key="f_motivo", height=160)
    with col4:
        st.text_area("Histórico de saúde", key="f_historico", height=160)

# ===== ABA 2: PRONTUÁRIO / EVOLUÇÃO =====
with aba_pront:
    st.markdown("#### Histórico de evolução")
    st.text_area(
        "Histórico (pode editar e salvar)", key="f_historico_view", height=260,
        help="Registros antigos separados por linhas. Edite se precisar corrigir.",
    )
    col_h1, col_h2 = st.columns([1, 3])
    with col_h1:
        if st.button("💾 Salvar edição do histórico"):
            uid = st.session_state.get("paciente_id")
            if not uid:
                st.warning("Salve o paciente primeiro.")
            else:
                salvar_historico_editado(uid, st.session_state.get("f_historico_view", ""))
                st.session_state._acao_pendente = ("recarregar", uid)
                st.session_state._flash_apos = ("success", "Histórico atualizado!")
                st.rerun()

    st.divider()
    st.markdown("#### Nova evolução")
    col_t1, col_t2, col_t3 = st.columns([3, 1, 1])
    with col_t1:
        st.selectbox("Modelo de procedimento", options=list(TEMPLATES.keys()), key="sel_template")
    with col_t2:
        st.write("")
        st.write("")
        st.button("➕ Inserir modelo", on_click=cb_inserir_template, use_container_width=True)
    with col_t3:
        st.write("")
        st.write("")
        st.button("🕐 Data/hora", on_click=cb_adicionar_data, use_container_width=True)

    st.text_area("Escreva a evolução de hoje", key="f_nova_evolucao", height=200)
    st.button("✅ Gravar evolução", type="primary", on_click=cb_gravar_evolucao)

# ===== ABA 3: ORÇAMENTO =====
with aba_orc:
    st.text_area("Orçamento / Plano de tratamento", key="f_orcamento", height=300)

# ===== ABA 4: RETORNO =====
with aba_ret:
    st.checkbox("Este paciente precisa de retorno", key="f_precisa_retorno")
    st.date_input(
        "Data do retorno", key="f_data_retorno",
        min_value=date(1900, 1, 1), max_value=date(2100, 1, 1), format="DD/MM/YYYY",
    )
    st.text_area("Anotações do retorno", key="f_texto_retorno", height=160)

# ===== ABA 5: GERAR PDF =====
with aba_pdf:
    uid_pdf = st.session_state.get("paciente_id")
    if not uid_pdf:
        st.info("Salve o paciente primeiro para gerar o PDF.")
    else:
        tipo_label = st.radio(
            "Qual documento?",
            ["Prontuário completo", "Só histórico clínico", "Só orçamento"],
        )
        mapa = {"Prontuário completo": "completo",
                "Só histórico clínico": "historico",
                "Só orçamento": "orcamento"}
        tipo = mapa[tipo_label]

        if st.button("📄 Gerar PDF", type="primary"):
            dados_pdf = {
                "nome": st.session_state.get("f_nome", ""),
                "cpf": st.session_state.get("f_cpf", ""),
                "nascimento": st.session_state.get("f_data_nascimento").strftime("%d/%m/%Y")
                if st.session_state.get("f_data_nascimento") else "",
                "telefone": st.session_state.get("f_telefone", ""),
                "endereco": st.session_state.get("f_endereco", ""),
                "profissao": st.session_state.get("f_profissao", ""),
                "motivo": st.session_state.get("f_motivo", ""),
                "historico_saude": st.session_state.get("f_historico", ""),
                "evolucao": st.session_state.get("f_historico_view", ""),
                "orcamento": st.session_state.get("f_orcamento", ""),
            }
            try:
                pdf_bytes = gerar_pdf(tipo, dados_pdf, st.session_state.get("usuario"))
                nome_limpo = "".join(ch for ch in dados_pdf["nome"]
                                     if ch.isalnum() or ch == " ").strip().replace(" ", "_")
                st.session_state.pdf_pronto = (
                    f"{tipo}_{nome_limpo or 'paciente'}.pdf", pdf_bytes
                )
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")

        if st.session_state.get("pdf_pronto"):
            nome_arq, conteudo = st.session_state.pdf_pronto
            st.download_button("⬇️ Baixar PDF", data=conteudo, file_name=nome_arq,
                               mime="application/pdf")

# --- AÇÕES PRINCIPAIS (rodapé) ---
st.divider()
col_a, col_b, _ = st.columns([1, 1, 3])
with col_a:
    if st.button("💾 Salvar paciente", type="primary", use_container_width=True):
        nome = st.session_state.get("f_nome", "").strip()
        if not nome:
            st.warning("O nome do paciente é obrigatório.")
        else:
            cpf_raw = st.session_state.get("f_cpf", "")
            cpf_limpo = "".join(filter(str.isdigit, cpf_raw))
            dados = {
                "nome": nome,
                "cpf": cpf_raw if cpf_limpo else None,
                "telefone": st.session_state.get("f_telefone", ""),
                "email": st.session_state.get("f_email", ""),
                "data_nascimento": st.session_state.get("f_data_nascimento").strftime("%Y-%m-%d"),
                "endereco": st.session_state.get("f_endereco", ""),
                "profissao": st.session_state.get("f_profissao", ""),
                "como_conheceu": st.session_state.get("f_como_conheceu", ""),
                "observacoes": st.session_state.get("f_observacoes", ""),
                "motivo": st.session_state.get("f_motivo", ""),
                "historico": st.session_state.get("f_historico", ""),
                "orcamento": st.session_state.get("f_orcamento", ""),
                "precisa_retorno": 1 if st.session_state.get("f_precisa_retorno") else 0,
                "data_retorno": st.session_state.get("f_data_retorno").strftime("%Y-%m-%d"),
                "texto_retorno": st.session_state.get("f_texto_retorno", ""),
            }
            novo_uid, erro = salvar_paciente(st.session_state.get("paciente_id"), dados)
            if erro:
                if "UNIQUE" in erro and "cpf" in erro:
                    st.error("Já existe um paciente com este CPF.")
                else:
                    st.error(f"Erro ao salvar: {erro}")
            else:
                st.session_state._acao_pendente = ("recarregar", novo_uid)
                st.session_state._flash_apos = ("success", "Cadastro salvo com sucesso!")
                st.rerun()

with col_b:
    if st.session_state.get("paciente_id"):
        if st.button("🗑️ Excluir paciente", use_container_width=True):
            st.session_state.confirmar_exclusao = True
            st.session_state.txt_conf_excluir = ""  # limpa confirmação anterior

if st.session_state.get("confirmar_exclusao"):
    nome_excluir = (st.session_state.get("f_nome") or "este paciente").strip()
    st.warning(
        f"⚠️ Você está prestes a excluir **{nome_excluir}**. "
        "Esta ação **não pode ser desfeita** e apaga todo o histórico deste paciente."
    )
    st.text_input(
        'Para confirmar, digite **EXCLUIR** (em maiúsculas):',
        key="txt_conf_excluir", placeholder="EXCLUIR",
    )
    pode_excluir = st.session_state.get("txt_conf_excluir", "").strip() == "EXCLUIR"
    c1, c2, _ = st.columns([1, 1, 4])
    if c1.button("Sim, excluir", disabled=not pode_excluir):
        excluir_paciente(st.session_state.get("paciente_id"))
        st.session_state.confirmar_exclusao = False
        st.session_state._acao_pendente = ("novo",)
        st.session_state._flash_apos = ("success", "Paciente excluído.")
        st.rerun()
    if c2.button("Cancelar"):
        st.session_state.confirmar_exclusao = False
        st.rerun()
