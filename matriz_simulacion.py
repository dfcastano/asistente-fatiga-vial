"""
matriz_simulacion.py
===============================================================================
Genera la Matriz de Simulación en Excel (entregable de la Clase 4).

Hoja "Matriz": las ecuaciones explícitas (M1, M3–M7) son FÓRMULAS de Excel que
se recalculan si se cambian las entradas (celdas azules). El FAD es el único
valor que viene del motor numérico (Newmark-β) y está resaltado en amarillo.
Hoja "Sensibilidad": barrido de velocidad (resonancia) y tornado (±20 %).
Hoja "Parametros": constantes del modelo, con su fuente.

Uso:  python matriz_simulacion.py        -> Matriz_Simulacion.xlsx
===============================================================================
"""
from io import BytesIO
from typing import Dict, Union

import numpy as np
from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import diagnostico as dg
import motor_fisico as mf
import sensibilidad as sb

FUENTE = "Arial"
AZUL = Font(name=FUENTE, size=10, color="0000FF", bold=True)
NEGRO = Font(name=FUENTE, size=10)
NEGRITA = Font(name=FUENTE, size=10, bold=True)
BLANCO = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
TITULO = Font(name=FUENTE, size=14, bold=True, color="1F3864")
GRIS = Font(name=FUENTE, size=9, italic=True, color="595959")
F_ENC = PatternFill("solid", fgColor="1F3864")
F_SEC = PatternFill("solid", fgColor="D9E2F3")
F_FAD = PatternFill("solid", fgColor="FFFF00")
F_ENT = PatternFill("solid", fgColor="EEF3FA")
BORDE = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)
IZQ = Alignment(horizontal="left", vertical="center", wrap_text=True)

DESCRIPCION = {
    "E1 - Base": "Camión 2 ejes, eje legal 8 t a 40 km/h sobre pavimento convencional",
    "E2 - Límite": "Sobrecarga (14 t) a alta velocidad (80 km/h), misma estructura",
    "E3 - Crítico": "Sobrecarga + subrasante blanda + carpeta delgada, a la velocidad crítica de resonancia",
    "E3 a 80 km/h (Entregable 1)": "Misma estructura de E3 a 80 km/h (referencia del Entregable 1)",
}


def _escenarios():
    esc = dict(mf.ESCENARIOS)
    esc.update(mf.ESCENARIO_REFERENCIA)
    return esc


# -----------------------------------------------------------------------------
def _hoja_parametros(wb, pico: float) -> Dict[str, str]:
    ws = wb.create_sheet("Parametros")
    ws["A1"] = "Parámetros fijos del modelo"; ws["A1"].font = TITULO
    ws["A2"] = "Celdas azules: valores de entrada editables. Negro: fórmulas."; ws["A2"].font = GRIS
    enc = ["Parámetro", "Símbolo", "Valor", "Unidad", "Fuente / nota"]
    for j, t in enumerate(enc, 1):
        c = ws.cell(3, j, t); c.font = BLANCO; c.fill = F_ENC; c.alignment = CENTRO
    filas = [
        ("g", "Aceleración de la gravedad", "g", mf.G, "m/s²", "Constante física"),
        ("a", "Radio de huella estándar", "a", mf.A_HUELLA, "m", "Eje 8.2 t de rueda doble (Huang, 2004)"),
        ("nu", "Relación de Poisson de la subrasante", "ν", 0.40, "–", "Valor típico para suelos finos"),
        ("rho", "Densidad de la subrasante", "ρ", 1900.0, "kg/m³", "Valor típico para suelos compactados"),
        ("H", "Profundidad del cono de carga", "H", mf.H_CONO, "m", "Calibración de la masa participante"),
        ("theta", "Ángulo del cono de carga", "θ", mf.ANG_CONO_DEG, "°", "Distribución de carga 30°"),
        ("R", "Radio inferior del cono", "R", "=C5+C8*TAN(RADIANS(C9))", "m", "R = a + H·tan θ"),
        ("K", "Factor de calibración de ε_t", "K", mf.K_CAL, "–", "Calibrado a ε_t ≈ 180 με en E1 (rango multicapa 150–250 με)"),
        ("psi", "Conversión MPa → psi", "–", mf.MPA_A_PSI, "psi/MPa", "1 MPa = 145.038 psi"),
        ("anos", "Periodo de diseño", "–", 20.0, "años", "Supuesto del estudio"),
        ("pico", "Pico del espectro de choque", "(d/Tₙ)pico", round(pico, 3), "–",
         "Resultado del motor (Newmark-β, ξ = 0.15). Ver hoja Sensibilidad"),
        ("legal", "Límite legal eje sencillo llanta doble", "–", dg.LIMITE_LEGAL_EJE_SIMPLE_T, "t",
         "Resolución 4100 de 2004, Ministerio de Transporte"),
    ]
    ref = {}
    for i, (key, nom, sim, val, uni, nota) in enumerate(filas, start=4):
        ws.cell(i, 1, nom).font = NEGRO
        ws.cell(i, 2, sim).font = NEGRO
        c = ws.cell(i, 3, val)
        es_formula = isinstance(val, str) and val.startswith("=")
        c.font = NEGRO if es_formula else AZUL
        c.number_format = "0.000"
        ws.cell(i, 4, uni).font = NEGRO
        ws.cell(i, 5, nota).font = GRIS
        for j in range(1, 6):
            ws.cell(i, j).border = BORDE
            ws.cell(i, j).alignment = IZQ if j in (1, 5) else CENTRO
        ref[key] = f"Parametros!$C${i}"
    for col, w in zip("ABCDE", (38, 12, 12, 10, 62)):
        ws.column_dimensions[col].width = w
    return ref


