# Especificación Técnica de Arquitectura Algorítmica: Modelado e Implementación de Conceptos ICT para Sistemas Automatizados

## Fundamentos Lógicos de la Entrega de Precios Interbancaria

La automatización de un sistema de negociación basado en la metodología de Inner Circle Trader (ICT) requiere conceptualizar el mercado no como un entorno de colisión caótica de oferta y demanda minorista, sino como un sistema centralizado regido por un algoritmo de entrega de precios interbancario (IPDA). Este motor de asignación de precios opera bajo un orden estrictamente lógico que desplaza la cotización hacia niveles específicos de liquidez intradiaria e ineficiencia estructural en intervalos temporales predeterminados. Por consiguiente, la variable temporal no es un mero filtro secundario, sino el catalizador primario de la acción del precio.

El tiempo determina cuándo el algoritmo entra en fases de acumulación, manipulación o distribución, mientras que el precio define las coordenadas exactas de ejecución. En términos de ingeniería de software, un bot de negociación no debe escanear patrones geométricos de forma continua, sino ejecutar rutinas de detección espacial únicamente cuando se activen ventanas temporales o macros específicas. Fuera de estos horizontes de entrega institucional, la acción del precio tiende a la aleatoriedad y a la neutralización de posiciones menores, lo que degrada la esperanza matemática del sistema.

Este comportamiento se rige por el modelo del Poder de Tres (PO3), el cual describe los tres ciclos de entrega del algoritmo dentro de una sesión operativa: la acumulación de posiciones dentro de un rango estrecho, la manipulación del precio mediante un movimiento falso en contra del sesgo diario (conocido como la oscilación de Judas o Judas Swing), y la distribución expansiva hacia el verdadero objetivo de liquidez. Cuando este proceso se completa a favor del flujo de órdenes institucionales, el mercado experimenta una Corrida de Liquidez de Baja Resistencia (LRLR), caracterizada por un desplazamiento acelerado que busca los stop loss expuestos en el extremo opuesto del rango operativo sin encontrar oposición significativa.

## Matrices de Premium y Descuento: Clasificación Operativa

El algoritmo de entrega clasifica el rango operativo actual mediante una segmentación binaria basada en el equilibrio del precio. El bot de trading debe definir primero el rango de negociación (Dealing Range), delimitado por un máximo y un mínimo estructurales validados en el gráfico de temporalidad de referencia. El punto medio de este rango representa el nivel de equilibrio. Toda cotización situada por encima de este nivel pertenece al régimen de Premium, mientras que cualquier cotización inferior se clasifica bajo el régimen de Descuento. Las instituciones financieras acumulan compras preferentemente en la zona de Descuento y distribuyen sus ventas en la zona de Premium.

Para estructurar la base de datos y la toma de decisiones del bot, se define una jerarquía estricta de las matrices de Premium y Descuento (PD Arrays), que representan los niveles específicos de soporte y resistencia algorítmicos donde el precio tiende a reaccionar.

| Nivel de Jerarquía | Matriz de Premium (Venta Corta) | Matriz de Descuento (Compra Larga) | Condición de Inactivación Algorítmica |
|-------------------|--------------------------------|-----------------------------------|----------------------------------------|
| 1 (Máxima) | Antiguo Máximo Estructural | Antiguo Mínimo Estructural | El precio cierra con el cuerpo de la vela más allá del nivel. |
| 2 | Bloque de Reversión Bajista (Bearish Breaker Block) | Bloque de Reversión Alcista (Bullish Breaker Block) | El cuerpo de la vela cierra por encima del máximo o mínimo del bloque. |
| 3 | Bloque de Mitigación Bajista (Bearish Mitigation Block) | Bloque de Mitigación Alcista (Bullish Mitigation Block) | El cuerpo de la vela invalida el bloque al cerrar fuera de sus extremos. |
| 4 | Brecha de Apertura Semanal / Diaria (Opening Gap) | Brecha de Apertura Semanal / Diaria (Opening Gap) | El precio cierra por completo la brecha estructural con cuerpos de vela. |
| 5 | Desequilibrio de Venta / Ineficiencia de Compra (SIBI) | Desequilibrio de Compra / Ineficiencia de Venta (BISI) | Invasión del cuerpo de vela más allá de la Invasión Consecuente (CE). |
| 6 | Bloque de Órdenes Bajista (Bearish Order Block) | Bloque de Órdenes Alcista (Bullish Order Block) | Cierre de cuerpo de vela más allá de su Umbral Medio (MT). |
| 7 (Mínima) | Bloque de Rechazo Bajista (Bearish Rejection Block) | Bloque de Rechazo Alcista (Bullish Rejection Block) | Perforación de la mecha del bloque por el precio de cotización actual. |

