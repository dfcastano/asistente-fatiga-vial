"""
motor_fisico.py
===============================================================================
Asistente Predictivo de Fatiga Vial por Ondas Dinámicas en Pavimentos Flexibles
Consultoría Castaño & Garzón — Proyecto Integrador Física e IA

Motor de cálculo simplificado (según retroalimentación de la docente):
  - Sin Navier-Cauchy ni dispersión de Rayleigh multicapa.
  - Modelo de 1 grado de libertad (1-GDL) + sistema de 2 capas
    (carpeta asfáltica sobre subrasante).
  - Carga del eje modelada como pulso transitorio (haversine).
  - Atenuación exponencial del esfuerzo con la profundidad.
  - Deformación unitaria -> repeticiones admisibles (fatiga del asfalto).

Cadena de cálculo (cada módulo es una función pura y verificable):

  M1  Pulso de carga ........ P_r, d, F(t)
  M2  Respuesta 1-GDL ....... k, m, ω_n, u(t), FAD
  M3  Amplitud de esfuerzo .. σ_din(P, v)
  M4  Atenuación ............ δ, σ(h1), ε_t
  M5  Fatiga ................ N_f
  M6  Degradación ........... vida remanente(t), vida útil
  M7  Ondas superficiales ... V_s, V_R, λ, A(r), PPV(r)

Unidades: SI internamente (N, m, s, Pa). Las entradas de usuario llegan en
unidades "de ingeniero" (t, km/h, cm, MPa) y se convierten en simular().
===============================================================================
"""
from dataclasses import dataclass, field
from typing import Dict

import numpy as np

# -----------------------------------------------------------------------------
# Constantes y parámetros fijos del modelo
# -----------------------------------------------------------------------------
G = 9.81                 # aceleración de la gravedad [m/s²]
A_HUELLA = 0.108         # radio de huella estándar (eje 8.2 t, rueda doble) [m]
P_EJE_ESTANDAR_T = 8.2   # eje simple estándar AASHTO (ESAL) [t]
H_CONO = 1.10            # profundidad de influencia del cono de carga [m]
ANG_CONO_DEG = 30.0      # ángulo de distribución del cono [°]
K_CAL = 1.15             # factor de calibración de ε_t (ver M4 y esquema)
MPA_A_PSI = 145.038      # 1 MPa = 145.038 psi


# -----------------------------------------------------------------------------
# Estructuras de datos
# -----------------------------------------------------------------------------
@dataclass
class Entradas:
    """Variables controladas por los deslizadores de Streamlit."""
    P_eje_t: float = 8.0       # carga por eje simple [t]
    v_kmh: float = 40.0        # velocidad del vehículo [km/h]
    h1_cm: float = 10.0        # espesor de la carpeta asfáltica [cm]
    E1_MPa: float = 3000.0     # módulo de la mezcla asfáltica [MPa]
    Mr_MPa: float = 80.0       # módulo resiliente de la subrasante [MPa]
    xi: float = 0.15           # razón de amortiguamiento del sistema [-]
    nu: float = 0.40           # relación de Poisson de la subrasante [-]
    rho: float = 1900.0        # densidad de la subrasante [kg/m³]
    ejes_dia: float = 400.0    # repeticiones diarias de este eje (carril de diseño)
    anos_diseno: float = 20.0  # periodo de diseño [años]


