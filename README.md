# Asistente Predictivo de Fatiga Vial por Ondas Dinámicas

Aplicación Streamlit que estima la fatiga de un pavimento flexible bajo cargas pesadas:
pulso transitorio de carga → oscilador de 1 grado de libertad (Newmark-β) → atenuación
exponencial → deformación de tracción → ley de fatiga del Asphalt Institute, con análisis
de resonancia, sensibilidad y alertas automáticas.

| Archivo | Contenido |
|---|---|
| `app.py` | Interfaz Streamlit |
| `motor_fisico.py` | Módulos M1–M7 y escenarios |
| `diagnostico.py` | Dictamen por reglas y alertas (M8) |
| `sensibilidad.py` | Resonancia, barrido de velocidad y tornado |
| `matriz_simulacion.py` | Exporta la Matriz de Simulación a Excel |
| `validacion.py` | Pruebas de verificación |

Ejecución local:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```