Para que una matriz PD sea considerada válida por el algoritmo del bot de trading, debe haber sido generada en confluencia con un objetivo en una temporalidad mayor. Un bloque de órdenes o un vacío de valor justo detectado de forma aislada en gráficos de baja temporalidad, sin estar respaldado por la llegada del precio a un objetivo estructural de alta temporalidad, carece de la relevancia institucional requerida y debe ser ignorado por la lógica del sistema para reducir la tasa de falsos positivos.

## Formalización Algorítmica de Estructura de Mercado y Desplazamiento

La base de la lógica estructural descansa sobre la identificación geométrica de puntos de giro o fractales (Swing Highs y Swing Lows). Para que un algoritmo detecte de forma inequívoca estas estructuras, un Swing High (SH) en el tiempo $t$ se define formalmente como un máximo local rodeado por máximos inferiores a ambos lados. Matemáticamente, se expresa mediante la siguiente condición para un fractal de tres velas:

$$
SH_t = \{Price_t \mid High_t > High_{t-1} \wedge High_t > High_{t+1}\}
$$

Inversamente, un Swing Low (SL) en el tiempo $t$ se define como un mínimo local flanqueado por mínimos superiores:

$$
SL_t = \{Price_t \mid Low_t < Low_{t-1} \wedge Low_t < Low_{t+1}\}
$$

Una tendencia alcista se caracteriza por una secuencia de máximos más altos (Higher Highs) y mínimos más altos (Higher Lows), mientras que una tendencia bajista se compone de máximos más bajos (Lower Highs) y mínimos más bajos (Lower Lows). El Cambio en la Estructura de Mercado o Market Structure Shift (MSS) representa la alteración formal de esta secuencia lógica y se produce tras una toma de liquidez previa. A diferencia de un quiebre de estructura menor o Change of Character (ChoCH) que puede ser puramente local, el MSS requiere un desplazamiento agresivo que valide el cambio de dirección del flujo de órdenes institucionales.

Para implementar esta lógica de detección en código sin ambigüedad, el bot de trading debe evaluar los siguientes eventos secuenciales:

- **Fase de Desplazamiento (Displacement)**: Se define como un movimiento direccional violento caracterizado por velas de rango amplio y con cuerpos significativamente mayores que sus mechas. Algorítmicamente, el bot debe verificar que la desviación estándar de la longitud de los cuerpos de las velas durante el desplazamiento sea superior a un umbral preestablecido del Rango Medio Verdadero (ATR).

- **Confirmación por Cierre**: La condición de confirmación del MSS exige que al menos una vela cierre con su cuerpo completo más allá del nivel extremo del último Swing Point opuesto. Un simple cruce con la mecha no constituye un MSS, sino un barrido de liquidez adicional.

- **Generación de Imbalances**: El desplazamiento que causa el MSS debe generar de manera obligatoria al menos un Vacío de Valor Justo en la misma dirección del movimiento. Si el movimiento rompe la estructura pero no deja ineficiencias en el gráfico, el algoritmo debe descartar la validez del desplazamiento, clasificándolo como una oscilación de baja probabilidad.

Una vez confirmado el MSS, el bot de trading puede clasificar movimientos de retroceso menores dentro de la nueva tendencia como inducciones (Inducements). Las inducciones representan movimientos temporales en contra del flujo principal diseñados para atraer capital minorista de baja temporalidad, barriendo sus máximos o mínimos a corto plazo antes de reanudar la expansión en la dirección del desplazamiento institucional.

## Modelado de Desequilibrios de Liquidez: BISI, SIBI y Rangos de Precio Balanceados

Un Vacío de Valor Justo (Fair Value Gap - FVG) es una ineficiencia en la entrega de precios que ocurre cuando el mercado se desplaza rápidamente en una sola dirección, impidiendo que el flujo bidireccional de órdenes se empareje de manera eficiente. Este fenómeno genera una asimetría de tres velas en el gráfico que el algoritmo IPDA tenderá a reequilibrar en el futuro cercano, actuando como un imán gravitacional para el precio.

### Desequilibrio de Compra con Ineficiencia de Venta (BISI)

