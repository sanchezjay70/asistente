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

# 1. CONFIGURACIÓN DE PÁGINA (Moderna)
st.set_page_config(page_title="Luz de la Palabra", page_icon="📖", layout="centered", initial_sidebar_state="collapsed")

# 2. DISEÑO VISUAL MEJORADO (CSS Premium)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Merriweather:ital,wght@0,300;0,700;1,300&display=swap');
html, body, .stApp { background-color: #F7F9FC; font-family: 'Inter', sans-serif; }
h1, h2, h3 { font-family: 'Merriweather', serif; color: #1E293B; }
.hero { background: linear-gradient(135deg, #1E293B 0%, #334155 100%); padding: 2rem; border-radius: 16px; text-align: center; margin-bottom: 2rem; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
.hero h1 { color: #F8FAFC !important; font-size: 2.2rem; font-weight: 700; margin-bottom: 0.5rem; }
.hero p { color: #CBD5E1; font-size: 1rem; }
.chat-user { background-color: #2563EB; color: white; padding: 1rem 1.5rem; border-radius: 20px 20px 5px 20px; margin: 1rem 0 1rem 20%; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2); font-size: 1rem; line-height: 1.5; }
.chat-ai { background-color: white; color: #334155; padding: 1.5rem; border-radius: 5px 20px 20px 20px; margin: 1rem 20% 1rem 0; border: 1px solid #E2E8F0; box-shadow: 0 4px 12px rgba(0,0,0,0.05); font-size: 1.05rem; line-height: 1.7; font-family: 'Merriweather', serif; }
.chat-ai strong { color: #0F172A; }
.stFileUploader { background-color: white; padding: 1rem; border-radius: 12px; border: 1px dashed #CBD5E1; }
.status-badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.875rem; font-weight: 600; background: #DEF7EC; color: #03543F; border: 1px solid #31C48D; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# ── Config persistente ─────────────────────────────────────────────
APP_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
PUBS_DIR = APP_DIR / "mis_publicaciones"
PUBS_DIR.mkdir(exist_ok=True)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_NAME = "Mis Publicaciones"

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

# ── SINCRONIZACIÓN AUTOMÁTICA EN SEGUNDO PLANO ─────────────────────
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
        
        jwpub_results = service.files().list(q=f"'{items[0]['id']}' in parents and trashed=false and name contains '.jwpub'", fields="files(id, name)").execute()
        for arch in jwpub_results.get('files', []):
            db_dest = PUBS_DIR / f"{re.sub(r'[^a-zA-Z0-9_\-]','_', Path(arch['name']).stem)}.db"
            if not db_dest.exists():
                req = service.files().get_media(fileId=arch['id'])
                fh = io.BytesIO()
                MediaIoBaseDownload(fh, req).next_chunk() # Descarga rápida
                with zipfile.ZipFile(io.BytesIO(fh.getvalue())) as zf:
                    db_bytes = _extraer_sqlite(zf)
                    if db_bytes: db_dest.write_bytes(db_bytes)
        return True
    except Exception: return False

# Ejecutar sincronización al abrir la app
is_synced = auto_sincronizar()

# ── PROMPT MAESTRO COMPLETO (¡INTACTO!) ───────────────────────────
instrucciones = """Eres 'Luz de la Palabra', un asistente experto en oratoria, enseñanza y la preparación de comentarios y discursos. Estás capacitado con los mejores principios de estudio, investigación y enseñanza.

Tu objetivo es ayudar al usuario a preparar sus asignaciones de forma estructurada, profunda y efectiva, utilizando estrictamente el material que él te proporcione.

INSTRUCCIONES ESTRICTAS DE COMPORTAMIENTO:

1. FUENTE DE INFORMACIÓN (REGLA DE ORO): Si el usuario pega un texto, párrafo, referencia, adjunta un documento (PDF/TXT) o la base de datos te da información, ESA es tu fuente de investigación. NUNCA digas que "no tienes la información". Analiza profundamente el texto proporcionado y cumple la tarea basándote en él.

2. ANÁLISIS PROFUNDO DE CAPÍTULOS O RELATOS:
   Cuando el usuario te pida analizar un capítulo o relato completo, estructura tu respuesta respondiendo a estas preguntas clave basándote en el texto:
   - CONTEXTO: ¿Cuál era el contexto? ¿Quién escribió esto y para quién? ¿En qué año sucedió? ¿Por qué se escribió? ¿Cuándo y dónde ocurrieron los hechos? ¿Cuáles eran las circunstancias? ¿Qué ocurrió antes y después?
   - SOBRE JEHOVÁ Y SU PROPÓSITO: ¿Qué me enseña esto sobre Jehová? ¿Cómo contribuye esta parte al cumplimiento del propósito de Dios? ¿Por qué incluyó Jehová este relato en su Palabra? ¿Qué relación tiene con el tema central de la Biblia? ¿Qué espera Jehová de quienes desean ser sus amigos? ¿Qué tipo de personas están cerca de Jehová, y de qué pueden estar seguras? ¿Qué tenemos que hacer para estar cerca de Jehová? ¿Qué debemos evitar para seguir siendo amigos de Jehová?
   - LECCIONES DE LOS PERSONAJES: ¿Cómo se sintieron las personas que aparecen en el pasaje? ¿Qué personajes demostraron fe (o falta de fe) y en qué se parecen a mí? ¿Qué cualidades mostraron y por qué debo imitarlas? ¿Qué defectos tuvieron y por qué debo evitarlos?
   - APLICACIÓN Y MINISTERIO: ¿Cómo puedo aplicar esta información en mi vida? ¿Cómo puede ayudarme este pasaje? ¿En qué situación de mi vida he visto que este principio es cierto? ¿Cómo puedo usar estos versículos para ayudar a otros?

3. CÓMO ESTUDIAR E INVESTIGAR PARA SACAR "PERLAS": 
   - Cuando se te pida buscar perlas espirituales, analiza el texto más allá de lo superficial.
   - Busca y destaca: cualidades divinas (qué nos enseña sobre Dios), principios bíblicos prácticos, lecciones para el ministerio o detalles del contexto histórico. 
   - Presenta estas perlas de forma clara y lista para ser comentada.

4. CÓMO RESPONDER A LAS PREGUNTAS DE ESTUDIO:
   - Lee con cuidado la pregunta específica del usuario.
   - Busca la respuesta exacta dentro del texto que te proporcionó.
   - Responde usando TUS PROPIAS PALABRAS de forma clara y directa. NO copies y pegues todo el párrafo original. Ve al grano y aísla la idea principal.

5. COMENTARIOS DE 30 SEGUNDOS:
   - Al pedirte un comentario para una reunión, redacta una respuesta de unas 60-75 palabras. 
   - Debe ser directa, usar palabras sencillas y, de ser posible, destacar el valor práctico de la información.

6. DESARROLLO DE BOSQUEJOS Y DISCURSOS:
   Aplica esta estructura obligatoria al rellenar o preparar un bosquejo:
   - Introducción: Crea aperturas que despierten el interés del auditorio inmediatamente.
   - Desarrollo (Técnica de Enseñanza): En cada punto principal o texto clave, debes aplicar tres pasos:
      a) EXPLICAR: Aclarar el significado del texto o el punto.
      b) ILUSTRAR: Usar comparaciones, ejemplos sencillos o situaciones cotidianas.
      c) APLICAR: Mostrarle al auditorio cómo poner en práctica esa enseñanza en su vida diaria de forma amorosa y razonable.
   - Conclusión: Breve, que repase los puntos clave y motive a la acción.

7. FUENTES Y REFERENCIAS (OBLIGATORIO): Al final de CADA respuesta, DEBES colocar la fuente exacta en la que te basaste. Indica la publicación, la página, el párrafo, la sección del documento adjunto o el texto bíblico utilizado.

8. CORRECCIONES DEL USUARIO: Si el usuario te dice que tu respuesta es incorrecta, acéptalo con amabilidad, revisa tu análisis previo en el historial de esta conversación y genera una nueva respuesta corregida basada en sus indicaciones.

9. TONO Y ESTILO:
   - Usa preguntas retóricas para hacer reflexionar al auditorio.
   - Mantén siempre un tono amable, animador, edificante y respetuoso."""

def preguntar_gemini(historial, pregunta, texto_pdf):
    try:
        cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else st.secrets.get("gemini_key", ""))
        contents = [types.Content(role="user" if m["r"]=="u" else "model", parts=[types.Part(text=m["t"])]) for m in historial]
        
        prompt_final = pregunta
        if texto_pdf: prompt_final += f"\n\n--- DOCUMENTO ADJUNTO (ÚSALO PARA CITAR PÁGINAS) ---\n{texto_pdf}"
        
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt_final)]))
        resp = cliente.models.generate_content(
            model="gemini-2.5-flash", contents=contents,
            config=types.GenerateContentConfig(temperature=0.2, system_instruction=instrucciones)
        )
        return resp.text
    except Exception as e: return f"❌ Error de conexión: {str(e)}"

# ── INTERFAZ VISUAL ───────────────────────────────────────────────
st.markdown('<div class="hero"><h1>📖 Luz de la Palabra</h1><p>Tu asistente bíblico personal, rápido y elegante.</p></div>', unsafe_allow_html=True)

if is_synced:
    st.markdown('<div class="status-badge">✅ Conectado y Sincronizado</div>', unsafe_allow_html=True)
else:
    st.warning("⚠️ No se pudo sincronizar Drive. Revisa los Secrets.")

# Adjuntos (PDF)
texto_adjunto = ""
with st.expander("📎 Adjuntar PDF (Recomendado para citas exactas de párrafos)"):
    archivo = st.file_uploader("", type=['pdf'])
    if archivo:
        lector = PyPDF2.PdfReader(archivo)
        for pag in lector.pages:
            if pag.extract_text(): texto_adjunto += pag.extract_text() + "\n"
        st.success("PDF cargado. Pregúntame sobre él y te daré la página.")

# Chat
if "hist" not in st.session_state: st.session_state.hist = []

for msg in st.session_state.hist:
    st.markdown(f'<div class="{"chat-user" if msg["r"]=="u" else "chat-ai"}">{msg["t"]}</div>', unsafe_allow_html=True)

if q := st.chat_input("Escribe tu pregunta o pídele que corrija algo..."):
    st.session_state.hist.append({"r":"u","t":q})
    st.markdown(f'<div class="chat-user">{q}</div>', unsafe_allow_html=True)
    
    with st.spinner("Investigando con precisión..."):
        historial_previo = st.session_state.hist[:-1]
        resp = preguntar_gemini(historial_previo, q, texto_adjunto)
        
    st.session_state.hist.append({"r":"a","t":resp})
    st.markdown(f'<div class="chat-ai">{resp}</div>', unsafe_allow_html=True)
    st.rerun()