# -----------------------------------------------------------------------------
def _hoja_matriz(ws, P: Dict[str, str]):
    esc = _escenarios()
    nombres = list(esc)
    res = {n: mf.simular(e) for n, e in esc.items()}
    base_e, base_r = mf.ESCENARIOS["E1 - Base"], res["E1 - Base"]
    cols = [get_column_letter(4 + i) for i in range(len(nombres))]
    ultima = get_column_letter(4 + len(nombres))

    ws["A1"] = "Matriz de Simulación — Asistente Predictivo de Fatiga Vial por Ondas Dinámicas"
    ws["A1"].font = TITULO
    ws["A2"] = ("Consultoría Castaño & Garzón · Camila Castaño Ledesma, Valentina Garzón Piamba · "
                "Proyecto Integrador Física e IA · Clase 4, noviembre de 2026")
    ws["A2"].font = GRIS
    ws["A3"] = ("Leyenda: texto azul = entradas editables · texto negro = fórmulas · fondo amarillo = FAD "
                "calculado por el motor numérico (Newmark-β, motor_fisico.py).")
    ws["A3"].font = GRIS

    enc = ["Variable", "Símbolo", "Unidad"] + nombres + ["Ecuación / fuente"]
    for j, t in enumerate(enc, 1):
        c = ws.cell(5, j, t); c.font = BLANCO; c.fill = F_ENC; c.alignment = CENTRO; c.border = BORDE
    ws.cell(6, 1, "Descripción del escenario").font = NEGRITA
    for j, n in enumerate(nombres):
        c = ws.cell(6, 4 + j, DESCRIPCION[n]); c.font = GRIS; c.alignment = CENTRO; c.border = BORDE
    ws.row_dimensions[6].height = 52

    fila = 7
    rows: Dict[str, int] = {}

    def seccion(titulo):
        nonlocal fila
        ws.cell(fila, 1, titulo).font = NEGRITA
        for j in range(1, len(enc) + 1):
            ws.cell(fila, j).fill = F_SEC; ws.cell(fila, j).border = BORDE
        fila += 1

    def linea(key, nombre, simbolo, unidad, valor, fmt, ecuacion, tipo="formula"):
        """valor: plantilla de fórmula (str con {c}) o función n -> valor."""
        nonlocal fila
        rows[key] = fila
        ws.cell(fila, 1, nombre).font = NEGRO
        ws.cell(fila, 2, simbolo).font = NEGRO
        ws.cell(fila, 3, unidad).font = NEGRO
        for j, (n, col) in enumerate(zip(nombres, cols)):
            if tipo == "formula":
                refs = {k: str(r) for k, r in rows.items()}   # {c}{clave} -> D12
                v = valor.format(c=col, **refs, **P)
            else:
                v = valor(n)
            c = ws.cell(fila, 4 + j, v)
            c.number_format = fmt
            c.font = AZUL if tipo == "entrada" else NEGRO
            if tipo == "entrada":
                c.fill = F_ENT
            if tipo == "motor":
                c.fill = F_FAD
            c.alignment = CENTRO if tipo != "texto" else IZQ
        ws.cell(fila, 4 + len(nombres), ecuacion).font = GRIS
        for j in range(1, len(enc) + 1):
            ws.cell(fila, j).border = BORDE
            if j <= 3:
                ws.cell(fila, j).alignment = IZQ if j == 1 else CENTRO
        ws.cell(fila, len(enc)).alignment = IZQ
        fila += 1

    ent = lambda attr: (lambda n: float(getattr(esc[n], attr)))
    seccion("1. ENTRADAS (deslizadores de la aplicación)")
    linea("P", "Carga por eje simple (rueda doble)", "P_eje", "t", ent("P_eje_t"), "0.0", "Escenario", "entrada")
    linea("v", "Velocidad del vehículo", "v", "km/h", ent("v_kmh"), "0", "Escenario", "entrada")
    linea("h1", "Espesor de carpeta asfáltica", "h₁", "cm", ent("h1_cm"), "0.0", "Escenario", "entrada")
    linea("E1", "Módulo de la mezcla asfáltica", "E₁", "MPa", ent("E1_MPa"), "#,##0", "Escenario", "entrada")
    linea("Mr", "Módulo resiliente de la subrasante", "Mr", "MPa", ent("Mr_MPa"), "0", "Escenario", "entrada")
    linea("xi", "Razón de amortiguamiento", "ξ", "–", ent("xi"), "0.00", "Escenario", "entrada")
    linea("ejes", "Ejes pesados por día (carril de diseño)", "n/día", "ejes", ent("ejes_dia"), "#,##0", "Escenario", "entrada")

    seccion("2. PULSO TRANSITORIO DE CARGA (M1)")
    linea("Pr", "Carga por rueda", "P_r", "kN", "={c}{P}*{g}/4", "0.0", "P_r = P_eje·g/4")
    linea("vms", "Velocidad", "v", "m/s", "={c}{v}/3.6", "0.00", "v [m/s] = v [km/h]/3.6")
    linea("d", "Duración del pulso", "d", "s", "=12*{a}/{c}{vms}", "0.0000", "d = 12a/v (Huang, 2004)")
    linea("f", "Frecuencia de carga", "f", "Hz", "=1/{c}{d}", "0.00", "f = 1/d")

    seccion("3. RESPUESTA DINÁMICA — OSCILADOR 1-GDL (M2)")
    linea("k", "Rigidez equivalente", "k", "MN/m", "=2*{c}{Mr}*{a}/(1-{nu}^2)", "0.00", "k = 2·Mr·a/(1−ν²)")
    linea("m", "Masa participante (cono de suelo)", "m", "kg", "={rho}*PI()/3*{H}*({a}^2+{a}*{R}+{R}^2)",
          "#,##0", "m = ρ·(π/3)·H·(a² + aR + R²)")
    linea("fn", "Frecuencia natural", "fₙ", "Hz", "=SQRT({c}{k}*1000000/{c}{m})/(2*PI())", "0.00", "fₙ = √(k/m)/2π")
    linea("Tn", "Periodo natural", "Tₙ", "s", "=1/{c}{fn}", "0.0000", "Tₙ = 1/fₙ")
    linea("dTn", "Relación duración/periodo", "d/Tₙ", "–", "={c}{d}/{c}{Tn}", "0.00", "Parámetro del espectro de choque")
    linea("vcrit", "Velocidad crítica de resonancia", "v_crit", "km/h", "=3.6*12*{a}/({pico}*{c}{Tn})", "0.0",
          "v_crit = 12a / ((d/Tₙ)pico·Tₙ)")
    linea("q", "Cercanía a la resonancia", "q", "–", "={c}{dTn}/{pico}", "0.00", "q = (d/Tₙ)/(d/Tₙ)pico ; q ≈ 1 → resonancia")
    linea("res", "Estado de resonancia", "–", "–",
          '=IF(AND({c}{q}>=0.85,{c}{q}<=1.2),"RESONANCIA",IF(AND({c}{q}>=0.7,{c}{q}<=1.5),"Proximidad","Fuera de resonancia"))',
          "@", "Regla de alerta del software")
    linea("uest", "Deflexión estática", "u_est", "mm", "={c}{Pr}/{c}{k}", "0.000", "u_est = P_r/k")
    linea("FAD", "Factor de amplificación dinámica", "FAD", "–", lambda n: round(res[n].FAD, 4), "0.000",
          "FAD = u_máx/u_est — integración numérica Newmark-β (motor_fisico.py)", "motor")
    linea("umax", "Deflexión dinámica máxima", "u_máx", "mm", "={c}{FAD}*{c}{uest}", "0.000", "u_máx = FAD·u_est")

    seccion("4. ESFUERZO Y DEFORMACIÓN (M3–M4)")
    linea("s0", "Esfuerzo de contacto estático", "σ₀", "MPa", "={c}{Pr}/1000/(PI()*{a}^2)", "0.000", "σ₀ = P_r/(πa²)")
    linea("sdin", "Amplitud de la onda de esfuerzo", "σ_din", "MPa", "={c}{s0}*{c}{FAD}", "0.000", "σ_din = σ₀·FAD(v)")
    linea("delta", "Longitud de atenuación", "δ", "m", "={a}*({c}{E1}/{c}{Mr})^(1/3)", "0.000", "δ = a·(E₁/Mr)^(1/3) (Odemark)")
    linea("sh1", "Esfuerzo en la base de la carpeta", "σ(h₁)", "MPa", "={c}{sdin}*EXP(-({c}{h1}/100)/{c}{delta})",
          "0.000", "σ(h₁) = σ_din·e^(−h₁/δ)")
    linea("eps", "Deformación unitaria de tracción", "ε_t", "με", "={K}*{c}{sh1}/{c}{E1}*1000000", "0.0",
          "ε_t = K·σ(h₁)/E₁")

    seccion("5. FATIGA Y VIDA ÚTIL (M5–M6)")
    linea("Nf", "Repeticiones admisibles a fatiga", "N_f", "rep.",
          "=0.0796*({c}{eps}/1000000)^(-3.291)*({c}{E1}*{psi})^(-0.854)", "0.00E+00",
          "N_f = 0.0796·ε_t^−3.291·E₁^−0.854 (Asphalt Institute; E₁ en psi)")
    linea("vida", "Vida útil a fatiga", "t_vida", "años", "={c}{Nf}/({c}{ejes}*365)", "0.00", "t = N_f/(365·ejes/día)")
    linea("red", "Reducción de vida respecto a E1", "–", "%", "=1-{c}{Nf}/$D${Nf}", "0.0%", "1 − N_f/N_f,E1")
    linea("nivel", "Nivel de riesgo", "–", "–",
          '=IF(OR({c}{red}>=0.7,{c}{vida}/{anos}<0.25),"Crítico",IF(OR({c}{red}>=0.4,{c}{vida}/{anos}<0.5),"Alto",'
          'IF(OR({c}{red}>=0.15,{c}{vida}/{anos}<1),"Moderado","Bajo")))',
          "@", "Reglas del módulo M8 (el más severo de los dos criterios)")

    seccion("6. ONDAS SUPERFICIALES (M7)")
    linea("Gm", "Módulo de corte de la subrasante", "G", "MPa", "={c}{Mr}/(2*(1+{nu}))", "0.0", "G = Mr/(2(1+ν))")
    linea("Vs", "Velocidad de onda de corte", "V_s", "m/s", "=SQRT({c}{Gm}*1000000/{rho})", "0.0", "V_s = √(G/ρ)")
    linea("VR", "Velocidad de onda Rayleigh", "V_R", "m/s", "={c}{Vs}*(0.87+1.12*{nu})/(1+{nu})", "0.0",
          "V_R = V_s(0.87 + 1.12ν)/(1 + ν) (Viktorov)")
    linea("lam", "Longitud de onda Rayleigh", "λ_R", "m", "={c}{VR}/{c}{f}", "0.00", "λ = V_R/f")

    seccion("7. DIAGNÓSTICO AUTOMÁTICO Y ALERTAS DEL SOFTWARE (M8)")
    alert = {n: dg.alertas(esc[n], res[n]) for n in nombres}
    dic = {n: dg.dictamen_reglas(esc[n], res[n], base_e, base_r) for n in nombres}
    linea("nalert", "Número de alertas críticas / altas", "–", "–",
          lambda n: f"{sum(a['nivel'] == 3 for a in alert[n])} críticas / {sum(a['nivel'] == 2 for a in alert[n])} altas",
          "@", "diagnostico.alertas()", "texto")
    linea("alist", "Alertas emitidas", "–", "–",
          lambda n: "\n".join(f"• {a['titulo']}" for a in alert[n]) or "Sin alertas", "@",
          "diagnostico.alertas()", "texto")
    linea("dict", "Dictamen técnico automático", "–", "–", lambda n: dic[n]["texto"].split(" ", 1)[1], "@",
          "diagnostico.dictamen_reglas()", "texto")
    linea("rec", "Recomendaciones", "–", "–",
          lambda n: "\n".join(f"• {x}" for x in dic[n]["recomendaciones"]) or "Mantener condición de referencia",
          "@", "diagnostico.dictamen_reglas()", "texto")
    ws.row_dimensions[rows["alist"]].height = 95
    ws.row_dimensions[rows["dict"]].height = 165
    ws.row_dimensions[rows["rec"]].height = 200

    # Formato condicional
    rango = f"D{rows['res']}:{ultima}{rows['res']}"
    ws.conditional_formatting.add(rango, FormulaRule(formula=[f'D{rows["res"]}="RESONANCIA"'],
                                  fill=PatternFill("solid", fgColor="F4B6B6"), font=Font(bold=True, color="9C0006")))
    ws.conditional_formatting.add(rango, FormulaRule(formula=[f'D{rows["res"]}="Proximidad"'],
                                  fill=PatternFill("solid", fgColor="FCE4D6")))
    rango = f"D{rows['nivel']}:{ultima}{rows['nivel']}"
    for txt, color in (("Crítico", "F4B6B6"), ("Alto", "FCE4D6"), ("Moderado", "FFF2CC"), ("Bajo", "E2EFDA")):
        ws.conditional_formatting.add(rango, FormulaRule(formula=[f'D{rows["nivel"]}="{txt}"'],
                                      fill=PatternFill("solid", fgColor=color), font=Font(bold=True)))

    ws.cell(rows["FAD"], 4).comment = Comment(
        "Único valor no explícito: se obtiene integrando m·ü + c·u̇ + k·u = F(t) con Newmark-β "
        "(motor_fisico.py). Depende solo de d/Tₙ y ξ.", "Castaño & Garzón")
    ws.cell(fila + 1, 1, "Nota: E3 se evalúa a su velocidad crítica de resonancia (≈ 50 km/h), hallada en el análisis "
                         "de sensibilidad. La columna G conserva E3 a 80 km/h (Entregable 1) como referencia.").font = GRIS

    for col, w in zip("ABC", (38, 9, 7)):
        ws.column_dimensions[col].width = w
    for col in cols:
        ws.column_dimensions[col].width = 26
    ws.column_dimensions[ultima].width = 48
    ws.freeze_panes = "D6"
    ws.sheet_view.zoomScale = 90
    return res


