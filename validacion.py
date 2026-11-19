"""
validacion.py — Pruebas de verificación del motor físico.
Ejecutar:  python validacion.py
"""
import numpy as np

import motor_fisico as mf


def prueba_espectro_choque():
    """
    V1. El integrador Newmark debe reproducir el espectro de choque del pulso
    haversine sin amortiguamiento: FAD -> 1 para pulsos largos (cuasi-estático)
    y un máximo ≈ 1.6–1.8 cuando d/T_n ≈ 1.
    """
    k, m = 1e6, 1000.0
    T_n = 2 * np.pi / np.sqrt(k / m)
    print("V1. Espectro de choque (ξ = 0)")
    for razon in [0.25, 0.5, 0.8, 1.0, 1.5, 3.0, 10.0]:
        r = mf.m2_respuesta(1000.0, razon * T_n, k, m, 0.0)
        print(f"    d/T_n = {razon:5.2f}   FAD = {r['FAD']:.3f}")


def prueba_tendencias():
    """V2. Tendencias físicas esperadas (monotonía de ε_t)."""
    print("V2. Tendencias físicas")
    base = mf.simular(mf.Entradas())
    casos = {
        "Más carga  (P 8 -> 12 t)    ε_t sube": mf.Entradas(P_eje_t=12.0),
        "Más espesor (h1 10 -> 15 cm) ε_t baja": mf.Entradas(h1_cm=15.0),
        "Suelo blando (Mr 80 -> 30)   ε_t sube": mf.Entradas(Mr_MPa=30.0),
    }
    for texto, ent in casos.items():
        r = mf.simular(ent)
        print(f"    {texto}:  {base.eps_t*1e6:6.1f} -> {r.eps_t*1e6:6.1f} με")


def prueba_cuarta_potencia():
    """V3. Contraste del efecto de la carga con la ley de la 4.a potencia (AASHO)."""
    v = 40.0
    r82 = mf.simular(mf.Entradas(P_eje_t=8.2, v_kmh=v))
    r14 = mf.simular(mf.Entradas(P_eje_t=14.0, v_kmh=v))
    print("V3. Ley de la 4.a potencia (misma velocidad)")
    print(f"    Modelo: N(8.2 t)/N(14 t) = {r82.N_f / r14.N_f:5.1f}   "
          f"AASHO: (14/8.2)^4 = {(14 / 8.2) ** 4:5.1f}")


if __name__ == "__main__":
    prueba_espectro_choque()
    prueba_tendencias()
    prueba_cuarta_potencia()
