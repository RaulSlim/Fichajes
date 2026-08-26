import os
import calendar
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from supabase import create_client, Client
from fpdf import FPDF

# 1. RECUPERAR LAS CLAVES DESDE GITHUB SECRETS
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
correo_origen = os.environ.get("MI_CORREO")
password_origen = os.environ.get("MI_PASSWORD_CORREO")
correo_destino = os.environ.get("CORREO_GESTOR")

if not all([url, key, correo_origen, password_origen, correo_destino]):
    raise ValueError("Faltan variables de entorno por configurar en GitHub Secrets.")

supabase: Client = create_client(url, key)

# 2. CALCULAR RANGO DE FECHAS (Mes actual si es prueba, mes anterior si es automático el día 1)
hoy = datetime.today()
if hoy.day == 1:
    ultimo_dia = hoy.replace(hour=23, minute=59, second=59) - timedelta(days=1)
    primer_dia = ultimo_dia.replace(day=1, hour=0, minute=0, second=0)
else:
    primer_dia = hoy.replace(day=1, hour=0, minute=0, second=0)
    _, dias_mes = calendar.monthrange(hoy.year, hoy.month)
    ultimo_dia = hoy.replace(day=dias_mes, hour=23, minute=59, second=59)

mes_texto = primer_dia.strftime("%m/%Y")

# 3. DESCARGAR DATOS DE SUPABASE
res_empleados = supabase.table('empleados').select('*').execute()
empleados_dict = {emp['email']: emp for emp in res_empleados.data}

res_fichajes = supabase.table('fichajes').select('*') \
    .gte('fecha_hora', primer_dia.isoformat()) \
    .lte('fecha_hora', ultimo_dia.isoformat()) \
    .order('fecha_hora').execute()

fichajes_por_empleado = {}
for f in res_fichajes.data:
    email = f['email']
    if email not in fichajes_por_empleado:
        fichajes_por_empleado[email] = []
    fichajes_por_empleado[email].append(f)

# 4. GENERAR EL PDF
class GeneradorPDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 14)
        self.cell(0, 10, 'REGISTRO DE JORNADA LABORAL', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

pdf = GeneradorPDF()

for email, registros in fichajes_por_empleado.items():
    pdf.add_page()
    perfil = empleados_dict.get(email, {})
    nombre_completo = f"{perfil.get('nombre', 'Desconocido')} {perfil.get('apellidos', '')}"
    dni = perfil.get('dni', 'SIN DNI')
    
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 8, f"Mes / Año: {mes_texto}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Trabajador: {nombre_completo}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"DNI / NIE: {dni}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(40, 10, "Fecha", border=1, align="C")
    pdf.cell(40, 10, "Tipo", border=1, align="C")
    pdf.cell(40, 10, "Hora (Local)", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "", 10)
    for reg in registros:
        fecha_obj = datetime.fromisoformat(reg['fecha_hora'].replace("Z", "+00:00"))
        # Ajustar hora UTC a hora de España (aprox +1/+2 según horario de verano, aquí simplificado para el PDF)
        str_fecha = fecha_obj.strftime("%d/%m/%Y")
        str_hora = fecha_obj.strftime("%H:%M:%S")
        
        pdf.cell(40, 10, str_fecha, border=1, align="C")
        pdf.cell(40, 10, reg['tipo'].upper(), border=1, align="C")
        pdf.cell(40, 10, str_hora, border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(10)
    pdf.set_font("helvetica", "I", 9)
    pdf.cell(0, 10, "Firma del trabajador: ___________________________", new_x="LMARGIN", new_y="NEXT")

ruta_pdf = "registro_mensual.pdf"
pdf.output(ruta_pdf)

# 5. ENVIAR EL CORREO A TRAVÉS DE GMAIL
msg = EmailMessage()
msg['Subject'] = f'Registros de Jornada - {mes_texto}'
msg['From'] = correo_origen
msg['To'] = correo_destino
msg.set_content('Buenos días,\n\nSe adjunta el documento PDF con los registros de jornada legal.\n\nEste es un mensaje automático.')

with open(ruta_pdf, 'rb') as f:
    msg.add_attachment(f.read(), maintype='application', subtype='pdf', filename=f'Registro_{mes_texto.replace("/", "_")}.pdf')

try:
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(correo_origen, password_origen)
        smtp.send_message(msg)
    print("¡Proceso completado! PDF generado y enviado con éxito a través de Gmail.")
except Exception as e:
    print(f"Error al enviar el correo: {e}")