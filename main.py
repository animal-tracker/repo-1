import serial
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime  # Importar datetime

# Configuracion del puerto serial
SERIAL_PORT = "COM5"  # Cambiar segun el sistema
BAUD_RATE = 115200  # Debe coincidir con el ESP32

# Configuracion del logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Inicializar Firestore
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def calcular_checksum(mensaje):
    """ Calcula el checksum sumando los valores ASCII de los caracteres. """
    return sum(ord(c) for c in mensaje) % 256  # Simulacion de un checksum simple

def guardar_en_firestore(datos_gps):
    """ Guarda o actualiza los datos GPS en Firestore. """
    try:
        # Referencia al documento usando el ID del dispositivo
        doc_ref = db.collection('Devices').document(datos_gps['ID'])
        
        # Usar set() con merge=True para no eliminar otros campos
        doc_ref.set({
            "latitude": datos_gps["Latitud"],
            "longitude": datos_gps["Longitud"],
            "temperature": datos_gps["Temperatura"],
            "last_update": datetime.utcnow()  # Anadir la fecha y hora actual
        }, merge=True)

        logger.info("Datos guardados o actualizados en Firestore: %s", datos_gps)
    except Exception as e:
        logger.error("Error al guardar en Firestore: %s", e)

try:
    # Abrir el puerto serial
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    logger.info(f"Escuchando en {SERIAL_PORT} a {BAUD_RATE} baudios...")

    while True:
        if ser.in_waiting > 0:  # Si hay datos disponibles
            data = ser.readline().decode("utf-8", errors="replace").strip()
            logger.info("Datos recibidos: %s", data)

            # Validar inicio del mensaje
            if not data.startswith("GTRC|"):
                logger.warning("Formato incorrecto, descartando...")
                continue  

            # Separar los datos esperados
            partes = data.split("|")
            if len(partes) != 6:
                logger.warning("Datos incompletos, descartando...")
                continue  

            _, device_id, lat, lng, temp, checksum_str = partes  # Extraer valores
            
            try:
                checksum_recibido = int(checksum_str)
                mensaje_sin_checksum = "|".join(partes[:-1])  # Mensaje sin el checksum
                checksum_calculado = calcular_checksum(mensaje_sin_checksum)
            except ValueError:
                logger.warning("Checksum no valido, descartando...")
                continue  

            # Validar checksum
            if checksum_calculado != checksum_recibido:
                logger.error("Checksum incorrecto (Esperado: %d, Recibido: %d)", checksum_calculado, checksum_recibido)
                continue  

            # Crear objeto con los datos
            datos_gps = {
                "ID": device_id,
                "Latitud": float(lat),
                "Longitud": float(lng),
                "Temperatura": float(temp),
                "Checksum": checksum_recibido
            }

            logger.info("Datos procesados correctamente: %s", datos_gps)

            # Guardar o actualizar los datos en Firestore
            guardar_en_firestore(datos_gps)

            # Enviar confirmacion
            respuesta = f"GTRC|{device_id}|OK\n"
            ser.write(respuesta.encode("utf-8"))
            logger.info("Respuesta enviada: %s", respuesta.strip())

except serial.SerialException as e:
    logger.error("Error al abrir el puerto serial: %s", e)

except KeyboardInterrupt:
    logger.info("Cerrando conexion...")
    ser.close()