El BISI es el vacío de valor justo de carácter alcista. Se genera durante una vela central fuertemente alcista (vela $t+1$) donde la mecha máxima de la vela previa (vela $t$) no llega a solaparse con la mecha mínima de la vela posterior (vela $t+2$). Algorítmicamente, se valida mediante la siguiente inecuación:

$$
Low_{t+2} > High_t
$$

El rango espacial de ineficiencia que el bot debe almacenar en memoria como zona de soporte potencial queda acotado por:

$$
\text{Rango BISI} = [High_t, Low_{t+2}]
$$

### Desequilibrio de Venta con Ineficiencia de Compra (SIBI)

El SIBI representa la ineficiencia de naturaleza bajista. Ocurre durante una vela central fuertemente bajista, validándose cuando:

$$
High_{t+2} < Low_t
$$

El rango de resistencia espacial se calcula como:

$$
\text{Rango SIBI} = [High_{t+2}, Low_t]
$$

### Invasión Consecuente (Consequent Encroachment)

El punto medio exacto de un Vacío de Valor Justo se denomina Invasión Consecuente (CE). Este nivel representa la coordenada de máxima sensibilidad algorítmica dentro del imbalance, actuando a menudo como el punto de giro donde el precio reacciona con mayor fuerza sin necesidad de cerrar por completo la brecha espacial. La fórmula para determinar el valor exacto de la Invasión Consecuente es:

$$
CE = \text{Límite Inferior} + 0.5 \times (\text{Límite Superior} - \text{Límite Inferior})
$$

Aplicando esta expresión a los tipos direccionales de FVG, el bot de trading debe calcular las coordenadas exactas empleando las siguientes ecuaciones específicas:

$$
CE_{BISI} = High_t + 0.5 \times (Low_{t+2} - High_t)
$$

$$
CE_{SIBI} = High_{t+2} + 0.5 \times (Low_t - High_{t+2})
$$

### Rango de Precio Balanceado (Balanced Price Range)

Cuando un movimiento agresivo e impulsivo hacia el alza es respondido de inmediato por un desplazamiento igual de agresivo hacia la baja (o viceversa), el mercado genera un solapamiento directo de dos ineficiencias opuestas (un BISI y un SIBI que comparten el mismo espacio de precios). Esta formación se conoce como Rango de Precio Balanceado (BPR). Desde una perspectiva algorítmica, el BPR representa una zona donde el precio ya ha sido entregado de manera eficiente a ambas partes del mercado, lo que lo convierte en un nivel de soporte o resistencia extremadamente rígido que el precio rara vez vuelve a cruzar con cierres de velas, actuando en su lugar como un imán rápido de rechazo.

Adicionalmente, el bot puede rastrear Desequilibrios de Volumen (Volume Imbalances), que se definen como brechas espaciales entre los cuerpos de dos velas consecutivas.

## Estructuras de Bloques de Ejecución: Order Blocks, Breakers, Mitigation y Rejection Blocks

La implementación de un bot de trading institucional requiere la definición algorítmica exacta de las diferentes clases de bloques que componen el flujo de órdenes del mercado. La distinción operativa entre estas estructuras reside en su origen y en la interacción previa con los polos de liquidez expuestos.

Un Bloque de Órdenes (OB) es el área de precios donde las instituciones acumulan o distribuyen grandes volúmenes de órdenes antes de inyectar suficiente capital para desplazar el mercado de manera unilateral. El Bloque de Órdenes Alcista (Bullish OB) se identifica como la última vela bajista (o grupo de velas bajistas consecutivas) previa a un impulso alcista que rompe la estructura con un desplazamiento decisivo. Su rango se define como el intervalo entre el máximo y el mínimo de dicha vela.

El **Umbral Medio (Mean Threshold)** es el nivel de equilibrio del Bloque de Órdenes, calculado como el punto medio de la distancia comprendida entre el máximo y el mínimo de la vela de referencia. Su definición matemática es:

$$
MT_{OB} = Low_{OB} + 0.5 \times (High_{OB} - Low_{OB})
$$

Para guiar la codificación lógica de la IA de manera inequívoca, se detalla la siguiente especificación de control que diferencia las estructuras de bloques:

