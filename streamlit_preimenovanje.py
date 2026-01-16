import os
import io
import zipfile
import streamlit as st
from datetime import datetime
from pathlib import Path
from typing import Dict, List
try:
    from dalux_api import DaluxUploadManager
    DALUX_AVAILABLE = True
except ImportError:
    DALUX_AVAILABLE = False

# Constants
TIP_OPTIONS = {
    "NAC": "Načrt", "DOK": "Dokument", "FOT": "Fotografija", "SIT": "Situacija",
    "PRO": "Projekt", "DOP": "Dopis", "POR": "Poročilo", "PON": "Ponudba",
    "POG": "Pogodba", "NAR": "Naročilo", "RAC": "Račun", "KOI": "Kontrola",
    "TER": "Terminski plan", "SPE": "Specifikacija", "EVD": "Evidenca"
}

FAZA_OPTIONS = {
    "PON": "Ponudba", "PRO": "Projektiranje", "PGD": "PGD",
    "PZI": "PZI", "PID": "PID", "IZV": "Izvedba",
    "ZAK": "Zaključek", "GAR": "Garancija", "SPL": "Splošno"
}

LOK_OPTIONS = {
    "NAR": "Naročnik", "IZV": "Izvajalec", "NAD": "Nadzornik",
    "PRO": "Projektant", "PDI": "Podizvajalec", "DOB": "Dobavitelj",
    "SKO": "Ostalo"
}

MAPNA_STRUKTURA = {
    "00_Navodila": [],
    "01_Pogodba_Admin": [
        "01_Ponudbe", "02_Pogodba", "03_Dodatki_Pogodbi",
        "04_Imenovanja", "05_Odlocbe", "06_Zavarovanja"
    ],
    "02_Projektna_dok": ["01_IDZ", "02_PGD", "03_PZI", "04_PID", "05_Soglasja"],
    "03_Izvedbena_dok": ["01_Atesti", "02_Delavniski_Nacrti", "03_Izjave_Certifikati", "04_Tehnicna_Dok"],
    "04_Planiranje": ["01_Terminski_Plan", "02_Fazni_Plan", "03_Sestanki"],
    "05_Nabava": ["01_Narocila", "02_Podizvajalci", "03_Dobavnice", "04_Ponudbe_Dobav"],
    "06_Financno": ["01_Situacije", "02_Dodatna_Dela", "03_Racuni", "04_Poravnave"],
    "07_Gradnja": ["01_Gradbeni_Dnevnik", "02_Zapisniki", "03_Foto_Porocila", "04_Kontrole", "05_Meritve"],
    "08_Korespondenca": ["01_Dopisi", "02_Odgovori", "03_Zahtevki", "04_Reklamacije"],
    "09_Prevzem_garancije": ["01_PID_Izvedeno", "02_Tehnicni_Prevzem", "03_Uporabno_Dovoljenje",
                             "04_Garancije", "05_Vzdrz_Navodila"],
    "10_Interno": ["01_Interni_Zapiski", "02_Kolektor"]
}