@dataclass
class Resultados:
    # M1
    P_r: float = 0.0           # carga por rueda [N]
    d: float = 0.0             # duración del pulso [s]
    f_carga: float = 0.0       # frecuencia de carga 1/d [Hz]
    # M2
    k: float = 0.0             # rigidez equivalente [N/m]
    m: float = 0.0             # masa participante [kg]
    f_n: float = 0.0           # frecuencia natural [Hz]
    T_n: float = 0.0           # periodo natural [s]
    u_est: float = 0.0         # deflexión estática [m]
    u_max: float = 0.0         # deflexión dinámica máxima [m]
    FAD: float = 0.0           # factor de amplificación dinámica [-]
    # M3 - M4
    sigma0: float = 0.0        # esfuerzo de contacto estático [Pa]
    sigma_din: float = 0.0     # amplitud de la onda de esfuerzo [Pa]
    delta: float = 0.0         # longitud de atenuación [m]
    sigma_h1: float = 0.0      # esfuerzo en la base de la carpeta [Pa]
    eps_t: float = 0.0         # deformación unitaria de tracción [m/m]
    # M5 - M6
    N_f: float = 0.0           # repeticiones admisibles a fatiga
    vida_util_anos: float = 0.0
    # M7
    V_s: float = 0.0
    V_R: float = 0.0
    lambda_R: float = 0.0
    # Series para graficar
    series: Dict[str, np.ndarray] = field(default_factory=dict)


# =============================================================================
# M1. PULSO TRANSITORIO DE CARGA
# =============================================================================
def m1_pulso_carga(P_eje_t: float, v_ms: float, a: float = A_HUELLA):
    """
    Carga por rueda (eje simple de rueda doble = 4 llantas):
        P_r = P_eje · g / 4
    Duración del pulso (Huang, 2004):
        d = 12·a / v
    Forma del pulso (haversine):
        F(t) = P_r · sin²(π t / d),   0 ≤ t ≤ d ;  F = 0 fuera del pulso
    """
    P_r = P_eje_t * 1000.0 * G / 4.0
    d = 12.0 * a / v_ms
    return P_r, d


def fuerza_haversine(t: np.ndarray, P_r: float, d: float) -> np.ndarray:
    F = P_r * np.sin(np.pi * t / d) ** 2
    F[t > d] = 0.0
    return F


# =============================================================================
# M2. RESPUESTA DINÁMICA — OSCILADOR DE 1 GRADO DE LIBERTAD
# =============================================================================
def m2_rigidez(Mr_Pa: float, nu: float, a: float = A_HUELLA) -> float:
    """Placa circular sobre semiespacio elástico:  k = 2·Mr·a / (1 − ν²)"""
    return 2.0 * Mr_Pa * a / (1.0 - nu ** 2)


def m2_masa_participante(rho: float, a: float = A_HUELLA,
                         H: float = H_CONO, ang_deg: float = ANG_CONO_DEG) -> float:
    """
    Masa del cono truncado de suelo que vibra bajo la huella:
        R = a + H·tan(θ)
        m = ρ · (π/3) · H · (a² + a·R + R²)
    """
    R = a + H * np.tan(np.radians(ang_deg))
    return rho * (np.pi / 3.0) * H * (a ** 2 + a * R + R ** 2)


def newmark_1gdl(m: float, c: float, k: float, t: np.ndarray, F: np.ndarray):
    """
    Integra  m·ü + c·u̇ + k·u = F(t)  con el método de Newmark-β
    de aceleración promedio (γ = 1/2, β = 1/4): incondicionalmente estable.
    Condiciones iniciales: u(0) = 0, u̇(0) = 0.   (Chopra, Dinámica de Estructuras)
    """
    gam, beta = 0.5, 0.25
    dt = t[1] - t[0]
    n = len(t)
    u, v, acc = np.zeros(n), np.zeros(n), np.zeros(n)
    acc[0] = (F[0] - c * v[0] - k * u[0]) / m

    k_hat = k + gam / (beta * dt) * c + m / (beta * dt ** 2)
    A = m / (beta * dt) + gam / beta * c
    B = m / (2.0 * beta) + dt * (gam / (2.0 * beta) - 1.0) * c

    for i in range(n - 1):
        dP = (F[i + 1] - F[i]) + A * v[i] + B * acc[i]
        du = dP / k_hat
        dv = gam / (beta * dt) * du - gam / beta * v[i] + dt * (1 - gam / (2 * beta)) * acc[i]
        da = du / (beta * dt ** 2) - v[i] / (beta * dt) - acc[i] / (2 * beta)
        u[i + 1], v[i + 1], acc[i + 1] = u[i] + du, v[i] + dv, acc[i] + da
    return u, v, acc