| Variable de Control Algorítmico | Bloque de Reversión (Breaker) | Bloque de Mitigación | Bloque de Rechazo (Rejection) |
|----------------------------------|-------------------------------|----------------------|-------------------------------|
| Rol en la Operación | Reversión estructural tras toma de liquidez. | Continuación de tendencia estructural. | Reversión rápida desde extremos del mercado. |
| Toma de Liquidez Requerida | Sí. Requisito obligatorio en el extremo opuesto antes del quiebre. | No. El precio falla en barrer la liquidez extrema (falla de oscilación). | Sí. Barrido rápido que genera un rechazo inmediato de la cotización. |
| Región de Referencia | Cuerpo del Bloque de Órdenes que fue invalidado. | Cuerpo del Bloque de Órdenes antiguo respetado. | Mecha extrema del barrido sin incluir el cuerpo. |
| Cierre de Vela de Validación | El cuerpo debe cerrar más allá del bloque inicial. | El cuerpo de la vela respeta la estructura y no rompe el bloque. | El cuerpo de la vela cierra dentro del rango anterior del mercado. |
| Coordenada de Entrada | Límite del cuerpo del bloque que ha fallado. | Límite del cuerpo del bloque antiguo respetado. | Apertura/Cierre del cuerpo hasta el extremo de la mecha. |
| Ubicación del Stop Loss | Justo detrás del máximo/mínimo del barrido de liquidez. | Justo detrás del extremo del bloque de mitigación. | Un tick más allá del final de la mecha extrema del rechazo. |

## El Modelo Unicornio y Estrategias de Confluencia

El Modelo Unicornio es una de las configuraciones operativas más potentes y consistentes en la metodología ICT. Su fiabilidad radica en la convergencia geométrica de dos de los PD Arrays más poderosos que se alinean exactamente en el mismo nivel de precios: un Breaker Block y un Vacío de Valor Justo (FVG). Al apilar estos dos elementos de forma superpuesta, el bot detecta una zona de alta confluencia institucional que incrementa la probabilidad de éxito de la operación.

Para validar y ejecutar un Modelo Unicornio, el algoritmo de la IA debe procesar las siguientes condiciones y parámetros de configuración:

- **Detección del Breaker Block**: El bot debe identificar un Breaker Block válido (alcista o bajista) formado inmediatamente después de un barrido de liquidez y un MSS.
- **Detección del Vacío de Valor Justo (FVG)**: El bot debe escanear si se generó un FVG (BISI para compras, SIBI para ventas) en la misma pierna de desplazamiento que creó el Breaker.
- **Validación de la Intersección Espacial**: El bot debe ejecutar una prueba de intersección de intervalos espaciales para verificar que el FVG se superponga con el rango geográfico del Breaker Block. Si no existe solapamiento físico entre ambos intervalos, la configuración del Modelo Unicornio queda automáticamente descartada.
- **Cálculo de la Zona de Entrada**: La zona de entrada institucional para la orden límite se limita estrictamente al área de intersección donde coinciden el cuerpo del Breaker y los límites del FVG.
- **Cálculo de Parámetros de Riesgo**:
  - **Entrada de Compra (Bullish Unicorn)**: Se ejecuta en el límite superior de la zona de intersección al retestear el área. El Stop Loss ($SL$) se posiciona de forma obligatoria entre 10 y 20 pips por debajo del mínimo de la vela que generó el FVG que se solapa con el Breaker.
  - **Entrada de Venta (Bearish Unicorn)**: Se ejecuta en el límite inferior de la zona de intersección al retestear el área. El Stop Loss se ubica estrictamente entre 10 y 20 pips por encima del máximo de la vela que originó el FVG que se cruza con el Breaker.
  - **Objetivo de Salida (Take Profit)**: Debe apuntar al siguiente flujo de liquidez opuesto, como máximos o mínimos iguales, o a un PD Array de temporalidad superior.

Esta configuración se puede potenciar mediante la integración de la Entrada de Negociación Óptima (OTE). El bot calcula los retrocesos del rango operativo (Dealing Range) mediante los niveles de Fibonacci de la pierna de desplazamiento. El nivel OTE se define formalmente en el intervalo porcentual de retroceso comprendido entre el 61.8% y el 79%, estableciendo el 70.5% como la coordenada de máxima precisión para la entrada (Golden Zone). La confluencia ideal para la IA se presenta cuando la zona de intersección del Modelo Unicornio se sitúa dentro de la región OTE calculada.

## Protocolos Temporales de Ejecución y Gestión de Liquidez

