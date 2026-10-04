import os
import uuid
import unicodedata
import urllib.parse
from io import BytesIO
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, abort, send_file
from supabase import create_client, Client
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, HRFlowable

app = Flask(__name__)
app.secret_key = "secret_key_ies_6039"

# Configuración Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# Bucket de Supabase Storage donde se guardan los documentos de los postulantes.
# Tiene que existir y estar configurado como público (ver instrucciones).
BUCKET_DOCUMENTOS = "documentos-postulantes"

def normalizar(texto):
    """Pasa el texto a minúsculas y le quita tildes/diacríticos, para poder comparar
    o filtrar sin que 'Orán' != 'oran' o 'Profesorado' != 'profesorado' rompan el match."""
    if not texto:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in texto if not unicodedata.combining(c))

def subir_archivo(file_storage, subcarpeta):
    """Sube un archivo adjunto del formulario a Supabase Storage y devuelve su URL pública.
    Devuelve None si el campo vino vacío (el postulante no adjuntó ese archivo)."""
    if not file_storage or file_storage.filename == '':
        return None
    try:
        ext = os.path.splitext(file_storage.filename)[1]
        nombre_archivo = f"{subcarpeta}/{uuid.uuid4().hex}{ext}"
        contenido = file_storage.read()
        supabase.storage.from_(BUCKET_DOCUMENTOS).upload(
            nombre_archivo,
            contenido,
            {"content-type": file_storage.mimetype or "application/octet-stream"}
        )
        return supabase.storage.from_(BUCKET_DOCUMENTOS).get_public_url(nombre_archivo)
    except Exception as e:
        print(f"Error al subir archivo a Storage: {e}")
        return None

LOGO_PATH = os.path.join(os.path.dirname(__file__), 'static', 'logo_salta.png')