# -----------------------------------------------------------------------------
def _hoja_sensibilidad(wb):
    ws = wb.create_sheet("Sensibilidad")
    ws["A1"] = "Análisis de sensibilidad y resonancia"; ws["A1"].font = TITULO
    ws["A2"] = ("Valores calculados con el motor numérico (sensibilidad.py): requieren integrar la ecuación "
                "de movimiento, por eso no son fórmulas de Excel.")
    ws["A2"].font = GRIS

    # Barrido de velocidad
    e_norm = mf.ESCENARIOS["E2 - Límite"]
    e_bland = mf.ESCENARIOS["E3 - Crítico"]
    v = np.arange(20.0, 121.0, 5.0)
    bn, bb = sb.barrido_velocidad(e_norm, v), sb.barrido_velocidad(e_bland, v)
    enc = ["Velocidad [km/h]", "FAD estructura normal (h₁ 10 cm, Mr 80)", "FAD estructura débil (h₁ 5 cm, Mr 30)",
           "N_f estructura normal, 14 t", "N_f estructura débil, 14 t"]
    ws["A4"] = "Tabla S1. Barrido de velocidad con eje de 14 t"; ws["A4"].font = NEGRITA
    for j, t in enumerate(enc, 1):
        c = ws.cell(5, j, t); c.font = BLANCO; c.fill = F_ENC; c.alignment = CENTRO; c.border = BORDE
    ws.row_dimensions[5].height = 42
    for i, vi in enumerate(v):
        vals = [vi, bn["FAD"][i], bb["FAD"][i], bn["N_f"][i], bb["N_f"][i]]
        for j, (val, fmt) in enumerate(zip(vals, ["0", "0.000", "0.000", "0.00E+00", "0.00E+00"]), 1):
            c = ws.cell(6 + i, j, float(val)); c.number_format = fmt; c.font = NEGRO
            c.alignment = CENTRO; c.border = BORDE
    fin = 5 + len(v)
    vn, vb = sb.velocidad_critica(e_norm), sb.velocidad_critica(e_bland)
    ws.cell(fin + 1, 1, f"Velocidad crítica: estructura normal ≈ {vn:.0f} km/h · estructura débil ≈ {vb:.0f} km/h").font = NEGRITA

    ch = ScatterChart()
    ch.title = "Curva de resonancia: FAD vs velocidad"
    ch.style = 13
    ch.x_axis.title = "Velocidad [km/h]"
    ch.y_axis.title = "FAD"
    xs = Reference(ws, min_col=1, min_row=6, max_row=fin)
    for col, color in ((2, "2F6DB5"), (3, "C0392B")):
        s = Series(Reference(ws, min_col=col, min_row=5, max_row=fin), xs, title_from_data=True)
        s.marker.symbol = "none"; s.smooth = True
        s.graphicalProperties.line.solidFill = color; s.graphicalProperties.line.width = 28000
        ch.series.append(s)
    ch.y_axis.scaling.min = 1.0
    ch.x_axis.scaling.min = 20; ch.x_axis.scaling.max = 120
    ch.roundedCorners = False
    ch.legend.position = "b"; ch.legend.overlay = False
    ch.title.overlay = False
    ch.x_axis.delete = False; ch.y_axis.delete = False
    ch.height, ch.width = 8.5, 16
    ws.add_chart(ch, "G4")

    # Tornado
    t0 = fin + 4
    ws.cell(t0, 1, "Tabla S2. Sensibilidad de N_f a cada variable (±20 %, resto constante)").font = NEGRITA
    enc = ["Variable", "E1: −20 %", "E1: +20 %", "E3: −20 %", "E3: +20 %"]
    for j, t in enumerate(enc, 1):
        c = ws.cell(t0 + 1, j, t); c.font = BLANCO; c.fill = F_ENC; c.alignment = CENTRO; c.border = BORDE
    t1 = {f["attr"]: f for f in sb.tornado(mf.ESCENARIOS["E1 - Base"])}
    t3 = {f["attr"]: f for f in sb.tornado(e_bland)}
    orden = [f["attr"] for f in sb.tornado(mf.ESCENARIOS["E1 - Base"])]
    for i, attr in enumerate(orden):
        vals = [t1[attr]["variable"], t1[attr]["bajo"] / 100, t1[attr]["alto"] / 100,
                t3[attr]["bajo"] / 100, t3[attr]["alto"] / 100]
        for j, val in enumerate(vals, 1):
            c = ws.cell(t0 + 2 + i, j, val); c.font = NEGRO; c.border = BORDE
            c.alignment = IZQ if j == 1 else CENTRO
            if j > 1:
                c.number_format = "+0.0%;-0.0%;0.0%"
    ws.cell(t0 + 3 + len(orden), 1,
            "Lectura: un valor positivo aumenta la vida a fatiga. En E3 (en resonancia) bajar o subir la "
            "velocidad AUMENTA la vida, porque cualquier cambio aleja al pulso del pico de resonancia.").font = GRIS
    for col, w in zip("ABCDE", (30, 22, 22, 22, 22)):
        ws.column_dimensions[col].width = w


# -----------------------------------------------------------------------------
def construir_excel(destino: Union[str, BytesIO] = "Matriz_Simulacion.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Matriz"
    pico, _ = sb.razon_resonancia(0.15)
    P = _hoja_parametros(wb, pico)
    _hoja_matriz(ws, P)
    _hoja_sensibilidad(wb)
    wb.save(destino)
    return destino


if __name__ == "__main__":
    print("Guardado:", construir_excel())
