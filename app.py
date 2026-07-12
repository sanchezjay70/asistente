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
st.set_page_config(page_title="Luz de la Palabra", page_icon="🧠", layout="centered", initial_sidebar_state="collapsed")

# 2. DISEÑO VISUAL
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Playfair+Display:ital,wght@0,400;0,700;1,400&display=swap');
html, body, .stApp { background-color: #0F172A; font-family: 'Inter', sans-serif; color: #E2E8F0; }
.hero { background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); padding: 2.5rem 2rem; border-radius: 20px; text-align: center; margin-bottom: 2rem; border: 1px solid #334155; }
.hero h1 { color: #F8FAFC !important; font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; }
.chat-user { background: linear-gradient(135deg, #2563EB, #3B82F6); color: white; padding: 1.2rem 1.5rem; border-radius: 24px 24px 4px 24px; margin: 1.5rem 0 1.5rem 15%; font-size: 1.05rem; line-height: 1.6; }
.chat-ai { background-color: #1E293B; color: #E2E8F0; padding: 1.5rem 2rem; border-radius: 4px 24px 24px 24px; margin: 1.5rem 15% 1.5rem 0; border: 1px solid #334155; font-size: 1.1rem; line-height: 1.8; }
.brain-mode { font-size: 0.75rem; color: #38BDF8; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ── Configuración Drive ──────────────────────────────────────────
APP_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
PUBS_DIR = APP_DIR / "mis_publicaciones"
PUBS_DIR.mkdir(exist_ok=True)
FOLDER_NAME = "Mis Publicaciones"
STOPWORDS = {"que","con","los","las","del","una","por","para","como","son","era","fue"}

# ── Funciones de Sincronización ──────────────────────────────────
@st.cache_resource(show_spinner=False)
def auto_sincronizar():
    try:
        if "google_credentials" not in st.secrets: return False
        info = json.loads(st.secrets["google_credentials"])
        creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        service = build('drive', 'v3', credentials=creds)
        res = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{FOLDER_NAME}' and trashed=false", fields="files(id, name)").execute()
        if not res.get('files'): return False
        archivos = service.files().list(q=f"'{res['files'][0]['id']}' in parents and trashed=false and (name contains '.jwpub' or name contains '.pdf')", fields="files(id, name)").execute()
        for arch in archivos.get('files', []):
            nombre = arch['name']
            dest = PUBS_DIR / (re.sub(r'[^a-zA-Z0-9_\-]','_', Path(nombre).stem) + (".db" if nombre.endswith('.jwpub') else ".pdf"))
            if not dest.exists():
                req = service.files().get_media(fileId=arch['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, req)
                while not downloader.next_chunk()[1]: pass
                if nombre.endswith('.jwpub'):
                    with zipfile.ZipFile(io.BytesIO(fh.getvalue())) as zf:
                        for e in sorted(zf.infolist(), key=lambda x: x.file_size, reverse=True)[:10]:
                            data = zf.read(e.filename)
                            if len(data) > 16 and data[:16].startswith(b"SQLite format 3"): dest.write_bytes(data); break
                else: dest.write_bytes(fh.getvalue())
        return True
    except: return False

is_synced = auto_sincronizar()

# ── Búsqueda ─────────────────────────────────────────────────────
def buscar_en_neuronas(consulta):
    palabras = [w for w in re.split(r'\W+', consulta.lower()) if len(w) >= 3 and w not in STOPWORDS][:8]
    res_jwpub, res_pdf = "", ""
    for db in PUBS_DIR.glob("*.db"):
        try:
            conn = sqlite3.connect(str(db)); c = conn.cursor()
            c.execute(f"SELECT Title FROM Document WHERE Title LIKE ?", [f"%{palabras[0]}%"])
            for r in c.fetchall(): res_jwpub += f"• {r[0]} (de {db.stem})\n"
        except: pass
    for pdf in PUBS_DIR.glob("*.pdf"):
        try:
            lector = PyPDF2.PdfReader(pdf)
            for i, p in enumerate(lector.pages):
                txt = p.extract_text()
                if txt and any(p in txt.lower() for p in palabras): res_pdf += f"--- {pdf.name} (Pág {i+1}) ---\n{txt[:600]}...\n\n"
        except: pass
    return res_jwpub, res_pdf

# ── PROMPT MAESTRO COMPLETO Y RESTAURADO ──────────────────────────
instrucciones = """Eres 'Luz de la Palabra', un asistente experto en oratoria, enseñanza y la preparación de comentarios y discursos. Estás capacitado con los mejores principios de estudio, investigación y enseñanza.

Tu objetivo es ayudar al usuario a preparar sus asignaciones de forma estructurada, profunda y efectiva, utilizando estrictamente el material que él te proporcione y tu propia base de conocimiento.

INSTRUCCIONES ESTRICTAS DE COMPORTAMIENTO:

1. FUENTE DE INFORMACIÓN (REGLA DE ORO): Si el usuario adjunta un documento (PDF/TXT) o la base de datos te da información, ESA es tu fuente de investigación principal. NUNCA digas que "no tienes la información". Analiza profundamente el texto y cumple la tarea.

2. ANÁLISIS PROFUNDO DE CAPÍTULOS O RELATOS:
   Cuando el usuario pida analizar un capítulo o relato, estructura tu respuesta respondiendo a:
   - CONTEXTO: ¿Quién escribió, para quién, cuándo, dónde y por qué?
   - SOBRE JEHOVÁ Y SU PROPÓSITO: ¿Qué enseña sobre Jehová? ¿Cómo contribuye al cumplimiento de su propósito?
   - LECCIONES DE LOS PERSONAJES: ¿Quiénes demostraron fe (o falta de fe)? ¿Qué cualidades imitar o defectos evitar?
   - APLICACIÓN Y MINISTERIO: ¿Cómo aplicar en mi vida y cómo ayudar a otros?

3. CÓMO ESTUDIAR E INVESTIGAR PARA SACAR "PERLAS": 
   - Analiza el texto más allá de lo superficial.
   - Busca: cualidades divinas, principios bíblicos prácticos, lecciones para el ministerio o detalles históricos.
   - Presenta estas perlas de forma clara, lista para ser comentada.

4. CÓMO RESPONDER A LAS PREGUNTAS DE ESTUDIO:
   - Responde usando TUS PROPIAS PALABRAS de forma clara y directa. NO copies y pegues párrafos completos. Ve al grano.

5. COMENTARIOS DE 30 SEGUNDOS:
   - Redacta una respuesta de 60-75 palabras. Directa, sencilla y con valor práctico.

6. DESARROLLO DE BOSQUEJOS Y DISCURSOS (ESTRUCTURA OBLIGATORIA):
   - Introducción: Despierta interés inmediatamente.
   - Desarrollo:
      a) EXPLICAR: Aclarar el significado.
      b) ILUSTRAR: Usar comparaciones o ejemplos sencillos.
      c) APLICAR: Mostrar cómo poner en práctica en la vida diaria.
   - Conclusión: Breve, repaso y motivación a la acción.

7. FUENTES Y REFERENCIAS (OBLIGATORIO): Al final de CADA respuesta, DEBES colocar la fuente exacta (publicación, página, párrafo o texto bíblico utilizado).

8. CORRECCIONES DEL USUARIO: Si te dice que tu respuesta es incorrecta, acéptalo, revisa y genera una nueva respuesta corregida con amabilidad.

9. TONO Y ESTILO:
   - Usa preguntas retóricas para hacer reflexionar.
   - Mantén un tono amable, animador, edificante y respetuoso."""

# ── Ejecución ────────────────────────────────────────────────────
def preguntar_gemini(historial, pregunta, ctx_jwpub, ctx_pdf):
    cliente = genai.Client(api_key=st.secrets.get("gemini_key", ""))
    contents = [types.Content(role="user" if m["r"]=="u" else "model", parts=[types.Part(text=m["t"])]) for m in historial]
    prompt = f"{pregunta}\n\n--- INFORMACIÓN DE TUS PUBLICACIONES ---\n{ctx_jwpub}\n--- DOCUMENTOS PDF ---\n{ctx_pdf}"
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    return cliente.models.generate_content(model="gemini-2.5-flash", contents=contents, config=types.GenerateContentConfig(temperature=0.3, system_instruction=instrucciones)).text

st.markdown('<div class="hero"><h1>🧠 Luz de la Palabra</h1><p>Inteligencia Artificial Bíblica Autónoma</p></div>', unsafe_allow_html=True)

if "hist" not in st.session_state: st.session_state.hist = []
for msg in st.session_state.hist:
    st.markdown(f'<div class="{"chat-user" if msg["r"]=="u" else "chat-ai"}">{msg["t"]}</div>', unsafe_allow_html=True)

if q := st.chat_input("Escribe tu pregunta bíblica..."):
    st.session_state.hist.append({"r":"u","t":q})
    st.markdown(f'<div class="chat-user">{q}</div>', unsafe_allow_html=True)
    with st.spinner("Investigando en tus publicaciones..."):
        ctx1, ctx2 = buscar_en_neuronas(q)
        resp = preguntar_gemini(st.session_state.hist[:-1], q, ctx1, ctx2)
    st.session_state.hist.append({"r":"a","t":resp})
    st.rerun()