def generar_comprobante_pdf(docente, materias_habilitadas):
    """Genera el PDF de comprobante de inscripción del postulante, con el logo del
    Ministerio de Educación y Cultura de Salta, y lo devuelve como BytesIO."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm
    )
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle('TituloComprobante', parent=styles['Title'], fontSize=16,
                                   textColor=colors.HexColor('#4c1d95'), spaceAfter=2)
    subtitulo_style = ParagraphStyle('Subtitulo', parent=styles['Normal'], fontSize=9,
                                      textColor=colors.HexColor('#64748b'), spaceAfter=12)
    label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=10,
                                  textColor=colors.HexColor('#334155'))
    h2_style = ParagraphStyle('H2Comp', parent=styles['Heading2'], fontSize=12,
                               textColor=colors.HexColor('#4c1d95'))
    pie_style = ParagraphStyle('Pie', parent=styles['Normal'], fontSize=8,
                                textColor=colors.HexColor('#94a3b8'))

    story = []

    if os.path.exists(LOGO_PATH):
        ancho_logo = 60 * mm
        alto_logo = ancho_logo * (103 / 370)  # mantiene la proporción real del logo
        story.append(RLImage(LOGO_PATH, width=ancho_logo, height=alto_logo))
        story.append(Spacer(1, 10))
    else:
        print(f"AVISO: no se encontró el logo en {LOGO_PATH}. El comprobante se genera sin logo.")

    story.append(Paragraph("Comprobante de Inscripción Docente", titulo_style))
    story.append(Paragraph(
        "Ministerio de Educación y Cultura - Provincia de Salta | Nomenclador y Relevamiento Docente",
        subtitulo_style
    ))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#c7d2fe'), thickness=1))
    story.append(Spacer(1, 14))

    fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
    story.append(Paragraph(f"<b>Fecha de emisión:</b> {fecha}", label_style))
    story.append(Spacer(1, 10))

    localidades = docente.get('localidades_postulacion') or []
    label_bold_style = ParagraphStyle('LabelBold', parent=styles['Normal'], fontSize=10,
                                       textColor=colors.HexColor('#4c1d95'), fontName='Helvetica-Bold')
    valor_style = ParagraphStyle('Valor', parent=styles['Normal'], fontSize=10,
                                  textColor=colors.HexColor('#334155'))
    datos = [
        [Paragraph("Nombre y Apellido:", label_bold_style), Paragraph(docente.get('nombre_apellido') or '', valor_style)],
        [Paragraph("DNI:", label_bold_style), Paragraph(docente.get('dni') or '', valor_style)],
        [Paragraph("Teléfono:", label_bold_style), Paragraph(docente.get('telefono') or '', valor_style)],
        [Paragraph("Email:", label_bold_style), Paragraph(docente.get('email') or '', valor_style)],
        [Paragraph("Domicilio:", label_bold_style), Paragraph(docente.get('domicilio') or '', valor_style)],
        [Paragraph("Localidades postuladas:", label_bold_style), Paragraph(", ".join(localidades), valor_style)],
        [Paragraph("Título 1:", label_bold_style), Paragraph(f"{docente.get('titulo_base_1') or ''} ({docente.get('anio_egreso_1') or ''})", valor_style)],
    ]
    if docente.get('titulo_base_2'):
        datos.append([Paragraph("Título 2:", label_bold_style), Paragraph(f"{docente.get('titulo_base_2')} ({docente.get('anio_egreso_2') or ''})", valor_style)])

    tabla_datos = Table(datos, colWidths=[50 * mm, 110 * mm])
    tabla_datos.setStyle(TableStyle([
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(tabla_datos)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Unidades Curriculares Habilitadas", h2_style))
    story.append(Spacer(1, 6))

    celda_style = ParagraphStyle('Celda', parent=styles['Normal'], fontSize=8,
                                  textColor=colors.HexColor('#1e293b'), leading=10)
    celda_header_style = ParagraphStyle('CeldaHeader', parent=styles['Normal'], fontSize=8,
                                         textColor=colors.HexColor('#4c1d95'), fontName='Helvetica-Bold', leading=10)

    if materias_habilitadas:
        filas = [[
            Paragraph("Código", celda_header_style),
            Paragraph("Unidad Curricular", celda_header_style),
            Paragraph("Carrera", celda_header_style),
            Paragraph("Instituto", celda_header_style),
        ]]
        for m in materias_habilitadas:
            inst = m.get('institutos') or {}
            filas.append([
                Paragraph(m.get('codigo') or '', celda_style),
                Paragraph(m.get('nombre_unidad_curricular') or '', celda_style),
                Paragraph(m.get('carrera') or '', celda_style),
                Paragraph(inst.get('nombre') or '', celda_style)
            ])
        tabla_mat = Table(filas, colWidths=[18 * mm, 50 * mm, 47 * mm, 45 * mm])
        tabla_mat.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ede9fe')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ]))
        story.append(tabla_mat)
    else:
        story.append(Paragraph(
            "No se encontraron materias compatibles en el nomenclador para los títulos "
            "ingresados al momento de la inscripción.",
            label_style
        ))

    story.append(Spacer(1, 26))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0'), thickness=0.5))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Este comprobante certifica que la postulación fue recibida por el sistema. "
        "No implica la aprobación de la inscripción, la cual queda sujeta a revisión administrativa.",
        pie_style
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer

def armar_mailto(docente, materias_habilitadas, instituto_id=None):
    """Arma un link mailto: con asunto y cuerpo pre-cargados con los datos del postulante
    y las materias habilitadas, dirigido al email del instituto correspondiente.

    Si se pasa instituto_id, filtra las materias para armar el correo solo con
    las que correspondan a ESE instituto puntual (para cuando el docente tiene
    materias habilitadas en más de un IES y hay que elegir a cuál enviar)."""
    materias_filtradas = materias_habilitadas
    if instituto_id:
        materias_filtradas = [
            m for m in materias_habilitadas
            if m.get('institutos') and str(m['institutos'].get('id')) == str(instituto_id)
        ]

    asunto = f"Postulación Docente - {docente.get('nombre_apellido')} (DNI: {docente.get('dni')})"

    lineas = [
        f"Nombre y Apellido: {docente.get('nombre_apellido')}",
        f"DNI: {docente.get('dni')}",
        f"Teléfono: {docente.get('telefono')}",
        f"Email: {docente.get('email')}",
        f"Título 1: {docente.get('titulo_base_1')} ({docente.get('anio_egreso_1')})",
    ]
    if docente.get('titulo_base_2'):
        lineas.append(f"Título 2: {docente.get('titulo_base_2')} ({docente.get('anio_egreso_2')})")
    lineas.append("")

    if materias_filtradas:
        lineas.append("Unidades curriculares habilitadas según nomenclador:")
        for m in materias_filtradas:
            lineas.append(f"- {m.get('codigo')} | {m.get('nombre_unidad_curricular')} ({m.get('carrera')})")
        email_destino = materias_filtradas[0].get('institutos', {}).get('email') or 'ies6039aguaray@gmail.com'
    else:
        lineas.append("No se encontraron materias compatibles en el nomenclador para los títulos ingresados.")
        email_destino = 'ies6039aguaray@gmail.com'

    cuerpo = "\n".join(lineas)

    return (
        f"mailto:{email_destino}"
        f"?subject={urllib.parse.quote(asunto)}"
        f"&body={urllib.parse.quote(cuerpo)}"
    )

def init_db():
    """Ejecuta las consultas SQL de inicialización y actualización de tablas en Supabase"""
    if not supabase:
        return
    
    # 1. Actualizar tabla de institutos (si hace falta)
    sql_institutos = """
    CREATE TABLE IF NOT EXISTS institutos (
        id SERIAL PRIMARY KEY,
        numero_ies VARCHAR(10) NOT NULL,
        nombre VARCHAR(150) NOT NULL,
        localidad VARCHAR(100) NOT NULL,
        direccion VARCHAR(200),
        email VARCHAR(100) NOT NULL,
        telefono VARCHAR(50)
    );
    """
    
    # 2. Asegurar que materias_nomenclador vincule la resolución de la carrera
    sql_materias = """
    CREATE TABLE IF NOT EXISTS materias_nomenclador (
        id SERIAL PRIMARY KEY,
        instituto_id INT REFERENCES institutos(id),
        resolucion VARCHAR(100) NOT NULL,
        carrera VARCHAR(200) NOT NULL,
        anio INT NOT NULL,
        codigo VARCHAR(20) NOT NULL,
        nombre_unidad_curricular VARCHAR(200) NOT NULL,
        regimen VARCHAR(50) NOT NULL,
        formato VARCHAR(50),
        titulos_habilitantes TEXT[]
    );
    """
    
    # 3. Crear o verificar tabla de postulaciones con campos de control administrativo
    sql_postulaciones_obs = "ALTER TABLE postulaciones_docentes ADD COLUMN IF NOT EXISTS observaciones TEXT DEFAULT '';"
    sql_postulaciones_est = "ALTER TABLE postulaciones_docentes ADD COLUMN IF NOT EXISTS estado_inscripcion VARCHAR(50) DEFAULT 'PENDIENTE';"

    # 4. Campo "vigente" para las materias/carreras del nomenclador
    sql_materias_vigente = "ALTER TABLE materias_nomenclador ADD COLUMN IF NOT EXISTS vigente VARCHAR(10) DEFAULT 'Sí';"

    # 5. Domicilio del docente postulante
    sql_postulaciones_domicilio = "ALTER TABLE postulaciones_docentes ADD COLUMN IF NOT EXISTS domicilio VARCHAR(255);"

    queries = [sql_institutos, sql_materias, sql_postulaciones_obs, sql_postulaciones_est, sql_materias_vigente, sql_postulaciones_domicilio]
    
    for query in queries:
        try:
            if hasattr(supabase, 'rpc'):
                pass
        except Exception as e:
            print(f"Aviso en inicialización de DB: {e}")

# Inicializar esquema al arrancar
init_db()

# 1. RUTA PRINCIPAL: Formulario de Postulación Docente (Sin Login)
@app.route('/')
def index():
    materias_res = supabase.table('materias_nomenclador').select('*').execute() if supabase else None
    materias = materias_res.data if materias_res else []
    return render_template('index.html', materias=materias)

# 2. PROCESAR INSCRIPCIÓN Y VALIDAR CONTRA NOMENCLADOR
@app.route('/postular', methods=['POST'])
def postular():
    if not supabase:
        flash("Error de conexión a la base de datos", "error")
        return redirect(url_for('index'))

    nombre = request.form.get('nombre_apellido')
    dni = request.form.get('dni')
    telefono = request.form.get('telefono')
    email = request.form.get('email')
    domicilio = request.form.get('domicilio')
    localidades = request.form.getlist('localidades')
    
    titulo_1 = request.form.get('titulo_base_1')
    egreso_1 = request.form.get('anio_egreso_1')
    titulo_2 = request.form.get('titulo_base_2')
    egreso_2 = request.form.get('anio_egreso_2')
    
    experiencia = request.form.get('experiencia')
    capacitacion = request.form.get('capacitacion')

    # Subir documentación adjunta a Supabase Storage
    dni_lado_a_url = subir_archivo(request.files.get('dni_a'), 'dni')
    dni_lado_b_url = subir_archivo(request.files.get('dni_b'), 'dni')
    titulo_1_lado_a_url = subir_archivo(request.files.get('titulo_a'), 'titulos')
    titulo_1_lado_b_url = subir_archivo(request.files.get('titulo_b'), 'titulos')
    cv_nominal_pdf_url = subir_archivo(request.files.get('cv_pdf'), 'cv')

    post_data = {
        "nombre_apellido": nombre,
        "dni": dni,
        "telefono": telefono,
        "email": email,
        "domicilio": domicilio,
        "localidades_postulacion": localidades,
        "titulo_base_1": titulo_1,
        "anio_egreso_1": int(egreso_1) if egreso_1 else None,
        "titulo_base_2": titulo_2,
        "anio_egreso_2": int(egreso_2) if egreso_2 else None,
        "experiencia_nivel": experiencia,
        "capacitaciones": capacitacion,
        "dni_lado_a_url": dni_lado_a_url,
        "dni_lado_b_url": dni_lado_b_url,
        "titulo_1_lado_a_url": titulo_1_lado_a_url,
        "titulo_1_lado_b_url": titulo_1_lado_b_url,
        "cv_nominal_pdf_url": cv_nominal_pdf_url
    }
    
    inserted = supabase.table('postulaciones_docentes').insert(post_data).execute()
    postulante_id = inserted.data[0]['id']

    titulos_docente = [normalizar(t) for t in [titulo_1, titulo_2] if t]
    all_materias = supabase.table('materias_nomenclador').select('*, institutos(*)').execute().data
    
    materias_habilitadas = []
    
    for mat in all_materias:
        habilitantes = [normalizar(h) for h in mat.get('titulos_habilitantes', [])]
        es_hab = any(any(t in hab or hab in t for hab in habilitantes) for t in titulos_docente)
        
        if es_hab:
            materias_habilitadas.append(mat)
            supabase.table('historial_relevamiento').insert({
                "postulante_id": postulante_id,
                "materia_id": mat['id'],
                "estado_habilitacion": "HABILITADO"
            }).execute()

    # Armar lista de institutos involucrados (para elegir a quién enviar el correo
    # cuando el docente tiene materias habilitadas en más de un instituto)
    institutos_vistos = {}
    for m in materias_habilitadas:
        inst = m.get('institutos')
        if inst and inst.get('id') is not None:
            institutos_vistos[inst['id']] = {
                'id': inst['id'],
                'nombre': inst.get('nombre', 'Instituto sin nombre')
            }
    institutos_involucrados = list(institutos_vistos.values())

    mailto_links = {}
    if institutos_involucrados:
        for inst in institutos_involucrados:
            mailto_links[str(inst['id'])] = armar_mailto(post_data, materias_habilitadas, instituto_id=inst['id'])
    else:
        mailto_links['default'] = armar_mailto(post_data, materias_habilitadas)

    return render_template('resultado_postulacion.html',
                           docente=post_data,
                           materias=materias_habilitadas,
                           mailto_links=mailto_links,
                           institutos_involucrados=institutos_involucrados,
                           postulante_id=postulante_id)

# 3. SECCIÓN ADMINISTRADOR: Nomenclador y Estadísticas
@app.route('/admin')
def admin():
    if not supabase:
        return "Supabase no está configurado."
    
    materias = supabase.table('materias_nomenclador').select('*, institutos(*)').execute().data
    postulaciones = supabase.table('postulaciones_docentes').select('*').execute().data
    institutos = supabase.table('institutos').select('*').order('nombre').execute().data
    
    return render_template('admin.html', materias=materias, postulaciones=postulaciones, institutos=institutos)

# 4. GUARDAR NUEVA MATERIA EN NOMENCLADOR (ADMIN)
@app.route('/admin/nueva-materia', methods=['POST'])
def nueva_materia():
    try:
        inst_id = request.form.get('instituto_id')

        data = {
            "resolucion": request.form.get('resolucion'),
            "carrera": request.form.get('carrera'),
            "anio": int(request.form.get('anio')),
            "codigo": request.form.get('codigo'),
            "nombre_unidad_curricular": request.form.get('nombre_unidad_curricular'),
            "regimen": request.form.get('regimen'),
            "formato": request.form.get('formato'),
            "titulos_habilitantes": [t.strip() for t in request.form.get('titulos', '').split(',') if t.strip()],
            "instituto_id": int(inst_id) if inst_id else None
        }
        supabase.table('materias_nomenclador').insert(data).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error al insertar materia: {e}")
        return f"Ocurrió un error al guardar en la base de datos: {e}", 500

# --- GESTIÓN DE INSTITUTOS (NOMBRE, EMAIL DE CONTACTO PARA POSTULACIONES) ---
@app.route('/admin/instituciones')
def admin_instituciones():
    if not supabase:
        return "Supabase no configurado."
    institutos = supabase.table('institutos').select('*').order('nombre').execute().data
    return render_template('admin_instituciones.html', institutos=institutos)

@app.route('/admin/instituciones/nueva', methods=['POST'])
def nueva_institucion():
    try:
        data = {
            "numero_ies": request.form.get('numero_ies'),
            "nombre": request.form.get('nombre'),
            "localidad": request.form.get('localidad'),
            "direccion": request.form.get('direccion'),
            "email": request.form.get('email'),
            "telefono": request.form.get('telefono')
        }
        supabase.table('institutos').insert(data).execute()
        return redirect(url_for('admin_instituciones'))
    except Exception as e:
        return f"Error al crear el instituto: {e}", 500

@app.route('/admin/instituciones/editar/<int:id>', methods=['POST'])
def editar_institucion(id):
    try:
        supabase.table('institutos').update({
            "numero_ies": request.form.get('numero_ies'),
            "nombre": request.form.get('nombre'),
            "localidad": request.form.get('localidad'),
            "direccion": request.form.get('direccion'),
            "email": request.form.get('email'),
            "telefono": request.form.get('telefono')
        }).eq('id', id).execute()
        return redirect(url_for('admin_instituciones'))
    except Exception as e:
        return f"Error al actualizar el instituto: {e}", 500

@app.route('/admin/instituciones/borrar/<int:id>', methods=['POST'])
def borrar_institucion(id):
    try:
        supabase.table('institutos').delete().eq('id', id).execute()
        return redirect(url_for('admin_instituciones'))
    except Exception as e:
        return f"Error al borrar el instituto: {e}", 500

# --- LISTADO DE CARRERAS Y RESOLUCIONES VINCULARES (ADMIN) ---
# Antes leía de una planilla Excel aparte ("institutos_carreras"), desconectada de todo.
# Ahora se arma directo desde el Nomenclador (materias_nomenclador + institutos), así que
# cualquier instituto o materia que cargues en las otras pantallas aparece acá automáticamente.
@app.route('/admin/institutos')
def admin_institutos():
    if not supabase:
        return "Supabase no configurado."
    datos = supabase.table('materias_nomenclador').select('*, institutos(*)').order('id', desc=True).execute().data
    return render_template('admin_institutos.html', materias=datos)

@app.route('/admin/institutos/editar/<int:id>', methods=['POST'])
def editar_instituto(id):
    try:
        supabase.table('materias_nomenclador').update({
            "carrera": request.form.get('carrera'),
            "resolucion": request.form.get('resolucion'),
            "codigo": request.form.get('codigo'),
            "nombre_unidad_curricular": request.form.get('nombre_unidad_curricular'),
            "regimen": request.form.get('regimen'),
            "vigente": request.form.get('vigente')
        }).eq('id', id).execute()
        return redirect(url_for('admin_institutos'))
    except Exception as e:
        return f"Error al actualizar: {e}", 500

@app.route('/admin/institutos/borrar/<int:id>', methods=['POST'])
def borrar_materia(id):
    try:
        supabase.table('materias_nomenclador').delete().eq('id', id).execute()
        return redirect(url_for('admin_institutos'))
    except Exception as e:
        return f"Error al borrar: {e}", 500

# --- SEGUIMIENTO DE INSCRIPCIONES DOCENTES (ADMIN) ---
@app.route('/admin/seguimiento')
def admin_seguimiento():
    if not supabase:
        return "Supabase no configurado."
    postulaciones = supabase.table('postulaciones_docentes').select('*').execute().data
    return render_template('admin_seguimiento.html', postulaciones=postulaciones)

@app.route('/admin/postulacion/editar/<int:id>', methods=['POST'])
def editar_postulacion(id):
    try:
        supabase.table('postulaciones_docentes').update({
            "estado_inscripcion": request.form.get('estado_inscripcion'),
            "observaciones": request.form.get('observaciones')
        }).eq('id', id).execute()
        return redirect(url_for('admin_seguimiento'))
    except Exception as e:
        return f"Error al actualizar postulación: {e}", 500

@app.route('/admin/postulacion/borrar/<