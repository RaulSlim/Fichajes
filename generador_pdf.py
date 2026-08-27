import os
import smtplib
import base64
import io
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

# 2. Obtener datos de Supabase
print("Descargando datos...")
res_empleados = supabase.table('empleados').select('*').execute()
empleados = res_empleados.data

res_fichajes = supabase.table('fichajes').select('*').order('fecha_hora').execute()
fichajes = res_fichajes.data

# Diccionario para cruzar email -> datos empleado
mapa_empleados = {}
for emp in empleados:
    mapa_empleados[emp['email']] = emp

# 3. Generar PDF
print("Generando PDF...")
class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 15)
        self.cell(0, 10, 'Registro de Horas - Gastrobar Don Apolonio', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.set_font('helvetica', 'I', 10)
        self.cell(0, 10, f'Documento generado el: {datetime.now().strftime("%d/%m/%Y")}', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(5)

pdf = PDF()
pdf.add_page()

# Anchos de columnas
w_trabajador = 45
w_dni = 20
w_fecha = 20
w_hora = 15
w_tipo = 40
w_firma = 50
alto_fila = 15

# Cabeceras
pdf.set_font('helvetica', 'B', 9)
pdf.cell(w_trabajador, 10, 'Trabajador', border=1, align='C')
pdf.cell(w_dni, 10, 'DNI', border=1, align='C')
pdf.cell(w_fecha, 10, 'Fecha', border=1, align='C')
pdf.cell(w_hora, 10, 'Hora', border=1, align='C')
pdf.cell(w_tipo, 10, 'Tipo', border=1, align='C')
pdf.cell(w_firma, 10, 'Firma', border=1, align='C')
pdf.ln()

pdf.set_font('helvetica', '', 8)

for f in fichajes:
    email = f.get('email', '')
    emp = mapa_empleados.get(email, {'nombre': email.split('@')[0], 'apellidos': '', 'dni': '-'})
    nombre_completo = f"{emp.get('nombre', '')} {emp.get('apellidos', '')}"
    dni = emp.get('dni', '-')
    
    # REPARACIÓN DE FECHA: Quitamos milisegundos y la Z para que Python 3.10 lo entienda
    fecha_cruda = f.get('fecha_hora')
    fecha_limpia = fecha_cruda.split('.')[0].split('+')[0].split('Z')[0]
    fecha_obj = datetime.fromisoformat(fecha_limpia)
    
    fecha_str = fecha_obj.strftime('%d/%m/%Y')
    hora_str = fecha_obj.strftime('%H:%M')
    tipo = f.get('tipo', '')
    firma_b64 = f.get('firma', None)

    # Control de salto de página
    if pdf.get_y() > 260:
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(w_trabajador, 10, 'Trabajador', border=1, align='C')
        pdf.cell(w_dni, 10, 'DNI', border=1, align='C')
        pdf.cell(w_fecha, 10, 'Fecha', border=1, align='C')
        pdf.cell(w_hora, 10, 'Hora', border=1, align='C')
        pdf.cell(w_tipo, 10, 'Tipo', border=1, align='C')
        pdf.cell(w_firma, 10, 'Firma', border=1, align='C')
        pdf.ln()
        pdf.set_font('helvetica', '', 8)

    # Guardar posiciones X e Y actuales para alinear la imagen
    x_start = pdf.get_x()
    y_start = pdf.get_y()

    # Celdas de texto
    pdf.cell(w_trabajador, alto_fila, nombre_completo[:25], border=1, align='C')
    pdf.cell(w_dni, alto_fila, dni, border=1, align='C')
    pdf.cell(w_fecha, alto_fila, fecha_str, border=1, align='C')
    pdf.cell(w_hora, alto_fila, hora_str, border=1, align='C')
    pdf.cell(w_tipo, alto_fila, tipo, border=1, align='C')
    
    # Celda de firma
    pdf.cell(w_firma, alto_fila, '', border=1)

    if firma_b64 and "," in firma_b64:
        try:
            base64_str = firma_b64.split(",")[1]
            image_bytes = base64.b64decode(base64_str)
            image_stream = io.BytesIO(image_bytes)
            
            img_x = x_start + w_trabajador + w_dni + w_fecha + w_hora + w_tipo + 5
            img_y = y_start + 2
            pdf.image(image_stream, x=img_x, y=img_y, w=40, h=11)
        except Exception as e:
            pdf.set_xy(x_start + w_trabajador + w_dni + w_fecha + w_hora + w_tipo, y_start + 5)
            pdf.cell(w_firma, 5, 'Error imagen', align='C')
    else:
        pdf.set_xy(x_start + w_trabajador + w_dni + w_fecha + w_hora + w_tipo, y_start + 5)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(w_firma, 5, 'Sin firma', align='C')
        pdf.set_text_color(0, 0, 0)
    
    pdf.set_xy(x_start, y_start + alto_fila)

pdf_ruta = "informe_fichajes.pdf"
pdf.output(pdf_ruta)
print("PDF generado con éxito.")

# 4. Enviar Correo
print("Enviando correo...")
mensaje = MIMEMultipart()
mensaje['From'] = mi_correo
mensaje['To'] = correo_gestor
mensaje['Subject'] = f"Registro de Horas - {datetime.now().strftime('%B %Y')}"

cuerpo = f"Hola,\n\nAdjunto el registro mensual de horas, entradas, salidas y firmas de los trabajadores.\n\nUn saludo."
mensaje.attach(MIMEText(cuerpo, 'plain'))

with open(pdf_ruta, "rb") as adjunto:
    parte = MIMEApplication(adjunto.read(), Name=os.path.basename(pdf_ruta))
    parte['Content-Disposition'] = f'attachment; filename="{os.path.basename(pdf_ruta)}"'
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