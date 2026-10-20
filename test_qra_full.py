import qra_standards as qra
import wind_rose_engine as wre
import consecuencias as c
import db_manager as db

print("=== 1. TEST METEOBLUE & WIND ROSE ===")
rv = wre.obtener_rosa_vientos_meteoblue(10.3149, -75.4876)
assert len(rv['sectores']) == 16, 'Debe tener 16 sectores'
assert rv['total_horas_analizadas'] >= 8000, 'Debe tener datos de 1 año'
print(f"  Meteoblue OK: Predominante = {rv['sector_predominante']}, Vel = {rv['velocidad_media_global_ms']} m/s")

print("=== 2. TEST PURPLE BOOK PGS 3 ===")
p_res = qra.calcular_probabilidad_ignicion_purple_book(tasa_kg_s=25.0, masa_total_kg=15000.0, sustancia_nombre='GLP / Propano')
assert p_res['p_direct'] == 0.50, f"P_direct debe ser 0.50, obtenido {p_res['p_direct']}"
assert p_res['p_bleve'] == 0.70, 'P_bleve debe ser 0.70'
assert p_res['p_vce'] == 0.40, 'P_vce debe ser 0.40'
assert p_res['p_flash_fire'] == 0.60, 'P_flash_fire debe ser 0.60'
print(f"  Purple Book OK: P_direct = {p_res['p_direct']}, P_delayed = {p_res['p_delayed']}, P_total = {p_res['probabilidad_ignicion_total']}")

print("=== 3. TEST BEVI v4.2 ===")
bevi_rec = qra.obtener_frecuencias_bevi('recipiente_presion', diametro_orificio_mm=25.4)
assert bevi_rec['frecuencia_ruptura_anual'] == 5e-7, 'Ruptura debe ser 5e-7'
assert bevi_rec['frecuencia_fuga_anual'] == 1e-5, 'Fuga 10mm debe ser 1e-5'
bevi_tub = qra.obtener_frecuencias_bevi('tubería', diametro_orificio_mm=50.0, longitud_tuberia_m=10.0)
import math
assert math.isclose(bevi_tub['frecuencia_ruptura_anual'], 1e-5, rel_tol=1e-5), 'Tubería <75mm ruptura 1e-6 * 10m'
print(f"  BEVI v4.2 OK: Recipiente = {bevi_rec['frecuencia_escenario_yr']}, Tubería 10m = {bevi_tub['frecuencia_escenario_yr']}")

print("=== 4. TEST YELLOW BOOK & NIST ===")
antoine_p = qra.calcular_presion_vapor_antoine('GLP / Propano', temp_c=30.0)
assert antoine_p > 5.0 and antoine_p < 20.0, f"P_sat anormal: {antoine_p}"
evap = qra.calcular_evaporacion_charco_yellow_book('Gasolina / Nafta', diametro_charco_m=10.0, temp_amb_c=32.0, vel_viento_ms=4.5)
assert evap['tasa_evaporacion_kg_s'] > 0.1, 'Tasa evaporación debe ser positiva'
sep = qra.calcular_sep_fuego_yellow_book('GLP / Propano', diametro_fuego_m=15.0)
assert sep['sep_act_kw_m2'] > 50.0 and sep['sep_act_kw_m2'] < 140.0, 'SEP anormal'
print(f"  Yellow Book & NIST OK: P_sat Antoine = {antoine_p:.2f} bar | Evap = {evap['tasa_evaporacion_kg_s']} kg/s | SEP = {sep['sep_act_kw_m2']} kW/m2")

print("=== 5. TEST QRA INTEGRAL & CONTORNOS ISORIESGO ===")
df_eq = db.get_equipos_df()
eq_0 = df_eq.iloc[0].to_dict()
dinamica = c.calcular_dinamica_fuga(eq_0, 5.0)
datos_rad = c.calcular_radios_consecuencia(dinamica, 'Radiación Térmica (Jet/Pool Fire)')
qra_full = c.calcular_analisis_qra_completo(eq_0, df_eq, dinamica, datos_rad)
assert qra_full['status'] == 'success'
assert '1e-05' in qra_full['contornos_isoriesgo']
assert '1e-06' in qra_full['contornos_isoriesgo']
assert '1e-07' in qra_full['contornos_isoriesgo']
print(f"  QRA Integral OK: Frec. Evento = {qra_full['frecuencia_evento_iniciador_yr']:.2e} /año")
for k, v in qra_full['contornos_isoriesgo'].items():
    nombre_limpio = v['nombre'].encode('ascii', 'ignore').decode('ascii')
    print(f"   -> Contorno {k}: {nombre_limpio} | R_max = {v['radio_maximo_m']} m | R_medio = {v['radio_medio_m']} m")

print("ALL TESTS PASSED SUCCESSFULLY!")
