import os
import re
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from datetime import datetime

ARCHIVO_CSV = "historial_loterias_peru.csv"

# 1. ENVIADOR DE MENSAJES TELEGRAM
def enviar_alerta_telegram(mensaje):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("[Aviso] No se encontraron credenciales de Telegram.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print("Notificación enviada con éxito a Telegram.")
    except Exception as e:
        print(f"Error al enviar mensaje a Telegram: {e}")

# 2. GENERADOR DE JUGADAS ANTI-COLISIÓN
def generar_jugadas(bolillas_totales=50, cantidad=2):
    seleccionadas = []
    for _ in range(20000):
        comb = np.sort(np.random.choice(range(1, bolillas_totales + 1), size=6, replace=False))
        # Filtros anti-colisión humana:
        if np.sum(comb >= 32) < 3:  # Evita acumular fechas del 1 al 31
            continue
        if np.any(np.diff(comb) == 1):  # Evita números consecutivos
            continue
        if max(np.bincount(comb % 10)) > 2:  # Evita terminaciones repetidas
            continue
            
        seleccionadas.append(comb.tolist())
        if len(seleccionadas) == cantidad:
            break
    return seleccionadas

# 3. EXTRACCIÓN DE RESULTADOS
def extraer_sorteos():
    url = "https://www.combinacionganadora.com/pe/tinka/resultados-anteriores/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
    }
    registros = []
    
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        for fila in soup.find_all("tr"):
            texto = fila.get_text(" ", strip=True)
            fecha_match = re.search(r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", texto)
            bolillas = [int(n) for n in re.findall(r"\b([1-4]?\d|50)\b", texto)]
            
            if fecha_match and len(bolillas) >= 6:
                seis = sorted(bolillas[:6])
                if len(set(seis)) == 6:
                    fecha_str = fecha_match.group(1)
                    registros.append({
                        "sorteo_id": f"Tinka_{fecha_str.replace('/', '-')}",
                        "juego": "La Tinka",
                        "fecha": fecha_str,
                        "B1": seis[0], "B2": seis[1], "B3": seis[2],
                        "B4": seis[3], "B5": seis[4], "B6": seis[5],
                        "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
    except Exception as e:
        print(f"[Aviso] Error en extracción: {e}")
        
    return pd.DataFrame(registros)

# 4. ACTUALIZACIÓN Y NOTIFICACIÓN
def main():
    df_nuevos = extraer_sorteos()
    hay_nuevos = False
    ultimo_sorteo = None
    
    if os.path.exists(ARCHIVO_CSV):
        df_historico = pd.read_csv(ARCHIVO_CSV)
        if not df_nuevos.empty:
            antes = len(df_historico)
            df_total = pd.concat([df_historico, df_nuevos], ignore_index=True)
            df_total = df_total.drop_duplicates(subset=["sorteo_id"], keep="last")
            if len(df_total) > antes:
                hay_nuevos = True
                ultimo_sorteo = df_total.iloc[-1]
        else:
            df_total = df_historico
    else:
        df_total = df_nuevos.drop_duplicates(subset=["sorteo_id"], keep="last")
        if not df_total.empty:
            hay_nuevos = True
            ultimo_sorteo = df_total.iloc[-1]
            
    df_total.to_csv(ARCHIVO_CSV, index=False)
    print(f"Base de datos sincronizada: {len(df_total)} registros.")
    
    # Prepara jugadas optimizadas
    jugadas = generar_jugadas(bolillas_totales=50, cantidad=2)
    j1_str = str(jugadas[0])
    j2_str = str(jugadas[1])
    
    # Redacta el mensaje para Telegram
    if hay_nuevos and ultimo_sorteo is not None:
        bols = [ultimo_sorteo[f'B{i}'] for i in range(1, 7)]
        mensaje = (
            f"🎰 *ACTUALIZACIÓN DE SORTEO DETECTADA*\n"
            f"📅 *Fecha:* `{ultimo_sorteo['fecha']}`\n"
            f"🎱 *Bolillas que salieron:* `{bols}`\n\n"
            f"📊 *Base de datos actualizada:* {len(df_total)} sorteos acumulados.\n\n"
            f"🎯 *Sugerencias Anti-Colisión Próximo Sorteo:*\n"
            f"• Jugada 1: `{j1_str}`\n"
            f"• Jugada 2: `{j2_str}`\n\n"
            f"_Regla de juego: Combinaciones optimizadas con baja probabilidad de dividir pozo._"
        )
    else:
        mensaje = (
            f"✅ *AUDITORÍA NOCTURNA COMPLETADA*\n"
            f"No hubo sorteo nuevo hoy. Base de datos al día con {len(df_total)} sorteos.\n\n"
            f"🎯 *Jugadas preparadas para el siguiente sorteo:*\n"
            f"• Opción A: `{j1_str}`\n"
            f"• Opción B: `{j2_str}`"
        )
        
    enviar_alerta_telegram(mensaje)

if __name__ == "__main__":
    main()
