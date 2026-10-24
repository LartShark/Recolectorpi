import os
import re
import html
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

ARCHIVO_LOTERIAS = "historial_loterias_peru.csv"
ARCHIVO_FUTBOL = "historial_futbol_ev.csv"
TZ_PERU = timezone(timedelta(hours=-5))

# Banca total de referencia en Soles (ajusta a tu capital real)
BANCA_SOLES = 200.0

# Ligas prioritarias para el apostador peruano
LIGAS_OBJETIVO = [
    ("soccer_peru_primera_division", "🇵🇪 Liga 1 Te Apuesto"),
    ("soccer_conmebol_copa_libertadores", "🏆 Copa Libertadores"),
    ("soccer_conmebol_copa_sudamericana", "🏆 Copa Sudamericana"),
    ("soccer_uefa_champs_league", "🇪🇺 UEFA Champions League"),
    ("soccer_spain_la_liga", "🇪🇸 LaLiga"),
    ("soccer_epl", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League"),
]

# Casas autorizadas y de alta liquidez que operan en Perú
CASAS_PERU_MAPA = {
    "betano": "Betano Perú",
    "betsson": "Betsson Perú",
    "pinnacle": "Pinnacle (Referencia)",
    "1xbet": "1xBet Perú",
    "marathonbet": "Marathonbet",
    "betfair_ex_eu": "Betfair",
}


# =========================================================
# 1. NOTIFICADOR TELEGRAM (MODO HTML)
# =========================================================
def enviar_alerta_telegram(mensaje):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[Aviso] Credenciales de Telegram no detectadas.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print("Mensaje enviado con éxito a Telegram.")
    except Exception as e:
        print(f"Error al enviar mensaje a Telegram: {e}")


# =========================================================
# 2. MOTOR DE LOTERÍAS PERÚ (LA TINKA)
# =========================================================
def generar_jugadas(bolillas_totales=50, cantidad=2):
    seleccionadas = []
    for _ in range(25000):
        comb = np.sort(np.random.choice(range(1, bolillas_totales + 1), size=6, replace=False))
        if np.sum(comb >= 32) < 3:
            continue
        if np.any(np.diff(comb) == 1):
            continue
        if max(np.bincount(comb % 10)) > 2:
            continue
        seleccionadas.append(comb.tolist())
        if len(seleccionadas) == cantidad:
            break
    return seleccionadas


def extraer_sorteos():
    urls = [
        "https://www.combinacionganadora.com/pe/tinka/resultados-anteriores/",
        "https://tinkaresultados.com/"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "es-PE,es;q=0.9"
    }
    registros = []
    ahora_str = datetime.now(TZ_PERU).strftime("%Y-%m-%d %H:%M:%S")

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for fila in soup.find_all(["tr", "div", "li"]):
                    texto = fila.get_text(" ", strip=True)
                    fecha_match = re.search(r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", texto)
                    bolillas = [int(n) for n in re.findall(r"\b([1-4]?\d|50)\b", texto)]

                    if fecha_match and len(bolillas) >= 6:
                        seis = sorted(bolillas[:6])
                        if len(set(seis)) == 6 and 1 <= min(seis) and max(seis) <= 50:
                            fecha_str = fecha_match.group(1).replace("/", "-")
                            registros.append({
                                "sorteo_id": f"Tinka_{fecha_str}",
                                "juego": "La Tinka",
                                "fecha": fecha_str,
                                "B1": seis[0], "B2": seis[1], "B3": seis[2],
                                "B4": seis[3], "B5": seis[4], "B6": seis[5],
                                "fecha_registro": ahora_str
                            })
            if registros:
                break
        except Exception as e:
            print(f"[Aviso] Excepción extrayendo lotería: {e}")

    return pd.DataFrame(registros)


def procesar_loterias():
    try:
        df_nuevos = extraer_sorteos()
        hay_nuevos = False
        ultimo_sorteo = None

        if os.path.exists(ARCHIVO_LOTERIAS):
            try:
                df_historico = pd.read_csv(ARCHIVO_LOTERIAS)
            except Exception:
                df_historico = pd.DataFrame()

            if not df_nuevos.empty:
                antes = len(df_historico)
                df_total = pd.concat([df_historico, df_nuevos], ignore_index=True)
                df_total = df_total.drop_duplicates(subset=["sorteo_id"], keep="last")
                if len(df_total) > antes:
                    hay_nuevos = True
                    ultimo_sorteo = df_total.iloc[-1]
                elif len(df_total) > 0:
                    ultimo_sorteo = df_total.iloc[-1]
            else:
                df_total = df_historico
                if len(df_total) > 0:
                    ultimo_sorteo = df_total.iloc[-1]
        else:
            df_total = df_nuevos.drop_duplicates(subset=["sorteo_id"], keep="last") if not df_nuevos.empty else pd.DataFrame(
                columns=["sorteo_id", "juego", "fecha", "B1", "B2", "B3", "B4", "B5", "B6", "fecha_registro"]
            )
            if not df_total.empty:
                hay_nuevos = True
                ultimo_sorteo = df_total.iloc[-1]

        df_total.to_csv(ARCHIVO_LOTERIAS, index=False)
        total_registros = len(df_total)

        jugadas = generar_jugadas(bolillas_totales=50, cantidad=2)
        j1_str, j2_str = str(jugadas[0]), str(jugadas[1])

        if hay_nuevos and ultimo_sorteo is not None:
            bols = [int(ultimo_sorteo[f"B{i}"]) for i in range(1, 7)]
            msg = (
                f"🎰 <b>ACTUALIZACIÓN LA TINKA</b>\n"
                f"📅 <b>Fecha:</b> <code>{html.escape(str(ultimo_sorteo['fecha']))}</code>\n"
                f"🎱 <b>Bolillas:</b> <code>{bols}</code>\n\n"
                f"📊 <b>Historial acumulado:</b> {total_registros} sorteos.\n\n"
                f"🎯 <b>Jugadas Anti-Colisión (Próximo Sorteo):</b>\n"
                f"• Jugada 1: <code>{j1_str}</code>\n"
                f"• Jugada 2: <code>{j2_str}</code>"
            )
        elif ultimo_sorteo is not None:
            bols = [int(ultimo_sorteo[f"B{i}"]) for i in range(1, 7)]
            msg = (
                f"✅ <b>AUDITORÍA LA TINKA</b>\n"
                f"Base sincronizada con <b>{total_registros} sorteos</b>.\n"
                f"Último sorteo ({html.escape(str(ultimo_sorteo['fecha']))}): <code>{bols}</code>\n\n"
                f"🎯 <b>Jugadas Anti-Colisión preparadas:</b>\n"
                f"• Opción A: <code>{j1_str}</code>\n"
                f"• Opción B: <code>{j2_str}</code>"
            )
        else:
            msg = (
                f"✅ <b>AUDITORÍA LA TINKA</b>\n"
                f"🎯 <b>Jugadas Anti-Colisión:</b>\n"
                f"• Opción A: <code>{j1_str}</code>\n"
                f"• Opción B: <code>{j2_str}</code>"
            )

        enviar_alerta_telegram(msg)
    except Exception as e:
        print(f"[Error] Fallo en módulo de lotería: {e}")


# =========================================================
# 3. MOTOR ADAPTADO A CASAS DE APUESTAS EN PERÚ
# =========================================================
def analizar_futbol():
    columnas_futbol = [
        "partido_id", "liga", "fecha_hora_peru", "local", "visita",
        "prob_L_%", "prob_E_%", "prob_V_%", "favorito",
        "cuota_min_teapuesto_apuestatotal", "mejor_mercado_ev", "mejor_cuota",
        "casa_peru", "ev_%", "sugerido_soles"
    ]

    if not os.path.exists(ARCHIVO_FUTBOL):
        pd.DataFrame(columns=columnas_futbol).to_csv(ARCHIVO_FUTBOL, index=False)

    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        enviar_alerta_telegram(
            "⚽ <b>MÓDULO DE FÚTBOL PERÚ PENDIENTE</b>\n"
            "Falta configurar <code>ODDS_API_KEY</code> en los Secrets de GitHub para escanear cuotas."
        )
        return

    try:
        ahora_peru = datetime.now(TZ_PERU)
        partidos_analizados = []

        for codigo_liga, nombre_liga in LIGAS_OBJETIVO:
            if len(partidos_analizados) >= 10:
                break

            url = f"https://api.the-odds-api.com/v4/sports/{codigo_liga}/odds"
            params = {
                "apiKey": api_key,
                "regions": "eu",
                "markets": "h2h",
                "oddsFormat": "decimal"
            }
            try:
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code != 200:
                    continue
                eventos = resp.json()
                if not isinstance(eventos, list):
                    continue
            except Exception as e:
                print(f"[Aviso] Error en {codigo_liga}: {e}")
                continue

            for ev in eventos:
                try:
                    dt_utc = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
                    dt_peru = dt_utc.astimezone(TZ_PERU)
                    horas_faltantes = (dt_peru - ahora_peru).total_seconds() / 3600.0
                    # Rango de 7 días hacia adelante
                    if horas_faltantes < 0 or horas_faltantes > 168:
                        continue

                    local = ev["home_team"]
                    visita = ev["away_team"]
                    casas = ev.get("bookmakers", [])
                    if not casas:
                        continue

                    cuotas_pinnacle = None
                    probs_todas_casas = []
                    mejores_cuotas_peru = {"Local": (0.0, ""), "Empate": (0.0, ""), "Visita": (0.0, "")}

                    for bm in casas:
                        mercados_h2h = [m for m in bm.get("markets", []) if m.get("key") == "h2h"]
                        if not mercados_h2h:
                            continue
                        precios = {o["name"]: float(o["price"]) for o in mercados_h2h[0].get("outcomes", [])}
                        if local not in precios or "Draw" not in precios or visita not in precios:
                            continue

                        c_l, c_e, c_v = precios[local], precios["Draw"], precios[visita]
                        inv = np.array([1.0 / c_l, 1.0 / c_e, 1.0 / c_v])
                        probs_limpias = inv / np.sum(inv)
                        probs_todas_casas.append(probs_limpias)

                        key_casa = bm.get("key", "").lower()
                        nombre_amigable = CASAS_PERU_MAPA.get(key_casa, bm.get("title", "Casa Online"))

                        if key_casa == "pinnacle":
                            cuotas_pinnacle = probs_limpias

                        if c_l > mejores_cuotas_peru["Local"][0]:
                            mejores_cuotas_peru["Local"] = (c_l, nombre_amigable)
                        if c_e > mejores_cuotas_peru["Empate"][0]:
                            mejores_cuotas_peru["Empate"] = (c_e, nombre_amigable)
                        if c_v > mejores_cuotas_peru["Visita"][0]:
                            mejores_cuotas_peru["Visita"] = (c_v, nombre_amigable)

                    if not probs_todas_casas:
                        continue

                    # Referencia limpia (Pinnacle o consenso de mercado sin comisiones)
                    probs_base = cuotas_pinnacle if cuotas_pinnacle is not None else np.mean(probs_todas_casas, axis=0)

                    # 10,000 iteraciones de Montecarlo
                    sim = np.random.choice([0, 1, 2], size=10000, p=probs_base)
                    probs_sim = np.array([np.mean(sim == 0), np.mean(sim == 1), np.mean(sim == 2)])
                    p_real = (probs_base + probs_sim) / 2.0

                    etiquetas = ["Local", "Empate", "Visita"]
                    idx_fav = int(np.argmax(p_real))
                    pronostico = etiquetas[idx_fav]

                    # Cuota mínima rentable para Te Apuesto o Apuesta Total (exige 2% de ventaja sobre probabilidad real)
                    cuota_min_teapuesto = round(1.02 / p_real[idx_fav], 2)

                    # Detección del mayor EV entre las casas activas en Perú
                    mejor_op = None
                    for op, prob in zip(etiquetas, p_real):
                        cuota_max, casa_nombre = mejores_cuotas_peru[op]
                        ev_val = (prob * cuota_max) - 1.0
                        b = cuota_max - 1.0
                        kelly_25 = max(0.0, ((prob * b - (1.0 - prob)) / b) * 0.25) if b > 0 else 0.0
                        monto_soles = round(BANCA_SOLES * kelly_25, 2) if ev_val >= 0.015 else 0.0

                        if mejor_op is None or ev_val > mejor_op["ev"]:
                            mejor_op = {
                                "mercado": op,
                                "cuota": cuota_max,
                                "casa": casa_nombre,
                                "ev": ev_val,
                                "prob": prob,
                                "soles": monto_soles
                            }

                    partidos_analizados.append({
                        "partido_id": f"{dt_peru.strftime('%Y-%m-%d')}_{local}_{visita}",
                        "liga": nombre_liga,
                        "fecha_hora_peru": dt_peru.strftime("%d/%m %H:%M"),
                        "local": local,
                        "visita": visita,
                        "prob_L_%": round(float(p_real[0]) * 100, 1),
                        "prob_E_%": round(float(p_real[1]) * 100, 1),
                        "prob_V_%": round(float(p_real[2]) * 100, 1),
                        "favorito": pronostico,
                        "cuota_min_teapuesto_apuestatotal": cuota_min_teapuesto,
                        "mejor_mercado_ev": mejor_op["mercado"],
                        "mejor_cuota": round(mejor_op["cuota"], 2),
                        "casa_peru": mejor_op["casa"],
                        "ev_%": round(mejor_op["ev"] * 100, 2),
                        "sugerido_soles": mejor_op["soles"]
                    })
                except Exception as e:
                    print(f"[Aviso] Salto de partido por excepción: {e}")

        # Guardar historial para Backtesting
        df_nuevos_f = pd.DataFrame(partidos_analizados)
        try:
            df_hist_f = pd.read_csv(ARCHIVO_FUTBOL)
        except Exception:
            df_hist_f = pd.DataFrame(columns=columnas_futbol)

        if not df_nuevos_f.empty:
            df_guardar = pd.concat([df_hist_f, df_nuevos_f[columnas_futbol]], ignore_index=True)
            df_guardar = df_guardar.drop_duplicates(subset=["partido_id"], keep="last")
        else:
            df_guardar = df_hist_f

        df_guardar.to_csv(ARCHIVO_FUTBOL, index=False)

        if not partidos_analizados:
            enviar_alerta_telegram("⚽ <b>ESCÁNER CASAS PERÚ</b>\nNo hay eventos con líneas activas en este momento.")
            return

        value_bets = [p for p in partidos_analizados if p["ev_%"] >= 1.5]
        value_bets.sort(key=lambda x: x["ev_%"], reverse=True)

        lineas = ["🇵🇪 <b>RADAR DE APUESTAS DEPORTIVAS (PERÚ)</b>"]
        lineas.append(f"<i>Banca: S/ {BANCA_SOLES:.0f} (Kelly 25%) | Historial: {len(df_guardar)} eventos</i>\n")

        if value_bets:
            lineas.append("🔥 <b>VALOR DETECTADO EN CASAS ONLINE PERÚ:</b>")
            for vb in value_bets[:3]:
                p_txt = html.escape(f"{vb['local']} vs {vb['visita']}")
                c_txt = html.escape(vb['casa_peru'])
                lineas.append(
                    f"• <b>{vb['liga']}</b> ({vb['fecha_hora_peru']})\n"
                    f"  {p_txt}\n"
                    f"  👉 Jugar: <b>{vb['mejor_mercado_ev']}</b> @ <code>{vb['mejor_cuota']}</code> ({c_txt})\n"
                    f"  📈 Ventaja: <b>+{vb['ev_%']}% EV</b> | Sugerido: <b>S/ {vb['sugerido_soles']:.2f}</b>"
                )
            lineas.append("")
        else:
            lineas.append("🛡️ <i>Sin desajustes online directos &gt; 1.5% en este minuto.</i>\n")

        lineas.append("🏪 <b>UMBRALES PARA TE APUESTO / APUESTA TOTAL / DORADOBET:</b>")
        for p in partidos_analizados[:4]:
            p_txt = html.escape(f"{p['local']} vs {p['visita']}")
            lineas.append(
                f"• {p['liga']} | <code>{p['fecha_hora_peru']}</code>\n"
                f"  <b>{p_txt}</b>\n"
                f"  Prob: L <code>{p['prob_L_%']}%</code> | E <code>{p['prob_E_%']}%</code> | V <code>{p['prob_V_%']}%</code>\n"
                f"  🎯 Favorito: <b>{p['favorito']}</b>\n"
                f"  📌 <i>En Te Apuesto / Apuesta Total solo juega si pagan &gt;</i> <code>{p['cuota_min_teapuesto_apuestatotal']}</code>"
            )

        enviar_alerta_telegram("\n".join(lineas))

    except Exception as e:
        print(f"[Error] Fallo en análisis de fútbol: {e}")


# =========================================================
# EJECUCIÓN PRINCIPAL (SIN ERROR DE MAIN)
# =========================================================
if __name__ == "__main__":
    procesar_loterias()
    analizar_futbol()
