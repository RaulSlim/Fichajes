import os
import smtplib
import base64
import io
import calendar
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
from supabase import create_client, Client
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# 1. Configuración de variables de entorno
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
correo_gestor = os.environ.get("CORREO_GESTOR")
mi_correo = os.environ.get("MI_CORREO")
mi_password = os.environ.get("MI_PASSWORD_CORREO")

if not all([url, key, correo_gestor, mi_correo, mi_password]):
    print("Error: Faltan variables de entorno.")
    exit(1)

supabase: Client = create_client(url, key)

# 2. FILTRO INTELIGENTE DE FECHAS
hoy = datetime.now()
# Si estamos a principio de mes (días 1 al 5), cogemos el mes anterior. Si no, el actual.
if hoy.day <= 5:
    mes_calculo = hoy.month - 1 if hoy.month > 1 else 12
    año_calculo = hoy.year if hoy.month > 1 else hoy.year - 1
else:
    mes_calculo = hoy.month
    año_calculo = hoy.year

ultimo_dia = calendar.monthrange(año_calculo, mes_calculo)[1]
fecha_inicio = f"{año_calculo}-{mes_calculo:02d}-01T00:00:00+00:00"
fecha_fin = f"{año_calculo}-{mes_calculo:02d}-{ultimo_dia}T23:59:59+00:00"

print(f"Descargando datos desde {fecha_inicio} hasta {fecha_fin}...")

# 3. Obtener datos filtrados
res_empleados = supabase.table('empleados').select('*').execute()
empleados = res_empleados.data

res_fichajes = supabase.table('fichajes')\
    .select('*')\
    .gte('fecha_hora', fecha_inicio)\
    .lte('fecha_hora', fecha_fin)\
    .order('fecha_hora')\
    .execute()
fichajes = res_fichajes.data

mapa_empleados = {}
for emp in empleados:
    mapa_empleados[emp['email']] = emp

# 4. Generar PDF
print("Generando PDF...")
class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 15)
        self.cell(0, 10, 'Registro de Horas - Gastrobar Don Apolonio', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.set_font('helvetica', 'I', 10)
        self.cell(0, 10, f'Periodo auditado: {mes_calculo:02d}/{año_calculo}', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(5)

pdf = PDF()
pdf.add_page()

w_trabajador = 45
w_dni = 20
w_fecha = 20
w_hora = 15
w_tipo = 40
w_firma = 50
alto_fila = 15

pdf.set_font('helvetica', 'B', 9)
for titulo, ancho in [('Trabajador', w_trabajador), ('DNI', w_dni), ('Fecha', w_fecha), ('Hora', w_hora), ('Tipo', w_tipo), ('Firma', w_firma)]:
    pdf.cell(ancho, 10, titulo, border=1, align='C')
pdf.ln()

pdf.set_font('helvetica', '', 8)

for f in fichajes:
    email = f.get('email', '')
    emp = mapa_empleados.get(email, {'nombre': email.split('@')[0], 'apellidos': '', 'dni': '-'})
    nombre_completo = f"{emp.get('nombre', '')} {emp.get('apellidos', '')}"
    dni = emp.get('dni', '-')
    
    fecha_cruda = f.get('fecha_hora')
    fecha_limpia = fecha_cruda.split('.')[0].split('+')[0].split('Z')[0]
    fecha_obj = datetime.fromisoformat(fecha_limpia)
    
    fecha_str = fecha_obj.strftime('%d/%m/%Y')
    hora_str = fecha_obj.strftime('%H:%M')
    tipo = f.get('tipo', '')
    firma_b64 = f.get('firma', None)

    if pdf.get_y() > 260:
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 9)
        for titulo, ancho in [('Trabajador', w_trabajador), ('DNI', w_dni), ('Fecha', w_fecha), ('Hora', w_hora), ('Tipo', w_tipo), ('Firma', w_firma)]:
            pdf.cell(ancho, 10, titulo, border=1, align='C')
        pdf.ln()
        pdf.set_font('helvetica', '', 8)

    x_start = pdf.get_x()
    y_start = pdf.get_y()

    pdf.cell(w_trabajador, alto_fila, nombre_completo[:25], border=1, align='C')
    pdf.cell(w_dni, alto_fila, dni, border=1, align='C')
    pdf.cell(w_fecha, alto_fila, fecha_str, border=1, align='C')
    pdf.cell(w_hora, alto_fila, hora_str, border=1, align='C')
    pdf.cell(w_tipo, alto_fila, tipo, border=1, align='C')
    pdf.cell(w_firma, alto_fila, '', border=1)

    if firma_b64 and "," in firma_b64:
        try:
            base64_str = firma_b64.split(",")[1]
            image_bytes = base64.b64decode(base64_str)
            image_stream = io.BytesIO(image_bytes)
            
            img_x = x_start + w_trabajador + w_dni + w_fecha + w_hora + w_tipo + 5
            img_y = y_start + 2
            pdf.image(image_stream, x=img_x, y=img_y, w=40, h=11)
        except:
            pdf.set_xy(x_start + w_trabajador + w_dni + w_fecha + w_hora + w_tipo, y_start + 5)
            pdf.cell(w_firma, 5, 'Error', align='C')
    else:
        pdf.set_xy(x_start + w_trabajador + w_dni + w_fecha + w_hora + w_tipo, y_start + 5)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(w_firma, 5, 'Sin firma', align='C')
        pdf.set_text_color(0, 0, 0)
    
    pdf.set_xy(x_start, y_start + alto_fila)

pdf_ruta = "informe_fichajes.pdf"
pdf.output(pdf_ruta)

# 5. Enviar Correo
print("Enviando correo...")
mensaje = MIMEMultipart()
mensaje['From'] = mi_correo
mensaje['To'] = correo_gestor
mensaje['Subject'] = f"Registro de Horas - {mes_calculo:02d}/{año_calculo}"

cuerpo = f"Hola,\n\nAdjunto el registro de horas y firmas de la plantilla correspondiente al periodo {mes_calculo:02d}/{año_calculo}.\n\nUn saludo."
mensaje.attach(MIMEText(cuerpo, 'plain'))

with open(pdf_ruta, "rb") as adjunto:
    parte = MIMEApplication(adjunto.read(), Name=os.path.basename(pdf_ruta))
    parte['Content-Disposition'] = f'attachment; filename="Registro_Horas_{mes_calculo:02d}_{año_calculo}.pdf"'
    mensaje.attach(parte)

try:
    servidor = smtplib.SMTP('smtp.gmail.com', 587)
    servidor.starttls()
    servidor.login(mi_correo, mi_password)
    servidor.send_message(mensaje)
    servidor.quit()
    print("¡Correo enviado correctamente al gestor!")
except Exception as e:
    print(f"Error al enviar el correo: {e}")
    exit(1)