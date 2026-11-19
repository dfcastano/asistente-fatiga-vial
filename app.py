"""
app.py — Interfaz Streamlit del Asistente Predictivo de Fatiga Vial
Ejecutar:  streamlit run app.py
"""
from dataclasses import asdict, replace
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import diagnostico as dg
import matriz_simulacion as ms
import motor_fisico as mf
import sensibilidad as sb

st.set_page_config(page_title="Asistente de Fatiga Vial", page_icon="🛣️", layout="wide")

COL = {"E1 - Base": "#2F6DB5", "E2 - Límite": "#E08A1E", "E3 - Crítico": "#C0392B"}
C_ACT = "#6A3FA0"
SLIDERS = [
    ("P_eje_t", "Carga por eje simple [t]", 4.0, 16.0, 0.5),
    ("v_kmh", "Velocidad [km/h]", 20.0, 120.0, 1.0),
    ("h1_cm", "Espesor de carpeta h₁ [cm]", 4.0, 20.0, 0.5),
    ("E1_MPa", "Módulo del asfalto E₁ [MPa]", 1500.0, 6000.0, 100.0),
    ("Mr_MPa", "Módulo de subrasante Mr [MPa]", 20.0, 150.0, 5.0),
    ("xi", "Amortiguamiento ξ", 0.05, 0.30, 0.01),
    ("ejes_dia", "Ejes pesados por día", 50.0, 2000.0, 50.0),
]
ATTRS = [s[0] for s in SLIDERS]


# ----------------------------------------------------------------- cálculo con caché
@st.cache_data(show_spinner=False)
def sim(params: tuple) -> mf.Resultados:
    return mf.simular(mf.Entradas(**dict(zip(ATTRS, params))))


@st.cache_data(show_spinner=False)
def barrido(params: tuple):
    e = mf.Entradas(**dict(zip(ATTRS, params)))
    return sb.barrido_velocidad(e, np.arange(20.0, 121.0, 2.0))


@st.cache_data(show_spinner=False)
def tornado(params: tuple):
    return sb.tornado(mf.Entradas(**dict(zip(ATTRS, params))))


@st.cache_data(show_spinner=False)
def mapa(xi: float):
    return sb.mapa_resonancia(mf.Entradas(xi=xi))


@st.cache_data(show_spinner=False)
def excel_bytes() -> bytes:
    buf = BytesIO()
    ms.construir_excel(buf)
    return buf.getvalue()


def tupla(e: mf.Entradas) -> tuple:
    return tuple(float(getattr(e, a)) for a in ATTRS)


# ----------------------------------------------------------------- estado / callbacks
def cargar(nombre: str):
    e = mf.ESCENARIOS[nombre]
    for a in ATTRS:
        st.session_state[a] = float(getattr(e, a))


def ir_a_resonancia():
    e = mf.Entradas(**{a: st.session_state[a] for a in ATTRS})
    st.session_state["v_kmh"] = float(np.clip(round(sb.velocidad_critica(e)), 20, 120))


if "P_eje_t" not in st.session_state:
    cargar("E1 - Base")

# ----------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown("### 🚚 Escenarios del estudio")
    c = st.columns(3)
    for i, n in enumerate(mf.ESCENARIOS):
        c[i].button(n.split(" - ")[0], on_click=cargar, args=(n,), help=n, use_container_width=True)
    st.button("🎯 Llevar a velocidad crítica", on_click=ir_a_resonancia, use_container_width=True,
              help="Ajusta la velocidad a la de resonancia de la estructura actual")
    st.markdown("### 🎚️ Variables")
    for a, etq, lo, hi, paso in SLIDERS:
        st.slider(etq, lo, hi, step=paso, key=a)
    st.caption("Modelo 1-GDL + 2 capas · Newmark-β · fatiga Asphalt Institute")

e = mf.Entradas(**{a: float(st.session_state[a]) for a in ATTRS})
r = sim(tupla(e))
eb = mf.ESCENARIOS["E1 - Base"]
rb = sim(tupla(eb))
dic = dg.dictamen_reglas(e, r, eb, rb)
alertas = dg.alertas(e, r)
est_res, q, v_crit = dg.estado_resonancia(e, r)
actual = next((n for n, x in mf.ESCENARIOS.items() if tupla(x) == tupla(e)), "Personalizado")

