import streamlit as st
import sqlite3, zipfile, json, os, re, io, time
from pathlib import Path
import google.genai as genai
from google.genai import types

# Librerías de Google Drive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

st.set_page_config(page_title="Luz de la Palabra", page_icon="📖", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,600;1,400&family=DM+Sans:wght@300;400;500;600&display=swap');
*,html,body{font-family:'DM Sans',sans-serif;}
h1,h2,h3{font-family:'EB Garamond',serif;}
.stApp{background:#f3efe6;}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0d1117 0%,#141b2d 100%) !important;border-right:1px solid #1e2535;}
section[data-testid="stSidebar"] *{color:#8a94b0 !important;}
section[data-testid="stSidebar"] .stTextInput input{background:#131825 !important;border:1px solid #252d42 !important;color:#c8d0e8 !important;border-radius:8px !important;font-size:13px !important;}
section[data-testid="stSidebar"] .stButton>button{background:linear-gradient(135deg,#c9a84c,#e8c060) !important;color:#0d1117 !important;border:none !important;border-radius:8px !important;font-weight:600 !important;width:100% !important;}
.hero{background:linear-gradient(160deg,#0d1117,#141b2d,#0d1a30);border-radius:20px;padding:2rem 2.5rem;margin-bottom:1.5rem;position:relative;overflow:hidden;box-shadow:0 12px 40px rgba(13,17,23,.35);}
.hero h1{color:#f0ece0 !important;font-size:2.2rem !important;margin:0 0 .2rem !important;font-weight:500 !important;font-style:italic;}
.hero p{color:#5a6480;font-size:.88rem;margin:0 0 .8rem;}
.msg-u{background:#1a2035;color:#e8ecf8 !important;border-radius:20px 20px 5px 20px;padding:12px 18px;margin:8px 0 8px 20%;font-size:.92rem;line-height:1.65;box-shadow:0 3px 14px rgba(26,26,46,.22);}
.msg-a{background:white;border:1px solid #e2d9c8;border-radius:5px 20px 20px 20px;padding:18px 22px;margin:8px 20% 8px 0;font-size:.93rem;line-height:1.78;box-shadow:0 3px 14px rgba(0,0,0,.05);}
.thinking{background:white;border:1px solid #e2d9c8;border-radius:5px 20px 20px 20px;padding:14px 20px;margin:8px 20% 8px 0;color:#8a98b8;font-size:.83rem;box-shadow:0 2px 8px rgba(0,0,0,.04);display:flex;align-items:center;gap:10px;}
.dot{width:7px;height:7px;border-radius:50%;background:#c9a84c;display:inline-block;animation:blink 1.3s infinite;}
.dot:nth-child(2){animation-delay:.2s;}.dot:nth-child(3){animation-delay:.4s;}
@keyframes blink{0%,80%,100%{opacity:.2;transform:scale(.8)}40%{opacity:1;transform:scale(1)}}
.src-chip{display:inline-flex;align-items:center;gap:4px;background:#e8f5ee;border:1px solid #b8ddc8;border-radius:20px;padding:3px 11px;font-size:.74rem;color:#2d7a5a;font-weight:500;margin:2px;}
.alert{border-radius:10px;padding:11px 16px;font-size:.86rem;margin:8px 0;}
.alert.ok{background:#e8f5ee;border-left:3px solid #2d7a5a;color:#0a5030;}
.alert.warn{background:#fff8e8;border-left:3px solid #c9a84c;color:#7a5010;}
.alert.info{background:#e8f0fe;border-left:3px solid #1a4a9a;color:#1a3080;}
.sec-label{font-size:.69rem;font-weight:600;color:#7a8098;text-transform:uppercase;letter-spacing:.1em;margin:20px 0 10px;display:flex;align-items:center;gap:8px;}
.pub-card{background:white;border-radius:12px;padding:14px 16px;border:1.5px solid #e2d9c8;transition:all .2s;position:relative;margin-bottom:4px;}
.pub-card.ok{border-color:#b8ddc8;background:linear-gradient(135deg,white,#f5fdf8);}
.pub-card .t{font-weight:600;font-size:.85rem;color:#1a2035;line-height:1.3;}
</style>
""", unsafe_allow_html=True)

# ── Config persistente ─────────────────────────────────────────────
APP_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
CFG_FILE = APP_DIR / ".luz_cfg.json"
PUBS_DIR = APP_DIR / "mis_publicaciones"
PUBS_DIR.mkdir(exist_ok=True)
CREDS_FILE = APP_DIR / "credenciales.json"

# ── CONEXIÓN GOOGLE DRIVE ──────────────────────────────────────────
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_NAME = "Mis Publicaciones"

@st.cache_resource
def iniciar_drive():
    if not CREDS_FILE.exists(): return None
    try:
        creds = service_account.Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        # Buscar la ID de la carpeta
        results = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{FOLDER_NAME}' and trashed=false", fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items: return None
        folder_id = items[0]['id']
        
        # Descargar archivos .db que no estén en local
        db_results = service.files().list(q=f"'{folder_id}' in parents and trashed=false and name contains '.db'", fields="files(id, name)").execute()
        dbs = db_results.get('files', [])
        for db in dbs:
            local_path = PUBS_DIR / db['name']
            if not local_path.exists():
                request = service.files().get_media(fileId=db['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                with open(local_path, 'wb') as f: f.write(fh.getvalue())
        return {"service": service, "folder_id": folder_id}
    except Exception as e:
        return None

drive_conn = iniciar_drive()

def subir_a_drive(local_path, file_name):
    if not drive_conn: return
    try:
        file_metadata = {'name': file_name, 'parents': [drive_conn["folder_id"]]}
        media = MediaFileUpload(local_path, mimetype='application/octet-stream')
        drive_conn["service"].files().create(body=file_metadata, media_body=media, fields='id').execute()
    except Exception as e: pass

# ── Funciones Base ─────────────────────────────────────────────
def load_cfg():
    if CFG_FILE.exists():
        try: return json.loads(CFG_FILE.read_text())
        except: pass
    return {"gemini_key":"","password":"estudio2026"}

def save_cfg(c): CFG_FILE.write_text(json.dumps(c, indent=2))

if "cfg" not in st.session_state: st.session_state.cfg = load_cfg()
cfg = st.session_state.cfg

with st.sidebar:
    st.markdown('<div style="padding:1rem 0 .5rem;font-family:\'EB Garamond\',serif;font-size:1.4rem;color:#c9a84c;font-style:italic;line-height:1.3">📖 Luz de la Palabra</div>', unsafe_allow_html=True)
    if not st.session_state.get("auth", False):
        pwd = st.text_input("Contraseña:", type="password")
        if st.button("Entrar"):
            if pwd == cfg.get("password","estudio2026"): st.session_state.auth = True; st.rerun()
            else: st.error("Contraseña incorrecta")
        st.stop()

    key = cfg.get("gemini_key","")
    with st.expander("🔑 Clave Gemini"):
        nk = st.text_input("Clave:", type="password")
        if st.button("Guardar clave"):
            cfg["gemini_key"] = nk; save_cfg(cfg); st.session_state.cfg = cfg; st.success("✅"); time.sleep(1); st.rerun()
    if not key: st.warning("Configura tu clave de Gemini"); st.stop()
    
    if drive_conn: st.success("☁️ Conectado a Google Drive")
    else: st.error("☁️ Sin conexión a Drive (revisa credenciales.json y la carpeta)")

# ── Importador JWPUB ───────────────────────────────────────────────
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

def importar_jwpub(archivo_bytes, nombre):
    nombre_limpio = re.sub(r"[^a-zA-Z0-9_\-]","_", Path(nombre).stem)
    db_dest = PUBS_DIR / f"{nombre_limpio}.db"
    try:
        with zipfile.ZipFile(io.BytesIO(archivo_bytes)) as zf:
            db_bytes = _extraer_sqlite(zf)
            if not db_bytes: return {"ok":False,"error":"No es un JWPUB válido"}
            db_dest.write_bytes(db_bytes)
            # Respaldo en Drive
            subir_a_drive(str(db_dest), f"{nombre_limpio}.db")
            return {"ok":True,"nombre":nombre_limpio}
    except Exception as e: return {"ok":False,"error":str(e)}

# ── Búsqueda e IA ──────────────────────────────────────────────
STOPWORDS = {"que","con","los","las","del","una","por","para","como","son","era","fue"}

def buscar_todo(consulta):
    palabras = [w for w in re.split(r'\W+', consulta.lower()) if len(w) >= 3 and w not in STOPWORDS][:8]
    if not palabras: return []
    resultados = []
    for db in PUBS_DIR.glob("*.db"):
        try:
            conn = sqlite3.connect(str(db)); conn.row_factory = sqlite3.Row; c = conn.cursor()
            cond = " OR ".join([f"LOWER(d.Title) LIKE ?"]*len(palabras))
            params = [f"%{p}%" for p in palabras]
            c.execute(f"SELECT Title FROM Document d WHERE {cond} LIMIT 10", params)
            for r in c.fetchall(): resultados.append({"pub": db.stem, "titulo": r["Title"]})
            conn.close()
        except: pass
    return resultados[:20]

def preguntar_gemini(pregunta, contexto):
    try:
        cliente = genai.Client(api_key=cfg["gemini_key"])
        prompt = f"Basa tu respuesta SOLO en estas publicaciones de los Testigos de Jehová:\n{contexto}\n\nPREGUNTA: {pregunta}"
        resp = cliente.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=3000)
        )
        return resp.text or "Sin respuesta."
    except Exception as e: return f"❌ Error: {str(e)}"

# ── Vistas ────────────────────────────────────────────────────────
st.markdown('<div class="hero"><h1>Luz de la Palabra</h1><p>Tu asistente bíblico sincronizado en la nube</p></div>', unsafe_allow_html=True)
pubs_ok = list(PUBS_DIR.glob("*.db"))
t_chat, t_biblio = st.tabs(["💬 Consultar", "📚 Biblioteca"])

with t_biblio:
    archivos = st.file_uploader("Sube archivos JWPUB (Se guardarán en tu Drive)", type=["jwpub","zip"], accept_multiple_files=True)
    if archivos and st.button("Guardar en mi Biblioteca"):
        for arch in archivos:
            res = importar_jwpub(arch.read(), arch.name)
            if res["ok"]: st.success(f"✅ {arch.name} importado y guardado en Drive!")
            else: st.error(f"⚠️ {arch.name}: Error al importar")
        time.sleep(2); st.rerun()
    if pubs_ok:
        for p in pubs_ok: st.markdown(f'<div class="pub-card ok"><div class="t">📖 {p.stem}</div></div>', unsafe_allow_html=True)

with t_chat:
    if "hist" not in st.session_state: st.session_state.hist = []
    for msg in st.session_state.hist:
        clase = "msg-u" if msg["r"]=="u" else "msg-a"
        st.markdown(f'<div class="{clase}">{msg["t"]}</div>', unsafe_allow_html=True)
    
    q = st.chat_input("Escribe tu pregunta...")
    if q:
        st.session_state.hist.append({"r":"u","t":q})
        st.markdown(f'<div class="msg-u">{q}</div>', unsafe_allow_html=True)
        caja = st.empty()
        caja.markdown('<div class="thinking">Buscando en tus publicaciones...</div>', unsafe_allow_html=True)
        res = buscar_todo(q)
        ctx = "\n".join([f"• {r['titulo']} (de {r['pub']})" for r in res]) if res else ""
        caja.markdown('<div class="thinking">Consultando a Gemini...</div>', unsafe_allow_html=True)
        resp = preguntar_gemini(q, ctx) if ctx else "No encontré referencias en tus publicaciones subidas."
        caja.empty()
        st.session_state.hist.append({"r":"a","t":resp})
        st.markdown(f'<div class="msg-a">{resp}</div>', unsafe_allow_html=True)
        st.rerun()