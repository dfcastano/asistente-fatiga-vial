"""
diagnostico.py
===============================================================================
Módulo de Diagnóstico Automático (Reglas + Prompt para IA)

Capa 1 — Reglas deterministas (siempre disponibles, reproducibles):
    1. Nivel de riesgo por reducción de vida útil y por vida útil vs diseño.
    2. Descomposición de la causa: como ε_t ∝ P_r · FAD · e^(−h1/δ) / E1,
       el logaritmo de la pérdida de vida se separa EXACTAMENTE en aportes:
         ln(N_base/N) = 3.291·[ln r_carga + ln r_dinámica + ln r_estructura]
                        + 0.854·ln(E1/E1_base)
    3. Recomendaciones según la causa dominante.

Capa 2 — Prompt para un modelo de lenguaje (semana 2): construir_prompt()
    entrega los resultados numéricos para que la IA redacte el dictamen.
===============================================================================
"""
import math
from typing import Dict, List

import sensibilidad as sb
from motor_fisico import Entradas, Resultados, reduccion_vida

NIVELES = ["🟢 Riesgo Bajo", "🟡 Riesgo Moderado", "🟠 Riesgo Alto", "🔴 Riesgo Crítico"]

RECOMENDACIONES = {
    "carga": "Control de pesos por eje (básculas/WIM) y restricción de sobrecargas.",
    "dinamica": "Reducir la velocidad de operación de vehículos pesados y mejorar "
                "la regularidad superficial (IRI) para limitar la amplificación dinámica.",
    "estructura": "Refuerzo estructural: aumentar el espesor de carpeta asfáltica y/o "
                  "estabilizar o reemplazar la subrasante de bajo módulo resiliente.",
}


def _nivel_por_reduccion(pct: float) -> int:
    if pct >= 70: return 3
    if pct >= 40: return 2
    if pct >= 15: return 1
    return 0


def _nivel_por_vida(vida: float, diseno: float) -> int:
    ratio = vida / diseno
    if ratio < 0.25: return 3
    if ratio < 0.50: return 2
    if ratio < 1.00: return 1
    return 0


def descomponer_causas(e: Entradas, r: Resultados,
                       eb: Entradas, rb: Resultados) -> Dict[str, float]:
    """Aporte (%) de cada grupo de variables a la pérdida de vida a fatiga."""
    ln_carga = 3.291 * math.log(r.P_r / rb.P_r)
    ln_dinamica = 3.291 * math.log(r.FAD / rb.FAD)
    ln_estructura = (3.291 * math.log((r.sigma_h1 / r.sigma_din) / (rb.sigma_h1 / rb.sigma_din)
                                      * (eb.E1_MPa / e.E1_MPa))
                     + 0.854 * math.log(e.E1_MPa / eb.E1_MPa))
    aportes = {"carga": ln_carga, "dinamica": ln_dinamica, "estructura": ln_estructura}
    positivos = {k: v for k, v in aportes.items() if v > 0}
    total = sum(positivos.values())
    if total <= 0:
        return {k: 0.0 for k in aportes}
    return {k: 100.0 * positivos.get(k, 0.0) / total for k in aportes}