# ----------------------------------------------------------------- encabezado
st.title("🛣️ Asistente Predictivo de Fatiga Vial por Ondas Dinámicas")
st.caption(f"Pavimentos flexibles · Consultoría Castaño & Garzón · Escenario activo: **{actual}**")

k = st.columns(6)
k[0].metric("FAD", f"{r.FAD:.2f}", f"{r.FAD - rb.FAD:+.2f} vs E1", delta_color="inverse")
k[1].metric("σ_din [MPa]", f"{r.sigma_din / 1e6:.2f}", f"{(r.sigma_din / rb.sigma_din - 1) * 100:+.0f} %",
            delta_color="inverse")
k[2].metric("ε_t [με]", f"{r.eps_t * 1e6:.0f}", f"{(r.eps_t / rb.eps_t - 1) * 100:+.0f} %", delta_color="inverse")
k[3].metric("N_f [rep.]", f"{r.N_f:.2e}", f"{(r.N_f / rb.N_f - 1) * 100:+.0f} %")
k[4].metric("Vida útil [años]", f"{r.vida_util_anos:.1f}", f"{r.vida_util_anos - rb.vida_util_anos:+.1f}")
k[5].metric("Velocidad crítica", f"{v_crit:.0f} km/h", f"actual {e.v_kmh:.0f} km/h", delta_color="off")

COLOR_NIVEL = {"🟢": "#E2EFDA", "🟡": "#FFF2CC", "🟠": "#FCE4D6", "🔴": "#F8D7DA"}
fondo = COLOR_NIVEL.get(dic["nivel"][0], "#EEEEEE")
izq, der = st.columns([3, 2])
with izq:
    st.markdown("#### 🤖 Dictamen técnico automático")
    st.markdown(f"<div style='background:{fondo};padding:14px 16px;border-radius:8px;color:#222;"
                f"font-size:1.02rem;line-height:1.45'>{dic['texto']}</div>", unsafe_allow_html=True)
    if dic["recomendaciones"]:
        st.markdown("**Recomendaciones**")
        for x in dic["recomendaciones"]:
            st.markdown(f"- {x}")
with der:
    st.markdown(f"#### 🚨 Alertas del software ({len(alertas)})")
    if not alertas:
        st.success("Sin alertas: condición dentro de los límites del modelo.", icon="✅")
    for a in alertas:
        txt = f"**{a['titulo']}.** {a['detalle']}"
        if a["nivel"] == 3:
            st.error(txt, icon="🚨")
        elif a["nivel"] == 2:
            st.warning(txt, icon="⚠️")
        else:
            st.info(txt, icon="ℹ️")


def estilo(fig, h=380):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white",
                      legend=dict(orientation="h", y=-0.2))
    return fig


tabs = st.tabs(["🌊 Onda transitoria", "🎯 Resonancia", "📊 Sensibilidad", "📉 Atenuación",
                "⏳ Degradación", "🧮 Matriz comparativa", "🧠 Prompt IA", "📐 Modelo"])

# ----------------------------------------------------------------- 1. onda transitoria
with tabs[0]:
    s, sbse = r.series, rb.series
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Pulso de carga por rueda F(t)",
                                                        "Respuesta del pavimento u(t)"))
    fig.add_trace(go.Scatter(x=sbse["t"] * 1e3, y=sbse["F"] / 1e3, name="E1 base",
                             line=dict(color="#999", dash="dash")), 1, 1)
    fig.add_trace(go.Scatter(x=s["t"] * 1e3, y=s["F"] / 1e3, name="Actual", line=dict(color=C_ACT, width=3)), 1, 1)
    fig.add_trace(go.Scatter(x=sbse["t"] * 1e3, y=sbse["u"] * 1e3, name="E1 base", showlegend=False,
                             line=dict(color="#999", dash="dash")), 1, 2)
    fig.add_trace(go.Scatter(x=s["t"] * 1e3, y=s["u"] * 1e3, name="Actual", showlegend=False,
                             line=dict(color=C_ACT, width=3)), 1, 2)
    fig.add_hline(y=r.u_est * 1e3, line_dash="dot", line_color=C_ACT, row=1, col=2,
                  annotation_text="u estática", annotation_position="top right")
    fig.update_xaxes(title_text="t [ms]", range=[0, max(300, r.d * 1e3 * 2.5)])
    fig.update_yaxes(title_text="F [kN]", row=1, col=1)
    fig.update_yaxes(title_text="u [mm]", row=1, col=2)
    st.plotly_chart(estilo(fig), use_container_width=True)
    c = st.columns(5)
    c[0].metric("Duración del pulso d", f"{r.d * 1e3:.0f} ms")
    c[1].metric("Frecuencia de carga f", f"{r.f_carga:.1f} Hz")
    c[2].metric("Frecuencia natural fₙ", f"{r.f_n:.1f} Hz")
    c[3].metric("d/Tₙ", f"{r.d / r.T_n:.2f}")
    c[4].metric("Deflexión máxima", f"{r.u_max * 1e3:.2f} mm")
    st.caption("El pulso haversine F(t) = P_r·sin²(πt/d) excita el oscilador m·ü + c·u̇ + k·u = F(t). "
               "Si la duración del pulso se parece al periodo natural (d/Tₙ ≈ 1), la respuesta se amplifica.")