La liquidez del mercado está dividida geográficamente en dos polos de órdenes pendientes: la Liquidez del Lado de la Compra (Buy-Side Liquidity - BSL) y la Liquidez del Lado de la Venta (Sell-Side Liquidity - SSL). El BSL se ubica por encima de máximos estructurales previos e intradía, donde descansan los stop loss de las posiciones cortas (Buy Stops), mientras que el SSL se localiza por debajo de mínimos estructurales, donde se acumulan las órdenes de salida de las posiciones largas (Sell Stops).

Para programar un bot de negociación determinista, se debe codificar la siguiente matriz de control intradiario vinculada a las ventanas temporales clave del mercado, tomando como referencia la zona horaria EST (America/New_York):

| Intervalo Temporal (EST) | Identificador de Sesión | Estado Algorítmico y Acciones de Control de la IA |
|--------------------------|--------------------------|---------------------------------------------------|
| 00:00 | Apertura de Medianoche | Establecimiento de Punto de Referencia: Almacena en memoria el precio exacto de la apertura de medianoche ($PMidnight$) como línea de valoración neutral para el sesgo diario. |
| 02:00 – 05:00 | London Killzone | Detección de Manipulación Primaria: Monitorea la formación del máximo o mínimo diario del precio. Escanea la toma de liquidez extrema en gráficos de 15 minutos. |
| 07:00 – 10:00 | New York Killzone | Ventana de Ejecución Principal: Mayor volumen transaccional diario. El bot habilita la detección activa de MSS tras barridos de liquidez y ejecuta órdenes límite en PD Arrays validados. |
| 08:30 | Apertura de Nueva York | Inyección de Volatilidad / Noticias: Bloqueo temporal de órdenes activas debido a reportes macroeconómicos de alto impacto. Las matrices PD formadas antes de las 08:30 son vulnerables a ser barridas. |
| 12:00 – 13:00 | Almuerzo de Nueva York | Inactivación por Falta de Volumen: El algoritmo minorista y los creadores de mercado reducen la profundidad. El bot debe pausar la apertura de nuevas posiciones para evitar el desgaste del capital por movimientos erráticos. |
| 13:30 – 16:00 | Afternoon Algorithm | Detección de Continuación: Reinicio del motor de entrega de precios. Se buscan retestees de bloques formados durante la sesión de la mañana y expansiones hacia la liquidez remanente. |
| 16:30 | Cierre de Mercado | Liquidación y Cierre de Sesión: Cierre forzado de posiciones intradiarias abiertas y desactivación de todas las órdenes límite pendientes para evitar la exposición al spread de cierre de sesión. |

## Directrices de Diseño para la IA: Conclusiones y Recomendaciones de Implementación

Para asegurar que un bot de trading ejecute los conceptos descritos de manera exitosa y sin ambigüedades lógicas, se establecen las siguientes directrices arquitectónicas para su desarrollo:

- **Sincronización Horaria Unificada**: El bot debe operar bajo una transformación temporal forzada a la zona horaria America/New_York para todas las evaluaciones lógicas, independientemente del servidor de datos o del corredor de bolsa utilizado. Esto previene errores de desalineación en las aperturas de sesiones y ventanas de macros.

- **Protocolo de Validación Multitemporal (Top-Down Validation)**: El bot debe escanear el gráfico diario, de 4 horas o de 1 hora únicamente para identificar los puntos de liquidez clave (BSL/SSL) y los PD Arrays de soporte y resistencia mayores. Una vez que el precio interactúa con estas zonas de alta temporalidad, se activa un hilo de ejecución secundario de baja temporalidad (gráficos de 5, 3 o 1 minuto) para buscar el MSS y las ineficiencias de entrada.

- **Verificación de Invasión de Cuerpos de Vela**: Se debe programar un control estricto que evalúe si los cuerpos de las velas cierran más allá de los niveles de invalidación teórica, tales como el Umbral Medio (MT) en bloques de órdenes o la Invasión Consecuente (CE) en vacíos de valor justo. Las mechas se interpretarán únicamente como herramientas de captura de liquidez, mientras que los cierres de cuerpo definirán la validez estructural de la zona.

- **Filtrado de Sesgo por Apertura de Medianoche**: Para optimizar las métricas de rentabilidad, la IA debe restringir las posiciones de compra a precios que se ubiquen por debajo de la apertura de medianoche, y las posiciones de venta a precios superiores a dicha apertura. Este filtro actúa como un validador de precio justo intradiario para evitar compras sobrevaloradas y ventas baratas.