def dictamen_reglas(e: Entradas, r: Resultados, eb: Entradas, rb: Resultados) -> Dict:
    """Dictamen técnico breve generado por reglas."""
    pct = reduccion_vida(r, rb)
    nivel = max(_nivel_por_reduccion(pct), _nivel_por_vida(r.vida_util_anos, e.anos_diseno))
    aportes = descomponer_causas(e, r, eb, rb)

    descripcion = {
        "carga": f"la sobrecarga del eje ({e.P_eje_t:.0f} t, "
                 f"{e.P_eje_t / eb.P_eje_t:.2f}× la carga base)",
        "dinamica": f"la amplificación dinámica a {e.v_kmh:.0f} km/h (FAD = {r.FAD:.2f}"
                    + (", condición de resonancia)" if estado_resonancia(e, r)[0] == 2 else ")"),
        "estructura": f"la estructura débil (carpeta de {e.h1_cm:.0f} cm sobre "
                      f"subrasante de {e.Mr_MPa:.0f} MPa)",
    }
    causas = [k for k, v in sorted(aportes.items(), key=lambda kv: -kv[1]) if v >= 15.0]

    if causas:
        texto_causas = " y ".join(descripcion[c] for c in causas)
        texto = (f"{NIVELES[nivel]}: la combinación de {texto_causas} reduce la vida útil "
                 f"del pavimento en un {pct:.0f} % por fatiga prematura "
                 f"(ε_t = {r.eps_t * 1e6:.0f} με; vida estimada {r.vida_util_anos:.1f} de "
                 f"{e.anos_diseno:.0f} años de diseño).")
    else:
        texto = (f"{NIVELES[nivel]}: condición de referencia. ε_t = {r.eps_t * 1e6:.0f} με, "
                 f"N_f = {r.N_f:.2e} repeticiones; vida estimada {r.vida_util_anos:.1f} de "
                 f"{e.anos_diseno:.0f} años de diseño.")

    recs = [RECOMENDACIONES[c] for c in causas]
    est, _, v_crit = estado_resonancia(e, r)
    if "dinamica" in causas and est == 2:
        recs[causas.index("dinamica")] = (
            f"Salir de la banda de resonancia: la velocidad crítica de esta estructura es "
            f"{v_crit:.0f} km/h. Limitar a los vehículos pesados fuera de ±15 km/h de ese valor "
            f"o rigidizar la estructura para subir la frecuencia natural.")
    return dict(nivel=NIVELES[nivel], reduccion_pct=pct, aportes=aportes, texto=texto,
                recomendaciones=recs)


# =============================================================================
# ALERTAS DEL SOFTWARE
# =============================================================================
LIMITE_LEGAL_EJE_SIMPLE_T = 11.0   # eje sencillo, llanta doble (Res. 4100 de 2004, MinTransporte)


def estado_resonancia(e: Entradas, r: Resultados):
    """
    q = (d/T_n) / (d/T_n)_pico.   q ≈ 1 → el pulso excita la frecuencia natural.
    Devuelve (estado, q, v_crit): 2 = resonancia, 1 = proximidad, 0 = fuera.
    """
    rp, _ = sb.razon_resonancia(round(e.xi, 4))
    q = (r.d / r.T_n) / rp
    v_crit = sb.velocidad_critica(e)
    if 0.85 <= q <= 1.20:
        return 2, q, v_crit
    if 0.70 <= q <= 1.50:
        return 1, q, v_crit
    return 0, q, v_crit