# Page config
st.set_page_config(
    page_title="Preimenovanje Projektnih Datotek",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #263740 0%, #34495e 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .file-item-complete {
        background: #d4edda;
        border-left: 4px solid #28a745;
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 5px;
    }
    .file-item-incomplete {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 5px;
    }
    .preview-box {
        background: #eaf7ff;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #3498db;
        margin: 1rem 0;
    }
    .stButton>button {
        width: 100%;
    }
    .upload-section {
        background: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        border: 2px dashed #6c757d;
        text-align: center;
        margin: 2rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
def init_session_state():
    if 'files' not in st.session_state:
        st.session_state.files = []
    if 'current_index' not in st.session_state:
        st.session_state.current_index = 0
    if 'projekt_sifra' not in st.session_state:
        st.session_state.projekt_sifra = ""
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 0
    if 'uploader_key' not in st.session_state:
        st.session_state.uploader_key = 0
    if 'projekt_started' not in st.session_state:
        st.session_state.projekt_started = False

    if 'TIP_OPTIONS' not in st.session_state:
        st.session_state.TIP_OPTIONS = TIP_OPTIONS.copy()
    if 'FAZA_OPTIONS' not in st.session_state:
        st.session_state.FAZA_OPTIONS = FAZA_OPTIONS.copy()
    if 'LOK_OPTIONS' not in st.session_state:
        st.session_state.LOK_OPTIONS = LOK_OPTIONS.copy()

    if 'dalux_api_key' not in st.session_state:
        st.session_state.dalux_api_key = ""
    if 'dalux_connected' not in st.session_state:
        st.session_state.dalux_connected = False
    if 'dalux_project_id' not in st.session_state:
        st.session_state.dalux_project_id = ""
    if 'dalux_file_area_id' not in st.session_state:
        st.session_state.dalux_file_area_id = ""
    if 'upload_mode' not in st.session_state:
        st.session_state.upload_mode = "zip"  # "zip" or "dalux"

    if 'load_projects' not in st.session_state:
        st.session_state.load_projects = False
    if 'temp_api_key' not in st.session_state:
        st.session_state.temp_api_key = ""

init_session_state()

# Helper functions
def add_file_to_processing(uploaded_file):
    """Add uploaded file to processing list"""
    file_content = uploaded_file.read()
    file_name = uploaded_file.name
    
    # Check if already added
    existing = [f['original_name'] for f in st.session_state.files]
    if file_name in existing:
        return False
    
    entry = {
        'original_name': file_name,
        'content': file_content,
        'extension': os.path.splitext(file_name)[1][1:],
        'tip': '',
        'faza': '',
        'lok': '',
        'ime': os.path.splitext(file_name)[0].replace(' ', '_')[:100],
        'datum': '',
        'target_subfolder': ''
    }
    st.session_state.files.append(entry)
    return True

def upload_to_dalux():
    """Upload all files to Dalux"""
    if not DALUX_AVAILABLE:
        st.error("Dalux API module not available")
        return False
    
    try:
        manager = DaluxUploadManager(st.session_state.dalux_api_key)
        
        # Prepare files organized by folder
        files_dict = {}
        for file_data in st.session_state.files:
            if is_file_complete(file_data):
                folder_path = file_data['target_subfolder']
                filename = generate_new_filename(file_data)
                content = file_data['content']
                
                if folder_path not in files_dict:
                    files_dict[folder_path] = []
                files_dict[folder_path].append((filename, content))
        
        # Upload using project_id
        with st.spinner("Nalagam datoteke v Dalux..."):
            results = manager.bulk_upload_from_structure(
                st.session_state.projekt_sifra,  
                files_dict
            )
        
        return results
    
    except Exception as e:
        st.error(f"Napaka pri nalaganju v Dalux: {str(e)}")
        return None

def generate_new_filename(file_data: Dict) -> str:
    """Generate new filename from metadata"""
    parts = [
        st.session_state.projekt_sifra,
        file_data.get('tip', ''),
        file_data.get('faza', ''),
        file_data.get('lok', ''),
        file_data.get('ime', '')
    ]
    
    if file_data.get('datum'):
        try:
            dt = datetime.strptime(file_data['datum'], "%Y%m%d")
            parts.append(dt.strftime("%Y%m%d"))
        except:
            pass
    
    parts = [p for p in parts if p]
    if not parts:
        return ""
    
    ext = file_data.get('extension', '')
    return f"{'-'.join(parts)}{'.' + ext if ext else ''}"
    

def is_file_complete(file_data: Dict) -> bool:
    """Check if file has all required data"""
    return all([
        file_data.get('tip'),
        file_data.get('faza'),
        file_data.get('lok'),
        file_data.get('ime'),
        file_data.get('target_subfolder')
    ])



def create_zip_with_structure() -> io.BytesIO:
    """Create ZIP file with proper folder structure and renamed files"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Create folder structure (empty folders)
        for main, subs in MAPNA_STRUKTURA.items():
            zip_file.writestr(f"{main}/", "")
            for sub in subs:
                zip_file.writestr(f"{main}/{sub}/", "")
        
        # Add renamed files
        for file_data in st.session_state.files:
            if is_file_complete(file_data):
                new_name = generate_new_filename(file_data)
                target_path = f"{file_data['target_subfolder']}/{new_name}"
                zip_file.writestr(target_path, file_data['content'])
    
    zip_buffer.seek(0)
    return zip_buffer

def add_custom_option(dict_key: str, code: str, desc: str):
    code = code.strip().upper()
    desc = desc.strip()
    
    if not code or not desc:
        return "❌ Vnesi kodo in opis"
    if len(code) != 3:
        return "❌ Koda mora imeti 3 črke"
    if code in st.session_state[dict_key]:
        return "❌ Ta koda že obstaja"
    
    st.session_state[dict_key][code] = desc
    return f"✅ Dodano: {code} — {desc}"

# Main app
st.markdown('<div class="main-header"><h1>📁 Preimenovanje Projektnih Datotek</h1></div>', unsafe_allow_html=True)

if not st.session_state.projekt_started:
    # Show project setup screen
    st.markdown("## Začni nov projekt")
    st.markdown("---")
    
    col_left, col_center, col_right = st.columns([1, 2, 1])
    
    with col_center:
        st.markdown("### Izberi projekt iz Dalux")
        
        # API Key input
        dalux_api_key = st.text_input(
            "Dalux API Key:",
            type="password",
            help="Vnesi svoj Dalux API ključ",
            key="startup_api_key"
        )
        
        # Button to load projects
        if st.button("🔍 Naloži projekte", type="secondary", use_container_width=True):
            st.session_state.temp_api_key = dalux_api_key
            st.session_state.load_projects = True
            st.rerun()
        
        # Show projects if loaded
        if st.session_state.get('load_projects', False) and st.session_state.get('temp_api_key'):
            if DALUX_AVAILABLE:
                try:
                    from dalux_api import DaluxAPIClient
                    client = DaluxAPIClient(st.session_state.temp_api_key)
                    
                    with st.spinner("Nalagam projekte..."):
                        projects = client.get_all_projects()
                    
                    if projects:
                        # Create options for selectbox
                        project_options = {
                            f"{p['data']['number']} - {p['data']['projectName']}": p['data']
                            for p in projects
                        }
                        
                        selected = st.selectbox(
                            "Izberi projekt:",
                            options=[""] + list(project_options.keys()),
                            format_func=lambda x: "Izberi projekt..." if x == "" else x,
                            key="project_selector"
                        )
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        if st.button("▶ Začni projekt", type="primary", use_container_width=True, disabled=not selected):
                            project_data = project_options[selected]
                            st.session_state.projekt_sifra = project_data['number']
                            st.session_state.dalux_api_key = st.session_state.temp_api_key
                            st.session_state.dalux_project_id = project_data['projectId']
                            st.session_state.projekt_started = True
                            
                            # Setup file area
                            try:
                                manager = DaluxUploadManager(st.session_state.dalux_api_key)
                                file_areas = manager.client.get_file_areas(project_data['projectId'])
                                if file_areas:
                                    st.session_state.dalux_file_area_id = file_areas[0]["data"]["fileAreaId"]
                                    st.session_state.dalux_connected = True
                            except:
                                pass
                            
                            # Clean up temp state
                            st.session_state.load_projects = False
                            st.session_state.temp_api_key = ""
                            st.rerun()
                        
                        if not selected:
                            st.info("Izberi projekt iz seznama")
                    else:
                        st.warning("Ni najdenih projektov")
                        
                except Exception as e:
                    st.error(f"Napaka pri pridobivanju projektov: {str(e)}")
                    st.info("Preveri API ključ in poskusi ponovno")
                    if st.button("🔄 Poskusi ponovno"):
                        st.session_state.load_projects = False
                        st.rerun()
            else:
                st.warning("⚠️ Dalux modul ni na voljo")
        
        elif dalux_api_key:
            st.info("Klikni 'Naloži projekte' za nadaljevanje")
        else:
            st.info("Vnesi API ključ za začetek")
    
    st.stop()

# Sidebar - Instructions & Settings
with st.sidebar:
    st.header("⚙️ Nastavitve")
    
    # Display current project code (read-only)
    st.text_input(
        "Šifra projekta:",
        value=st.session_state.projekt_sifra,
        help="Šifra se uporabi kot prefix v vseh datotekah",
        disabled=True
    )
    
    if st.button("🔄 Zamenjaj projekt", type="secondary", use_container_width=True):
        st.session_state.projekt_started = False
        st.session_state.projekt_sifra = ""
        st.session_state.dalux_project_id = ""
        st.session_state.dalux_file_area_id = ""
        st.session_state.dalux_api_key = ""
        st.session_state.dalux_connected = False
        st.session_state.files = []
        st.session_state.current_index = 0
        st.session_state.current_page = 0
        st.rerun()

    st.markdown("---")
    st.header("Dalux status")

    if st.session_state.projekt_started and st.session_state.dalux_project_id:
        st.success("✅ Povezan z Dalux")
        st.caption(f"Projekt ID: {st.session_state.dalux_project_id}")
        st.caption(f"Šifra: {st.session_state.projekt_sifra}")
    else:
        st.info("ℹ️ Dalux povezava se vzpostavi pri izbiri projekta")
    
    st.markdown("---")
    
    st.header("ℹ️ Navodila")
    with st.expander("📖 Kako uporabljati", expanded=False):
        st.markdown("""
        1. **Naloži datoteke** - Uporabi spodnji gumb za nalaganje
        2. **Izpolni podatke** - Za vsako datoteko vnesi TIP, FAZO, LOK, IME
        3. **Izberi podmapo** - Določi kam bo datoteka shranjena
        4. **Prenesi ZIP** - Ko so vse datoteke pripravljene, prenesi ZIP
        
        **Obvezna polja:** TIP, FAZA, LOK, IME, Ciljna podmapa
        """)
    
    st.subheader("➕ Dodaj nove kode")

    with st.expander("➕ Dodaj TIP"):
        tip_code = st.text_input("Koda (3 črke)", key="new_tip_code")
        tip_desc = st.text_input("Opis", key="new_tip_desc")
        if st.button("Dodaj TIP"):
            msg = add_custom_option("TIP_OPTIONS", tip_code, tip_desc)
            st.toast(msg)

    with st.expander("➕ Dodaj FAZA"):
        faza_code = st.text_input("Koda (3 črke)", key="new_faza_code")
        faza_desc = st.text_input("Opis", key="new_faza_desc")
        if st.button("Dodaj FAZA"):
            msg = add_custom_option("FAZA_OPTIONS", faza_code, faza_desc)
            st.toast(msg)

    with st.expander("➕ Dodaj LOK"):
        lok_code = st.text_input("Koda (3 črke)", key="new_lok_code")
        lok_desc = st.text_input("Opis", key="new_lok_desc")
        if st.button("Dodaj LOK"):
            msg = add_custom_option("LOK_OPTIONS", lok_code, lok_desc)
            st.toast(msg)
    
    st.markdown("---")
    
    if st.session_state.files:
        complete = sum(1 for f in st.session_state.files if is_file_complete(f))
        st.metric("Napredek", f"{complete}/{len(st.session_state.files)}")
        
        if st.button("🗑️ Počisti vse", type="secondary"):
            st.session_state.files = []
            st.session_state.current_index = 0
            st.rerun()

# Main area - Two columns
col1, col2 = st.columns([1, 2])

with col1:
    st.header("📤 1. Naloži datoteke")
    
    # File uploader with dynamic key to reset it
    uploaded_files = st.file_uploader(
        "Izberi datoteke za procesiranje",
        accept_multiple_files=True,
        help="Izberi lahko več datotek hkrati (Ctrl+Click ali Shift+Click)",
        key=f"uploader_{st.session_state.uploader_key}"
    )
    
    if uploaded_files:
        added = 0
        for uploaded_file in uploaded_files:
            if add_file_to_processing(uploaded_file):
                added += 1
        
        if added > 0:
            st.success(f"✅ Dodanih {added} novih datotek")
            # Increment uploader key to clear the widget
            st.session_state.uploader_key += 1
            st.rerun()
    
    if not st.session_state.files:
        st.info("👆 Naloži datoteke za začetek")
    
    st.markdown("---")
    
    # File list with pagination
    if st.session_state.files:
        st.subheader(f"📋 Seznam datotek ({len(st.session_state.files)})")
        
        # Pagination settings
        files_per_page = 10
        total_pages = (len(st.session_state.files) - 1) // files_per_page + 1
        
        # Page navigation
        if total_pages > 1:
            page_col1, page_col2, page_col3 = st.columns([1, 2, 1])
            with page_col1:
                if st.button("◀", disabled=st.session_state.current_page == 0, key="prev_page"):
                    st.session_state.current_page -= 1
                    st.rerun()
            with page_col2:
                st.markdown(f"<div style='text-align: center;'>Stran {st.session_state.current_page + 1} / {total_pages}</div>", unsafe_allow_html=True)
            with page_col3:
                if st.button("▶", disabled=st.session_state.current_page >= total_pages - 1, key="next_page"):
                    st.session_state.current_page += 1
                    st.rerun()
        
        # Calculate slice for current page
        start_idx = st.session_state.current_page * files_per_page
        end_idx = min(start_idx + files_per_page, len(st.session_state.files))
        
        # Display files for current page
        for idx in range(start_idx, end_idx):
            file_data = st.session_state.files[idx]
            complete = is_file_complete(file_data)
            
            col_status, col_name, col_delete = st.columns([2, 6, 2])
            
            with col_status:
                st.write("✅" if complete else "⏳")
            
            with col_name:
                if st.button(
                    file_data['original_name'],
                    key=f"select_{idx}",
                    help="Klikni za urejanje",
                    use_container_width=True
                ):
                    st.session_state.current_index = idx
                    st.rerun()
            
            with col_delete:
                if st.button("❌", key=f"delete_{idx}", help="Odstrani datoteko"):
                    # Remove the file
                    st.session_state.files.pop(idx)
                    
                    # Adjust current index if needed
                    if len(st.session_state.files) > 0:
                        if st.session_state.current_index >= len(st.session_state.files):
                            st.session_state.current_index = len(st.session_state.files) - 1
                    else:
                        st.session_state.current_index = 0
                    
                    # Adjust current page if needed
                    if st.session_state.files:
                        new_total_pages = (len(st.session_state.files) - 1) // files_per_page + 1
                        if st.session_state.current_page >= new_total_pages:
                            st.session_state.current_page = max(0, new_total_pages - 1)
                    else:
                        st.session_state.current_page = 0
                    
                    # Increment uploader key to reset the file uploader widget
                    st.session_state.uploader_key += 1
                    st.rerun()

with col2:
    st.header("✏️ 2. Uredi podatke")
    
    if st.session_state.files and st.session_state.current_index < len(st.session_state.files):
        current_file = st.session_state.files[st.session_state.current_index]
        
        # Navigation
        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
        with nav_col1:
            if st.button("◀ Prejšnja", disabled=st.session_state.current_index == 0):
                st.session_state.current_index -= 1
                st.rerun()
        with nav_col2:
            st.markdown(f"<div style='text-align: center; padding: 10px;'><strong>Datoteka {st.session_state.current_index + 1} / {len(st.session_state.files)}</strong></div>", unsafe_allow_html=True)
        with nav_col3:
            if st.button("Naslednja ▶", disabled=st.session_state.current_index >= len(st.session_state.files) - 1):
                st.session_state.current_index += 1
                st.rerun()
        
        st.info(f"📄 **Originalno ime:** `{current_file['original_name']}`")
        
        st.markdown("---")
        
        # Form
        tip = st.selectbox(
            "TIP dokumenta: *",
            options=[""] + list(st.session_state.TIP_OPTIONS.keys()),
            format_func=lambda x: f"{x} - {st.session_state.TIP_OPTIONS.get(x, '')}" if x else "⚠️ Izberi TIP...",
            index=list(TIP_OPTIONS.keys()).index(current_file['tip']) + 1 if current_file['tip'] in TIP_OPTIONS else 0,
            key=f"tip_{st.session_state.current_index}"
        )
        current_file['tip'] = tip
        
        faza = st.selectbox(
            "FAZA projekta: *",
            options=[""] + list(st.session_state.FAZA_OPTIONS.keys()),
            format_func=lambda x: f"{x} - {st.session_state.FAZA_OPTIONS.get(x, '')}" if x else "⚠️ Izberi FAZO...",
            index=list(FAZA_OPTIONS.keys()).index(current_file['faza']) + 1 if current_file['faza'] in FAZA_OPTIONS else 0,
            key=f"faza_{st.session_state.current_index}"
        )
        current_file['faza'] = faza
        
        lok = st.selectbox(
            "LOK (Vloga): *",
            options=[""] + list(st.session_state.LOK_OPTIONS.keys()),
            format_func=lambda x: f"{x} - {st.session_state.LOK_OPTIONS.get(x, '')}" if x else "⚠️ Izberi LOK...",
            index=list(LOK_OPTIONS.keys()).index(current_file['lok']) + 1 if current_file['lok'] in LOK_OPTIONS else 0,
            key=f"lok_{st.session_state.current_index}"
        )
        current_file['lok'] = lok
        
        ime = st.text_input(
            "IME dokumenta (maks. 100 znakov): *",
            value=current_file['ime'],
            max_chars=100,
            help="Presledki bodo samodejno zamenjani z _",
            key=f"ime_{st.session_state.current_index}"
        )
        current_file['ime'] = ime.replace(' ', '_')[:100]
        st.caption(f"Znakov: {len(current_file['ime'])}/100")
        
        datum = st.text_input(
            "DATUM (opcijsko):",
            value=current_file['datum'],
            placeholder="YYYY-MM-DD (npr. 2024-03-15)",
            help="Format: YYYY-MM-DD",
            key=f"datum_{st.session_state.current_index}"
        )
        current_file['datum'] = datum
        
        # Target subfolder picker
        st.markdown("**Ciljna podmapa: ***")
        
        # Create flat list of all possible paths
        all_paths = []
        for main, subs in MAPNA_STRUKTURA.items():
            all_paths.append(main)
            for sub in subs:
                all_paths.append(f"{main}/{sub}")
        
        target_subfolder = st.selectbox(
            "Izberi kam bo datoteka shranjena:",
            options=[""] + all_paths,
            index=all_paths.index(current_file['target_subfolder']) + 1 if current_file['target_subfolder'] in all_paths else 0,
            key=f"target_{st.session_state.current_index}",
            help="Izberi mapo iz strukture projekta"
        )
        current_file['target_subfolder'] = target_subfolder
        
        st.markdown("---")
        # Check if file just became complete and trigger rerun
        was_complete_before = st.session_state.get(f'was_complete_{st.session_state.current_index}', False)
        is_complete_now = is_file_complete(current_file)
        
        if not was_complete_before and is_complete_now:
            st.session_state[f'was_complete_{st.session_state.current_index}'] = True
            st.rerun()
        elif was_complete_before and not is_complete_now:
            st.session_state[f'was_complete_{st.session_state.current_index}'] = False
        elif not was_complete_before and not is_complete_now:
            st.session_state[f'was_complete_{st.session_state.current_index}'] = False
        
        # Preview section after form
        new_name = generate_new_filename(current_file)
        
        if new_name and current_file['target_subfolder']:
            full_path = f"{current_file['target_subfolder']}/{new_name}"
            
            st.markdown(f"""
            <div class="preview-box">
                <strong>📝 Novo ime datoteke:</strong><br>
                <code style="font-size: 1.1em; color: #2c3e50;">{new_name}</code><br><br>
                <strong>📁 Pot v ZIP arhivu:</strong><br>
                <code style="color: #2c3e50;">{full_path}</code>
            </div>
            """, unsafe_allow_html=True)
            
            if is_file_complete(current_file):
                st.success("✅ Vsi podatki izpolnjeni!")
                
            else:
                st.warning("⚠️ Izpolni vsa obvezna polja (označena z *)")
                
        elif new_name or current_file['target_subfolder']:
            st.info("⏳ Predogled bo prikazan ko bodo izpolnjena vsa obvezna polja")
    
    else:
        st.info("👈 Izberi datoteko iz seznama za urejanje")

# Download section
st.markdown("---")
st.header("📥 3. Prenesi rezultat ali naloži v Dalux")

if st.session_state.files:
    complete_files = sum(1 for f in st.session_state.files if is_file_complete(f))
    incomplete_files = len(st.session_state.files) - complete_files
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Skupaj datotek", len(st.session_state.files))
    with col2:
        st.metric("Pripravljeno", complete_files, delta=None if complete_files == len(st.session_state.files) else f"-{incomplete_files}")
    with col3:
        st.metric("Manjka", incomplete_files)
    
    if complete_files == len(st.session_state.files):
        st.success("🎉 Vse datoteke so pripravljene!")
        
        # Choose upload mode
        upload_mode = st.radio(
            "Izberi način:",
            options=["zip", "dalux"],
            format_func=lambda x: "📦 Prenesi ZIP arhiv" if x == "zip" else "☁️ Naloži direktno v Dalux",
            horizontal=True,
            key="upload_mode_radio"
        )
        st.session_state.upload_mode = upload_mode
        
        if upload_mode == "zip":
            # Generate ZIP
            zip_buffer = create_zip_with_structure()
            
            st.download_button(
                label="⬇️ PRENESI ZIP ARHIV S PREIMENOVANIMI DATOTEKAMI",
                data=zip_buffer,
                file_name=f"projekt_{st.session_state.projekt_sifra}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )
            
            st.info("💡 ZIP vsebuje celotno mapno strukturo projekta z preimenovanimi datotekami")
        
        elif upload_mode == "dalux":
            if not DALUX_AVAILABLE:
                st.error("❌ Dalux modul ni na voljo")
            elif not st.session_state.dalux_connected:
                st.warning("⚠️ Najprej se poveži z Dalux v stranskem meniju")
            else:
                st.info(f"📤 Naložil bom {complete_files} datotek v Dalux projekt: {st.session_state.projekt_sifra}")
                
                
                if st.button("☁️ NALOŽI V DALUX", type="primary", use_container_width=True):
                    results = upload_to_dalux()
                    
                    if results:
                        st.success(f"✅ Uspešno naloženih: {results['success']}")
                        if results['failed'] > 0:
                            st.error(f"❌ Neuspešnih: {results['failed']}")
                        
                        # Show details
                        with st.expander("📋 Podrobnosti nalaganja"):
                            for detail in results['details']:
                                if detail['status'] == 'success':
                                    st.success(f"✅ {detail['file']} → {detail['folder']}")
                                else:
                                    st.error(f"❌ {detail['file']}: {detail['error']}")
    
    elif complete_files > 0:
        st.warning(f"⚠️ {incomplete_files} datotekam še manjkajo podatki. Izpolni vse, da lahko preneseš ZIP ali naloži v Dalux.")
        
        # Show which files are incomplete
        with st.expander("📋 Prikaži nepopolne datoteke"):
            for idx, f in enumerate(st.session_state.files):
                if not is_file_complete(f):
                    missing = []
                    if not f.get('tip'): missing.append("TIP")
                    if not f.get('faza'): missing.append("FAZA")
                    if not f.get('lok'): missing.append("LOK")
                    if not f.get('ime'): missing.append("IME")
                    if not f.get('target_subfolder'): missing.append("Podmapa")
                    
                    st.write(f"❌ **{f['original_name']}** - Manjka: {', '.join(missing)}")
    else:
        st.warning("⚠️ Še nobena datoteka ni pripravljena. Začni z izpolnjevanjem podatkov.")

else:
    st.info("👆 Najprej naloži datoteke")

# Footer
st.markdown("---")
