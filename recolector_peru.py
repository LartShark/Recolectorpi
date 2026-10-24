import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

ARCHIVO_CSV = "historial_loterias_peru.csv"

def extraer_sorteos_la_tinka():
    """
    Descarga los últimos resultados públicos de sorteos peruanos.
    Usa un user-agent de navegador estándar para evitar bloqueos.
    """
    url = "https://www.combinacionganadora.com/pe/tinka/resultados-anteriores/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
    }
    registros = []
    
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        filas = soup.find_all("tr")
        for fila in filas:
            texto = fila.get_text(" ", strip=True)
            # Detecta fechas con formato DD/MM/AAAA o AAAA-MM-DD
            fecha_match = re.search(r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", texto)
            # Extrae todas las bolillas numéricas entre 1 y 50
            bolillas = [int(n) for n in re.findall(r"\b([1-4]?\d|50)\b", texto)]
            
            if fecha_match and len(bolillas) >= 6:
                seis_bolillas = sorted(bolillas[:6])
                # Valida que sean 6 números únicos
                if len(set(seis_bolillas)) == 6:
                    fecha_str = fecha_match.group(1)
                    registros.append({
                        "sorteo_id": f"Tinka_{fecha_str.replace('/', '-')}",
                        "juego": "La Tinka",
                        "fecha": fecha_str,
                        "B1": seis_bolillas[0],
                        "B2": seis_bolillas[1],
                        "B3": seis_bolillas[2],
                        "B4": seis_bolillas[3],
                        "B5": seis_bolillas[4],
                        "B6": seis_bolillas[5],
                        "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
    except Exception as e:
        print(f"[Aviso] No se pudo conectar a la fuente externa: {e}")
        
    return pd.DataFrame(registros)

def actualizar_dataset():
    df_nuevos = extraer_sorteos_la_tinka()
    
    if os.path.exists(ARCHIVO_CSV):
        df_historico = pd.read_csv(ARCHIVO_CSV)
        if not df_nuevos.empty:
            df_total = pd.concat([df_historico, df_nuevos], ignore_index=True)
            df_total = df_total.drop_duplicates(subset=["sorteo_id"], keep="last")
        else:
            df_total = df_historico
    else:
        if not df_nuevos.empty:
            df_total = df_nuevos.drop_duplicates(subset=["sorteo_id"], keep="last")
        else:
            # Si la web tarda en responder la primera vez, genera estructura base
            columnas = ["sorteo_id", "juego", "fecha", "B1", "B2", "B3", "B4", "B5", "B6", "fecha_registro"]
            df_total = pd.DataFrame(columns=columnas)
            
    df_total.to_csv(ARCHIVO_CSV, index=False)
    print(f"Éxito: Archivo '{ARCHIVO_CSV}' sincronizado con {len(df_total)} sorteos.")

if __name__ == "__main__":
    actualizar_dataset()