def alertas(e: Entradas, r: Resultados) -> List[Dict]:
    """Lista de alertas (nivel 3 = crítica, 2 = alta, 1 = aviso), de mayor a menor."""
    out = []
    est, q, v_crit = estado_resonancia(e, r)
    if est == 2:
        out.append(dict(nivel=3, titulo="Resonancia dinámica",
                        detalle=f"La frecuencia del pulso de carga (f = {r.f_carga:.1f} Hz) excita la "
                                f"frecuencia natural del pavimento (fₙ = {r.f_n:.1f} Hz). "
                                f"FAD = {r.FAD:.2f}: el esfuerzo se amplifica un {100 * (r.FAD - 1):.0f} %. "
                                f"Velocidad crítica de esta estructura: {v_crit:.0f} km/h."))
    elif est == 1:
        out.append(dict(nivel=2, titulo="Proximidad a resonancia",
                        detalle=f"La velocidad ({e.v_kmh:.0f} km/h) está cerca de la velocidad crítica "
                                f"({v_crit:.0f} km/h). FAD = {r.FAD:.2f}."))
    if e.P_eje_t > LIMITE_LEGAL_EJE_SIMPLE_T:
        out.append(dict(nivel=3, titulo="Sobrecarga ilegal",
                        detalle=f"Eje de {e.P_eje_t:.1f} t: supera el límite legal de "
                                f"{LIMITE_LEGAL_EJE_SIMPLE_T:.0f} t para eje sencillo de llanta doble."))
    elif e.P_eje_t > mf_eje_estandar():
        out.append(dict(nivel=1, titulo="Carga superior al eje estándar",
                        detalle=f"Eje de {e.P_eje_t:.1f} t frente al eje estándar de diseño de 8.2 t."))
    eps = r.eps_t * 1e6
    if eps > 300:
        out.append(dict(nivel=3, titulo="Deformación de tracción excesiva",
                        detalle=f"ε_t = {eps:.0f} με en la base de la carpeta (> 300 με)."))
    elif eps > 200:
        out.append(dict(nivel=2, titulo="Deformación de tracción elevada",
                        detalle=f"ε_t = {eps:.0f} με en la base de la carpeta (> 200 με)."))
    ratio = r.vida_util_anos / e.anos_diseno
    if ratio < 0.25:
        out.append(dict(nivel=3, titulo="Falla por fatiga prematura",
                        detalle=f"Vida útil estimada de {r.vida_util_anos:.1f} años frente a "
                                f"{e.anos_diseno:.0f} años de diseño."))
    elif ratio < 1.0:
        out.append(dict(nivel=2, titulo="Vida útil inferior al diseño",
                        detalle=f"Vida útil estimada de {r.vida_util_anos:.1f} de {e.anos_diseno:.0f} años."))
    if e.Mr_MPa < 50:
        out.append(dict(nivel=2, titulo="Subrasante de baja capacidad",
                        detalle=f"Mr = {e.Mr_MPa:.0f} MPa (CBR ≈ {e.Mr_MPa / 10:.0f} %). "
                                "Baja la frecuencia natural y la velocidad crítica."))
    if e.h1_cm < 7.5:
        out.append(dict(nivel=2, titulo="Carpeta asfáltica delgada",
                        detalle=f"h₁ = {e.h1_cm:.0f} cm: menor distribución del esfuerzo hacia la subrasante."))
    out.sort(key=lambda a: -a["nivel"])
    return out


def mf_eje_estandar() -> float:
    from motor_fisico import P_EJE_ESTANDAR_T
    return P_EJE_ESTANDAR_T


def construir_prompt(nombre: str, e: Entradas, r: Resultados, dictamen: Dict) -> str:
    """Prompt para que un modelo de lenguaje redacte el dictamen (capa 2, opcional)."""
    return (
        "Actúa como ingeniero civil especialista en pavimentos. Con los resultados del "
        "modelo físico, redacta un dictamen técnico de máximo 3 frases, en español, "
        "iniciando con el nivel de riesgo. No inventes cifras distintas a las dadas.\n\n"
        f"Escenario: {nombre}\n"
        f"Entradas: eje {e.P_eje_t} t, velocidad {e.v_kmh} km/h, carpeta {e.h1_cm} cm, "
        f"E1 {e.E1_MPa} MPa, subrasante Mr {e.Mr_MPa} MPa.\n"
        f"Resultados: FAD {r.FAD:.2f}, σ_din {r.sigma_din / 1e6:.2f} MPa, "
        f"ε_t {r.eps_t * 1e6:.0f} με, N_f {r.N_f:.2e}, vida útil {r.vida_util_anos:.1f} años.\n"
        f"Reglas: {dictamen['nivel']}, reducción de vida {dictamen['reduccion_pct']:.0f} %, "
        f"aportes por causa {dictamen['aportes']}.\n"
    )


if __name__ == "__main__":
    from motor_fisico import ESCENARIOS, simular

    eb = ESCENARIOS["E1 - Base"]
    rb = simular(eb)
    for nombre, e in ESCENARIOS.items():
        r = simular(e)
        d = dictamen_reglas(e, r, eb, rb)
        print(f"\n[{nombre}]\n  {d['texto']}")
        print("  Aportes a la pérdida de vida: "
              + ", ".join(f"{k} {v:.0f} %" for k, v in d["aportes"].items()))
        for rec in d["recomendaciones"]:
            print(f"  → {rec}")
        for a in alertas(e, r):
            print(f"  [ALERTA {a['nivel']}] {a['titulo']}: {a['detalle']}")
