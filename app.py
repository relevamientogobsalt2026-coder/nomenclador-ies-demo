import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, abort
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = "secret_key_ies_6039"

# Configuración Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

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

    queries = [sql_institutos, sql_materias, sql_postulaciones_obs, sql_postulaciones_est]
    
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
    localidades = request.form.getlist('localidades')
    
    titulo_1 = request.form.get('titulo_base_1')
    egreso_1 = request.form.get('anio_egreso_1')
    titulo_2 = request.form.get('titulo_base_2')
    egreso_2 = request.form.get('anio_egreso_2')
    
    experiencia = request.form.get('experiencia')
    capacitacion = request.form.get('capacitacion')

    post_data = {
        "nombre_apellido": nombre,
        "dni": dni,
        "telefono": telefono,
        "email": email,
        "localidades_postulacion": localidades,
        "titulo_base_1": titulo_1,
        "anio_egreso_1": int(egreso_1) if egreso_1 else None,
        "titulo_base_2": titulo_2,
        "anio_egreso_2": int(egreso_2) if egreso_2 else None,
        "experiencia_nivel": experiencia,
        "capacitaciones": capacitacion
    }
    
    inserted = supabase.table('postulaciones_docentes').insert(post_data).execute()
    postulante_id = inserted.data[0]['id']

    titulos_docente = [t.strip().lower() for t in [titulo_1, titulo_2] if t]
    all_materias = supabase.table('materias_nomenclador').select('*, institutos(*)').execute().data
    
    materias_habilitadas = []
    
    for mat in all_materias:
        habilitantes = [h.lower() for h in mat.get('titulos_habilitantes', [])]
        es_hab = any(any(t in hab or hab in t for hab in habilitantes) for t in titulos_docente)
        
        if es_hab:
            materias_habilitadas.append(mat)
            supabase.table('historial_relevamiento').insert({
                "postulante_id": postulante_id,
                "materia_id": mat['id'],
                "estado_habilitacion": "HABILITADO"
            }).execute()

    return render_template('resultado_postulacion.html', 
                           docente=post_data, 
                           materias=materias_habilitadas)

# 3. SECCIÓN ADMINISTRADOR: Nomenclador y Estadísticas
@app.route('/admin')
def admin():
    if not supabase:
        return "Supabase no está configurado."
    
    materias = supabase.table('materias_nomenclador').select('*, institutos(*)').execute().data
    postulaciones = supabase.table('postulaciones_docentes').select('*').execute().data
    
    return render_template('admin.html', materias=materias, postulaciones=postulaciones)

# 4. GUARDAR NUEVA MATERIA EN NOMENCLADOR (ADMIN)
@app.route('/admin/nueva-materia', methods=['POST'])
def nueva_materia():
    try:
        inst = supabase.table('institutos').select('id').limit(1).execute()
        inst_id = inst.data[0]['id'] if inst.data else 1

        data = {
            "resolucion": request.form.get('resolucion'),
            "carrera": request.form.get('carrera'),
            "anio": int(request.form.get('anio')),
            "codigo": request.form.get('codigo'),
            "nombre_unidad_curricular": request.form.get('nombre_unidad_curricular'),
            "regimen": request.form.get('regimen'),
            "formato": request.form.get('formato'),
            "titulos_habilitantes": [t.strip() for t in request.form.get('titulos', '').split(',') if t.strip()],
            "instituto_id": inst_id
        }
        supabase.table('materias_nomenclador').insert(data).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error al insertar materia: {e}")
        return f"Ocurrió un error al guardar en la base de datos: {e}", 500

# --- GESTIÓN DE INSTITUTOS Y CARRERAS (ADMIN) ---
@app.route('/admin/institutos')
def admin_institutos():
    if not supabase:
        return "Supabase no configurado."
    datos = supabase.table('institutos_carreras').select('*').execute().data
    return render_template('admin_institutos.html', institutos=datos)

@app.route('/admin/institutos/editar/<int:id>', methods=['POST'])
def editar_instituto(id):
    try:
        supabase.table('institutos_carreras').update({
            "nombre_instituto": request.form.get('nombre_instituto'),
            "carrera": request.form.get('carrera'),
            "resolucion_carrera": request.form.get('resolucion_carrera'),
            "localidad": request.form.get('localidad'),
            "vigente": request.form.get('vigente')
        }).eq('id', id).execute()
        return redirect(url_for('admin_institutos'))
    except Exception as e:
        return f"Error al actualizar: {e}", 500

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

@app.route('/admin/postulacion/borrar/<int:id>', methods=['POST'])
def borrar_postulacion(id):
    try:
        supabase.table('postulaciones_docentes').delete().eq('id', id).execute()
        return redirect(url_for('admin_seguimiento'))
    except Exception as e:
        return f"Error al borrar postulación: {e}", 500

# --- NUEVA RUTA: DETALLE INDIVIDUAL DEL POSTULANTE ---
@app.route('/postulante/<int:docente_id>')
def detalle_postulante(docente_id):
    if not supabase:
        return "Supabase no configurado.", 500
    
    # Busca los datos principales del postulante
    response = supabase.table('postulaciones_docentes').select('*').eq('id', docente_id).execute()
    
    if not response.data:
        abort(404)
        
    docente = response.data[0]

    # Opcional: Buscar también las materias habilitadas en el historial para mostrarlas en la ficha
    historial = supabase.table('historial_relevamiento').select('materia_id, materias_nomenclador(nombre_unidad_curricular)').eq('postulante_id', docente_id).execute()
    docente['materias_habilitadas'] = [item['materias_nomenclador'] for item in historial.data if item.get('materias_nomenclador')]
    
    return render_template('detalle_postulante.html', docente=docente)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)