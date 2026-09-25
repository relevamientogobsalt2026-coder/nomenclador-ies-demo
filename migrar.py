import os
import pandas as pd
from supabase import create_client

SUPABASE_URL = "https://imnsocjichlmdcwxinim.supabase.co".strip()
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImltbnNvY2ppY2hsbWRjd3hpbmltIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTAxNTkyMDAsImV4cCI6MjEwNTczNTIwMH0.1qhn62hkJKo6Pkm0NNLMILEzLknozeliov-0pKMMrkI".strip()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

excel_path = 'Terciarios y Carreras Salta 2026.xlsx'

try:
    print("Leyendo archivo Excel...")
    df = pd.read_excel(excel_path, sheet_name='Institutos y Carreras')
    
    # Limpiar espacios en los nombres de las columnas por seguridad
    df.columns = df.columns.str.strip()
    
    print(f"Se encontraron {len(df)} filas. Iniciando subida a Supabase...")

    for index, row in df.iterrows():
        # Función para evitar valores NaN y limpiar espacios
        def clean(val):
            if pd.isna(val):
                return ""
            return str(val).strip()

        data = {
            "nombre_instituto": clean(row.get('Nombre del Instituto')),
            "numero_instituto": clean(row.get('Número de Instituto')),
            "carrera": clean(row.get('Carrera')),
            "resolucion_carrera": clean(row.get('Resolución de la Carrera')),
            "localidad": clean(row.get('Ubicación / Localidad')),
            "gestion": clean(row.get('Gestión (Público / Privado)')),
            "tipo_sede": clean(row.get('Es Anexo / Sede / Extensión Áulica')),
            "vigente": clean(row.get('Vigente en 2026'))
        }
        
        try:
            supabase.table('institutos_carreras').insert(data).execute()
        except Exception as row_err:
            print(f"Error al insertar la fila {index + 2}: {row_err}")

    print("¡Proceso de migración finalizado!")

except Exception as e:
    print(f"Ocurrió un error general (revisá tu conexión a internet o el archivo Excel): {e}")