# ----------------------------------------------------------------- 2. resonancia
with tabs[1]:
    estado = ["Fuera de resonancia", "Proximidad a resonancia", "EN RESONANCIA"][est_res]
    st.markdown(f"**Estado: {estado}** · q = (d/Tₙ)/(d/Tₙ)pico = {q:.2f} · "
                f"velocidad crítica de esta estructura = **{v_crit:.0f} km/h**")
    b = barrido(tupla(e))
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_vrect(x0=v_crit - 15, x1=v_crit + 15, fillcolor="#C0392B", opacity=0.10, line_width=0,
                      annotation_text="banda de resonancia", annotation_position="top left")
        fig.add_trace(go.Scatter(x=b["v"], y=b["FAD"], name="FAD", line=dict(color=C_ACT, width=3)))
        fig.add_trace(go.Scatter(x=[e.v_kmh], y=[r.FAD], mode="markers", name="Condición actual",
                                 marker=dict(size=14, color="#C0392B", symbol="diamond")))
        fig.add_vline(x=v_crit, line_dash="dash", line_color="#C0392B")
        fig.update_layout(title="Curva de resonancia de la estructura actual",
                          xaxis_title="Velocidad [km/h]", yaxis_title="FAD")
        st.plotly_chart(estilo(fig), use_container_width=True)
    with c2:
        mp = mapa(round(e.xi, 2))
        fig = go.Figure(go.Heatmap(x=mp["v"], y=mp["Mr"], z=mp["FAD"], colorscale="YlOrRd",
                                   colorbar=dict(title="FAD")))
        fig.add_trace(go.Scatter(x=mp["v_crit"], y=mp["Mr"], mode="lines", name="v crítica",
                                 line=dict(color="black", dash="dash")))
        fig.add_trace(go.Scatter(x=[e.v_kmh], y=[e.Mr_MPa], mode="markers", name="Actual",
                                 marker=dict(size=14, color=C_ACT, symbol="x")))
        fig.update_layout(title="Mapa de resonancia: velocidad vs módulo de subrasante",
                          xaxis_title="Velocidad [km/h]", yaxis_title="Mr [MPa]")
        st.plotly_chart(estilo(fig), use_container_width=True)
    razones, fad = sb.espectro_choque(e.xi)
    rp, fp = sb.razon_resonancia(round(e.xi, 4))
    fig = go.Figure(go.Scatter(x=razones, y=fad, name=f"ξ = {e.xi:.2f}", line=dict(color="#2F6DB5", width=3)))
    fig.add_trace(go.Scatter(x=[r.d / r.T_n], y=[r.FAD], mode="markers", name="Actual",
                             marker=dict(size=14, color=C_ACT, symbol="diamond")))
    fig.add_vline(x=rp, line_dash="dash", line_color="#C0392B", annotation_text=f"pico d/Tₙ = {rp:.2f}")
    fig.update_layout(title="Espectro de choque del pulso haversine: FAD = Φ(d/Tₙ, ξ)",
                      xaxis_title="d/Tₙ", yaxis_title="FAD")
    st.plotly_chart(estilo(fig, 330), use_container_width=True)
    st.info("**Física:** como d = 12a/v y Tₙ = 2π√(m/k), la resonancia ocurre en "
            "v_crit = 12a / ((d/Tₙ)pico·Tₙ). Una subrasante blanda baja k, alarga Tₙ y lleva la "
            "velocidad crítica a velocidades urbanas (≈ 50 km/h con Mr = 30 MPa).", icon="🔬")