def m2_respuesta(P_r: float, d: float, k: float, m: float, xi: float):
    """
    ω_n = √(k/m),  c = 2·ξ·√(k·m),  u_est = P_r / k
    FAD = u_max / u_est   (factor de amplificación dinámica)
    """
    w_n = np.sqrt(k / m)
    T_n = 2 * np.pi / w_n
    c = 2.0 * xi * np.sqrt(k * m)
    dt = min(d, T_n) / 400.0
    t = np.arange(0.0, d + 4.0 * T_n, dt)       # pulso + vibración libre
    F = fuerza_haversine(t, P_r, d)
    u, _, _ = newmark_1gdl(m, c, k, t, F)
    u_est = P_r / k
    u_max = float(np.max(np.abs(u)))
    return dict(w_n=w_n, T_n=T_n, c=c, t=t, F=F, u=u,
                u_est=u_est, u_max=u_max, FAD=u_max / u_est)


# =============================================================================
# M3. AMPLITUD DE LA ONDA DE ESFUERZO  σ_din(P, v)
# =============================================================================
def m3_esfuerzo_dinamico(P_r: float, FAD: float, a: float = A_HUELLA):
    """
    σ0    = P_r / (π a²)        (esfuerzo de contacto estático)
    σ_din = σ0 · FAD(v)         -> depende de la carga (P) y de la velocidad (v)
    """
    sigma0 = P_r / (np.pi * a ** 2)
    return sigma0, sigma0 * FAD


# =============================================================================
# M4. ATENUACIÓN EXPONENCIAL CON LA PROFUNDIDAD  ->  ε_t
# =============================================================================
def m4_atenuacion(sigma_din: float, h1: float, E1_Pa: float, Mr_Pa: float,
                  a: float = A_HUELLA, K: float = K_CAL):
    """
    Longitud de atenuación (equivalencia de espesores de Odemark):
        δ = a · (E1 / Mr)^(1/3)
    Esfuerzo a la profundidad z:
        σ(z) = σ_din · e^(−z/δ)
    Deformación de tracción en la fibra inferior de la carpeta:
        ε_t = K · σ(h1) / E1
    """
    delta = a * (E1_Pa / Mr_Pa) ** (1.0 / 3.0)
    sigma_h1 = sigma_din * np.exp(-h1 / delta)
    eps_t = K * sigma_h1 / E1_Pa
    return delta, sigma_h1, eps_t


# =============================================================================
# M5. FATIGA DEL ASFALTO (Asphalt Institute)
# =============================================================================
def m5_fatiga(eps_t: float, E1_MPa: float) -> float:
    """
    N_f = 0.0796 · ε_t^(−3.291) · E1^(−0.854)      [E1 en psi, ε_t en m/m]
    """
    return 0.0796 * eps_t ** (-3.291) * (E1_MPa * MPA_A_PSI) ** (-0.854)


# =============================================================================
# M6. CURVA DE DEGRADACIÓN (regla de Miner)
# =============================================================================
def m6_degradacion(N_f: float, ejes_dia: float, anos_diseno: float):
    """
    n(t)              = ejes_dia · 365 · t
    Daño D(t)         = n(t) / N_f
    Vida remanente(t) = 100 · max(0, 1 − D(t))   [%]
    Vida útil         = N_f / (ejes_dia · 365)   [años]
    """
    anos = np.linspace(0.0, anos_diseno, 201)
    D = ejes_dia * 365.0 * anos / N_f
    vida_rem = 100.0 * np.clip(1.0 - D, 0.0, 1.0)
    return anos, vida_rem, N_f / (ejes_dia * 365.0)


