"""
sensibilidad.py
===============================================================================
Análisis de sensibilidad y resonancia del motor físico.

Idea central: el oscilador de 1-GDL es lineal, así que el factor de
amplificación dinámica depende SOLO de dos números adimensionales:

        FAD = Φ(d/T_n, ξ)          (espectro de choque del pulso haversine)

Como d = 12a/v y T_n = 2π√(m/k), la resonancia ocurre a una velocidad crítica:

        v_crit = 12·a / ((d/T_n)_pico · T_n)

Funciones:
  espectro_choque()    curva FAD vs d/T_n para un ξ dado
  razon_resonancia()   (d/T_n) donde el FAD es máximo
  velocidad_critica()  v_crit de la estructura [km/h]
  barrido_velocidad()  FAD, ε_t y N_f en función de la velocidad
  tornado()            cambio de N_f al variar ±20 % cada entrada
  mapa_resonancia()    FAD en el plano velocidad – módulo de subrasante
===============================================================================
"""
from dataclasses import replace
from functools import lru_cache
from typing import Dict, List

import numpy as np

import motor_fisico as mf

_K_REF, _M_REF = 1e6, 1000.0
_TN_REF = 2 * np.pi / np.sqrt(_K_REF / _M_REF)


def _fad_normalizado(razon: float, xi: float) -> float:
    return mf.m2_respuesta(1.0, razon * _TN_REF, _K_REF, _M_REF, xi)["FAD"]


@lru_cache(maxsize=32)
def _espectro_cache(xi: float):
    razones = np.round(np.arange(0.20, 4.001, 0.05), 3)
    fad = np.array([_fad_normalizado(r, xi) for r in razones])
    return razones, fad


def espectro_choque(xi: float):
    """Curva FAD = Φ(d/T_n) para el amortiguamiento ξ."""
    return _espectro_cache(round(float(xi), 4))


@lru_cache(maxsize=32)
def razon_resonancia(xi: float):
    """(d/T_n) del pico del espectro y FAD máximo (búsqueda fina)."""
    razones = np.arange(0.60, 1.80, 0.01)
    fad = np.array([_fad_normalizado(r, xi) for r in razones])
    i = int(np.argmax(fad))
    return float(razones[i]), float(fad[i])


def periodo_natural(Mr_MPa: float, nu: float, rho: float) -> float:
    k = mf.m2_rigidez(Mr_MPa * 1e6, nu)
    m = mf.m2_masa_participante(rho)
    return 2 * np.pi * np.sqrt(m / k)


def velocidad_critica(e: mf.Entradas) -> float:
    """Velocidad a la que el pulso entra en resonancia con la estructura [km/h]."""
    rp, _ = razon_resonancia(round(e.xi, 4))
    Tn = periodo_natural(e.Mr_MPa, e.nu, e.rho)
    return 3.6 * 12.0 * mf.A_HUELLA / (rp * Tn)


def barrido_velocidad(e: mf.Entradas, v=None) -> Dict[str, np.ndarray]:
    v = np.arange(20.0, 121.0, 2.0) if v is None else np.asarray(v, float)
    res = [mf.simular(replace(e, v_kmh=float(vi))) for vi in v]
    return dict(v=v,
                FAD=np.array([r.FAD for r in res]),
                d_Tn=np.array([r.d / r.T_n for r in res]),
                eps_t=np.array([r.eps_t for r in res]),
                N_f=np.array([r.N_f for r in res]))


VARIABLES_TORNADO = [
    ("P_eje_t", "Carga por eje P"),
    ("v_kmh", "Velocidad v"),
    ("h1_cm", "Espesor de carpeta h₁"),
    ("E1_MPa", "Módulo del asfalto E₁"),
    ("Mr_MPa", "Módulo de subrasante Mr"),
    ("xi", "Amortiguamiento ξ"),
]


def tornado(e: mf.Entradas, delta: float = 0.20) -> List[Dict]:
    """
    Cambio porcentual de N_f al variar cada entrada en ±delta (resto fijo).
    Devuelve la lista ordenada de mayor a menor influencia.
    """
    N0 = mf.simular(e).N_f
    filas = []
    for attr, nombre in VARIABLES_TORNADO:
        x0 = getattr(e, attr)
        Nb = mf.simular(replace(e, **{attr: x0 * (1 - delta)})).N_f
        Na = mf.simular(replace(e, **{attr: x0 * (1 + delta)})).N_f
        filas.append(dict(variable=nombre, attr=attr,
                          bajo=100 * (Nb / N0 - 1), alto=100 * (Na / N0 - 1)))
    filas.sort(key=lambda f: -max(abs(f["bajo"]), abs(f["alto"])))
    return filas


def mapa_resonancia(e: mf.Entradas, v=None, Mr=None):
    """FAD en el plano (v, Mr) usando el espectro de choque (rápido)."""
    v = np.linspace(20, 120, 81) if v is None else np.asarray(v, float)
    Mr = np.linspace(20, 150, 66) if Mr is None else np.asarray(Mr, float)
    razones, fad = espectro_choque(e.xi)
    V, M = np.meshgrid(v, Mr)
    d = 12.0 * mf.A_HUELLA / (V / 3.6)
    Tn = np.vectorize(lambda x: periodo_natural(x, e.nu, e.rho))(M)
    Z = np.interp(d / Tn, razones, fad)
    rp, _ = razon_resonancia(round(e.xi, 4))
    v_crit = 3.6 * 12.0 * mf.A_HUELLA / (rp * np.array([periodo_natural(x, e.nu, e.rho) for x in Mr]))
    return dict(v=v, Mr=Mr, FAD=Z, v_crit=v_crit)


if __name__ == "__main__":
    rp, fp = razon_resonancia(0.15)
    print(f"Pico del espectro (ξ = 0.15): d/T_n = {rp:.2f}, FAD máx = {fp:.3f}")
    for nombre, e in mf.ESCENARIOS.items():
        print(f"{nombre:14s} v_crit = {velocidad_critica(e):5.1f} km/h")
    print("\nTornado (E1 base, ±20 %): cambio de N_f")
    for f in tornado(mf.ESCENARIOS["E1 - Base"]):
        print(f"  {f['variable']:26s} −20 %: {f['bajo']:+7.1f} %   +20 %: {f['alto']:+7.1f} %")