- **Sincronización Estricta de Parámetros de Riesgo**: El bot debe calcular de manera dinámica el tamaño de la posición basándose en la distancia exacta del Stop Loss técnico, el cual debe situarse siempre detrás del extremo de la vela que originó el FVG en el Modelo Unicornio, o detrás de la mecha del barrido de liquidez en operaciones basadas en bloques de reversión. Si el tamaño del FVG requiere un Stop Loss excesivamente amplio en relación al perfil de riesgo permitido, la operación debe ser cancelada de manera preventiva.

## Fuentes citadas

1. Why do you believe there is a single algorithm that controls price? What evidence is there?, https://www.reddit.com/r/InnerCircleTraders/comments/1gk4enn/why_do_you_believe_there_is_a_single_algorithm/
2. Tell me your experience with this : r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1e4jdc3/tell_me_your_experience_with_this/
3. Complete ICT Trading Strategy 2022 — The 2022 Mentorship Model + Free PDF, https://innercircletrader.net/tutorials/complete-ict-trading-strategy-2022/
4. ICT Index Futures Session Lines | Trading Indicator - LuxAlgo, https://www.luxalgo.com/library/indicator/CMYepDcm-ict-index-futures-session-lines/
5. Fair Value Gap indicator - Support Board - Sierra Chart, https://www.sierrachart.com/SupportBoard.php?ThreadID=75732
6. List of ict strategy names? : r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1ivi7sm/list_of_ict_strategy
7. ICT 2016 concepts - beginner's rant! : r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1ee1jyl/ict_2016_concepts_beginners_rant/
8. ICT Forex Trading Notes Overview | PDF | Market Trend - Scribd, https://www.scribd.com/document/696430255/Inner-Circle-Trader-lect-Forex-lect-Notes
9. What is pd array ? : r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/17vucto/what_is_pd_arav
10. ICT Order Block Explained — Bullish & Bearish OB Setup with Examples + Free PDF, https://innercircletrader.net/tutorials/ict-order-block/
11. ICT Breaker Block Trading — Failed Order Block Strategy (Free PDF) - ICT Trading, https://innercircletrader.net/tutorials/ict-breaker-block-trading/
12. ICT Mitigation Block Explained — Continuation Setup vs Breaker Block (Free PDF), https://innercircletrader.net/tutorials/ict-mitigation-block-explained/
13. ICT SIBI and BISI Explained — Sell-Side & Buy-Side Imbalance FVGs + Free PDF, https://innercircletrader.net/tutorials/sibi-and-bisi-the-ict-concepts/
14. ICT Consequent Encroachment — Mean Threshold & 50% of FVG + PDF - ICT Trading, https://innercircletrader.net/tutorials/ict-consequent-encroachment/
15. 2 month learning ICT : r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1fkuxt4/2_month_learning_ict/
16. ICT Rejection Block — Wick Rejection Reversal Setup (Free PDF) - ICT Trading, https://innercircletrader.net/tutorials/ict-rejection-block/
17. When is it a valid OB : r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1pyxuzn/when_is_it_a_valid_ob/
18. A Simple Guide to Analyzing Market Structure with ICT Concepts : r/InnerCircleTraders, https://www.reddit.com/r/InnerCircleTraders/comments/1jpwie9/a_simple_guide_to_analyzing_market_structure_with/
19. ICT Basics: A Beginners Guide | TrendSpider Blog, https://trendspider.com/blog/ict-basics-a-beginners-guide/
20. ICT 2024 Mentorship Lecture 1 Notes — 08:30 AM Model + PDF, https://innercircletrader.net/tutorials/ict-2024/lecture-1/
21. ICT Unicorn Model — Breaker Block & Fair Value Gap Overlap Setup + Free PDF, https://innercircletrader.net/id/tutorial/model-unicorn-ict/
22. What do you guys do when price doesn't hit the FVGs middle thresh hold (50%)? - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1ksrt0h/what_do_you_guy_s_do_when_price_doesnt_hit_the/
23. Master ICT Optimal Trade Entry (OTE) — Fibonacci Setup with Examples + Free PDF, https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/
24. ICT Unicorn Model — Breaker Block & Fair Value Gap Overlap Setup + Free PDF, https://innercircletrader.net/id/tutorial/model-unicorn-ict/
25. This is the one ICT trick that made me a savage on the charts: r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1ig6wgh/this_is_the_one_ict_trick_that_made_me_a_savage/
26. Whats your go to ICT entry model? : r/InnerCircleTraders - Reddit, https://www.reddit.com/r/InnerCircleTraders/comments/1pzf6Oe/whats_your_go_t o_ict_entry_model/