# =============================================================================
# M7. ONDAS SUPERFICIALES (Rayleigh) Y ATENUACIÓN CON LA DISTANCIA
# =============================================================================
def m7_ondas_superficiales(Mr_Pa: float, nu: float, rho: float, f: float,
                           xi: float, u0: float, r0: float = A_HUELLA,
                           r_max: float = 30.0):
    """
    G   = Mr / (2(1+ν))                 V_s = √(G/ρ)
    V_R = V_s · (0.87 + 1.12ν)/(1 + ν)  (aproximación de Viktorov)
    λ_R = V_R / f                       (V = f·λ)
    Ecuación de Bornitz (onda superficial, n = 0.5):
        A(r) = A0 · √(r0/r) · e^(−α (r − r0)),   α = 2π f ξ / V_R
    Velocidad pico de partícula:  PPV ≈ 2π f · A(r)
    """
    G_mod = Mr_Pa / (2.0 * (1.0 + nu))
    V_s = np.sqrt(G_mod / rho)
    V_R = V_s * (0.87 + 1.12 * nu) / (1.0 + nu)
    lam = V_R / f
    alpha = 2.0 * np.pi * f * xi / V_R
    r = np.linspace(r0, r_max, 300)
    A = u0 * np.sqrt(r0 / r) * np.exp(-alpha * (r - r0))
    PPV = 2.0 * np.pi * f * A
    return dict(V_s=V_s, V_R=V_R, lambda_R=lam, alpha=alpha, r=r, A=A, PPV=PPV)


# =============================================================================
# ORQUESTADOR: ejecuta M1 → M7 para un escenario
# =============================================================================
def simular(e: Entradas) -> Resultados:
    # Conversión de unidades de ingeniero a SI
    v = e.v_kmh / 3.6
    h1 = e.h1_cm / 100.0
    E1, Mr = e.E1_MPa * 1e6, e.Mr_MPa * 1e6

    r = Resultados()
    # M1
    r.P_r, r.d = m1_pulso_carga(e.P_eje_t, v)
    r.f_carga = 1.0 / r.d
    # M2
    r.k = m2_rigidez(Mr, e.nu)
    r.m = m2_masa_participante(e.rho)
    dyn = m2_respuesta(r.P_r, r.d, r.k, r.m, e.xi)
    r.f_n, r.T_n = dyn["w_n"] / (2 * np.pi), dyn["T_n"]
    r.u_est, r.u_max, r.FAD = dyn["u_est"], dyn["u_max"], dyn["FAD"]
    # M3
    r.sigma0, r.sigma_din = m3_esfuerzo_dinamico(r.P_r, r.FAD)
    # M4
    r.delta, r.sigma_h1, r.eps_t = m4_atenuacion(r.sigma_din, h1, E1, Mr)
    # M5
    r.N_f = m5_fatiga(r.eps_t, e.E1_MPa)
    # M6
    anos, vida_rem, r.vida_util_anos = m6_degradacion(r.N_f, e.ejes_dia, e.anos_diseno)
    # M7
    ondas = m7_ondas_superficiales(Mr, e.nu, e.rho, r.f_carga, e.xi, r.u_max)
    r.V_s, r.V_R, r.lambda_R = ondas["V_s"], ondas["V_R"], ondas["lambda_R"]

    z = np.linspace(0.0, 0.6, 200)
    r.series = dict(
        t=dyn["t"], F=dyn["F"], u=dyn["u"],                   # onda transitoria
        z=z, sigma_z=r.sigma_din * np.exp(-z / r.delta),      # atenuación vertical
        anos=anos, vida_rem=vida_rem,                         # degradación
        r=ondas["r"], A_r=ondas["A"], PPV_r=ondas["PPV"],     # atenuación horizontal
    )
    return r


def reduccion_vida(r_esc: Resultados, r_base: Resultados) -> float:
    """Reducción de vida útil respecto al escenario base [%]."""
    return 100.0 * (1.0 - r_esc.N_f / r_base.N_f)