# ----------------------------------------------------------------- 3. sensibilidad
with tabs[2]:
    t = tornado(tupla(e))
    nombres = [f["variable"] for f in t][::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=nombres, x=[f["bajo"] for f in t][::-1], orientation="h", name="Variable −20 %",
                         marker_color="#2F6DB5"))
    fig.add_trace(go.Bar(y=nombres, x=[f["alto"] for f in t][::-1], orientation="h", name="Variable +20 %",
                         marker_color="#E08A1E"))
    fig.update_layout(barmode="overlay", title="Diagrama de tornado: cambio de N_f al variar ±20 % cada entrada",
                      xaxis_title="Cambio en la vida a fatiga N_f [%]")
    fig.add_vline(x=0, line_color="#333")
    st.plotly_chart(estilo(fig, 400), use_container_width=True)
    st.dataframe(pd.DataFrame([{"Variable": f["variable"], "−20 %": f"{f['bajo']:+.1f} %",
                                "+20 %": f"{f['alto']:+.1f} %"} for f in t]),
                 hide_index=True, use_container_width=True)
    st.caption("Valores positivos alargan la vida del pavimento. La carga domina por el exponente 3.291 "
               "de la ecuación de fatiga. En resonancia, cambiar la velocidad en cualquier sentido mejora la vida.")

# ----------------------------------------------------------------- 4. atenuación
with tabs[3]:
    s = r.series
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Atenuación con la profundidad σ(z)",
                                                        "Onda superficial con la distancia A(r)"))
    fig.add_trace(go.Scatter(x=s["sigma_z"] / 1e6, y=s["z"] * 100, name="σ(z)", line=dict(color=C_ACT, width=3)), 1, 1)
    fig.add_trace(go.Scatter(x=[r.sigma_h1 / 1e6], y=[e.h1_cm], mode="markers", name="Base de la carpeta",
                             marker=dict(size=12, color="#C0392B")), 1, 1)
    fig.add_trace(go.Scatter(x=s["r"], y=s["A_r"] * 1e3, name="A(r)", line=dict(color="#2F6DB5", width=3)), 1, 2)
    fig.update_yaxes(autorange="reversed", title_text="z [cm]", row=1, col=1)
    fig.update_xaxes(title_text="σ [MPa]", row=1, col=1)
    fig.update_yaxes(type="log", title_text="A [mm]", row=1, col=2)
    fig.update_xaxes(title_text="r [m]", row=1, col=2)
    st.plotly_chart(estilo(fig), use_container_width=True)
    c = st.columns(4)
    c[0].metric("δ (longitud de atenuación)", f"{r.delta:.2f} m")
    c[1].metric("V_s", f"{r.V_s:.0f} m/s")
    c[2].metric("V_R (Rayleigh)", f"{r.V_R:.0f} m/s")
    c[3].metric("λ_R = V_R/f", f"{r.lambda_R:.1f} m")

# ----------------------------------------------------------------- 5. degradación
with tabs[4]:
    fig = go.Figure()
    for n, x in mf.ESCENARIOS.items():
        rr = sim(tupla(x))
        fig.add_trace(go.Scatter(x=rr.series["anos"], y=rr.series["vida_rem"], name=n,
                                 line=dict(color=COL[n], dash="dot")))
    fig.add_trace(go.Scatter(x=r.series["anos"], y=r.series["vida_rem"], name="Actual",
                             line=dict(color=C_ACT, width=4)))
    fig.update_layout(title=f"Vida remanente a fatiga ({e.ejes_dia:.0f} ejes/día, regla de Miner)",
                      xaxis_title="Años de servicio", yaxis_title="Vida remanente [%]", yaxis_range=[0, 105])
    st.plotly_chart(estilo(fig, 420), use_container_width=True)

