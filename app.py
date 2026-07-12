import streamlit as st
import sqlite3, zipfile, json, os, re, io
from pathlib import Path
import google.genai as genai
from google.genai import types
import PyPDF2

# Librerías de Google Drive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="Luz de la Palabra", page_icon="📖", layout="wide", initial_sidebar_state="expanded")

# 2. DISEÑO VISUAL (Moderno pero seguro, sin dañar la caja de texto)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Merriweather:ital,wght@0,300;0,700;1,300&display=swap');
html, body, .stApp { background-color: #F8FAFC; font-family: 'Inter', sans-serif; }
.hero { background: linear-gradient(135deg, #1E293B 0%, #334155 100%); padding: 2rem; border-radius: 16px; text-align: center; margin-bottom: 2rem; color: white; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
.hero h1 { font-family: 'Merriweather', serif; font-size: 2.2rem; margin-bottom: 0.5rem; color: white !important; }
.chat-user { background-color: #2563EB; color: white; padding: 1.2rem 1.5rem; border-radius: 20px 20px 5px 20px; margin: 1rem 0 1rem 15%; font-size: 1.05rem; line-height: 1.5; box-shadow: 0 4px 6px rgba(37,99,235,0.2); }
.chat-ai { background-color: white; color: #1E293B; padding: 1.5rem; border-radius: 5px 20px 20px 20px; margin: 1rem 15% 1rem 0; border: 1px solid #E2E8F0; font-size: 1.05rem; line-height: 1.7; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
.chat-ai strong { color: #0F172A; }
.status-badge { display: inline-block; padding: 0.3rem 1rem; border-radius: 999px; font-size: 0.85rem; font-weight: 600; background: #DEF7EC; color: #03543F; border: 1px solid #31C48D; margin-bottom: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ── Configuración y Seguridad (¡Restaurado!) ─────────────────────────
APP_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
CFG_FILE = APP_DIR / ".luz_cfg.json"
PUBS_DIR = APP_DIR / "mis_publicaciones"
PUBS_DIR.mkdir(exist_ok=True)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_NAME = "Mis Publicaciones"
STOPWORDS = {"que","con","los","las","del","una","por","para","como","son","era","fue"}

def load_cfg():
    if CFG_FILE.exists():
        try: return json.loads(CFG_FILE.read_text())
        except: pass
    return {"gemini_key":"","password":"estudio2026"}

def save_cfg(c): CFG_FILE.write_text(json.dumps(c, indent=2))

if "cfg" not in st.session_state: st.session_state.cfg = load_cfg()
cfg = st.session_state.cfg

# ── BARRA LATERAL: CLAVES Y SEGURIDAD (¡Restaurado!) ───────────────
with st.sidebar:
    st.markdown("### 📖 Luz de la Palabra")
    
    # Sistema de Contraseña
    if not st.session_state.get("auth", False):
        pwd = st.text_input("Contraseña de Acceso:", type="password")
        if st.button("Entrar"):
            if pwd == cfg.get("password", "estudio2026"): 
                st.session_state.auth = True
                st.rerun()
            else: 
                st.error("Contraseña incorrecta")
        st.stop() # Detiene la app si no hay clave

    # Clave de Gemini
    key = cfg.get("gemini_key","")
    with st.expander("🔑 Configuración de Gemini"):
        nk = st.text_input("Clave API:", type="password")
        if st.button("Guardar Clave"):
            cfg["gemini_key"] = nk
            save_cfg(cfg)
            st.session_state.cfg = cfg
            st.success("✅ Guardada")
            st.rerun()
            
    if not key: 
        st.warning("⚠️ Configura tu clave de Gemini para empezar.")
        st.stop()

# ── UTILIDADES ───────────────────────────────────────────────────
def _es_sqlite(b): return len(b) > 16 and b[:16].startswith(b"SQLite format 3")
def _extraer_sqlite(zf):
    for e in sorted(zf.infolist(), key=lambda x: x.file_size, reverse=True)[:10]:
        try:
            data = zf.read(e.filename)
            if _es_sqlite(data): return data
            if data[:2] == b"PK": 
                with zipfile.ZipFile(io.BytesIO(data)) as inner:
                    res = _extraer_sqlite(inner)
                    if res: return res
        except: pass
    return None

# ── SINCRONIZACIÓN AUTOMÁTICA CON DRIVE ──────────────────────────
@st.cache_resource(show_spinner=False)
def auto_sincronizar():
    try:
        if "google_credentials" not in st.secrets: return False
        info = json.loads(st.secrets["google_credentials"])
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        
        results = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{FOLDER_NAME}' and trashed=false", fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items: return False
        
        archivos_drive = service.files().list(q=f"'{items[0]['id']}' in parents and trashed=false and (name contains '.jwpub' or name contains '.pdf')", fields="files(id, name)").execute()
        
        for arch in archivos_drive.get('files', []):
            nombre = arch['name']
            if nombre.lower().endswith('.jwpub'):
                db_dest = PUBS_DIR / f"{re.sub(r'[^a-zA-Z0-9_\-]','_', Path(nombre).stem)}.db"
                if not db_dest.exists():
                    req = service.files().get_media(fileId=arch['id'])
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, req)
                    while not downloader.next_chunk()[1]: pass
                    with zipfile.ZipFile(io.BytesIO(fh.getvalue())) as zf:
                        db_bytes = _extraer_sqlite(zf)
                        if db_bytes: db_dest.write_bytes(db_bytes)
            
            elif nombre.lower().endswith('.pdf'):
                pdf_dest = PUBS_DIR / nombre
                if not pdf_dest.exists():
                    req = service.files().get_media(fileId=arch['id'])
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, req)
                    while not downloader.next_chunk()[1]: pass
                    pdf_dest.write_bytes(fh.getvalue())
        return True
    except: return False

is_synced = auto_sincronizar()

# ── BÚSQUEDA HÍBRIDA (JWPUB Y PDF JUNTOS) ────────────────────────
def buscar_en_neuronas(consulta):
    palabras = [w for w in re.split(r'\W+', consulta.lower()) if len(w) >= 3 and w not in STOPWORDS][:8]
    if not palabras: return "", ""
    
    res_jwpub = []
    res_pdf = ""
    
    # 1. Buscar en JWPUB (Recuperado el código que funcionaba)
    for db in PUBS_DIR.glob("*.db"):
        try:
            conn = sqlite3.connect(str(db)); conn.row_factory = sqlite3.Row; c = conn.cursor()
            cond = " OR ".join([f"LOWER(d.Title) LIKE ?"]*len(palabras))
            params = [f"%{p}%" for p in palabras]
            c.execute(f"SELECT Title FROM Document d WHERE {cond} LIMIT 5", params)
            for r in c.fetchall(): res_jwpub.append(f"• {r['Title']} (de {db.stem})")
            conn.close()
        except: pass

    # 2. Buscar en PDF
    for pdf_file in PUBS_DIR.glob("*.pdf"):
        try:
            lector = PyPDF2.PdfReader(pdf_file)
            for i, pag in enumerate(lector.pages):
                texto = pag.extract_text()
                if texto and any(p in texto.lower() for p in palabras):
                    res_pdf += f"--- Documento: {pdf_file.name} | Página: {i+1} ---\n{texto[:800]}...\n\n"
                    if len(res_pdf) > 4000: break
        except: pass

    ctx_jwpub = "\n".join(res_jwpub) if res_jwpub else ""
    return ctx_jwpub, res_pdf

# ── PROMPT MAESTRO COMPLETO ──────────────────────────────────────
instrucciones = """Eres 'Luz de la Palabra', un asistente experto en oratoria, enseñanza y la preparación de comentarios y discursos. Estás capacitado con los mejores principios de estudio, investigación y enseñanza.

Tu objetivo es ayudar al usuario a preparar sus asignaciones de forma estructurada, profunda y efectiva.

INSTRUCCIONES ESTRICTAS DE COMPORTAMIENTO:

1. FUENTE DE INFORMACIÓN (REGLA DE ORO): 
Te proporcionaré recursos extraídos de la memoria del usuario. Analízalos profundamente.
- Si la respuesta está en los textos PDF, úsalos y cita la página y párrafo.
- Si ves referencias a libros/revistas JWPUB, USA TU PROPIO CONOCIMIENTO INTERNO SOBRE ESAS PUBLICACIONES DE LOS TESTIGOS DE JEHOVÁ para dar la respuesta, y cita de qué publicación lo sacaste.

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

6. FUENTES Y REFERENCIAS (OBLIGATORIO): Al final de CADA respuesta, DEBES colocar la fuente exacta.

7. TONO Y ESTILO:
   - Usa preguntas retóricas.
   - Mantén un tono amable, animador, edificante y respetuoso. Usa negritas y viñetas."""

def preguntar_gemini(historial, pregunta, ctx_jwpub, ctx_pdf):
    try:
        cliente = genai.Client(api_key=st.session_state.cfg.get("gemini_key", ""))
        contents = [types.Content(role="user" if m["r"]=="u" else "model", parts=[types.Part(text=m["t"])]) for m in historial]
        
        prompt_final = pregunta
        if ctx_jwpub or ctx_pdf: 
            prompt_final += "\n\n--- RECURSOS ENCONTRADOS EN TU MEMORIA (DRIVE) ---\n"
            if ctx_jwpub: 
                prompt_final += f"\n💡 PUBLICACIONES JWPUB RELACIONADAS (Usa tu conocimiento interno sobre estos libros/revistas para dar la respuesta):\n{ctx_jwpub}\n"
            if ctx_pdf: 
                prompt_final += f"\n📄 TEXTO EXACTO DE TUS PDF (Úsalo para citar párrafos o páginas):\n{ctx_pdf}\n"
        
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt_final)]))
        resp = cliente.models.generate_content(
            model="gemini-2.5-flash", contents=contents,
            config=types.GenerateContentConfig(temperature=0.3, system_instruction=instrucciones)
        )
        return resp.text
    except Exception as e: return f"❌ Error de conexión: {str(e)}"

# ── INTERFAZ VISUAL ───────────────────────────────────────────────
st.markdown('<div class="hero"><h1>📖 Luz de la Palabra</h1><p>Tu asistente bíblico personal, rápido y elegante</p></div>', unsafe_allow_html=True)

if is_synced:
    st.markdown('<div class="status-badge">✅ Conectado y sincronizado con Google Drive</div>', unsafe_allow_html=True)
else:
    st.warning("⚠️ Sin conexión a Drive. Trabajando solo con memoria interna base.")

# ── CHAT PRINCIPAL ────────────────────────────────────────────────
if "hist" not in st.session_state: st.session_state.hist = []

for msg in st.session_state.hist:
    clase = "chat-user" if msg["r"]=="u" else "chat-ai"
    st.markdown(f'<div class="{clase}">{msg["t"]}</div>', unsafe_allow_html=True)

if q := st.chat_input("Escribe tu pregunta bíblica..."):
    st.session_state.hist.append({"r":"u","t":q})
    st.markdown(f'<div class="chat-user">{q}</div>', unsafe_allow_html=True)
    
    with st.spinner("Investigando en tus publicaciones..."):
        ctx_jwpub, ctx_pdf = buscar_en_neuronas(q)
        historial_previo = st.session_state.hist[:-1]
        resp = preguntar_gemini(historial_previo, q, ctx_jwpub, ctx_pdf)
        
    st.session_state.hist.append({"r":"a","t":resp})
    st.markdown(f'<div class="chat-ai">{resp}</div>', unsafe_allow_html=True)
    st.rerun()