# -----------------------------------------------------------------------------
# Escenarios del estudio técnico
#   E1 → E2: cambia el tránsito (sobrecarga + alta velocidad).
#   E3: estructura débil (carpeta delgada + subrasante blanda) con sobrecarga,
#       evaluada a su VELOCIDAD CRÍTICA DE RESONANCIA (v_crit ≈ 50 km/h,
#       ver sensibilidad.velocidad_critica). En el Entregable 1 se evaluó a
#       80 km/h; ese caso se conserva como referencia en ESCENARIO_REFERENCIA.
# -----------------------------------------------------------------------------
ESCENARIOS = {
    "E1 - Base":    Entradas(P_eje_t=8.0,  v_kmh=40.0, h1_cm=10.0, Mr_MPa=80.0),
    "E2 - Límite":  Entradas(P_eje_t=14.0, v_kmh=80.0, h1_cm=10.0, Mr_MPa=80.0),
    "E3 - Crítico": Entradas(P_eje_t=14.0, v_kmh=50.0, h1_cm=5.0,  Mr_MPa=30.0),
}
ESCENARIO_REFERENCIA = {
    "E3 a 80 km/h (Entregable 1)": Entradas(P_eje_t=14.0, v_kmh=80.0, h1_cm=5.0, Mr_MPa=30.0),
}


# -----------------------------------------------------------------------------
# Verificación por consola:  python motor_fisico.py
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    res = {nombre: simular(ent) for nombre, ent in ESCENARIOS.items()}
    base = res["E1 - Base"]

    filas = [
        ("Carga por rueda P_r [kN]",      lambda r: r.P_r / 1e3,       "{:8.1f}"),
        ("Duración pulso d [s]",          lambda r: r.d,               "{:8.4f}"),
        ("Frec. de carga f [Hz]",         lambda r: r.f_carga,         "{:8.1f}"),
        ("Rigidez k [MN/m]",              lambda r: r.k / 1e6,         "{:8.2f}"),
        ("Masa participante m [kg]",      lambda r: r.m,               "{:8.0f}"),
        ("Frec. natural f_n [Hz]",        lambda r: r.f_n,             "{:8.2f}"),
        ("Relación d/T_n [-]",            lambda r: r.d / r.T_n,       "{:8.2f}"),
        ("FAD [-]",                       lambda r: r.FAD,             "{:8.3f}"),
        ("Deflexión máx u_max [mm]",      lambda r: r.u_max * 1e3,     "{:8.3f}"),
        ("σ_din [MPa]",                   lambda r: r.sigma_din / 1e6, "{:8.3f}"),
        ("δ atenuación [m]",              lambda r: r.delta,           "{:8.3f}"),
        ("σ(h1) [MPa]",                   lambda r: r.sigma_h1 / 1e6,  "{:8.3f}"),
        ("ε_t [με]",                      lambda r: r.eps_t * 1e6,     "{:8.1f}"),
        ("N_f [repeticiones]",            lambda r: r.N_f,             "{:8.2e}"),
        ("Vida útil [años]",              lambda r: r.vida_util_anos,  "{:8.2f}"),
        ("Reducción vs E1 [%]",           lambda r: reduccion_vida(r, base), "{:8.1f}"),
        ("V_R onda Rayleigh [m/s]",       lambda r: r.V_R,             "{:8.1f}"),
        ("λ_R [m]",                       lambda r: r.lambda_R,        "{:8.2f}"),
    ]
    nombres = list(res)
    print(f"{'Variable':32s}" + "".join(f"{n:>15s}" for n in nombres))
    print("-" * (32 + 15 * len(nombres)))
    for etiqueta, fn, fmt in filas:
        print(f"{etiqueta:32s}" + "".join(f"{fmt.format(fn(res[n])):>15s}" for n in nombres))

    # Contraste con la ley de la cuarta potencia (AASHO Road Test)
    fec = (14.0 / P_EJE_ESTANDAR_T) ** 4
    print(f"\nLey de la 4.a potencia: (14/8.2)^4 = {fec:.1f}  ->  reducción esperada ≈ "
          f"{100 * (1 - 1 / fec):.0f} % (E2 vs eje estándar)")
