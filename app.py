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