# ----------------------------------------------------------------- 6. matriz
with tabs[5]:
    filas = []
    todos = dict(mf.ESCENARIOS)
    todos.update(mf.ESCENARIO_REFERENCIA)
    todos["Actual"] = e
    for n, x in todos.items():
        rr = sim(tupla(x))
        estr, _, vc = dg.estado_resonancia(x, rr)
        filas.append({"Escenario": n, "P [t]": x.P_eje_t, "v [km/h]": x.v_kmh, "h₁ [cm]": x.h1_cm,
                      "Mr [MPa]": x.Mr_MPa, "fₙ [Hz]": round(rr.f_n, 1), "d/Tₙ": round(rr.d / rr.T_n, 2),
                      "v_crit [km/h]": round(vc), "FAD": round(rr.FAD, 3),
                      "Resonancia": ["No", "Próxima", "SÍ"][estr],
                      "ε_t [με]": round(rr.eps_t * 1e6), "N_f": f"{rr.N_f:.2e}",
                      "Vida [años]": round(rr.vida_util_anos, 2),
                      "Reducción": f"{mf.reduccion_vida(rr, rb):.1f} %",
                      "Nivel": dg.dictamen_reglas(x, rr, eb, rb)["nivel"]})
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    nombres = list(mf.ESCENARIOS)
    res3 = [sim(tupla(mf.ESCENARIOS[n])) for n in nombres]
    with c1:
        fig = go.Figure(go.Bar(x=nombres, y=[x.eps_t * 1e6 for x in res3], marker_color=[COL[n] for n in nombres],
                               text=[f"{x.eps_t * 1e6:.0f}" for x in res3], textposition="outside"))
        fig.update_layout(title="Deformación de tracción ε_t [με]",
                          yaxis_range=[0, 1.18 * max(x.eps_t * 1e6 for x in res3)])
        st.plotly_chart(estilo(fig, 340), use_container_width=True)
    with c2:
        fig = go.Figure(go.Bar(x=nombres, y=[x.vida_util_anos for x in res3], marker_color=[COL[n] for n in nombres],
                               text=[f"{x.vida_util_anos:.1f}" for x in res3], textposition="outside"))
        fig.update_layout(title="Vida útil a fatiga [años]",
                          yaxis_range=[0, 1.18 * max(x.vida_util_anos for x in res3)])
        st.plotly_chart(estilo(fig, 340), use_container_width=True)
    st.download_button("⬇️ Descargar Matriz de Simulación (Excel)", data=excel_bytes(),
                       file_name="Matriz_Simulacion.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ----------------------------------------------------------------- 7. prompt IA
with tabs[6]:
    st.markdown("El dictamen de arriba lo generan **reglas deterministas** (reproducibles). "
                "Este prompt permite que un modelo de lenguaje redacte el dictamen con los mismos números:")
    st.code(dg.construir_prompt(actual, e, r, dic), language="text")
    st.markdown("**Descomposición de la pérdida de vida por causa**")
    ap = dic["aportes"]
    fig = go.Figure(go.Pie(labels=["Carga", "Dinámica (velocidad)", "Estructura"],
                           values=[ap["carga"], ap["dinamica"], ap["estructura"]], hole=0.5,
                           marker_colors=["#E08A1E", "#6A3FA0", "#2F6DB5"]))
    st.plotly_chart(estilo(fig, 320), use_container_width=True)

# ----------------------------------------------------------------- 8. modelo
with tabs[7]:
    st.latex(r"P_r=\frac{P_{eje}\,g}{4}\qquad d=\frac{12a}{v}\qquad F(t)=P_r\sin^2\!\left(\frac{\pi t}{d}\right)")
    st.latex(r"m\ddot u+c\dot u+ku=F(t)\qquad k=\frac{2M_r a}{1-\nu^2}\qquad \mathrm{FAD}=\frac{u_{m\acute{a}x}}{u_{est}}")
    st.latex(r"\sigma_{din}=\frac{P_{eje}\,g}{4\pi a^2}\,\mathrm{FAD}(v)\qquad \sigma(z)=\sigma_{din}e^{-z/\delta}"
             r"\qquad \delta=a\left(\frac{E_1}{M_r}\right)^{1/3}")
    st.latex(r"\varepsilon_t=K\frac{\sigma(h_1)}{E_1}\qquad N_f=0.0796\,\varepsilon_t^{-3.291}E_1^{-0.854}")
    st.latex(r"v_{crit}=\frac{12a}{(d/T_n)_{pico}\,T_n}\qquad V_s=\sqrt{G/\rho}\qquad \lambda=\frac{V_R}{f}")
