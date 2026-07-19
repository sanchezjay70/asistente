import streamlit as st
import zipfile, json, os, re, io, hashlib
from pathlib import Path
import google.genai as genai
from google.genai import types
import PyPDF2

# Librerías de Google Drive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ══════════════════════════════════════════════════════════════════
# 1. CONFIGURACIÓN DE PÁGINA
# ══════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Luz de la Palabra", page_icon="📖", layout="wide", initial_sidebar_state="expanded")

# ══════════════════════════════════════════════════════════════════
# 2. DISEÑO VISUAL — TEMA CLARO
# ══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Merriweather:ital,wght@0,300;0,700;1,300&display=swap');

html, body, .stApp {
    background: #F7F8FA;
    font-family: 'Inter', sans-serif;
    color: #1E293B;
}

section[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E5E9F0;
}

.hero {
    background: linear-gradient(135deg, #1E293B 0%, #334155 100%);
    padding: 2.4rem 2rem;
    border-radius: 20px;
    text-align: center;
    margin-bottom: 1.5rem;
    color: white;
    box-shadow: 0 15px 35px rgba(30,41,59,0.15);
}
.hero h1 {
    font-family: 'Merriweather', serif;
    font-size: 2.3rem;
    margin-bottom: 0.4rem;
    color: #F1E5B0 !important;
}
.hero p { color: #CBD5E1; font-size: 1rem; margin: 0; }

.chat-user {
    background: #2563EB;
    color: white;
    padding: 1.1rem 1.5rem;
    border-radius: 20px 20px 5px 20px;
    margin: 1rem 0 1rem 15%;
    font-size: 1.02rem;
    line-height: 1.5;
    box-shadow: 0 4px 12px rgba(37,99,235,0.2);
}
.chat-ai {
    background: #FFFFFF;
    color: #1E293B;
    padding: 1.5rem 1.6rem;
    border-radius: 5px 20px 20px 20px;
    margin: 1rem 15% 1rem 0;
    border: 1px solid #E5E9F0;
    font-size: 1.02rem;
    line-height: 1.75;
    box-shadow: 0 4px 16px rgba(15,23,42,0.06);
}
.chat-ai strong { color: #0F172A; }
.chat-ai h1, .chat-ai h2, .chat-ai h3 { color: #1E3A8A; }

.status-badge {
    display: inline-block;
    padding: 0.35rem 1.1rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 1.2rem;
    border: 1px solid;
}
.status-ok   { background: #DEF7EC; color: #03543F; border-color: #31C48D; }
.status-warn { background: #FEF3C7; color: #92400E; border-color: #F59E0B; }

.source-tag {
    display: inline-block;
    background: #EEF2FF;
    border: 1px solid #C7D2FE;
    color: #3730A3;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.78rem;
    margin: 0.15rem 0.2rem 0.6rem 0;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# 3. CONFIGURACIÓN Y SEGURIDAD
# ══════════════════════════════════════════════════════════════════
APP_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
CFG_FILE = APP_DIR / ".luz_cfg.json"
PUBS_DIR = APP_DIR / "mis_publicaciones"
PUBS_DIR.mkdir(exist_ok=True)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_NAME = "Mis Publicaciones"
STOPWORDS = {"que", "con", "los", "las", "del", "una", "por", "para", "como", "son", "era", "fue", "esta", "este"}


def load_cfg():
    if CFG_FILE.exists():
        try:
            return json.loads(CFG_FILE.read_text())
        except Exception:
            pass
    return {"gemini_key": "", "password": "estudio2026"}


def save_cfg(c):
    CFG_FILE.write_text(json.dumps(c, indent=2))


if "cfg" not in st.session_state:
    st.session_state.cfg = load_cfg()
cfg = st.session_state.cfg

GEMINI_KEY_ENV = os.environ.get("GEMINI_API_KEY", "")

if "debug_log" not in st.session_state:
    st.session_state.debug_log = []


def log_debug(msg):
    st.session_state.debug_log.append(msg)


# ══════════════════════════════════════════════════════════════════
# 4. BARRA LATERAL
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 📖 Luz de la Palabra")

    if not st.session_state.get("auth", False):
        pwd = st.text_input("Contraseña de Acceso:", type="password")
        if st.button("Entrar", use_container_width=True):
            if pwd == cfg.get("password", "estudio2026"):
                st.session_state.auth = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
        st.stop()

    key = GEMINI_KEY_ENV or cfg.get("gemini_key", "")
    with st.expander("🔑 Configuración de Gemini"):
        if GEMINI_KEY_ENV:
            st.caption("✅ Usando GEMINI_API_KEY desde variable de entorno.")
        else:
            st.caption("⚠️ Recomendado: define GEMINI_API_KEY como variable de entorno en vez de guardarla en disco.")
        nk = st.text_input("Clave API (respaldo local):", type="password")
        if st.button("Guardar Clave"):
            cfg["gemini_key"] = nk
            save_cfg(cfg)
            st.session_state.cfg = cfg
            st.success("✅ Guardada")
            st.rerun()

    with st.expander("🔒 Cambiar contraseña de acceso"):
        np1 = st.text_input("Nueva contraseña", type="password", key="np1")
        np2 = st.text_input("Confirmar contraseña", type="password", key="np2")
        if st.button("Actualizar contraseña"):
            if np1 and np1 == np2:
                cfg["password"] = np1
                save_cfg(cfg)
                st.session_state.cfg = cfg
                st.success("✅ Contraseña actualizada")
            else:
                st.error("Las contraseñas no coinciden o están vacías")

    if not key:
        st.warning("⚠️ Configura tu clave de Gemini para empezar.")
        st.stop()

    with st.expander("🛠️ Diagnóstico"):
        if st.session_state.debug_log:
            for entry in st.session_state.debug_log[-20:]:
                st.text(entry)
        else:
            st.caption("Sin incidencias registradas.")
        if st.button("Limpiar registro"):
            st.session_state.debug_log = []
            st.rerun()

    st.markdown("---")
    if st.button("🗑️ Nueva conversación", use_container_width=True):
        st.session_state.hist = []
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# 5. UTILIDADES DE TEXTO
# ══════════════════════════════════════════════════════════════════
def _limpiar_html(texto):
    if not texto:
        return ""
    texto = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', texto, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r'<[^>]+>', ' ', texto)
    texto = re.sub(r'&nbsp;', ' ', texto)
    texto = re.sub(r'&amp;', '&', texto)
    texto = re.sub(r'&[a-z]+;', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def _extraer_titulo_html(html):
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if m:
        t = _limpiar_html(m.group(1))
        if t:
            return t
    m = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.IGNORECASE | re.DOTALL)
    if m:
        t = _limpiar_html(m.group(1))
        if t:
            return t
    return None


# ══════════════════════════════════════════════════════════════════
# 6. SINCRONIZACIÓN AUTOMÁTICA CON DRIVE (EPUB + PDF)
# ══════════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def auto_sincronizar():
    try:
        if "google_credentials" not in st.secrets:
            log_debug("[sync] No hay 'google_credentials' en st.secrets.")
            return False
        info = json.loads(st.secrets["google_credentials"])
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)

        results = service.files().list(
            q=f"mimeType='application/vnd.google-apps.folder' and name='{FOLDER_NAME}' and trashed=false",
            fields="files(id, name)"
        ).execute()
        items = results.get('files', [])
        if not items:
            log_debug(f"[sync] No se encontró la carpeta '{FOLDER_NAME}' en Drive.")
            return False

        archivos_drive = service.files().list(
            q=f"'{items[0]['id']}' in parents and trashed=false and (name contains '.epub' or name contains '.pdf')",
            fields="files(id, name)"
        ).execute()

        descargados = 0
        for arch in archivos_drive.get('files', []):
            nombre = arch['name']
            if not (nombre.lower().endswith('.epub') or nombre.lower().endswith('.pdf')):
                continue
            try:
                dest = PUBS_DIR / nombre
                if not dest.exists():
                    req = service.files().get_media(fileId=arch['id'])
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, req)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                    dest.write_bytes(fh.getvalue())
                    descargados += 1
            except Exception as e:
                log_debug(f"[sync] Error descargando '{nombre}': {e}")

        log_debug(f"[sync] Sincronización OK. Archivos nuevos: {descargados}")
        return True
    except Exception as e:
        log_debug(f"[sync] Falló la sincronización: {e}")
        return False


n_epub_local = len(list(PUBS_DIR.glob("*.epub")))
n_pdf_local = len(list(PUBS_DIR.glob("*.pdf")))

sincronizar_con_drive = st.sidebar.toggle(
    "🔄 Sincronizar con Drive al iniciar",
    value=cfg.get("sincronizar_con_drive", n_epub_local + n_pdf_local == 0),
    help="Si ya tienes tus publicaciones guardadas localmente, puedes apagar esto para que la app abra más rápido."
)
if sincronizar_con_drive != cfg.get("sincronizar_con_drive"):
    cfg["sincronizar_con_drive"] = sincronizar_con_drive
    save_cfg(cfg)
    st.session_state.cfg = cfg

is_synced = auto_sincronizar() if sincronizar_con_drive else False

st.sidebar.file_uploader(
    "O arrastra aquí tus .epub / .pdf directamente",
    type=["epub", "pdf"],
    accept_multiple_files=True,
    key="uploader_manual",
    help="Alternativa a Drive: coloca tus publicaciones directamente."
)
if st.session_state.get("uploader_manual"):
    for f in st.session_state["uploader_manual"]:
        destino = PUBS_DIR / f.name
        if not destino.exists():
            destino.write_bytes(f.getbuffer())


# ══════════════════════════════════════════════════════════════════
# 7. BÚSQUEDA HÍBRIDA (EPUB Y PDF) — ESCANEA TODAS LAS PUBLICACIONES
# ══════════════════════════════════════════════════════════════════
# Diseño: primero se recopilan TODAS las coincidencias de TODOS los archivos
# (sin detenerse temprano), cada una con un puntaje de relevancia. Luego se
# arma el contexto final repartiendo espacio en round-robin entre archivos
# distintos, para que ninguna publicación agote el presupuesto y deje a las
# demás sin oportunidad de aparecer.

MAX_COINCIDENCIAS_POR_ARCHIVO = 3   # tope de fragmentos que se toman de una misma publicación
MAX_CHARS_POR_FRAGMENTO = 1400      # tamaño de cada fragmento citado


def _puntaje_relevancia(texto_lower, palabras):
    return sum(texto_lower.count(p) for p in palabras)


def _manifest_actual():
    """Nombre + fecha de modificación de cada archivo, para saber si el corpus cacheado sigue vigente."""
    archivos = sorted(PUBS_DIR.glob("*.epub")) + sorted(PUBS_DIR.glob("*.pdf"))
    return {p.name: p.stat().st_mtime for p in archivos}


def _hash_manifest(manifest):
    s = json.dumps(manifest, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()


def _extraer_secciones_epub(epub_path):
    """Lee y limpia UNA vez el HTML de cada sección del EPUB. No busca nada, solo extrae texto."""
    secciones = []
    try:
        with zipfile.ZipFile(epub_path) as z:
            nombres_html = [
                n for n in z.namelist()
                if n.lower().endswith(('.xhtml', '.html', '.htm')) and not n.startswith('__MACOSX')
            ]
            if not nombres_html:
                log_debug(f"[epub] {epub_path.name}: no se hallaron archivos HTML/XHTML dentro.")
                return secciones
            for nombre_html in nombres_html:
                try:
                    data = z.read(nombre_html).decode('utf-8', errors='ignore')
                except Exception as e:
                    log_debug(f"[epub] Error leyendo {nombre_html} en {epub_path.name}: {e}")
                    continue
                texto_limpio = _limpiar_html(data)
                if not texto_limpio:
                    continue
                titulo = _extraer_titulo_html(data) or nombre_html
                secciones.append({"titulo": titulo, "texto": texto_limpio})
    except zipfile.BadZipFile:
        log_debug(f"[epub] {epub_path.name} no es un EPUB/ZIP válido.")
    except Exception as e:
        log_debug(f"[epub] Error general con {epub_path.name}: {e}")
    return secciones


def _extraer_paginas_pdf(pdf_path):
    """Lee UNA vez el texto de cada página del PDF. No busca nada, solo extrae texto."""
    paginas = []
    try:
        lector = PyPDF2.PdfReader(pdf_path)
        for i, pag in enumerate(lector.pages):
            texto = pag.extract_text()
            if texto:
                paginas.append({"titulo": f"{pdf_path.name} · página {i + 1}", "texto": texto})
    except Exception as e:
        log_debug(f"[busqueda] Error leyendo PDF {pdf_path.name}: {e}")
    return paginas


@st.cache_resource(show_spinner="Preparando tus publicaciones (solo la primera vez o si agregaste archivos nuevos)...")
def _extraer_corpus(_manifest_hash):
    """Extrae y limpia el texto de TODAS las publicaciones UNA sola vez por cada versión de tus archivos.
    _manifest_hash cambia si agregas/quitas/modificas archivos, y eso invalida el caché automáticamente."""
    corpus_epub = []
    for epub_file in sorted(PUBS_DIR.glob("*.epub")):
        corpus_epub.append({"archivo": epub_file.stem, "secciones": _extraer_secciones_epub(epub_file)})
    corpus_pdf = []
    for pdf_file in sorted(PUBS_DIR.glob("*.pdf")):
        corpus_pdf.append({"archivo": pdf_file.stem, "secciones": _extraer_paginas_pdf(pdf_file)})
    total_secciones = sum(len(c["secciones"]) for c in corpus_epub) + sum(len(c["secciones"]) for c in corpus_pdf)
    log_debug(f"[corpus] Extraído: {len(corpus_epub)} EPUB + {len(corpus_pdf)} PDF, {total_secciones} secciones/páginas en total.")
    return corpus_epub, corpus_pdf


def _candidatos_de_secciones(archivo_stem, secciones, palabras):
    """Solo puntúa texto YA extraído y limpio — sin tocar disco, por eso es rápido."""
    candidatos = []
    for sec in secciones:
        texto_lower = sec["texto"].lower()
        score = _puntaje_relevancia(texto_lower, palabras)
        if score > 0:
            candidatos.append({
                "score": score,
                "titulo": sec["titulo"],
                "archivo": archivo_stem,
                "texto": sec["texto"][:MAX_CHARS_POR_FRAGMENTO],
            })
    candidatos.sort(key=lambda c: -c["score"])
    return candidatos[:MAX_COINCIDENCIAS_POR_ARCHIVO]


def _ensamblar_round_robin(candidatos, max_chars):
    """Reparte el presupuesto de caracteres en rondas entre archivos distintos,
    para que ninguno acapare todo el espacio a costa de los demás."""
    por_archivo = {}
    for c in candidatos:
        por_archivo.setdefault(c["archivo"], []).append(c)
    for lst in por_archivo.values():
        lst.sort(key=lambda c: -c["score"])

    resultado = ""
    archivos_activos = list(por_archivo.keys())
    while archivos_activos and len(resultado) < max_chars:
        progreso = False
        for archivo in list(archivos_activos):
            lst = por_archivo[archivo]
            if not lst:
                archivos_activos.remove(archivo)
                continue
            c = lst.pop(0)
            resultado += f"--- {c['titulo']} (de {c['archivo']}) ---\n{c['texto']}\n\n"
            progreso = True
            if len(resultado) >= max_chars:
                break
        if not progreso:
            break
    return resultado.strip()


def buscar_en_neuronas(consulta, max_chars_epub=10000, max_chars_pdf=6000):
    palabras = [w for w in re.split(r'\W+', consulta.lower()) if len(w) >= 3 and w not in STOPWORDS][:8]
    if not palabras:
        return "", ""

    manifest_hash = _hash_manifest(_manifest_actual())
    corpus_epub, corpus_pdf = _extraer_corpus(manifest_hash)

    candidatos_epub = []
    for item in corpus_epub:
        candidatos_epub.extend(_candidatos_de_secciones(item["archivo"], item["secciones"], palabras))

    candidatos_pdf = []
    for item in corpus_pdf:
        candidatos_pdf.extend(_candidatos_de_secciones(item["archivo"], item["secciones"], palabras))

    archivos_con_match_epub = {c["archivo"] for c in candidatos_epub}
    log_debug(f"[busqueda] Publicaciones EPUB con coincidencia: {len(archivos_con_match_epub)} de {len(corpus_epub)}")

    res_epub = _ensamblar_round_robin(candidatos_epub, max_chars_epub)
    res_pdf = _ensamblar_round_robin(candidatos_pdf, max_chars_pdf)

    return res_epub, res_pdf


# ══════════════════════════════════════════════════════════════════
# 8. PROMPT MAESTRO
# ══════════════════════════════════════════════════════════════════
instrucciones = """Eres 'Luz de la Palabra', un asistente experto en oratoria, enseñanza y la preparación de comentarios y discursos, alineado con las publicaciones de los testigos de Jehová.

Tu objetivo es ayudar al usuario a preparar sus asignaciones de forma estructurada, profunda y efectiva.

INSTRUCCIONES ESTRICTAS DE COMPORTAMIENTO:

1. FUENTE DE INFORMACIÓN (REGLA DE ORO):
   Se te proporcionará contexto extraído directamente de las publicaciones del usuario (EPUB y/o PDF).
   - Si el contexto incluye TEXTO REAL extraído de una publicación, ese texto es tu fuente principal y autoritativa. Básate en él y cita el título exacto y, si es PDF, la página.
   - Si no se encontró contexto relevante para la pregunta, dilo explícitamente y responde con conocimiento general, aclarándolo como tal.
   - Nunca presentes conocimiento general como si fuera una cita textual de una publicación específica.

2. ANÁLISIS PROFUNDO DE CAPÍTULOS O RELATOS:
   Estructura tu respuesta respondiendo a:
   - CONTEXTO: ¿Quién escribió esto, para quién y en qué circunstancias?
   - SOBRE JEHOVÁ Y SU PROPÓSITO: ¿Qué enseña sobre Jehová? ¿Qué espera él de nosotros?
   - LECCIONES DE LOS PERSONAJES: ¿Qué cualidades mostraron y por qué imitarlas?
   - APLICACIÓN Y MINISTERIO: ¿Cómo aplicar esto en mi vida y ministerio?

3. CÓMO ESTUDIAR E INVESTIGAR PARA SACAR "PERLAS":
   - Busca y destaca: cualidades divinas, principios bíblicos prácticos y lecciones para el ministerio.

4. COMENTARIOS DE 30 SEGUNDOS:
   - Redacta una respuesta de unas 60-75 palabras. Directa y sencilla.

5. DESARROLLO DE BOSQUEJOS Y DISCURSOS (ESTRUCTURA OBLIGATORIA):
   - Introducción: Crea aperturas que despierten interés.
   - Desarrollo:
      a) EXPLICAR: Aclarar el significado.
      b) ILUSTRAR: Usar comparaciones o ejemplos cotidianos.
      c) APLICAR: Mostrar cómo poner en práctica en la vida diaria.
   - Conclusión: Breve, que motive a la acción.

6. FUENTES Y REFERENCIAS (OBLIGATORIO):
   Al final de CADA respuesta, coloca la fuente exacta: título de la publicación y, si aplica, página/párrafo. Si parte de la respuesta es conocimiento general (no extraído del contexto), acláralo por separado.

7. TONO Y ESTILO:
   - Usa preguntas retóricas.
   - Mantén un tono amable, animador, edificante y respetuoso. Usa negritas y viñetas."""


def preguntar_gemini(historial, pregunta, ctx_epub, ctx_pdf):
    try:
        cliente = genai.Client(api_key=key)
        contents = [
            types.Content(role="user" if m["r"] == "u" else "model", parts=[types.Part(text=re.sub('<[^<]+?>', '', m["t"]))])
            for m in historial
        ]

        prompt_final = pregunta
        if ctx_epub or ctx_pdf:
            prompt_final += "\n\n--- RECURSOS ENCONTRADOS EN TU MEMORIA (DRIVE) ---\n"
            if ctx_epub:
                prompt_final += f"\n📚 TEXTO EXTRAÍDO DE TUS PUBLICACIONES EPUB:\n{ctx_epub}\n"
            if ctx_pdf:
                prompt_final += f"\n📄 TEXTO EXACTO DE TUS PDF (cita párrafo o página):\n{ctx_pdf}\n"
        else:
            prompt_final += "\n\n[No se encontró contexto extraído en tus publicaciones locales para esta consulta. Responde con conocimiento general y acláralo.]"

        contents.append(types.Content(role="user", parts=[types.Part(text=prompt_final)]))
        resp = cliente.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.3, system_instruction=instrucciones)
        )
        return resp.text, bool(ctx_epub or ctx_pdf)
    except Exception as e:
        log_debug(f"[gemini] {e}")
        return f"❌ Error de conexión: {str(e)}", False


# ══════════════════════════════════════════════════════════════════
# 9. INTERFAZ VISUAL
# ══════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="hero"><h1>📖 Luz de la Palabra</h1>'
    '<p>Tu asistente bíblico personal, basado en tus propias publicaciones</p></div>',
    unsafe_allow_html=True
)

n_epub = len(list(PUBS_DIR.glob("*.epub")))
n_pdf = len(list(PUBS_DIR.glob("*.pdf")))

if is_synced:
    st.markdown(
        f'<div class="status-badge status-ok">✅ Conectado con Google Drive · {n_epub} publicaciones EPUB · {n_pdf} PDF</div>',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        f'<div class="status-badge status-warn">⚠️ Sin conexión a Drive · usando {n_epub} EPUB y {n_pdf} PDF ya guardados localmente</div>',
        unsafe_allow_html=True
    )

# ══════════════════════════════════════════════════════════════════
# 10. CHAT PRINCIPAL
# ══════════════════════════════════════════════════════════════════
if "hist" not in st.session_state:
    st.session_state.hist = []

for msg in st.session_state.hist:
    clase = "chat-user" if msg["r"] == "u" else "chat-ai"
    st.markdown(f'<div class="{clase}">{msg["t"]}</div>', unsafe_allow_html=True)

if q := st.chat_input("Escribe tu pregunta bíblica..."):
    st.session_state.hist.append({"r": "u", "t": q})
    st.markdown(f'<div class="chat-user">{q}</div>', unsafe_allow_html=True)

    with st.spinner("Investigando en tus publicaciones..."):
        ctx_epub, ctx_pdf = buscar_en_neuronas(q)
        historial_previo = st.session_state.hist[:-1]
        resp, tuvo_contexto = preguntar_gemini(historial_previo, q, ctx_epub, ctx_pdf)

    if tuvo_contexto:
        resp = '<span class="source-tag">📚 Basado en tus publicaciones</span><br><br>' + resp
    else:
        resp = '<span class="source-tag">🧠 Conocimiento general</span><br><br>' + resp

    st.session_state.hist.append({"r": "a", "t": resp})
    st.markdown(f'<div class="chat-ai">{resp}</div>', unsafe_allow_html=True)
    st.rerun()
